"""Transactional ENA metadata snapshots and offline rebuilding."""

from __future__ import annotations

import json
import logging
import platform
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .. import __version__
from ..accession import parse_accession
from ..ena_client import EnaClient
from ..inventory import read_inventory, sha256sum
from ..manifest import build_manifest, read_run_metadata, write_manifest
from .acquire import MetadataClient, acquire_raw, atomic_write
from .normalize import normalize
from .schemas import SNAPSHOT_SCHEMA_VERSION

LOGGER = logging.getLogger(__name__)
SENSITIVE_OPTIONS = {"--api-key", "--password", "--token"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _snapshot_id(outdir: Path, instant: datetime) -> str:
    base = instant.strftime("%Y%m%dT%H%M%S.%fZ")
    used = set()
    snapshot_path = outdir / "metadata" / "snapshot.json"
    if snapshot_path.is_file():
        try:
            used.add(json.loads(snapshot_path.read_text(encoding="utf-8"))["snapshot_id"])
        except (KeyError, json.JSONDecodeError):
            pass
    archive = outdir / "metadata" / "archive"
    if archive.is_dir():
        used.update(path.name for path in archive.iterdir())
    if base not in used:
        return base
    suffix = 1
    while f"{base}-{suffix:02d}" in used:
        suffix += 1
    return f"{base}-{suffix:02d}"


def _describe(path: Path, root: Path, artifact_type: str) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256sum(path),
        "artifact_type": artifact_type,
    }


def _sanitize_invocation(invocation: list[str] | None) -> list[str]:
    if invocation is None:
        return ["Python API"]
    sanitized: list[str] = []
    redact_next = False
    for argument in invocation:
        if redact_next:
            sanitized.append("<redacted>")
            redact_next = False
        elif argument in SENSITIVE_OPTIONS:
            sanitized.append(argument)
            redact_next = True
        elif any(argument.startswith(f"{option}=") for option in SENSITIVE_OPTIONS):
            sanitized.append(f"{argument.split('=', 1)[0]}=<redacted>")
        else:
            sanitized.append(argument)
    return sanitized


def create_snapshot(
    accession: str,
    outdir: Path,
    *,
    client: MetadataClient | None = None,
    refresh: bool = False,
    policy: str | None = None,
    now: Callable[[], datetime] = utc_now,
    invocation: list[str] | None = None,
) -> tuple[Path, bool]:
    parsed = parse_accession(accession)
    current = outdir / "metadata"
    current_snapshot = current / "snapshot.json"
    if current_snapshot.exists() and not refresh:
        raise FileExistsError(f"Metadata snapshot exists at {current}; use --refresh")
    if not current_snapshot.exists() and (outdir / "manifest.tsv").exists():
        raise FileExistsError(
            f"Orphan manifest exists at {outdir / 'manifest.tsv'} without snapshot provenance; "
            "move or remove it explicitly before metadata acquisition"
        )
    transaction_time = now()
    stamp = _snapshot_id(outdir, transaction_time)
    staging_root = outdir / f".metadata-staging-{stamp}"
    if staging_root.exists():
        raise FileExistsError(f"Snapshot staging path already exists: {staging_root}")
    metadata_dir = staging_root / "metadata"
    try:
        LOGGER.info("Snapshot started for %s as %s", parsed.value, stamp)
        requests, warnings = acquire_raw(client or EnaClient(), parsed.value, metadata_dir)
        counts, project_accession, study_accession = normalize(metadata_dir, parsed.value, stamp)
        manifest_path = staging_root / "manifest.tsv"
        if policy is not None:
            files_path = metadata_dir / "derived" / "files.tsv"
            write_manifest(
                build_manifest(
                    read_inventory(files_path),
                    policy,
                    read_run_metadata(files_path),
                ),
                manifest_path,
            )
        if current.exists():
            archive = metadata_dir / "archive"
            if (current / "archive").is_dir():
                shutil.copytree(current / "archive", archive, dirs_exist_ok=True)
            previous = json.loads((current / "snapshot.json").read_text(encoding="utf-8"))
            previous_id = previous["snapshot_id"]
            destination = archive / previous_id
            shutil.copytree(current, destination, ignore=shutil.ignore_patterns("archive"))
            if (outdir / "manifest.tsv").is_file():
                shutil.copy2(outdir / "manifest.tsv", destination / "manifest.tsv")
        artifacts = []
        for path in sorted(metadata_dir.rglob("*")):
            if path.is_file() and path.name != "snapshot.json" and "archive" not in path.parts:
                kind = "raw" if "raw" in path.parts else "derived"
                artifacts.append(_describe(path, staging_root, kind))
        if manifest_path.is_file():
            artifacts.append(_describe(manifest_path, staging_root, "manifest"))
        snapshot = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "tool_version": __version__,
            "application": "ENA Project Archiver",
            "application_version": __version__,
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "command": _sanitize_invocation(invocation),
            "snapshot_id": stamp,
            "created_at": transaction_time.isoformat().replace("+00:00", "Z"),
            "input_accession": parsed.value,
            "project_accession": project_accession,
            "study_accession": study_accession,
            "source": "ENA",
            "status": "partial" if warnings else "complete",
            "requests": requests,
            "artifacts": sorted(artifacts, key=lambda item: str(item["path"])),
            "warnings": warnings,
            "errors": [],
            "record_counts": counts,
            "canonical_project_missing": not project_accession.startswith("PRJ"),
        }
        if snapshot["canonical_project_missing"]:
            warning = "ENA did not expose a canonical PRJ accession; using Study identity"
            snapshot["warnings"].append(warning)
            snapshot["status"] = "partial"
        atomic_write(
            metadata_dir / "snapshot.json",
            (json.dumps(snapshot, indent=2, sort_keys=True) + "\n").encode(),
        )

        from ..validation import validate_metadata

        staging_errors = validate_metadata(staging_root)
        if staging_errors:
            raise ValueError("Staged metadata validation failed:\n" + "\n".join(staging_errors))

        new_manifest_created = manifest_path.is_file()
        old_metadata = outdir / f".metadata-old-{stamp}"
        old_manifest = outdir / f".manifest-old-{stamp}.tsv"
        if current.exists():
            current.replace(old_metadata)
        if (outdir / "manifest.tsv").exists():
            (outdir / "manifest.tsv").replace(old_manifest)
        try:
            metadata_dir.replace(current)
            if manifest_path.exists():
                manifest_path.replace(outdir / "manifest.tsv")
        except Exception:
            if current.exists():
                shutil.rmtree(current)
            if old_metadata.exists():
                old_metadata.replace(current)
            if old_manifest.exists():
                old_manifest.replace(outdir / "manifest.tsv")
            raise
        finally:
            shutil.rmtree(staging_root, ignore_errors=True)
        shutil.rmtree(old_metadata, ignore_errors=True)
        if old_manifest.exists() and not new_manifest_created:
            LOGGER.info(
                "Archived the previous manifest with snapshot %s; the metadata-only refresh "
                "has no current acquisition manifest",
                previous_id,
            )
        old_manifest.unlink(missing_ok=True)
        LOGGER.info("Snapshot completed for %s with status %s", parsed.value, snapshot["status"])
        return current / "snapshot.json", bool(snapshot["warnings"])
    except Exception:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise


def normalize_existing(metadata_dir: Path) -> dict[str, int]:
    snapshot = json.loads((metadata_dir / "snapshot.json").read_text(encoding="utf-8"))
    counts, _, _ = normalize(metadata_dir, snapshot["input_accession"], snapshot["snapshot_id"])
    return counts
