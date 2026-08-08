"""Accumulate structural and integrity problems across an ENA archive."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .downloader import safe_destination, verify_file
from .inventory import InventoryError, read_inventory, sha256sum
from .manifest import ManifestError, build_manifest, read_manifest, read_run_metadata
from .metadata.schemas import EXPERIMENT_COLUMNS, RUN_COLUMNS, SAMPLE_COLUMNS
from .selection import SelectionError


def _read_table(path: Path, columns: tuple[str, ...], errors: list[str]) -> list[dict[str, str]]:
    if not path.is_file():
        errors.append(f"Missing normalized table: {path}")
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != columns:
            errors.append(f"Unsupported columns: {path}")
            return []
        return list(reader)


def validate_archive(outdir: Path) -> list[str]:
    errors: list[str] = []
    snapshot_path = outdir / "metadata" / "snapshot.json"
    if not snapshot_path.is_file():
        return [f"Missing snapshot: {snapshot_path}"]
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"Invalid snapshot: {exc}"]
    if str(snapshot.get("schema_version", "")).split(".")[0] != "1":
        errors.append(f"Unsupported snapshot schema: {snapshot.get('schema_version')!r}")
    for artifact in snapshot.get("artifacts", []):
        path = (outdir / str(artifact.get("path", ""))).resolve()
        try:
            path.relative_to(outdir.resolve())
        except ValueError:
            errors.append(f"Snapshot artifact escapes archive: {artifact.get('path')}")
            continue
        if not path.is_file():
            errors.append(f"Missing snapshot artifact: {path}")
        elif path.stat().st_size != artifact.get("size_bytes"):
            errors.append(f"Artifact size mismatch: {path}")
        elif sha256sum(path) != artifact.get("sha256"):
            errors.append(f"Artifact SHA-256 mismatch: {path}")

    derived = outdir / "metadata" / "derived"
    samples = _read_table(derived / "samples.tsv", SAMPLE_COLUMNS, errors)
    experiments = _read_table(derived / "experiments.tsv", EXPERIMENT_COLUMNS, errors)
    runs = _read_table(derived / "runs.tsv", RUN_COLUMNS, errors)
    sample_ids = {row["sample_accession"] for row in samples}
    experiment_ids = {row["experiment_accession"] for row in experiments}
    for row in experiments:
        if row["sample_accession"] and row["sample_accession"] not in sample_ids:
            errors.append(
                f"Experiment {row['experiment_accession']} references missing Sample "
                f"{row['sample_accession']}"
            )
    for row in runs:
        if row["experiment_accession"] not in experiment_ids:
            errors.append(
                f"Run {row['run_accession']} references missing Experiment "
                f"{row['experiment_accession']}"
            )

    inventory = []
    try:
        inventory = read_inventory(derived / "files.tsv")
    except (OSError, InventoryError) as exc:
        errors.append(f"Invalid inventory: {exc}")
    identities = {
        (
            item.run_accession,
            item.representation,
            item.file_index,
            item.download_url,
            item.md5,
            item.size_bytes,
        )
        for item in inventory
    }
    if len(identities) != len(inventory):
        errors.append("Inventory contains duplicate remote file records")

    manifest_path = outdir / "manifest.tsv"
    if manifest_path.is_file():
        try:
            manifest = read_manifest(manifest_path)
        except (OSError, ManifestError) as exc:
            errors.append(f"Invalid manifest: {exc}")
            manifest = []
        seen_paths = set()
        for entry in manifest:
            identity = (
                entry.run_accession,
                entry.representation,
                entry.file_index,
                entry.remote_url,
                entry.md5,
                entry.size_bytes,
            )
            if identity not in identities:
                errors.append(f"Manifest object absent from inventory: {entry.local_relpath}")
            if entry.local_relpath in seen_paths:
                errors.append(f"Contradictory duplicate local path: {entry.local_relpath}")
            seen_paths.add(entry.local_relpath)
            try:
                destination = safe_destination(outdir, entry.local_relpath)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            if not destination.is_file():
                errors.append(f"Missing downloaded object: {entry.local_relpath}")
            elif not verify_file(destination, entry):
                errors.append(f"Downloaded object failed size or MD5: {entry.local_relpath}")
        policies = {entry.selection_policy for entry in manifest}
        if len(policies) != 1:
            errors.append("Manifest must contain exactly one selection policy")
        elif inventory:
            try:
                expected = build_manifest(
                    inventory,
                    next(iter(policies)),
                    read_run_metadata(derived / "files.tsv"),
                )
                expected_rows = {
                    (
                        entry.run_accession,
                        entry.representation,
                        entry.file_index,
                        entry.selection_reason,
                        entry.local_relpath,
                    )
                    for entry in expected
                }
                actual_rows = {
                    (
                        entry.run_accession,
                        entry.representation,
                        entry.file_index,
                        entry.selection_reason,
                        entry.local_relpath,
                    )
                    for entry in manifest
                }
                if actual_rows != expected_rows:
                    errors.append("Manifest does not match its declared selection policy")
            except SelectionError as exc:
                errors.append(f"Manifest selection policy is unsatisfied: {exc}")
    return errors
