"""Accumulate structural and integrity problems across an ENA archive."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .downloader import safe_destination, verify_file
from .inventory import InventoryError, read_inventory, sha256sum
from .manifest import ManifestError, build_manifest, read_manifest, read_run_metadata
from .metadata.schemas import (
    EXPERIMENT_COLUMNS,
    RUN_COLUMNS,
    SAMPLE_ATTRIBUTE_COLUMNS,
    SAMPLE_COLUMNS,
    SNAPSHOT_SCHEMA_VERSION,
    require_supported_schema,
)
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


def _unique_values(
    rows: list[dict[str, str]], field: str, table_name: str, errors: list[str]
) -> set[str]:
    values: set[str] = set()
    for row in rows:
        value = row[field]
        if not value:
            errors.append(f"Empty {field} in {table_name}")
        elif value in values:
            errors.append(f"Duplicate {field} {value} in {table_name}")
        values.add(value)
    return values


def validate_metadata(outdir: Path) -> list[str]:
    errors: list[str] = []
    snapshot_path = outdir / "metadata" / "snapshot.json"
    if not snapshot_path.is_file():
        return [f"Missing snapshot: {snapshot_path}"]
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"Invalid snapshot: {exc}"]
    try:
        require_supported_schema(
            str(snapshot.get("schema_version", "")), SNAPSHOT_SCHEMA_VERSION, "snapshot"
        )
    except ValueError as exc:
        errors.append(str(exc))
    for field in (
        "snapshot_id",
        "created_at",
        "input_accession",
        "project_accession",
        "study_accession",
        "source",
        "status",
    ):
        if not snapshot.get(field):
            errors.append(f"Snapshot missing provenance field: {field}")
    artifacts = snapshot.get("artifacts", [])
    if not isinstance(artifacts, list):
        errors.append("Snapshot artifacts ledger must be a list")
        artifacts = []
    ledger_paths: set[str] = set()
    for artifact in artifacts:
        relative_path = str(artifact.get("path", ""))
        if relative_path in ledger_paths:
            errors.append(f"Duplicate snapshot artifact ledger path: {relative_path}")
        ledger_paths.add(relative_path)
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
    actual_artifacts = {
        path.relative_to(outdir).as_posix()
        for path in outdir.rglob("*")
        if path.is_file()
        and path != snapshot_path
        and "archive" not in path.relative_to(outdir).parts
        and (
            path.relative_to(outdir).parts[0] == "metadata"
            or path.relative_to(outdir).as_posix() == "manifest.tsv"
        )
    }
    for missing in sorted(actual_artifacts - ledger_paths):
        errors.append(f"File is absent from snapshot artifact ledger: {missing}")
    for unexpected in sorted(ledger_paths - actual_artifacts):
        errors.append(f"Snapshot artifact ledger has no current file: {unexpected}")

    derived = outdir / "metadata" / "derived"
    samples = _read_table(derived / "samples.tsv", SAMPLE_COLUMNS, errors)
    attributes = _read_table(derived / "sample_attributes.tsv", SAMPLE_ATTRIBUTE_COLUMNS, errors)
    experiments = _read_table(derived / "experiments.tsv", EXPERIMENT_COLUMNS, errors)
    runs = _read_table(derived / "runs.tsv", RUN_COLUMNS, errors)
    sample_ids = _unique_values(samples, "sample_accession", "samples.tsv", errors)
    _unique_values(experiments, "experiment_accession", "experiments.tsv", errors)
    _unique_values(runs, "run_accession", "runs.tsv", errors)
    for row in attributes:
        if row["sample_accession"] not in sample_ids:
            errors.append(f"SampleAttribute references missing Sample {row['sample_accession']}")
    for row in experiments:
        if row["sample_accession"] and row["sample_accession"] not in sample_ids:
            errors.append(
                f"Experiment {row['experiment_accession']} references missing Sample "
                f"{row['sample_accession']}"
            )
        if row["study_accession"] != snapshot.get("study_accession"):
            errors.append(
                f"Experiment {row['experiment_accession']} Study identity conflicts with snapshot"
            )
    experiment_by_id = {row["experiment_accession"]: row for row in experiments}
    for row in runs:
        experiment = experiment_by_id.get(row["experiment_accession"])
        if experiment is None:
            errors.append(
                f"Run {row['run_accession']} references missing Experiment "
                f"{row['experiment_accession']}"
            )
            continue
        for field in ("sample_accession", "secondary_sample_accession"):
            if row[field] != experiment[field]:
                errors.append(
                    f"Run {row['run_accession']} {field} conflicts with Experiment "
                    f"{row['experiment_accession']}"
                )
        if row["study_accession"] != snapshot.get("project_accession"):
            errors.append(f"Run {row['run_accession']} project identity conflicts with snapshot")
        if row["secondary_study_accession"] != snapshot.get("study_accession"):
            errors.append(f"Run {row['run_accession']} Study identity conflicts with snapshot")

    inventory = []
    try:
        inventory = read_inventory(derived / "files.tsv")
    except (OSError, InventoryError) as exc:
        errors.append(f"Invalid inventory: {exc}")
    logical_identities: set[tuple[str, str, int]] = set()
    run_by_id = {row["run_accession"]: row for row in runs}
    for item in inventory:
        identity = (item.run_accession, item.representation, item.file_index)
        if identity in logical_identities:
            errors.append(f"Duplicate inventory file identity: {identity}")
        logical_identities.add(identity)
        run = run_by_id.get(item.run_accession)
        if run is None:
            errors.append(f"Inventory references missing Run {item.run_accession}")
            continue
        for field in (
            "experiment_accession",
            "sample_accession",
            "secondary_sample_accession",
        ):
            if getattr(item, field) != run[field]:
                errors.append(
                    f"Inventory {identity} {field} conflicts with Run {item.run_accession}"
                )
        if item.project_accession != run["study_accession"]:
            errors.append(f"Inventory {identity} project identity conflicts with Run")
        if item.study_accession != run["secondary_study_accession"]:
            errors.append(f"Inventory {identity} Study identity conflicts with Run")

    manifest_path = outdir / "manifest.tsv"
    if manifest_path.is_file():
        try:
            manifest = read_manifest(manifest_path)
        except (OSError, ManifestError) as exc:
            errors.append(f"Invalid manifest: {exc}")
            manifest = []
        for entry in manifest:
            identity = (entry.run_accession, entry.representation, entry.file_index)
            inventory_matches = [
                item
                for item in inventory
                if (item.run_accession, item.representation, item.file_index) == identity
                and item.download_url == entry.remote_url
                and item.md5 == entry.md5
                and item.size_bytes == entry.size_bytes
            ]
            if not inventory_matches:
                errors.append(f"Manifest object absent from inventory: {entry.local_relpath}")
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
    expected_counts = {
        "samples": len(samples),
        "sample_attributes": len(attributes),
        "experiments": len(experiments),
        "runs": len(runs),
        "files": len(inventory),
    }
    for name, expected in expected_counts.items():
        if snapshot.get("record_counts", {}).get(name) != expected:
            errors.append(
                f"Snapshot record count mismatch for {name}: "
                f"expected {expected}, recorded {snapshot.get('record_counts', {}).get(name)!r}"
            )
    project_path = derived / "project.json"
    try:
        project = json.loads(project_path.read_text(encoding="utf-8"))
        for field in ("input_accession", "project_accession", "study_accession", "snapshot_id"):
            if project.get(field) != snapshot.get(field):
                errors.append(f"project.json {field} conflicts with snapshot")
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"Invalid project.json: {exc}")
    return errors


def validate_archive(outdir: Path) -> list[str]:
    errors = validate_metadata(outdir)
    manifest_path = outdir / "manifest.tsv"
    if not manifest_path.is_file():
        return errors
    try:
        manifest = read_manifest(manifest_path)
    except (OSError, ManifestError):
        return errors
    for entry in manifest:
        try:
            destination = safe_destination(outdir, entry.local_relpath)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not destination.is_file():
            errors.append(f"Missing downloaded object: {entry.local_relpath}")
        elif not verify_file(destination, entry):
            errors.append(f"Downloaded object failed size or MD5: {entry.local_relpath}")
    return errors
