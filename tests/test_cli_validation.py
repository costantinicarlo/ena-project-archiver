from pathlib import Path

from test_snapshot import FakeClient, fixed_now

from ena_project.cli import build_parser, main
from ena_project.manifest import read_manifest
from ena_project.metadata.snapshot import create_snapshot
from ena_project.validation import validate_archive


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
    assert "submitted files selected: 2" in output


def test_cli_semantic_exit_statuses(tmp_path: Path) -> None:
    assert (
        main(["manifest", str(tmp_path / "missing.tsv"), "--output", str(tmp_path / "out.tsv")])
        == 2
    )
    assert main(["validate", str(tmp_path)]) == 5
