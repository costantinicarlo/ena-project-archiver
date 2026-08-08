from dataclasses import replace
from pathlib import Path

import pytest

from ena_project.inventory import parse_filereport
from ena_project.manifest import ManifestError, build_manifest, write_manifest
from ena_project.models import RemoteFile
from ena_project.selection import SelectionError, select_files

FIXTURES = Path(__file__).parent / "fixtures"


def remote(run: str, representation: str, name: str = "same.fastq.gz") -> RemoteFile:
    return RemoteFile(
        "1.0",
        "PRJEB1",
        "ERP1",
        run,
        f"ERX{run[3:]}",
        f"ERS{run[3:]}",
        "",
        representation,
        1,
        name,
        f"ftp.sra.ebi.ac.uk/{run}/{name}",
        f"https://ftp.sra.ebi.ac.uk/{run}/{name}",
        3,
        "900150983cd24fb0d6963f7d28e17f72",
        "available",
        "",
    )


def test_archival_preference_and_fallbacks() -> None:
    records = [
        remote("ERR1", "submitted"),
        remote("ERR1", "sra", "ERR1"),
        remote("ERR2", "sra", "ERR2"),
        remote("ERR2", "fastq"),
        remote("ERR3", "fastq"),
    ]
    selected = select_files(records)
    assert [(item.run_accession, item.representation) for item, _ in selected] == [
        ("ERR1", "submitted"),
        ("ERR2", "sra"),
        ("ERR3", "fastq"),
    ]
    assert selected[1][1] == "submitted_not_available_from_ena"


def test_explicit_policies_do_not_fallback_and_all_selects_every_valid_set() -> None:
    records = [remote("ERR1", "submitted"), remote("ERR1", "fastq")]
    with pytest.raises(SelectionError, match="sra representation unavailable"):
        select_files(records, "sra")
    assert len(select_files(records, "all")) == 2


def test_advertised_invalid_preferred_representation_blocks_fallback() -> None:
    invalid = replace(remote("ERR1", "submitted"), availability="malformed")
    with pytest.raises(SelectionError, match="submitted representation is malformed"):
        select_files([invalid, remote("ERR1", "sra", "ERR1")])


def test_manifest_selects_every_file_and_is_deterministic(tmp_path: Path) -> None:
    records = parse_filereport((FIXTURES / "filereport.tsv").read_bytes())
    first_entries = build_manifest(records)
    assert [item.file_name for item in first_entries] == [
        "original_R1.fastq.gz",
        "original_R2.fastq.gz",
    ]
    first = tmp_path / "first.tsv"
    second = tmp_path / "second.tsv"
    write_manifest(first_entries, first)
    write_manifest(build_manifest(reversed(records)), second)
    assert first.read_bytes() == second.read_bytes()


def test_duplicate_submitted_basenames_are_isolated_by_run() -> None:
    entries = build_manifest([remote("ERR1", "submitted"), remote("ERR2", "submitted")])
    assert entries[0].local_relpath == "submitted/ERR1/same.fastq.gz"
    assert entries[1].local_relpath == "submitted/ERR2/same.fastq.gz"


def test_unsafe_filename_is_rejected() -> None:
    with pytest.raises(ManifestError, match="Unsafe remote filename"):
        build_manifest([replace(remote("ERR1", "submitted"), file_name="../escape")])


def test_submitted_bam_and_sra_only_runs_retain_repository_filenames() -> None:
    records = [
        remote("ERR1", "submitted", "original.bam"),
        remote("ERR2", "sra", "ERR2"),
    ]
    entries = build_manifest(records)
    assert [(item.representation, item.file_name) for item in entries] == [
        ("submitted", "original.bam"),
        ("sra", "ERR2"),
    ]


def test_run_without_any_representation_fails() -> None:
    with pytest.raises(SelectionError, match="no archival representation available"):
        select_files([], run_accessions=["ERR1"])
