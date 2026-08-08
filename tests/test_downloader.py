import os
import subprocess
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from ena_project.downloader import (
    build_history_index,
    download_batch,
    download_one,
    validate_destination,
    verify_file,
)
from ena_project.manifest import write_manifest
from ena_project.models import ManifestEntry


def entry(content: bytes = b"abc", path: str = "submitted/ERR1/data.fastq.gz") -> ManifestEntry:
    import hashlib

    return ManifestEntry(
        "1.0",
        "PRJEB1",
        "ERP1",
        path.split("/")[1],
        "ERX1",
        "ERS1",
        "",
        "WGS",
        "GENOMIC",
        "PAIRED",
        "ILLUMINA",
        "Illumina",
        path.split("/")[0],
        "archival",
        "submitted_original_preferred",
        1,
        path.split("/")[-1],
        len(content),
        hashlib.md5(content).hexdigest(),
        "https://ftp.sra.ebi.ac.uk/data",
        path,
    )


def test_download_resumes_part_and_atomically_verifies(tmp_path: Path) -> None:
    record = entry()
    part = tmp_path / f"{record.local_relpath}.part"
    part.parent.mkdir(parents=True)
    part.write_bytes(b"a")

    def fake_run(command: list[str], check: bool) -> subprocess.CompletedProcess:
        Path(command[command.index("--output") + 1]).open("ab").write(b"bc")
        return subprocess.CompletedProcess(command, 0)

    destination = download_one(record, tmp_path, "curl", run_command=fake_run)
    assert destination.read_bytes() == b"abc"
    assert verify_file(destination, record)


def test_existing_corrupt_file_is_quarantined(tmp_path: Path) -> None:
    record = entry()
    destination = tmp_path / record.local_relpath
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"bad")

    def fake_run(command: list[str], check: bool) -> subprocess.CompletedProcess:
        Path(command[command.index("--output") + 1]).write_bytes(b"abc")
        return subprocess.CompletedProcess(command, 0)

    download_one(record, tmp_path, "curl", run_command=fake_run, timestamp=lambda: 7)
    assert destination.with_name(f"{destination.name}.bad.7").read_bytes() == b"bad"


def test_existing_verified_file_is_skipped_without_transfer(tmp_path: Path) -> None:
    record = entry()
    destination = tmp_path / record.local_relpath
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"abc")

    def unexpected_run(command: list[str], check: bool) -> subprocess.CompletedProcess:
        raise AssertionError("verified file should not trigger curl")

    assert download_one(record, tmp_path, "curl", run_command=unexpected_run) == destination


def test_historical_valid_object_is_superseded_not_quarantined(tmp_path: Path) -> None:
    old = entry(b"old")
    current = entry(b"new")
    old_manifest = tmp_path / "metadata/archive/20260101T000000Z/manifest.tsv"
    write_manifest([old], old_manifest)
    destination = tmp_path / current.local_relpath
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"old")

    def fake_run(command: list[str], check: bool) -> subprocess.CompletedProcess:
        Path(command[command.index("--output") + 1]).write_bytes(b"new")
        return subprocess.CompletedProcess(command, 0)

    download_one(current, tmp_path, "curl", run_command=fake_run, timestamp=lambda: 7)
    assert (tmp_path / "superseded/20260101T000000Z" / current.local_relpath).read_bytes() == b"old"
    assert not list(destination.parent.glob("*.bad.*"))


def test_superseded_historical_object_cannot_be_overwritten(tmp_path: Path) -> None:
    old = entry(b"old")
    current = entry(b"new")
    old_manifest = tmp_path / "metadata/archive/20260101T000000Z/manifest.tsv"
    write_manifest([old], old_manifest)
    destination = tmp_path / current.local_relpath
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"old")
    occupied = tmp_path / "superseded/20260101T000000Z" / current.local_relpath
    occupied.parent.mkdir(parents=True)
    occupied.write_bytes(b"different-valid-history")

    def fake_run(command: list[str], check: bool) -> subprocess.CompletedProcess:
        Path(command[command.index("--output") + 1]).write_bytes(b"new")
        return subprocess.CompletedProcess(command, 0)

    download_one(
        current,
        tmp_path,
        "curl",
        run_command=fake_run,
        history_index=build_history_index(tmp_path),
    )
    assert occupied.read_bytes() == b"different-valid-history"
    assert (
        tmp_path / "superseded/20260101T000000Z-01" / current.local_relpath
    ).read_bytes() == b"old"


def test_batch_collects_failures_and_retries_only_failures(tmp_path: Path) -> None:
    records = [entry(path="submitted/ERR1/a"), entry(path="submitted/ERR2/b")]
    calls = Counter()

    def fake_download(record: ManifestEntry, outdir: Path, curl: str) -> Path:
        calls[record.run_accession] += 1
        if record.run_accession == "ERR2" and calls[record.run_accession] < 2:
            raise RuntimeError("transient")
        return outdir / record.local_relpath

    assert download_batch(records, tmp_path, "curl", attempts=2, download=fake_download) == []
    assert calls == Counter({"ERR2": 2, "ERR1": 1})


def test_batch_writes_stable_persistent_failure_report(tmp_path: Path) -> None:
    record = entry()

    def always_fails(record: ManifestEntry, outdir: Path, curl: str) -> Path:
        raise RuntimeError("persistent")

    assert download_batch([record], tmp_path, "curl", attempts=2, download=always_fails) == [record]
    assert (tmp_path / "logs/failed_accessions.txt").read_text() == (
        f"ERR1\t{record.local_relpath}\n"
    )


def test_macos_missing_volume_and_path_escape_are_rejected(tmp_path: Path, monkeypatch) -> None:
    with pytest.raises(FileNotFoundError, match="not mounted"):
        validate_destination(Path("/Volumes/DefinitelyMissing/project"), platform="darwin")

    volume = Path("/Volumes/ena-project-test-dir")
    original_exists = Path.exists
    original_is_dir = Path.is_dir

    def fake_exists(path: Path) -> bool:
        return path == volume or original_exists(path)

    def fake_is_dir(path: Path) -> bool:
        return path == volume or original_is_dir(path)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "is_dir", fake_is_dir)
    monkeypatch.setattr(os.path, "ismount", lambda path: False)
    monkeypatch.setattr(os, "access", lambda path, mode: False)
    with pytest.raises(FileNotFoundError, match="not a mounted volume"):
        validate_destination(Path("/Volumes/ena-project-test-dir/project"), platform="darwin")
    with pytest.raises(ValueError, match="escapes OUTDIR"):
        download_one(replace(entry(), local_relpath="../escape"), tmp_path, "curl")
