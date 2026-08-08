from dataclasses import replace
from pathlib import Path

from test_snapshot import FakeClient, fixed_now

from ena_project.cli import build_parser, main
from ena_project.manifest import read_manifest
from ena_project.metadata.snapshot import create_snapshot
from ena_project.validation import validate_archive, validate_metadata


def test_cli_exposes_all_contract_commands() -> None:
    parser = build_parser()
    for command in (
        "metadata",
        "snapshot",
        "manifest",
        "download",
        "validate",
        "metadata-normalize",
    ):
        try:
            parser.parse_args([command, "--help"])
        except SystemExit as exc:
            assert exc.code == 0


def test_archive_validation_checks_metadata_manifest_and_downloads(tmp_path: Path) -> None:
    create_snapshot("PRJEB1", tmp_path, client=FakeClient(), policy="archival", now=fixed_now)
    entries = read_manifest(tmp_path / "manifest.tsv")
    contents = {"original_R1.fastq.gz": b"abc", "original_R2.fastq.gz": b"abcd"}
    for entry in entries:
        destination = tmp_path / entry.local_relpath
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(contents[entry.file_name])
    assert validate_archive(tmp_path) == []
    entries[0] and (tmp_path / entries[0].local_relpath).write_bytes(b"bad")
    errors = validate_archive(tmp_path)
    assert any("failed size or MD5" in error for error in errors)


def test_cli_manifest_and_dry_run_are_offline(tmp_path: Path, capsys) -> None:
    create_snapshot("PRJEB1", tmp_path, client=FakeClient(), now=fixed_now)
    files = tmp_path / "metadata/derived/files.tsv"
    assert main(["manifest", str(files), "--output", str(tmp_path / "manifest.tsv")]) == 0
    assert (
        main(["download", str(tmp_path / "manifest.tsv"), "--outdir", str(tmp_path), "--dry-run"])
        == 0
    )
    output = capsys.readouterr().out
    assert "Selected files: 2" in output
    assert "  2 submitted" in output
    assert "Selected bytes: 7 (7 B)" in output


def test_download_retry_aliases_share_one_value() -> None:
    parser = build_parser()
    modern = parser.parse_args(
        ["download", "PRJEB1", "--outdir", "/tmp/archive", "--batch-attempts", "5"]
    )
    legacy = parser.parse_args(
        ["download", "PRJEB1", "--outdir", "/tmp/archive", "--attempts", "4"]
    )
    assert modern.batch_attempts == 5
    assert legacy.batch_attempts == 4


def test_dry_run_counts_fallback_per_run_not_file(tmp_path: Path, capsys) -> None:
    create_snapshot("PRJEB1", tmp_path, client=FakeClient(), policy="fastq", now=fixed_now)
    entries = read_manifest(tmp_path / "manifest.tsv")
    fallback_entries = [
        replace(entry, selection_reason="submitted_and_sra_not_available_from_ena")
        for entry in entries
    ]
    from ena_project.manifest import write_manifest

    write_manifest(fallback_entries, tmp_path / "manifest.tsv")
    assert (
        main(["download", str(tmp_path / "manifest.tsv"), "--outdir", str(tmp_path), "--dry-run"])
        == 0
    )
    output = capsys.readouterr().out
    assert "  1 submitted_and_sra_not_available_from_ena" in output


def test_cli_semantic_exit_statuses(tmp_path: Path) -> None:
    assert (
        main(["manifest", str(tmp_path / "missing.tsv"), "--output", str(tmp_path / "out.tsv")])
        == 2
    )
    assert main(["validate", str(tmp_path)]) == 5


def test_accession_download_rejects_another_projects_snapshot(tmp_path: Path) -> None:
    create_snapshot("PRJEB1", tmp_path, client=FakeClient(), policy="archival", now=fixed_now)
    assert main(["download", "PRJEB999", "--outdir", str(tmp_path), "--dry-run"]) == 2


def test_accession_download_rebuilds_requested_policy_offline(tmp_path: Path, capsys) -> None:
    create_snapshot("PRJEB1", tmp_path, client=FakeClient(), policy="archival", now=fixed_now)
    assert (
        main(
            [
                "download",
                "ERP000001",
                "--outdir",
                str(tmp_path),
                "--representation",
                "fastq",
                "--dry-run",
            ]
        )
        == 0
    )
    assert {entry.selection_policy for entry in read_manifest(tmp_path / "manifest.tsv")} == {
        "fastq"
    }
    assert "Selected files: 3" in capsys.readouterr().out


def test_metadata_only_snapshot_generates_manifest_offline_for_alias(
    tmp_path: Path,
) -> None:
    create_snapshot("PRJEB1", tmp_path, client=FakeClient(), now=fixed_now)
    assert not (tmp_path / "manifest.tsv").exists()
    assert main(["download", "ERP000001", "--outdir", str(tmp_path), "--dry-run"]) == 0
    assert (tmp_path / "manifest.tsv").is_file()


def test_metadata_only_validation_precedes_download(tmp_path: Path) -> None:
    create_snapshot("PRJEB1", tmp_path, client=FakeClient(), policy="archival", now=fixed_now)
    assert main(["validate", str(tmp_path), "--metadata-only"]) == 0
    assert main(["validate", str(tmp_path)]) == 5


def test_metadata_validation_rejects_duplicate_inventory_file_identity(tmp_path: Path) -> None:
    create_snapshot("PRJEB1", tmp_path, client=FakeClient(), now=fixed_now)
    files_path = tmp_path / "metadata/derived/files.tsv"
    lines = files_path.read_text().splitlines()
    files_path.write_text("\n".join([*lines, lines[1]]) + "\n")
    errors = validate_metadata(tmp_path)
    assert any("Duplicate inventory file identity" in error for error in errors)
