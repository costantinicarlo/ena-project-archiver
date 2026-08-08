"""Build, read, and write the immutable acquisition manifest."""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import TextIO

from .inventory import read_inventory
from .metadata.schemas import MANIFEST_COLUMNS, SCHEMA_VERSION
from .models import ManifestEntry, RemoteFile
from .selection import select_files


class ManifestError(ValueError):
    """Raised when a manifest is unsafe or structurally invalid."""


def safe_local_relpath(record: RemoteFile) -> str:
    if not record.run_accession or "/" in record.run_accession or "\\" in record.run_accession:
        raise ManifestError(f"Unsafe Run accession: {record.run_accession!r}")
    name = PurePosixPath(record.file_name)
    if name.is_absolute() or len(name.parts) != 1 or name.name in {"", ".", ".."}:
        raise ManifestError(f"Unsafe remote filename: {record.file_name!r}")
    if any(ord(character) < 32 for character in record.file_name):
        raise ManifestError(f"Control character in remote filename: {record.file_name!r}")
    return f"{record.representation}/{record.run_accession}/{record.file_name}"


def build_manifest(
    files: Iterable[RemoteFile],
    policy: str = "archival",
    run_metadata: Mapping[str, Mapping[str, str]] | None = None,
) -> list[ManifestEntry]:
    metadata = run_metadata or {}
    entries = []
    for record, reason in select_files(files, policy, metadata):
        if record.size_bytes is None:
            raise ManifestError(f"{record.run_accession}: selected file has no byte count")
        run = metadata.get(record.run_accession, {})
        entries.append(
            ManifestEntry(
                schema_version=SCHEMA_VERSION,
                project_accession=record.project_accession,
                study_accession=record.study_accession,
                run_accession=record.run_accession,
                experiment_accession=record.experiment_accession,
                sample_accession=record.sample_accession,
                secondary_sample_accession=record.secondary_sample_accession,
                library_strategy=run.get("library_strategy", ""),
                library_source=run.get("library_source", ""),
                library_layout=run.get("library_layout", ""),
                instrument_platform=run.get("instrument_platform", ""),
                instrument_model=run.get("instrument_model", ""),
                representation=record.representation,
                selection_policy=policy,
                selection_reason=reason,
                file_index=record.file_index,
                file_name=record.file_name,
                size_bytes=record.size_bytes,
                md5=record.md5,
                remote_url=record.download_url,
                local_relpath=safe_local_relpath(record),
            )
        )
    return sorted(
        entries, key=lambda item: (item.run_accession, item.representation, item.file_index)
    )


def _write(entries: Iterable[ManifestEntry], handle: TextIO) -> None:
    writer = csv.DictWriter(
        handle, fieldnames=MANIFEST_COLUMNS, delimiter="\t", lineterminator="\n"
    )
    writer.writeheader()
    for entry in sorted(
        entries, key=lambda item: (item.run_accession, item.representation, item.file_index)
    ):
        writer.writerow(asdict(entry))


def write_manifest(entries: Iterable[ManifestEntry], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        _write(entries, handle)


def manifest_from_inventory(
    files_path: Path, output: Path, policy: str = "archival"
) -> list[ManifestEntry]:
    entries = build_manifest(read_inventory(files_path), policy, read_run_metadata(files_path))
    write_manifest(entries, output)
    return entries


def read_run_metadata(files_path: Path) -> dict[str, dict[str, str]]:
    runs_path = files_path.with_name("runs.tsv")
    if not runs_path.is_file():
        return {}
    with runs_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        metadata = {}
        for row in reader:
            run_accession = row.get("run_accession", "")
            if not run_accession:
                raise ManifestError(f"Missing run_accession in {runs_path}")
            metadata[run_accession] = dict(row)
        return metadata


def read_manifest(path: Path) -> list[ManifestEntry]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != MANIFEST_COLUMNS:
            raise ManifestError("Unsupported manifest columns")
        entries = []
        for line_number, row in enumerate(reader, 2):
            try:
                values = dict(row)
                values["file_index"] = int(values["file_index"])
                values["size_bytes"] = int(values["size_bytes"])
                entry = ManifestEntry(**values)
            except (TypeError, ValueError) as exc:
                raise ManifestError(f"Invalid manifest row {line_number}: {exc}") from exc
            expected = PurePosixPath(entry.local_relpath)
            if expected.is_absolute() or ".." in expected.parts or len(expected.parts) < 3:
                raise ManifestError(f"Unsafe local_relpath at row {line_number}")
            entries.append(entry)
    return entries
