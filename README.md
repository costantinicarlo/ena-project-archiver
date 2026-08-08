# ENA Project Archiver

`ena-project` creates reproducible, provenance-preserving local archives of public raw-read
projects from the European Nucleotide Archive (ENA). It accepts `PRJEB`, `PRJNA`, `PRJDB`, `ERP`,
`SRP`, and `DRP` project or Study accessions and keeps ENA acquisition separate from NCBI
provenance.

The archive records a chain of evidence:

```text
raw ENA responses -> complete file inventory -> selection policy -> manifest -> verified files
```

ENA can expose original submitted objects, archive-generated FASTQ, and SRA representations for
the same Run. Submitted data can be FASTQ, BAM, CRAM, FAST5, or another accepted format. The
default `archival` policy therefore chooses every submitted file for a Run, falls back to SRA only
when submitted files are genuinely unavailable, then falls back to generated FASTQ. Advertised
but malformed submitted metadata is an error, never a reason to fall back.

## Installation

Python 3.9 or newer and `curl` are required.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
ena-project --help
```

For development:

```bash
python -m pip install -e '.[dev]'
python -m pytest
ruff check src tests
```

## Typical workflow

```bash
OUTDIR=/path/to/PRJEB123456/sources/ena

ena-project snapshot PRJEB123456 --outdir "$OUTDIR"
ena-project validate "$OUTDIR"
ena-project download "$OUTDIR/manifest.tsv" --outdir "$OUTDIR" --dry-run
ena-project download "$OUTDIR/manifest.tsv" --outdir "$OUTDIR" --jobs 2
ena-project validate "$OUTDIR"
```

Use `metadata` instead of `snapshot` to preserve and normalize metadata without making a manifest.
Use `manifest` to select a different representation entirely offline:

```bash
ena-project manifest "$OUTDIR/metadata/derived/files.tsv" \
  --representation fastq --output /path/to/fastq-manifest.tsv
```

`files.tsv` is ENA's complete reported inventory. `manifest.tsv` is a policy decision derived from
that inventory. Changing policy never changes the inventory.

## Integrity and recovery

Sequence objects are written to `<filename>.part`, resumed by curl, checked against the ENA byte
count and MD5, and atomically renamed. MD5 identifies the exact repository object advertised by
ENA. Snapshot artifacts additionally use SHA-256 to protect the local provenance ledger.

Existing verified files are skipped. Unrecognized corrupt files become `.bad.<timestamp>`. If an
existing file matches a previous manifest but ENA now advertises a new checksum at the same path,
the old valid object moves to `superseded/<snapshot-id>/` before reacquisition.

`--refresh` stages a complete replacement and archives the previous metadata plus its manifest
under `metadata/archive/<snapshot-id>/`. A failed refresh leaves the current snapshot untouched.

## Commands

```text
ena-project metadata ACCESSION --outdir PATH
ena-project snapshot ACCESSION --outdir PATH [--representation POLICY]
ena-project manifest FILES.TSV --output MANIFEST.TSV [--representation POLICY]
ena-project download ACCESSION|MANIFEST.TSV --outdir PATH [--dry-run]
ena-project validate PATH
ena-project metadata-normalize --metadata-dir PATH/metadata
```

Policies are `archival`, `submitted`, `fastq`, `sra`, and `all`. Exit statuses are `0` success,
`1` runtime failure, `2` invalid input/configuration, `3` required retrieval or download incomplete,
`4` usable partial metadata, `5` normalization/validation failure, and `130` interruption.

See [docs/design.md](docs/design.md), [docs/tutorial.md](docs/tutorial.md), and
[docs/troubleshooting.md](docs/troubleshooting.md). Contract coverage is recorded in
[docs/compliance-matrix.md](docs/compliance-matrix.md).

## License

MIT. ENA metadata and downloaded scientific records retain their own provenance and terms.
See [LICENSE](LICENSE) for the full text.
