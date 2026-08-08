"""Deterministically normalize preserved ENA Portal and Browser evidence."""

from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import TypeVar

from ..accession import parse_accession
from ..inventory import parse_filereport, write_inventory
from ..models import ExperimentRecord, RunRecord, SampleAttribute, SampleRecord
from .acquire import atomic_write
from .schemas import (
    EXPERIMENT_COLUMNS,
    PROJECT_SCHEMA_VERSION,
    RUN_COLUMNS,
    SAMPLE_ATTRIBUTE_COLUMNS,
    SAMPLE_COLUMNS,
)

Record = TypeVar("Record")


def _write_table(path: Path, columns: Sequence[str], rows: Iterable[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})
    temporary.replace(path)


def _sample_attributes(
    xml_dir: Path, canonical_accessions: Mapping[str, str]
) -> list[SampleAttribute]:
    attributes = set()
    for path in sorted(xml_dir.glob("*.xml")) if xml_dir.is_dir() else []:
        root = ET.fromstring(path.read_bytes())
        sample = next(
            (element for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "SAMPLE"), None
        )
        xml_accession = sample.get("accession", "") if sample is not None else ""
        accession = canonical_accessions.get(xml_accession, xml_accession)
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1] != "SAMPLE_ATTRIBUTE":
                continue
            values = {}
            for child in element:
                values[child.tag.rsplit("}", 1)[-1]] = (child.text or "").strip()
            if accession and values.get("TAG"):
                attributes.add(
                    (accession, values["TAG"], values.get("VALUE", ""), values.get("UNITS", ""))
                )
    return [SampleAttribute(*values) for values in sorted(attributes)]


def _study_details(xml_dir: Path) -> dict[str, str]:
    details: dict[str, str] = {}
    for path in sorted(xml_dir.glob("*.xml")) if xml_dir.is_dir() else []:
        root = ET.fromstring(path.read_bytes())
        study = next(
            (element for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "STUDY"),
            None,
        )
        if study is None:
            continue
        details["center_name"] = study.get("center_name", "")
        for element in study.iter():
            name = element.tag.rsplit("}", 1)[-1]
            text = (element.text or "").strip()
            if name == "STUDY_TITLE" and text:
                details["title"] = text
            elif name in {"STUDY_DESCRIPTION", "DESCRIPTION"} and text:
                details["description"] = text
        if details:
            break
    return details


def _unique_by_accession(
    records: Iterable[Record], accession_name: str, record_type: str
) -> dict[str, Record]:
    unique: dict[str, Record] = {}
    for record in records:
        accession = str(getattr(record, accession_name))
        previous = unique.get(accession)
        if previous is not None and previous != record:
            raise ValueError(f"Conflicting {record_type} metadata for accession {accession}")
        unique[accession] = record
    return unique


def normalize(
    metadata_dir: Path, input_accession: str, snapshot_id: str
) -> tuple[dict[str, int], str, str]:
    raw = metadata_dir / "raw" / "portal" / "filereport.tsv"
    with raw.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if not rows:
        raise ValueError("Preserved file report contains no Runs")
    project_accessions = sorted(
        {row.get("study_accession", "") for row in rows if row.get("study_accession")}
    )
    study_accessions = sorted(
        {
            row.get("secondary_study_accession", "")
            for row in rows
            if row.get("secondary_study_accession")
        }
    )
    if len(project_accessions) != 1:
        raise ValueError(
            "ENA acquisition contains incompatible canonical projects: "
            + ", ".join(project_accessions)
        )
    project_accession = project_accessions[0]
    if len(study_accessions) > 1:
        raise ValueError(
            f"BioProject {project_accession} contains multiple ENA Studies "
            f"({', '.join(study_accessions)}). v0.1 archives one Study acquisition unit at a "
            "time. Repeat the command using a specific ERP/SRP/DRP accession."
        )
    study_accession = study_accessions[0] if study_accessions else project_accession
    requested = parse_accession(input_accession)
    represented = project_accessions if requested.kind == "project" else study_accessions
    if requested.value not in represented:
        raise ValueError(
            f"ENA response identity does not match requested {requested.kind} accession "
            f"{requested.value}: returned {sorted(represented)}"
        )
    first = rows[0]
    study_details = _study_details(metadata_dir / "raw" / "xml" / "studies")
    project = {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "input_accession": input_accession,
        "project_accession": project_accession,
        "study_accession": study_accession,
        "study_alias": first.get("study_alias") or None,
        "title": study_details.get("title") or first.get("study_title") or None,
        "description": study_details.get("description") or None,
        "center_name": study_details.get("center_name") or None,
        "first_public": first.get("first_public") or None,
        "last_updated": first.get("last_updated") or None,
        "snapshot_id": snapshot_id,
        "source": "ENA",
    }
    derived = metadata_dir / "derived"
    atomic_write(
        derived / "project.json", (json.dumps(project, indent=2, sort_keys=True) + "\n").encode()
    )

    samples = _unique_by_accession(
        (
            SampleRecord(
                row.get("sample_accession", ""),
                row.get("secondary_sample_accession", ""),
                row.get("sample_alias", ""),
                row.get("sample_title", ""),
                row.get("tax_id", ""),
                row.get("scientific_name", ""),
                row.get("collection_date", ""),
                row.get("country", ""),
                row.get("location", ""),
                row.get("first_public", ""),
                row.get("last_updated", ""),
            )
            for row in rows
            if row.get("sample_accession")
        ),
        "sample_accession",
        "Sample",
    )
    experiments = _unique_by_accession(
        (
            ExperimentRecord(
                row.get("experiment_accession", ""),
                study_accession,
                row.get("sample_accession", ""),
                row.get("secondary_sample_accession", ""),
                row.get("experiment_alias", ""),
                row.get("library_name", ""),
                row.get("library_strategy", ""),
                row.get("library_source", ""),
                row.get("library_selection", ""),
                row.get("library_layout", ""),
                row.get("instrument_platform", ""),
                row.get("instrument_model", ""),
            )
            for row in rows
            if row.get("experiment_accession")
        ),
        "experiment_accession",
        "Experiment",
    )
    runs = _unique_by_accession(
        (
            RunRecord(
                row.get("run_accession", ""),
                row.get("experiment_accession", ""),
                project_accession,
                study_accession,
                row.get("sample_accession", ""),
                row.get("secondary_sample_accession", ""),
                row.get("run_alias", ""),
                row.get("library_strategy", ""),
                row.get("library_source", ""),
                row.get("library_layout", ""),
                row.get("instrument_platform", ""),
                row.get("instrument_model", ""),
                row.get("base_count", ""),
                row.get("read_count", ""),
                row.get("first_public", ""),
                row.get("last_updated", ""),
            )
            for row in rows
            if row.get("run_accession")
        ),
        "run_accession",
        "Run",
    )
    sample_aliases = {
        alias: row["sample_accession"]
        for row in rows
        for alias in (row.get("sample_accession", ""), row.get("secondary_sample_accession", ""))
        if alias and row.get("sample_accession")
    }
    attributes = _sample_attributes(metadata_dir / "raw" / "xml" / "samples", sample_aliases)
    _write_table(
        derived / "samples.tsv",
        SAMPLE_COLUMNS,
        (asdict(samples[key]) for key in sorted(samples)),
    )
    _write_table(
        derived / "sample_attributes.tsv",
        SAMPLE_ATTRIBUTE_COLUMNS,
        (asdict(item) for item in attributes),
    )
    _write_table(
        derived / "experiments.tsv",
        EXPERIMENT_COLUMNS,
        (asdict(experiments[key]) for key in sorted(experiments)),
    )
    _write_table(
        derived / "runs.tsv",
        RUN_COLUMNS,
        (asdict(runs[key]) for key in sorted(runs)),
    )
    files = parse_filereport(raw.read_bytes())
    write_inventory(files, derived / "files.tsv")
    return (
        {
            "samples": len(samples),
            "sample_attributes": len(attributes),
            "experiments": len(experiments),
            "runs": len(runs),
            "files": len(files),
        },
        project_accession,
        study_accession,
    )
