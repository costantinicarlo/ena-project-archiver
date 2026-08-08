"""Recognition of supported ENA project and Study accessions."""

from __future__ import annotations

import re
from dataclasses import dataclass

PROJECT_PATTERN = re.compile(r"^PRJ(?:EB|NA|DB)\d+$", re.ASCII)
STUDY_PATTERN = re.compile(r"^(?:ERP|SRP|DRP)\d+$", re.ASCII)


class AccessionError(ValueError):
    """Raised when an accession is not a supported project identifier."""


@dataclass(frozen=True)
class Accession:
    value: str
    kind: str


def parse_accession(value: str) -> Accession:
    normalized = value.strip().upper()
    if PROJECT_PATTERN.fullmatch(normalized):
        return Accession(normalized, "project")
    if STUDY_PATTERN.fullmatch(normalized):
        return Accession(normalized, "study")
    raise AccessionError(
        f"Unsupported accession {value!r}; expected PRJEB/PRJNA/PRJDB or ERP/SRP/DRP"
    )
