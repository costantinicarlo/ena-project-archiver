"""Bounded, identifying HTTP client for ENA APIs."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import __version__

PORTAL_URL = "https://www.ebi.ac.uk/ena/portal/api/filereport"
RETURN_FIELDS_URL = "https://www.ebi.ac.uk/ena/portal/api/returnFields"
BROWSER_URL = "https://www.ebi.ac.uk/ena/browser/api/xml"
FILEREPORT_FIELDS = (
    "study_accession",
    "secondary_study_accession",
    "study_alias",
    "study_title",
    "sample_accession",
    "secondary_sample_accession",
    "sample_alias",
    "sample_title",
    "tax_id",
    "scientific_name",
    "collection_date",
    "country",
    "location",
    "experiment_accession",
    "experiment_alias",
    "library_name",
    "library_strategy",
    "library_source",
    "library_selection",
    "library_layout",
    "instrument_platform",
    "instrument_model",
    "run_accession",
    "run_alias",
    "base_count",
    "read_count",
    "first_public",
    "last_updated",
    "submitted_ftp",
    "submitted_md5",
    "submitted_bytes",
    "fastq_ftp",
    "fastq_md5",
    "fastq_bytes",
    "sra_ftp",
    "sra_md5",
    "sra_bytes",
)


class EnaRequestError(RuntimeError):
    """Raised after a required ENA request exhausts retries."""


@dataclass(frozen=True)
class Response:
    url: str
    content: bytes
    status: int


class EnaClient:
    def __init__(
        self,
        timeout: int = 60,
        attempts: int = 4,
        opener: Callable[..., object] = urlopen,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if timeout <= 0 or attempts <= 0:
            raise ValueError("timeout and attempts must be positive")
        self.timeout = timeout
        self.attempts = attempts
        self.opener = opener
        self.sleeper = sleeper

    def _get(self, url: str) -> Response:
        request = Request(url, headers={"User-Agent": f"ena-project/{__version__}"})
        last_error: Exception | None = None
        for attempt in range(1, self.attempts + 1):
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    return Response(url, response.read(), int(response.status))
            except HTTPError as exc:
                last_error = exc
                if exc.code < 500 and exc.code != 429:
                    break
            except (URLError, TimeoutError) as exc:
                last_error = exc
            if attempt < self.attempts:
                self.sleeper(min(8.0, float(2 ** (attempt - 1))))
        raise EnaRequestError(f"ENA request failed: {url}: {last_error}")

    def fetch_filereport(self, accession: str) -> Response:
        query = urlencode(
            {
                "accession": accession,
                "result": "read_run",
                "fields": ",".join(FILEREPORT_FIELDS),
                "format": "tsv",
                "download": "true",
            }
        )
        response = self._get(f"{PORTAL_URL}?{query}")
        if not response.content.strip():
            raise EnaRequestError(f"ENA returned no public read_run records for {accession}")
        return response

    def fetch_xml(self, accession: str) -> Response:
        return self._get(f"{BROWSER_URL}/{accession}")

    def fetch_return_fields(self) -> Response:
        return self._get(f"{RETURN_FIELDS_URL}?{urlencode({'result': 'read_run'})}")
