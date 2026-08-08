"""Transactional ENA metadata snapshots and offline rebuilding."""

from __future__ import annotations

import json
import logging
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
from .schemas import SCHEMA_VERSION

LOGGER = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _snapshot_id(now: datetime) -> str:
    return now.strftime("%Y%m%dT%H%M%SZ")


def _describe(path: Path, root: Path, artifact_type: str) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256sum(path),
        "artifact_type": artifact_type,
    }


def create_snapshot(
    accession: str,
    outdir: Path,
    *,
    client: MetadataClient | None = None,
    refresh: bool = False,
    policy: str | None = None,
    now: Callable[[], datetime] = utc_now,
) -> tuple[Path, bool]:
    parsed = parse_accession(accession)
    current = outdir / "metadata"
    if (current / "snapshot.json").exists() and not refresh:
        raise FileExistsError(f"Metadata snapshot exists at {current}; use --refresh")
    stamp = _snapshot_id(now())
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
            "schema_version": SCHEMA_VERSION,
            "tool_version": __version__,
            "snapshot_id": stamp,
            "created_at": now().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
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
