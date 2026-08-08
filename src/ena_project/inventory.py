"""Parse ENA file-report rows into one-record-per-remote-file inventory."""

from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import TextIO
from urllib.parse import urlparse

from .metadata.schemas import FILE_COLUMNS, REPRESENTATIONS, SCHEMA_VERSION
from .models import RemoteFile


class InventoryError(ValueError):
    """Raised when advertised ENA file metadata is malformed."""


def _parts(value: str) -> list[str]:
    return value.split(";") if value else []


def _download_url(remote_path: str) -> str:
    if remote_path.startswith("ftp.sra.ebi.ac.uk/"):
        return f"https://{remote_path}"
    parsed = urlparse(remote_path)
    if parsed.scheme == "ftp" and parsed.hostname == "ftp.sra.ebi.ac.uk":
        return f"https://{parsed.netloc}{parsed.path}"
    if parsed.scheme == "https" and parsed.hostname == "ftp.sra.ebi.ac.uk":
        return remote_path
    raise InventoryError(f"Unexpected ENA file host or URL: {remote_path!r}")


def _file_name(remote_path: str) -> str:
    path = urlparse(remote_path).path or remote_path
    name = PurePosixPath(path).name
    if not name or name in {".", ".."} or any(ord(character) < 32 for character in name):
        raise InventoryError(f"Unsafe or empty remote filename: {remote_path!r}")
    return name


def _size(value: str, context: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise InventoryError(f"{context}: invalid byte count {value!r}") from exc
    if parsed <= 0:
        raise InventoryError(f"{context}: byte count must be positive")
    return parsed


def explode_representation(row: Mapping[str, str], representation: str) -> list[RemoteFile]:
    if representation not in REPRESENTATIONS:
        raise InventoryError(f"Unsupported representation: {representation}")
    paths = _parts(row.get(f"{representation}_ftp", ""))
    checksums = _parts(row.get(f"{representation}_md5", ""))
    byte_counts = _parts(row.get(f"{representation}_bytes", ""))
    if not paths and not checksums and not byte_counts:
        return []
    context = f"{row.get('run_accession', '<unknown>')} {representation}"
    if not paths or len(paths) != len(checksums) or len(paths) != len(byte_counts):
        raise InventoryError(
            f"{context}: malformed file arrays (urls={len(paths)}, md5={len(checksums)}, "
            f"bytes={len(byte_counts)})"
        )
    records = []
    for index, (remote_path, md5, size) in enumerate(zip(paths, checksums, byte_counts), 1):
        if not remote_path or not md5 or not size:
            raise InventoryError(f"{context}: empty file-array element at index {index}")
        normalized_md5 = md5.lower()
        if len(normalized_md5) != 32 or any(
            char not in "0123456789abcdef" for char in normalized_md5
        ):
            raise InventoryError(f"{context}: invalid MD5 at index {index}: {md5!r}")
        records.append(
            RemoteFile(
                schema_version=SCHEMA_VERSION,
                project_accession=row.get("study_accession", ""),
                study_accession=row.get("secondary_study_accession", ""),
                run_accession=row.get("run_accession", ""),
                experiment_accession=row.get("experiment_accession", ""),
                sample_accession=row.get("sample_accession", ""),
                secondary_sample_accession=row.get("secondary_sample_accession", ""),
                representation=representation,
                file_index=index,
                file_name=_file_name(remote_path),
                remote_path=remote_path,
                download_url=_download_url(remote_path),
                size_bytes=_size(size, context),
                md5=normalized_md5,
                availability="available",
                inventory_note="",
            )
        )
    return records


def parse_filereport(content: bytes) -> list[RemoteFile]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    if not reader.fieldnames or "run_accession" not in reader.fieldnames:
        raise InventoryError("ENA file report is missing a run_accession header")
    records = []
    for row in reader:
        for representation in REPRESENTATIONS:
            records.extend(explode_representation(row, representation))
    return sorted(
        records, key=lambda item: (item.run_accession, item.representation, item.file_index)
    )


def _write(records: Iterable[RemoteFile], handle: TextIO) -> None:
    writer = csv.DictWriter(handle, fieldnames=FILE_COLUMNS, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    for record in sorted(
        records, key=lambda item: (item.run_accession, item.representation, item.file_index)
    ):
        row = asdict(record)
        row["size_bytes"] = "" if record.size_bytes is None else record.size_bytes
        writer.writerow(row)


def write_inventory(records: Iterable[RemoteFile], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        _write(records, handle)


def read_inventory(path: Path) -> list[RemoteFile]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != FILE_COLUMNS:
            raise InventoryError("Unsupported files.tsv columns")
        records = []
        for line_number, row in enumerate(reader, 2):
            try:
                size = int(row["size_bytes"]) if row["size_bytes"] else None
                index = int(row["file_index"])
                records.append(
                    RemoteFile(
                        schema_version=row["schema_version"],
                        project_accession=row["project_accession"],
                        study_accession=row["study_accession"],
                        run_accession=row["run_accession"],
                        experiment_accession=row["experiment_accession"],
                        sample_accession=row["sample_accession"],
                        secondary_sample_accession=row["secondary_sample_accession"],
                        representation=row["representation"],
                        file_index=index,
                        file_name=row["file_name"],
                        remote_path=row["remote_path"],
                        download_url=row["download_url"],
                        size_bytes=size,
                        md5=row["md5"],
                        availability=row["availability"],
                        inventory_note=row["inventory_note"],
                    )
                )
            except (KeyError, ValueError) as exc:
                raise InventoryError(f"Invalid files.tsv row {line_number}: {exc}") from exc
            record = records[-1]
            if record.schema_version.split(".")[0] != SCHEMA_VERSION.split(".")[0]:
                raise InventoryError(f"Unsupported schema at row {line_number}")
            if record.representation not in REPRESENTATIONS:
                raise InventoryError(f"Invalid representation at row {line_number}")
            if record.availability != "available":
                raise InventoryError(f"Invalid availability at row {line_number}")
            if record.size_bytes is None or record.size_bytes <= 0:
                raise InventoryError(f"Invalid byte count at row {line_number}")
            if len(record.md5) != 32 or any(char not in "0123456789abcdef" for char in record.md5):
                raise InventoryError(f"Invalid MD5 at row {line_number}")
            if _file_name(record.file_name) != record.file_name:
                raise InventoryError(f"Invalid filename at row {line_number}")
            _download_url(record.download_url)
    return records


def sha256sum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
