"""Stable schema versions, compatibility checks, and column order."""

PROJECT_SCHEMA_VERSION = "1.0"
INVENTORY_SCHEMA_VERSION = "1.0"
MANIFEST_SCHEMA_VERSION = "1.0"
SNAPSHOT_SCHEMA_VERSION = "1.1"
NORMALIZED_TABLE_SCHEMA_VERSION = "1.0"

# Compatibility alias for callers that predate independent schema versions.
SCHEMA_VERSION = INVENTORY_SCHEMA_VERSION


def schema_major(version: str) -> int:
    try:
        major, minor = version.split(".", 1)
        if not major.isdigit() or not minor.isdigit():
            raise ValueError
        return int(major)
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"Invalid schema version: {version!r}") from exc


def require_supported_schema(version: str, supported: str, artifact: str) -> None:
    if schema_major(version) != schema_major(supported):
        raise ValueError(f"Unsupported {artifact} schema version: {version!r}")


FILE_COLUMNS = (
    "schema_version",
    "project_accession",
    "study_accession",
    "run_accession",
    "experiment_accession",
    "sample_accession",
    "secondary_sample_accession",
    "representation",
    "file_index",
    "file_name",
    "remote_path",
    "download_url",
    "size_bytes",
    "md5",
    "availability",
    "inventory_note",
)

REPRESENTATIONS = ("submitted", "fastq", "sra")

SAMPLE_COLUMNS = (
    "sample_accession",
    "secondary_sample_accession",
    "sample_alias",
    "sample_title",
    "tax_id",
    "scientific_name",
    "collection_date",
    "country",
    "location",
    "first_public",
    "last_updated",
)
SAMPLE_ATTRIBUTE_COLUMNS = (
    "sample_accession",
    "attribute_name",
    "attribute_value",
    "attribute_units",
)
EXPERIMENT_COLUMNS = (
    "experiment_accession",
    "study_accession",
    "sample_accession",
    "secondary_sample_accession",
    "experiment_alias",
    "library_name",
    "library_strategy",
    "library_source",
    "library_selection",
    "library_layout",
    "instrument_platform",
    "instrument_model",
)
RUN_COLUMNS = (
    "run_accession",
    "experiment_accession",
    "study_accession",
    "secondary_study_accession",
    "sample_accession",
    "secondary_sample_accession",
    "run_alias",
    "library_strategy",
    "library_source",
    "library_layout",
    "instrument_platform",
    "instrument_model",
    "base_count",
    "read_count",
    "first_public",
    "last_updated",
)

MANIFEST_COLUMNS = (
    "schema_version",
    "project_accession",
    "study_accession",
    "run_accession",
    "experiment_accession",
    "sample_accession",
    "secondary_sample_accession",
    "library_strategy",
    "library_source",
    "library_layout",
    "instrument_platform",
    "instrument_model",
    "representation",
    "selection_policy",
    "selection_reason",
    "file_index",
    "file_name",
    "size_bytes",
    "md5",
    "remote_url",
    "local_relpath",
)
