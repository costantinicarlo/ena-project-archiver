"""Pure per-Run representation-selection policies."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from .models import RemoteFile

POLICIES = ("archival", "submitted", "fastq", "sra", "all")


class SelectionError(ValueError):
    """Raised when a policy cannot select a complete representation."""


def _valid(records: list[RemoteFile]) -> bool:
    return bool(records) and all(
        item.availability == "available"
        and item.size_bytes is not None
        and item.size_bytes > 0
        and len(item.md5) == 32
        and bool(item.download_url)
        for item in records
    )


def select_files(
    records: Iterable[RemoteFile],
    policy: str = "archival",
    run_accessions: Iterable[str] = (),
) -> list[tuple[RemoteFile, str]]:
    if policy not in POLICIES:
        raise SelectionError(f"Unsupported representation policy: {policy}")
    grouped: dict[str, dict[str, list[RemoteFile]]] = defaultdict(lambda: defaultdict(list))
    for run_accession in run_accessions:
        grouped[run_accession]
    for record in records:
        grouped[record.run_accession][record.representation].append(record)
    if not grouped:
        raise SelectionError("Inventory contains no Runs")

    selected = []
    for run_accession in sorted(grouped):
        representations = grouped[run_accession]
        for values in representations.values():
            values.sort(key=lambda item: item.file_index)
        if policy == "all":
            valid_names = [
                name for name in ("submitted", "fastq", "sra") if _valid(representations[name])
            ]
            if not valid_names:
                raise SelectionError(f"{run_accession}: no valid representation available")
            for name in valid_names:
                selected.extend(
                    (item, "all_available_representations") for item in representations[name]
                )
            continue
        if policy != "archival":
            if not _valid(representations[policy]):
                raise SelectionError(f"{run_accession}: {policy} representation unavailable")
            selected.extend((item, f"explicit_{policy}_policy") for item in representations[policy])
            continue
        if representations["submitted"]:
            if not _valid(representations["submitted"]):
                raise SelectionError(f"{run_accession}: submitted representation is malformed")
            selected.extend(
                (item, "submitted_original_preferred") for item in representations["submitted"]
            )
        elif _valid(representations["sra"]):
            selected.extend(
                (item, "submitted_not_available_from_ena") for item in representations["sra"]
            )
        elif representations["sra"]:
            raise SelectionError(f"{run_accession}: SRA fallback representation is malformed")
        elif _valid(representations["fastq"]):
            selected.extend(
                (item, "submitted_and_sra_not_available_from_ena")
                for item in representations["fastq"]
            )
        elif representations["fastq"]:
            raise SelectionError(f"{run_accession}: FASTQ fallback representation is malformed")
        else:
            raise SelectionError(f"{run_accession}: no archival representation available")
    return selected
