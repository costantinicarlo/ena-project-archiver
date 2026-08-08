"""Reusable validation for untrusted repository paths and URLs."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from urllib.parse import urlparse

ENA_DOWNLOAD_HOSTS = frozenset({"ftp.sra.ebi.ac.uk"})
RUN_ACCESSION_PATTERN = re.compile(r"^[ESD]RR\d+$", re.ASCII)


def validate_run_accession(value: str) -> str:
    if not RUN_ACCESSION_PATTERN.fullmatch(value):
        raise ValueError(f"Unsafe or invalid Run accession: {value!r}")
    return value


def validate_file_name(value: str) -> str:
    name = PurePosixPath(value)
    if (
        name.is_absolute()
        or len(name.parts) != 1
        or name.name in {"", ".", ".."}
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"Unsafe remote filename: {value!r}")
    return value


def validate_ena_download_url(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ENA_DOWNLOAD_HOSTS
        or not parsed.path.startswith("/")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"Untrusted or unsupported ENA download URL: {value!r}")
    return value


def canonical_local_relpath(representation: str, run_accession: str, file_name: str) -> str:
    validate_run_accession(run_accession)
    validate_file_name(file_name)
    return f"{representation}/{run_accession}/{file_name}"
