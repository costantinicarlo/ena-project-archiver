import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ena_project.ena_client import EnaRequestError, Response
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
    assert snapshot["record_counts"]["files"] == 5
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
    assert (tmp_path / "metadata/archive/20260808T162700Z/snapshot.json").is_file()


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
