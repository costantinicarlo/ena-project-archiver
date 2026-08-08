"""Retrieve ENA raw evidence into a transaction staging directory."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Protocol

from ..ena_client import FILEREPORT_FIELDS, EnaRequestError, Response


class MetadataClient(Protocol):
    def fetch_filereport(self, accession: str) -> Response: ...
    def fetch_xml(self, accession: str) -> Response: ...


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def validate_filereport_header(content: bytes) -> None:
    try:
        header = content.decode("utf-8-sig").splitlines()[0].split("\t")
    except (IndexError, UnicodeDecodeError) as exc:
        raise EnaRequestError("ENA file report has no valid UTF-8 header") from exc
    if len(header) != len(set(header)):
        raise EnaRequestError("ENA file report contains duplicate header fields")
    expected = list(FILEREPORT_FIELDS)
    if set(header) != set(expected):
        missing = [field for field in expected if field not in header]
        unknown = [field for field in header if field not in expected]
        raise EnaRequestError(
            "ENA file report schema mismatch: "
            f"missing={missing or 'none'}, unknown={unknown or 'none'}"
        )


def acquire_raw(
    client: MetadataClient, accession: str, metadata_dir: Path
) -> tuple[list[dict[str, object]], list[str]]:
    portal = client.fetch_filereport(accession)
    portal_path = metadata_dir / "raw" / "portal" / "filereport.tsv"
    atomic_write(portal_path, portal.content)
    validate_filereport_header(portal.content)
    reader = csv.DictReader(io.StringIO(portal.content.decode("utf-8-sig")), delimiter="\t")
    rows = list(reader)
    if not rows:
        raise EnaRequestError(f"ENA returned no public Runs for {accession}")
    object_accessions = {
        "studies": {
            value
            for row in rows
            for value in (row.get("study_accession", ""), row.get("secondary_study_accession", ""))
            if value
        },
        "samples": {
            value
            for row in rows
            for value in (
                row.get("sample_accession", ""),
                row.get("secondary_sample_accession", ""),
            )
            if value
        },
        "experiments": {
            row.get("experiment_accession", "") for row in rows if row.get("experiment_accession")
        },
        "runs": {row.get("run_accession", "") for row in rows if row.get("run_accession")},
    }
    requests: list[dict[str, object]] = [
        {"url": portal.url, "status": portal.status, "artifact": "raw/portal/filereport.tsv"}
    ]
    warnings = []
    for group in ("studies", "samples", "experiments", "runs"):
        for object_accession in sorted(object_accessions[group]):
            try:
                response = client.fetch_xml(object_accession)
            except EnaRequestError as exc:
                warnings.append(f"Optional Browser XML unavailable for {object_accession}: {exc}")
                continue
            relative = Path("raw") / "xml" / group / f"{object_accession}.xml"
            atomic_write(metadata_dir / relative, response.content)
            requests.append(
                {"url": response.url, "status": response.status, "artifact": relative.as_posix()}
            )
    return requests, warnings
