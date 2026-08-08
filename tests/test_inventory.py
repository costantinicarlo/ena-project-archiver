import csv
from pathlib import Path

import pytest

from ena_project.accession import AccessionError, parse_accession
from ena_project.inventory import (
    InventoryError,
    explode_representation,
    parse_filereport,
    write_inventory,
)

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_rows(name: str) -> list[dict[str, str]]:
    with (FIXTURES / "cases" / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def test_supported_accessions_are_normalized() -> None:
    assert parse_accession(" prjeb123 ").value == "PRJEB123"
    assert parse_accession("SRP42").kind == "study"
    with pytest.raises(AccessionError):
        parse_accession("ERR123")


def test_file_arrays_are_exploded_without_independent_sorting(tmp_path: Path) -> None:
    records = parse_filereport((FIXTURES / "filereport.tsv").read_bytes())
    submitted = [item for item in records if item.representation == "submitted"]
    fastq = [item for item in records if item.representation == "fastq"]
    assert [item.file_name for item in submitted] == [
        "original_R1.fastq.gz",
        "original_R2.fastq.gz",
    ]
    assert [item.size_bytes for item in fastq] == [3, 4, 1]
    first = tmp_path / "files-a.tsv"
    second = tmp_path / "files-b.tsv"
    write_inventory(records, first)
    write_inventory(reversed(records), second)
    assert first.read_bytes() == second.read_bytes()


@pytest.mark.parametrize(
    "case", fixture_rows("malformed-array-cases.tsv"), ids=lambda row: row["case"]
)
def test_malformed_advertised_representation_is_an_error(case: dict[str, str]) -> None:
    row = {
        "run_accession": "ERR1",
        "submitted_ftp": "ftp.sra.ebi.ac.uk/a;ftp.sra.ebi.ac.uk/b",
        "submitted_md5": "900150983cd24fb0d6963f7d28e17f72;d41d8cd98f00b204e9800998ecf8427e",
        "submitted_bytes": "3;4",
    }
    row[case["field"]] = case["value"]
    with pytest.raises(InventoryError, match=case["expected_error"]):
        explode_representation(row, "submitted")


def test_absent_representation_is_not_malformed() -> None:
    assert explode_representation({"run_accession": "ERR1"}, "submitted") == []


@pytest.mark.parametrize(
    "case", fixture_rows("representation-cases.tsv"), ids=lambda row: row["case"]
)
def test_persisted_representation_shapes(case: dict[str, str]) -> None:
    observed = []
    for representation in ("submitted", "fastq", "sra"):
        count = len(explode_representation(case, representation))
        if count:
            observed.append(f"{representation}:{count}")
    assert ",".join(sorted(observed)) == ",".join(sorted(case["expected"].split(",")))
