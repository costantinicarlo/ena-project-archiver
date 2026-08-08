"""Typed records shared by inventory, selection, and acquisition layers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectRecord:
    input_accession: str
    project_accession: str
    study_accession: str
    study_alias: str = ""
    title: str = ""
    description: str = ""
    center_name: str = ""
    first_public: str = ""
    last_updated: str = ""


@dataclass(frozen=True)
class SampleRecord:
    sample_accession: str
    secondary_sample_accession: str = ""
    sample_alias: str = ""
    sample_title: str = ""
    tax_id: str = ""
    scientific_name: str = ""
    collection_date: str = ""
    country: str = ""
    location: str = ""
    first_public: str = ""
    last_updated: str = ""


@dataclass(frozen=True)
class SampleAttribute:
    sample_accession: str
    attribute_name: str
    attribute_value: str
    attribute_units: str = ""


@dataclass(frozen=True)
class ExperimentRecord:
    experiment_accession: str
    study_accession: str = ""
    sample_accession: str = ""
    secondary_sample_accession: str = ""
    experiment_alias: str = ""
    library_name: str = ""
    library_strategy: str = ""
    library_source: str = ""
    library_selection: str = ""
    library_layout: str = ""
    instrument_platform: str = ""
    instrument_model: str = ""


@dataclass(frozen=True)
class RunRecord:
    run_accession: str
    experiment_accession: str = ""
    study_accession: str = ""
    secondary_study_accession: str = ""
    sample_accession: str = ""
    secondary_sample_accession: str = ""
    run_alias: str = ""
    library_strategy: str = ""
    library_source: str = ""
    library_layout: str = ""
    instrument_platform: str = ""
    instrument_model: str = ""
    base_count: str = ""
    read_count: str = ""
    first_public: str = ""
    last_updated: str = ""


@dataclass(frozen=True)
class RemoteFile:
    schema_version: str
    project_accession: str
    study_accession: str
    run_accession: str
    experiment_accession: str
    sample_accession: str
    secondary_sample_accession: str
    representation: str
    file_index: int
    file_name: str
    remote_path: str
    download_url: str
    size_bytes: int | None
    md5: str
    availability: str
    inventory_note: str


@dataclass(frozen=True)
class ManifestEntry:
    schema_version: str
    project_accession: str
    study_accession: str
    run_accession: str
    experiment_accession: str
    sample_accession: str
    secondary_sample_accession: str
    library_strategy: str
    library_source: str
    library_layout: str
    instrument_platform: str
    instrument_model: str
    representation: str
    selection_policy: str
    selection_reason: str
    file_index: int
    file_name: str
    size_bytes: int
    md5: str
    remote_url: str
    local_relpath: str
