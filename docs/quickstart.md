# From an ENA Accession to a Durable Archive

Publications may cite a BioProject such as `PRJEB...`, `PRJNA...`, or `PRJDB...`, or an ENA/INSDC
Study such as `ERP...`, `SRP...`, or `DRP...`. A PRJ accession is the canonical cross-repository
project identity. ERP, SRP, and DRP identify the corresponding Study namespace. The archiver keeps
the accession you supplied, the canonical project, and the Study identity separately, so beginning
with either alias does not erase provenance. Version 0.1.0 deliberately rejects a project report
containing multiple Studies; archive each Study explicitly instead of silently collapsing them.

## Choose a location and install

Make repository provenance visible in the directory layout. A useful location is
`BIOPROJECTS/PRJEB123456/sources/ena`; a sibling `sources/ncbi-sra` can then remain an independent
acquisition. The value of `--outdir` is exactly the ENA archive root.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .

ACCESSION=PRJEB123456
OUTDIR=/path/to/BIOPROJECTS/PRJEB123456/sources/ena
```

Python 3.9 or newer and `curl` are required. On macOS, verify that an external volume is mounted at
the intended path under `/Volumes`; the program refuses a misspelled unmounted volume.

## Snapshot before transferring sequence data

```bash
ena-project snapshot "$ACCESSION" --outdir "$OUTDIR"
ena-project validate "$OUTDIR" --metadata-only
```

The snapshot preserves the Portal file report and available Browser XML under `metadata/raw`.
Derived files under `metadata/derived` are deterministic interpretations. Inspect `project.json`
for identity and provenance, `samples.tsv`, `experiments.tsv`, and `runs.tsv` for the biological
model, and `sample_attributes.tsv` for arbitrary long-form sample fields. Metadata-only validation
checks schemas, the artifact ledger, unique accessions, relationships, inventory identities,
record counts, and manifest policy without expecting sequence objects to exist.

`files.tsv` and `manifest.tsv` answer different questions. The inventory records every supported
physical object ENA advertised. The manifest records the objects selected by one policy. Under the
default `archival` policy each Run prefers all original submitted files, then SRA only if submitted
files are absent, then ENA-generated FASTQ. Generated FASTQ is standardized by ENA and is not
necessarily the object originally submitted by the researcher. Submitted objects may instead be
FASTQ, BAM, CRAM, FAST5, or another accepted format.

## Measure and acquire

```bash
ena-project download "$ACCESSION" --outdir "$OUTDIR" --dry-run
```

The dry run reports representation decisions per Run separately from physical-file counts,
fallback Run reasons, exact and IEC byte totals, free space, and a warning if the remaining bytes
exceed current capacity. Keep additional space for `.part` files, filesystem overhead, later
refreshes, and superseded objects.

Start with conservative concurrency:

```bash
ena-project download "$ACCESSION" --outdir "$OUTDIR" \
  --jobs 2 --batch-attempts 3
```

`--batch-attempts` controls passes over files that still fail. By contrast, `snapshot --attempts`
controls ENA HTTP request attempts; accession-driven download exposes those as
`--metadata-attempts`. The old download spelling `--attempts` is a deprecated alias for one
release.

Each transfer goes to `<filename>.part`, resumes through curl, verifies ENA byte count and MD5,
then moves atomically to its final path. Watch `logs/download.log` for progress. Persistent failures
are listed in `logs/failed_accessions.txt`, and the command exits nonzero without discarding files
that completed successfully. After an interruption, rerun the same command. Verified final files
are skipped and safe partials resume.

## Validate the completed archive

```bash
ena-project validate "$OUTDIR"
```

Plain `validate` is intentionally stricter than `--metadata-only`: when a manifest exists it
requires every selected sequence object and verifies size plus MD5. A pre-download full validation
therefore fails by design. SHA-256 in `snapshot.json` protects local metadata artifacts; ENA MD5
identifies the repository sequence objects.

## Change policy without contacting ENA

An existing matching snapshot can generate another policy entirely offline:

```bash
ena-project download "$ACCESSION" --outdir "$OUTDIR" \
  --representation fastq --dry-run
```

The command rebuilds `manifest.tsv` from `files.tsv` and `runs.tsv` when the requested policy differs.
Explicit `fastq`, `submitted`, and `sra` policies do not fall back. `all` selects every complete
available representation and can consume substantially more storage. The lower-level equivalent is:

```bash
ena-project manifest "$OUTDIR/metadata/derived/files.tsv" \
  --representation archival --output "$OUTDIR/manifest.tsv"
```

## Refresh without erasing history

```bash
ena-project snapshot "$ACCESSION" --outdir "$OUTDIR" --refresh
ena-project validate "$OUTDIR" --metadata-only
```

Refresh retrieves and validates a staged snapshot before promotion. The previous snapshot and its
manifest move together under `metadata/archive/<snapshot-id>`. A metadata-only refresh archives the
old manifest and leaves no stale current manifest. Downloaded sequence files are not deleted.

If a new manifest advertises different bytes at an existing path, a local file matching an archived
manifest is a valid repository revision, not corruption. It moves to
`superseded/<snapshot-id>/<original-path>` before the new object is acquired. Unrecognized invalid
files are quarantined as `.bad.<timestamp>`.

## Rebuild and recover

Derived metadata can be regenerated from preserved raw evidence without network access:

```bash
ena-project metadata-normalize --metadata-dir "$OUTDIR/metadata"
```

If metadata acquisition reports a malformed ENA field array, conflicting accession, unexpected
file-report schema, or multiple Studies, inspect the preserved raw report and do not force a
fallback. If a matching snapshot is structurally damaged, restore it from its archived copy or run
an explicit refresh after preserving diagnostic evidence. If an orphan `manifest.tsv` exists with
no snapshot, resolve its provenance manually; acquisition refuses to guess and will not delete it.

This separation of raw evidence, normalized inventory, policy decision, immutable manifest, and
verified bytes is what makes the archive reproducible rather than merely downloaded.
