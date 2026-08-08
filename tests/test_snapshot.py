import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ena_project.ena_client import EnaRequestError, Response
from ena_project.metadata.normalize import normalize as real_normalize
from ena_project.metadata.snapshot import create_snapshot, normalize_existing

FIXTURES = Path(__file__).parent / "fixtures"


class FakeClient:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def fetch_filereport(self, accession: str) -> Response:
        if self.fail:
            raise EnaRequestError("offline")
        return Response(
            "https://example.test/report", (FIXTURES / "filereport.tsv").read_bytes(), 200
        )

    def fetch_xml(self, accession: str) -> Response:
        return Response(
            f"https://example.test/{accession}", (FIXTURES / "sample.xml").read_bytes(), 200
        )


def fixed_now() -> datetime:
    return datetime(2026, 8, 8, 16, 27, tzinfo=timezone.utc)


def test_snapshot_preserves_raw_normalizes_and_builds_manifest(tmp_path: Path) -> None:
    snapshot_path, partial = create_snapshot(
        "ERP000001", tmp_path, client=FakeClient(), policy="archival", now=fixed_now
    )
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert not partial
    assert snapshot["project_accession"] == "PRJEB1"
    assert snapshot["study_accession"] == "ERP000001"
    assert snapshot["record_counts"]["files"] == 6
    assert snapshot["schema_version"] == "1.1"
    assert snapshot["application"] == "ENA Project Archiver"
    assert snapshot["application_version"]
    assert snapshot["python_version"]
    assert snapshot["platform"]
    assert (tmp_path / "metadata/raw/portal/filereport.tsv").read_bytes() == (
        FIXTURES / "filereport.tsv"
    ).read_bytes()
    assert (
        "isolation source\tsoil"
        in (tmp_path / "metadata/derived/sample_attributes.tsv").read_text()
    )
    assert (tmp_path / "manifest.tsv").is_file()


def test_snapshot_refuses_overwrite_and_refresh_archives_previous(tmp_path: Path) -> None:
    create_snapshot("PRJEB1", tmp_path, client=FakeClient(), now=fixed_now)
    with pytest.raises(FileExistsError, match="--refresh"):
        create_snapshot("PRJEB1", tmp_path, client=FakeClient(), now=fixed_now)

    def later() -> datetime:
        return datetime(2026, 8, 9, 1, 2, 3, tzinfo=timezone.utc)

    create_snapshot("PRJEB1", tmp_path, client=FakeClient(), refresh=True, now=later)
    assert (tmp_path / "metadata/archive/20260808T162700.000000Z/snapshot.json").is_file()


def test_failed_refresh_leaves_current_snapshot_unchanged(tmp_path: Path) -> None:
    path, _ = create_snapshot("PRJEB1", tmp_path, client=FakeClient(), now=fixed_now)
    before = path.read_bytes()
    with pytest.raises(EnaRequestError):
        create_snapshot(
            "PRJEB1",
            tmp_path,
            client=FakeClient(fail=True),
            refresh=True,
            now=lambda: datetime(2026, 8, 9, tzinfo=timezone.utc),
        )
    assert path.read_bytes() == before


def test_offline_normalization_is_deterministic(tmp_path: Path) -> None:
    create_snapshot("PRJEB1", tmp_path, client=FakeClient(), now=fixed_now)
    derived = tmp_path / "metadata/derived"
    before = {path.name: path.read_bytes() for path in derived.iterdir()}
    normalize_existing(tmp_path / "metadata")
    assert before == {path.name: path.read_bytes() for path in derived.iterdir()}


def test_two_snapshots_in_same_second_receive_distinct_ids(tmp_path: Path) -> None:
    first_path, _ = create_snapshot("PRJEB1", tmp_path, client=FakeClient(), now=fixed_now)
    first_id = json.loads(first_path.read_text())["snapshot_id"]
    second_path, _ = create_snapshot(
        "PRJEB1", tmp_path, client=FakeClient(), refresh=True, now=fixed_now
    )
    second_id = json.loads(second_path.read_text())["snapshot_id"]
    assert first_id != second_id
    assert (tmp_path / "metadata/archive" / first_id / "snapshot.json").is_file()


def test_orphan_manifest_is_not_deleted_by_metadata_acquisition(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.tsv"
    manifest.write_text("untrusted orphan\n")
    before = manifest.read_bytes()
    with pytest.raises(FileExistsError, match="Orphan manifest"):
        create_snapshot("PRJEB1", tmp_path, client=FakeClient(), now=fixed_now)
    assert manifest.read_bytes() == before


def test_inconsistent_staged_refresh_cannot_replace_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot_path, _ = create_snapshot(
        "PRJEB1", tmp_path, client=FakeClient(), policy="archival", now=fixed_now
    )
    before_snapshot = snapshot_path.read_bytes()
    before_manifest = (tmp_path / "manifest.tsv").read_bytes()

    def corrupt_normalize(*args, **kwargs):
        result = real_normalize(*args, **kwargs)
        runs_path = args[0] / "derived" / "runs.tsv"
        with runs_path.open("a", encoding="utf-8") as handle:
            handle.write(runs_path.read_text(encoding="utf-8").splitlines()[1] + "\n")
        return result

    monkeypatch.setattr("ena_project.metadata.snapshot.normalize", corrupt_normalize)
    with pytest.raises(ValueError, match="Staged metadata validation failed"):
        create_snapshot("PRJEB1", tmp_path, client=FakeClient(), refresh=True, now=fixed_now)
    assert snapshot_path.read_bytes() == before_snapshot
    assert (tmp_path / "manifest.tsv").read_bytes() == before_manifest


def test_metadata_only_refresh_archives_and_removes_stale_manifest(tmp_path: Path) -> None:
    snapshot_path, _ = create_snapshot(
        "PRJEB1", tmp_path, client=FakeClient(), policy="archival", now=fixed_now
    )
    previous_id = json.loads(snapshot_path.read_text())["snapshot_id"]
    previous_manifest = (tmp_path / "manifest.tsv").read_bytes()
    create_snapshot("PRJEB1", tmp_path, client=FakeClient(), refresh=True, now=fixed_now)
    assert not (tmp_path / "manifest.tsv").exists()
    assert (
        tmp_path / "metadata" / "archive" / previous_id / "manifest.tsv"
    ).read_bytes() == previous_manifest


class FileReportClient(FakeClient):
    def __init__(self, content: bytes) -> None:
        super().__init__()
        self.content = content

    def fetch_filereport(self, accession: str) -> Response:
        return Response("https://example.test/report", self.content, 200)


def _duplicate_fixture(**updates: str) -> bytes:
    lines = (FIXTURES / "filereport.tsv").read_text().splitlines()
    header = lines[0].split("\t")
    second = lines[1].split("\t")
    for field, value in updates.items():
        second[header.index(field)] = value
    return ("\n".join([lines[0], lines[1], "\t".join(second)]) + "\n").encode()


def test_multi_study_project_is_rejected(tmp_path: Path) -> None:
    client = FileReportClient(_duplicate_fixture(secondary_study_accession="ERP000002"))
    with pytest.raises(ValueError, match="multiple ENA Studies"):
        create_snapshot("PRJEB1", tmp_path, client=client, now=fixed_now)


def test_returned_identity_must_match_requested_accession(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not match requested"):
        create_snapshot("PRJEB999", tmp_path, client=FakeClient(), now=fixed_now)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unknown", "no-run"])
def test_filereport_header_must_match_requested_schema(tmp_path: Path, mutation: str) -> None:
    lines = (FIXTURES / "filereport.tsv").read_text().splitlines()
    header = lines[0].split("\t")
    row = lines[1].split("\t")
    if mutation == "missing":
        index = header.index("sample_title")
        header.pop(index)
        row.pop(index)
    elif mutation == "duplicate":
        header[1] = header[0]
    elif mutation == "unknown":
        header[1] = "replacement_field"
    else:
        index = header.index("run_accession")
        header.pop(index)
        row.pop(index)
    content = ("\t".join(header) + "\n" + "\t".join(row) + "\n").encode()
    with pytest.raises(EnaRequestError, match="file report"):
        create_snapshot("PRJEB1", tmp_path, client=FileReportClient(content), now=fixed_now)


def test_snapshot_invocation_redacts_sensitive_values(tmp_path: Path) -> None:
    snapshot_path, _ = create_snapshot(
        "PRJEB1",
        tmp_path,
        client=FakeClient(),
        now=fixed_now,
        invocation=["ena-project", "snapshot", "PRJEB1", "--token=secret", "--password", "secret"],
    )
    command = json.loads(snapshot_path.read_text())["command"]
    assert "secret" not in " ".join(command)
    assert command[-1] == "<redacted>"


@pytest.mark.parametrize(
    ("field", "value", "kind"),
    [
        ("sample_title", "conflict", "Sample"),
        ("library_name", "conflict", "Experiment"),
        ("run_alias", "conflict", "Run"),
    ],
)
def test_conflicting_duplicate_biological_accessions_fail(
    tmp_path: Path, field: str, value: str, kind: str
) -> None:
    client = FileReportClient(_duplicate_fixture(**{field: value}))
    with pytest.raises(ValueError, match=f"Conflicting {kind} metadata"):
        create_snapshot("PRJEB1", tmp_path, client=client, now=fixed_now)
