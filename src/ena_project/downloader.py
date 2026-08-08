"""Resumable verified downloads with quarantine and supersession handling."""

from __future__ import annotations

import concurrent.futures
import functools
import hashlib
import logging
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Callable

from .manifest import read_manifest
from .models import ManifestEntry

LOGGER = logging.getLogger(__name__)


def md5sum(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_file(path: Path, entry: ManifestEntry) -> bool:
    return path.is_file() and path.stat().st_size == entry.size_bytes and md5sum(path) == entry.md5


def validate_destination(path: Path, platform: str = sys.platform) -> Path:
    requested = path.expanduser()
    parts = requested.parts
    if platform == "darwin" and len(parts) >= 3 and parts[0] == "/" and parts[1] == "Volumes":
        volume = Path("/Volumes") / parts[2]
        if not volume.is_dir():
            raise FileNotFoundError(
                f"Destination volume is not mounted: {volume}. "
                "Check the spelling with: ls -la /Volumes"
            )
        if not os.access(volume, os.W_OK):
            raise PermissionError(f"Destination volume is not writable: {volume}")
    return requested.resolve()


def safe_destination(outdir: Path, local_relpath: str) -> Path:
    root = outdir.resolve()
    destination = (root / local_relpath).resolve()
    try:
        destination.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Manifest path escapes OUTDIR: {local_relpath}") from exc
    return destination


HistoryIndex = dict[str, tuple[tuple[str, ManifestEntry], ...]]


def build_history_index(outdir: Path) -> HistoryIndex:
    matches: dict[str, list[tuple[str, ManifestEntry]]] = {}
    archive = outdir / "metadata" / "archive"
    if not archive.is_dir():
        return {}
    for manifest_path in sorted(archive.glob("*/manifest.tsv")):
        snapshot_id = manifest_path.parent.name
        for entry in read_manifest(manifest_path):
            matches.setdefault(entry.local_relpath, []).append((snapshot_id, entry))
    return {key: tuple(values) for key, values in matches.items()}


def _preserve_superseded(
    source: Path, outdir: Path, snapshot_id: str, historical: ManifestEntry
) -> Path:
    suffix = 0
    while True:
        preserved_id = snapshot_id if suffix == 0 else f"{snapshot_id}-{suffix:02d}"
        target = safe_destination(outdir, f"superseded/{preserved_id}/{historical.local_relpath}")
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            source.replace(target)
            return target
        if verify_file(target, historical):
            source.unlink()
            return target
        suffix += 1


def _quarantine(path: Path, timestamp: Callable[[], float]) -> Path:
    destination = path.with_name(f"{path.name}.bad.{int(timestamp())}")
    path.replace(destination)
    LOGGER.warning("Quarantined invalid file %s as %s", path, destination)
    return destination


def download_one(
    entry: ManifestEntry,
    outdir: Path,
    curl_path: str,
    *,
    run_command: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    timestamp: Callable[[], float] = time.time,
    history_index: HistoryIndex | None = None,
) -> Path:
    destination = safe_destination(outdir, entry.local_relpath)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if verify_file(destination, entry):
        LOGGER.info("Verified existing file; skipping %s", entry.local_relpath)
        return destination
    if destination.exists():
        history = history_index if history_index is not None else build_history_index(outdir)
        historical = next(
            (
                (snapshot_id, old)
                for snapshot_id, old in history.get(entry.local_relpath, ())
                if verify_file(destination, old)
            ),
            None,
        )
        if historical is not None:
            snapshot_id, old = historical
            superseded = _preserve_superseded(destination, outdir, snapshot_id, old)
            LOGGER.info("Preserved repository revision at %s", superseded)
        else:
            _quarantine(destination, timestamp)
    part = destination.with_name(f"{destination.name}.part")
    if part.exists() and part.stat().st_size > entry.size_bytes:
        _quarantine(part, timestamp)
    if verify_file(part, entry):
        part.replace(destination)
        return destination
    command = [
        curl_path,
        "--fail",
        "--location",
        "--continue-at",
        "-",
        "--retry",
        "3",
        "--retry-delay",
        "2",
        "--retry-all-errors",
        "--output",
        str(part),
        entry.remote_url,
    ]
    LOGGER.info("Downloading %s", entry.local_relpath)
    run_command(command, check=True)
    if not verify_file(part, entry):
        _quarantine(part, timestamp)
        raise RuntimeError(
            f"Downloaded file failed size or MD5 verification: {entry.local_relpath}"
        )
    part.replace(destination)
    LOGGER.info("Download verified: %s", entry.local_relpath)
    return destination


def download_batch(
    entries: Iterable[ManifestEntry],
    outdir: Path,
    curl_path: str,
    jobs: int = 2,
    attempts: int = 3,
    *,
    download: Callable[[ManifestEntry, Path, str], Path] = download_one,
) -> list[ManifestEntry]:
    if jobs <= 0 or attempts <= 0:
        raise ValueError("jobs and attempts must be positive")
    pending = list(entries)
    transaction_download = download
    if download is download_one:
        transaction_download = functools.partial(
            download_one, history_index=build_history_index(outdir)
        )
    for attempt in range(1, attempts + 1):
        failures = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
            futures = {
                executor.submit(transaction_download, entry, outdir, curl_path): entry
                for entry in pending
            }
            for future in concurrent.futures.as_completed(futures):
                entry = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    LOGGER.error("%s failed on pass %d: %s", entry.local_relpath, attempt, exc)
                    failures.append(entry)
        pending = sorted(
            failures, key=lambda item: (item.run_accession, item.representation, item.file_index)
        )
        if not pending:
            break
    logs = outdir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    report = logs / "failed_accessions.txt"
    if pending:
        report.write_text(
            "".join(f"{item.run_accession}\t{item.local_relpath}\n" for item in pending),
            encoding="utf-8",
        )
    else:
        report.unlink(missing_ok=True)
    return pending


def find_curl() -> str:
    path = shutil.which("curl")
    if path is None:
        raise RuntimeError("Required command not found in PATH: curl")
    return path
