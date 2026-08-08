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
    ("field", "value", "message"),
    [
        ("submitted_md5", "900150983cd24fb0d6963f7d28e17f72", "malformed file arrays"),
        ("submitted_bytes", "3;4;5", "malformed file arrays"),
        ("submitted_md5", "not-an-md5;d41d8cd98f00b204e9800998ecf8427e", "invalid MD5"),
        ("submitted_bytes", "three;4", "invalid byte count"),
        ("submitted_ftp", "ftp.sra.ebi.ac.uk/a;;ftp.sra.ebi.ac.uk/c", "malformed file arrays"),
    ],
)
def test_malformed_advertised_representation_is_an_error(
    field: str, value: str, message: str
) -> None:
    row = {
        "run_accession": "ERR1",
        "submitted_ftp": "ftp.sra.ebi.ac.uk/a;ftp.sra.ebi.ac.uk/b",
        "submitted_md5": "900150983cd24fb0d6963f7d28e17f72;d41d8cd98f00b204e9800998ecf8427e",
        "submitted_bytes": "3;4",
    }
    row[field] = value
    with pytest.raises(InventoryError, match=message):
        explode_representation(row, "submitted")


def test_absent_representation_is_not_malformed() -> None:
    assert explode_representation({"run_accession": "ERR1"}, "submitted") == []
