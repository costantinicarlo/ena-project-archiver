# Design

## Evidence before policy

An ENA Run is not one downloadable object. The Portal API may advertise several physical files in each of three representations. `inventory.py` pairs URL, MD5, and byte arrays positionally and creates one `RemoteFile` per physical object. It does not independently sort those arrays.

`metadata/derived/files.tsv` records every valid supported object ENA advertised. `selection.py` then applies a pure per-Run policy. `manifest.tsv` records the resulting decision, including its reason and explicit destination path. The downloader obeys that path and never reconstructs it.

Under `archival`, submitted originals have highest provenance value. SRA and then generated FASTQ are fallbacks only for genuine absence. A malformed preferred representation stops selection. `all` selects every complete available representation and can be storage-expensive.

## Snapshot transaction

The Portal response and individual Browser XML responses are written under a staging root. Normalization reads those preserved bytes. Every raw and derived artifact receives a size and SHA-256 entry in `snapshot.json`. Only a coherent staged tree is promoted. During refresh, the previous metadata tree and manifest are copied into the new `metadata/archive/<snapshot-id>/` before promotion; sequence files are not deleted.

Raw evidence is never reformatted. Derived JSON uses sorted keys, and TSV files define headers, line endings, and sort orders. Identical evidence, software, and policy therefore produce identical derived bytes except for explicitly provenance-bearing timestamps.

## Data transaction

Each manifest entry maps to a run-specific path such as `submitted/ERR123/original-name.fastq.gz`. Remote basenames are untrusted: absolute paths, path components, control characters, directory escape, and unexpected hosts are rejected.

Curl transfers to `.part` with resume enabled. Size is checked before MD5; only a verified partial is atomically renamed. A mismatching final object is compared with manifests in metadata history. Historical matches move under `superseded/<snapshot-id>/`; unknown mismatches are quarantined.

Workers own independent paths. Failures are collected, bounded retry passes contain only failed entries, and a stable report remains in `logs/failed_accessions.txt`.

## Dependency decisions

The runtime uses only Python's standard library and external curl. This keeps installation modest and leaves HTTP parsing, policy, normalization, and download execution independently testable. SRA Toolkit is not required.

The ENA `returnFields` discovery endpoint is not queried on every run. The client requests an explicit versioned field list, and fixture plus live smoke tests detect upstream incompatibility. Avoiding an extra schema request reduces repeated traffic; a future release may cache and validate `returnFields` explicitly.
