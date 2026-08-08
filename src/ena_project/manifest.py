"""Build, read, and write the immutable acquisition manifest."""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from pathlib import Path
from typing import TextIO

from .inventory import read_inventory
from .metadata.schemas import (
    MANIFEST_COLUMNS,
    MANIFEST_SCHEMA_VERSION,
    REPRESENTATIONS,
    require_supported_schema,
)
from .models import ManifestEntry, RemoteFile
from .selection import POLICIES, select_files
from .trust import (
    canonical_local_relpath,
    validate_ena_download_url,
    validate_file_name,
    validate_run_accession,
)


class ManifestError(ValueError):
    """Raised when a manifest is unsafe or structurally invalid."""


def safe_local_relpath(record: RemoteFile) -> str:
    try:
        return canonical_local_relpath(
            record.representation, record.run_accession, record.file_name
        )
    except ValueError as exc:
        raise ManifestError(str(exc)) from exc


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
                schema_version=MANIFEST_SCHEMA_VERSION,
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
        identities: set[tuple[str, str, int]] = set()
        local_paths: set[str] = set()
        for line_number, row in enumerate(reader, 2):
            try:
                values = dict(row)
                values["file_index"] = int(values["file_index"])
                values["size_bytes"] = int(values["size_bytes"])
                entry = ManifestEntry(**values)
            except (TypeError, ValueError) as exc:
                raise ManifestError(f"Invalid manifest row {line_number}: {exc}") from exc
            try:
                require_supported_schema(entry.schema_version, MANIFEST_SCHEMA_VERSION, "manifest")
                if entry.representation not in REPRESENTATIONS:
                    raise ValueError(f"Unknown representation: {entry.representation!r}")
                if entry.selection_policy not in POLICIES:
                    raise ValueError(f"Unknown selection policy: {entry.selection_policy!r}")
                if entry.file_index <= 0:
                    raise ValueError("file_index must be positive")
                if entry.size_bytes <= 0:
                    raise ValueError("size_bytes must be positive")
                if len(entry.md5) != 32 or any(
                    character not in "0123456789abcdef" for character in entry.md5
                ):
                    raise ValueError(f"Invalid MD5: {entry.md5!r}")
                validate_run_accession(entry.run_accession)
                validate_file_name(entry.file_name)
                validate_ena_download_url(entry.remote_url)
                canonical = canonical_local_relpath(
                    entry.representation, entry.run_accession, entry.file_name
                )
                if entry.local_relpath != canonical:
                    raise ValueError(
                        f"local_relpath must be canonical {canonical!r}, got "
                        f"{entry.local_relpath!r}"
                    )
            except ValueError as exc:
                raise ManifestError(f"Invalid manifest row {line_number}: {exc}") from exc
            identity = (entry.run_accession, entry.representation, entry.file_index)
            if identity in identities:
                raise ManifestError(f"Duplicate manifest file identity at row {line_number}")
            if entry.local_relpath in local_paths:
                raise ManifestError(f"Duplicate local_relpath at row {line_number}")
            identities.add(identity)
            local_paths.add(entry.local_relpath)
            entries.append(entry)
    return entries
