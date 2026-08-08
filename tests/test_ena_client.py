import os
from urllib.error import URLError

import pytest

from ena_project.ena_client import FILEREPORT_FIELDS, EnaClient, EnaRequestError


class HttpResponse:
    status = 200

    def __init__(self, content: bytes) -> None:
        self.content = content

    def read(self) -> bytes:
        return self.content

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None


def test_client_identifies_itself_requests_explicit_fields_and_retries() -> None:
    requests = []
    sleeps = []

    def opener(request, timeout: int):
        requests.append((request, timeout))
        if len(requests) == 1:
            raise URLError("temporary")
        return HttpResponse(b"run_accession\nERR1\n")

    client = EnaClient(timeout=12, attempts=2, opener=opener, sleeper=sleeps.append)
    response = client.fetch_filereport("PRJEB1")
    assert response.status == 200
    assert requests[0][1] == 12
    assert "fields=" in requests[0][0].full_url
    assert requests[0][0].get_header("User-agent").startswith("ena-project/")
    assert sleeps == [1.0]


def test_empty_public_result_is_distinct_from_request_failure() -> None:
    client = EnaClient(opener=lambda request, timeout: HttpResponse(b""))
    with pytest.raises(EnaRequestError, match="no public read_run records"):
        client.fetch_filereport("PRJEB999999999")


@pytest.mark.skipif(
    os.environ.get("ENA_LIVE_SCHEMA_TEST") != "1",
    reason="set ENA_LIVE_SCHEMA_TEST=1 to query ENA returnFields",
)
def test_live_required_filereport_fields_are_still_supported() -> None:
    response = EnaClient(timeout=30, attempts=2).fetch_return_fields()
    rows = response.content.decode("utf-8-sig").splitlines()
    available = {row.split("\t", 1)[0] for row in rows[1:] if row}
    assert set(FILEREPORT_FIELDS) <= available
