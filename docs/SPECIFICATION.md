---
modified: 2026-08-08 16:44:16 +00:00
---
> [!note] 
> ok, turn this into a **formal design/specification contract**

Below is the specification I would use as the authoritative implementation contract for the first ENA application. I have deliberately separated **normative requirements** from later extensions so that an implementation agent has relatively little freedom to reinterpret the archival philosophy.

# ENA Project Archiver

## Formal Design and Implementation Specification

**Status:** Proposed specification for v0.1  
**Working application name:** `ena-project`  
**Repository working name:** `ena-project-archiver`  
**Primary purpose:** Reproducible archival acquisition of raw sequencing data and associated metadata from the European Nucleotide Archive (ENA)

---

## 1. Purpose

`ena-project` SHALL provide a reproducible, provenance-preserving mechanism for acquiring public raw sequencing datasets from the European Nucleotide Archive.

The fundamental archival unit SHALL normally be an INSDC BioProject/ENA Study and its associated Samples, Experiments, Runs and raw read files.

The conceptual workflow is:

```text
ENA project or study accession
        ↓
canonical accession resolution
        ↓
immutable metadata snapshot
        ↓
normalized Study–Sample–Experiment–Run model
        ↓
complete ENA remote-file inventory
        ↓
explicit representation-selection policy
        ↓
immutable acquisition manifest
        ↓
resumable file download
        ↓
size + MD5 verification
        ↓
validated local archive
```

The application is intended to be the ENA counterpart of `ncbi-sra-bioproject-downloader`, while reflecting ENA's different file-distribution model rather than mechanically reproducing NCBI-specific assumptions.

The implementation SHALL prioritize:

1. provenance;
    
2. reproducibility;
    
3. preservation of repository evidence;
    
4. explicit acquisition policy;
    
5. safe recovery from interruption or corruption;
    
6. long-term intelligibility of the resulting archive;
    
7. portability between macOS and Linux.
    

Convenience for immediate downstream analysis is important but SHALL NOT override archival provenance.

---

# 2. Normative terminology

The terms **MUST**, **MUST NOT**, **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are normative.

A requirement using MUST/SHALL is part of the v0.1 acceptance contract.

A SHOULD requirement may be departed from only for a documented technical reason.

A MAY requirement is optional.

---

# 3. Scientific and archival model

ENA commonly exposes several possible representations of a raw-read Run:

- the files originally submitted to ENA;
    
- ENA-generated standardized FASTQ;
    
- an SRA-format representation suitable for the SRA Toolkit.
    

Submitted files may themselves be FASTQ, BAM, CRAM, FAST5, HDF5 or other accepted formats. ENA-generated FASTQ is therefore an analysis-friendly standardized representation, not necessarily the original deposited object. Submitted files may also be unavailable when the run originated at another INSDC partner, and ENA-generated FASTQ cannot be produced for every native data type. ([ENA Documentation](https://ena-docs.readthedocs.io/en/latest/faq/archive-generated-files.html?utm_source=chatgpt.com "Archive Generated Run Files — ENA Documentation 1 documentation"))

Consequently, the application MUST distinguish:

```text
repository inventory
        ≠
archival selection
        ≠
local analysis format
```

The application SHALL NOT assume that FASTQ is the sole or universally preferred representation of a Run.

---

# 4. Scope of v0.1

## 4.1 Included

Version 0.1 SHALL archive ENA **raw-read datasets** associated with an ENA Study/BioProject.

It SHALL understand the following ENA/INSDC object hierarchy:

```text
Study / BioProject
    │
    ├── Sample / BioSample
    │
    └── Experiment
            │
            └── Run
                    │
                    ├── submitted files
                    ├── ENA-generated FASTQ
                    └── SRA representation
```

The implementation SHALL support public:

```text
PRJ*
ERP*
SRP*
DRP*
```

project/study identifiers as user-facing project inputs.

The underlying ENA client MAY understand Sample, Experiment and Run accession families where useful internally.

## 4.2 Explicitly excluded from v0.1

The application SHALL NOT recursively acquire:

- genome assemblies;
    
- transcriptome assemblies;
    
- annotated nucleotide sequences;
    
- VCF or other analysis products;
    
- metagenome analysis objects;
    
- publications;
    
- linked external database resources;
    
- controlled-access sequencing datasets.
    

Such relationships MAY be preserved in metadata when returned by ENA, but SHALL NOT trigger recursive downloads.

Support for ENA Analysis objects and other ENA sequence classes is reserved for later releases.

---

# 5. Relationship with the existing NCBI archiver

The new application SHALL be a **separate software repository**.

It SHALL NOT be implemented as an ENA mode inside `ncbi-sra-bioproject-downloader`.

The two applications SHOULD nevertheless share recognizable design semantics:

```text
remote repository
    ↓
raw metadata evidence
    ↓
normalized metadata
    ↓
durable manifest
    ↓
verified download
    ↓
validated archive
```

The current NCBI implementation already treats raw responses as immutable evidence, normalized files as reproducible interpretations, the manifest as the durable download contract, and downloads as verified transactions rather than filename-based operations. Those principles SHALL be retained.

Generic duplicated logic MAY initially exist in both repositories.

A common library SHALL NOT be extracted before working implementations demonstrate which abstractions are genuinely repository-independent.

---

# 6. Canonical archive identity

## 6.1 BioProject accession

Where ENA exposes an INSDC BioProject accession such as:

```text
PRJEB12345
PRJNA12345
PRJDB12345
```

that accession SHALL be considered the canonical project identity.

The associated ENA secondary Study accession SHALL also be retained, for example:

```text
PRJEB12345
ERP012345
```

Both identifiers SHALL occur in normalized metadata.

## 6.2 Input accession resolution

When the user supplies an ENA Study accession such as:

```text
ERP012345
SRP012345
DRP012345
```

the application SHALL resolve the associated canonical `PRJ*` accession when ENA provides one.

The user-supplied accession SHALL always be preserved separately as:

```text
input_accession
```

The resolved primary identifier SHALL be stored as:

```text
project_accession
```

The ENA secondary Study identifier SHALL be stored as:

```text
study_accession
```

The implementation MUST NOT silently replace or discard aliases.

## 6.3 Resolution failure

If a valid public Study can be retrieved but ENA does not expose a corresponding `PRJ*` accession, the Study accession MAY become the archive identifier.

This condition MUST:

- be explicitly recorded in `snapshot.json`;
    
- generate a warning;
    
- never be inferred from string manipulation alone.
    

---

# 7. Recommended storage hierarchy

The long-term archive SHOULD distinguish biological project identity from repository provenance.

Recommended global layout:

```text
BIOPROJECTS/
└── PRJEB123456/
    └── sources/
        ├── ena/
        └── ncbi-sra/
```

`ena-project` SHALL treat the path passed through `--outdir` as the exact root of the ENA acquisition unit.

It SHALL NOT automatically assume that the user's global archive is named `BIOPROJECTS`.

Example:

```bash
ena-project snapshot PRJEB123456 \
    --outdir /Volumes/Bioinfo/BIOPROJECTS/PRJEB123456/sources/ena
```

The repository/source distinction is important because identically accessioned Runs obtained through different INSDC repositories need not represent byte-identical archival objects.

---

# 8. ENA interfaces

## 8.1 Portal/File Report API

The ENA Portal API SHALL be the principal source for:

- project/run discovery;
    
- object crosswalks;
    
- run-level metadata;
    
- remote file inventory;
    
- remote byte counts;
    
- remote MD5 checksums.
    

ENA provides a dedicated `filereport` resource for this purpose. Study/BioProject, Experiment, Sample and Run accessions can be supplied to the `read_run` result, and file-related fields such as FASTQ URLs, MD5 values and byte sizes can be requested explicitly. ([ENA Documentation](https://ena-docs.readthedocs.io/en/latest/retrieval/programmatic-access/file-reports.html?utm_source=chatgpt.com "Retrieving ENA File reports — ENA Documentation 1 documentation"))

The implementation MUST request fields explicitly rather than depending indefinitely on ENA's default column set.

Required file-field families are conceptually:

```text
submitted_ftp
submitted_md5
submitted_bytes

fastq_ftp
fastq_md5
fastq_bytes

sra_ftp
sra_md5
sra_bytes
```

The implementation SHOULD consult or test against ENA's advertised `returnFields` endpoint so changes to the upstream schema fail explicitly rather than producing silently malformed manifests. ENA exposes that mechanism specifically for discovering available result fields. ([ENA Documentation](https://ena-docs.readthedocs.io/en/latest/retrieval/programmatic-access/advanced-search.html?utm_source=chatgpt.com "How to Perform Advanced Searches Across ENA Programmatically — ENA Documentation 1 documentation"))

## 8.2 Browser API

The ENA Browser API SHALL be used for preservation of complete XML metadata records where available.

ENA explicitly supports XML retrieval for Study, Sample, Experiment and Run records. Browser XML contains submitter metadata as well as archive-added cross-references. ([ENA Documentation](https://ena-docs.readthedocs.io/en/latest/retrieval/programmatic-access/browser-api.html?utm_source=chatgpt.com "How to Download Records using the ENA Browser API — ENA Documentation 1 documentation"))

The implementation SHOULD retrieve XML for each unique:

```text
Study
Sample
Experiment
Run
```

identified during discovery.

Portal API results SHALL NOT be treated as a complete substitute for raw archival XML.

## 8.3 Source preservation

Every server response designated as raw archival evidence SHALL be written to disk without semantic rewriting.

Normalization MUST operate from preserved raw responses whenever practical.

---

# 9. Metadata acquisition transaction

A metadata snapshot SHALL occur as a transaction.

The application SHALL first retrieve and validate all required upstream responses into temporary/staging locations.

Only once the snapshot is internally coherent SHALL it become the current metadata state.

An interruption MUST NOT leave a mixture of old and new current metadata.

Conceptually:

```text
current snapshot
      │
      ├── refresh requested
      ↓
retrieve into staging
      ↓
validate staging
      ↓
archive previous snapshot
      ↓
atomic promotion
      ↓
new current snapshot
```

---

# 10. Output directory contract

The ENA archive root SHALL have the following structure:

```text
OUTDIR/
├── manifest.tsv
│
├── metadata/
│   ├── snapshot.json
│   │
│   ├── raw/
│   │   ├── portal/
│   │   │   └── filereport.tsv
│   │   │
│   │   └── xml/
│   │       ├── studies/
│   │       ├── samples/
│   │       ├── experiments/
│   │       └── runs/
│   │
│   ├── derived/
│   │   ├── project.json
│   │   ├── samples.tsv
│   │   ├── sample_attributes.tsv
│   │   ├── experiments.tsv
│   │   ├── runs.tsv
│   │   └── files.tsv
│   │
│   └── archive/
│       └── <snapshot-id>/
│
├── submitted/
│   └── <RUN>/
│       └── <original filenames>
│
├── fastq/
│   └── <RUN>/
│       └── <ENA FASTQ filenames>
│
├── sra/
│   └── <RUN>/
│       └── <SRA filenames>
│
├── superseded/
│   └── <snapshot-id>/
│
├── tmp/
│
└── logs/
    ├── download.log
    └── failed_accessions.txt
```

Run-specific subdirectories are REQUIRED.

The tool SHALL NOT flatten all submitted files into a single directory because different Runs may contain identically named submitted files.

Remote filenames SHALL be retained whenever safely representable on the local filesystem.

The application SHALL NOT rename submitted files to sample or run identifiers merely for convenience.

---

# 11. Raw metadata contract

The application SHALL preserve the exact successful ENA responses on which normalization was based.

At minimum:

```text
metadata/raw/portal/filereport.tsv
```

SHALL contain the raw file-report response used to construct the Run and file inventories.

Browser XML SHALL be preserved separately by object accession.

For example:

```text
metadata/raw/xml/studies/ERP012345.xml

metadata/raw/xml/samples/ERS000001.xml
metadata/raw/xml/samples/SAMEA000001.xml

metadata/raw/xml/experiments/ERX000001.xml

metadata/raw/xml/runs/ERR000001.xml
```

The implementation MAY avoid storing duplicate equivalent XML aliases when one accession resolves to the identical underlying object, but the alias relationship MUST then be recorded in normalized metadata.

Raw files SHALL NOT be reformatted for aesthetics.

---

# 12. Normalized metadata products

Normalized files are stable machine-readable interpretations of the raw ENA responses.

They SHALL be UTF-8.

TSV tables SHALL:

- contain one header row;
    
- use literal tab separators;
    
- use one logical record per row;
    
- avoid embedded unescaped newlines;
    
- have deterministic column order;
    
- have deterministic record ordering.
    

Schema versions SHALL be explicit.

## 12.1 `project.json`

`project.json` SHALL contain at least:

```text
schema_version
input_accession
project_accession
study_accession
study_alias
title
description
center_name
first_public
last_updated
snapshot_id
source
```

Missing upstream values SHALL be represented explicitly using the chosen JSON null convention rather than invented placeholders.

## 12.2 `samples.tsv`

Minimum v1 columns:

```text
sample_accession
secondary_sample_accession
sample_alias
sample_title
tax_id
scientific_name
collection_date
country
location
first_public
last_updated
```

Not every field will exist for every Sample.

## 12.3 `sample_attributes.tsv`

Arbitrary BioSample/ENA Sample attributes SHALL NOT be discarded merely because they do not fit the stable wide table.

They SHALL be retained in long form:

```text
sample_accession
attribute_name
attribute_value
attribute_units
```

If units do not exist, the field SHALL be empty.

## 12.4 `experiments.tsv`

Minimum v1 columns:

```text
experiment_accession
study_accession
sample_accession
secondary_sample_accession
experiment_alias
library_name
library_strategy
library_source
library_selection
library_layout
instrument_platform
instrument_model
```

## 12.5 `runs.tsv`

Minimum v1 columns:

```text
run_accession
experiment_accession
study_accession
secondary_study_accession
sample_accession
secondary_sample_accession
run_alias
library_strategy
library_source
library_layout
instrument_platform
instrument_model
base_count
read_count
first_public
last_updated
```

Records SHALL be sorted by `run_accession`.

---

# 13. Complete remote file inventory

## 13.1 `files.tsv`

`files.tsv` is one of the central archival products.

It SHALL represent **every downloadable raw-read file exposed by ENA in the supported representations**, regardless of which files are subsequently selected for acquisition.

One row SHALL correspond to exactly one remote file.

ENA often returns multiple file URLs, byte counts and checksums in semicolon-delimited fields. These arrays SHALL be exploded into one-file-per-row records.

The order supplied by ENA SHALL be preserved using `file_index`.

Minimum schema:

```text
schema_version
project_accession
study_accession
run_accession
experiment_accession
sample_accession
secondary_sample_accession
representation
file_index
file_name
remote_path
download_url
size_bytes
md5
availability
inventory_note
```

Allowed `representation` values in v0.1:

```text
submitted
fastq
sra
```

`file_name` SHALL normally be derived from the final path component of the ENA-provided remote path.

`remote_path` SHALL preserve ENA's value as closely as possible.

`download_url` SHALL contain the URL actually suitable for the downloader.

The application SHOULD use HTTPS where ENA exposes the same FTP-hosted object over HTTPS.

The implementation MUST NOT derive remote file locations solely from knowledge of ENA's FTP directory structure when ENA already supplies the authoritative file path.

ENA documents separate storage structures for submitted, generated FASTQ and SRA representations, but these structures are repository implementation details and SHALL NOT replace API-derived URLs. ([ENA Documentation](https://ena-docs.readthedocs.io/en/latest/retrieval/file-download/sra-ftp-structure.html?utm_source=chatgpt.com "SRA FTP Structure — ENA Documentation 1 documentation"))

---

# 14. File-array consistency

For every ENA representation, the associated URL, MD5 and byte-count arrays MUST be internally consistent.

For example, if:

```text
fastq_ftp
```

contains two entries, then:

```text
fastq_md5
fastq_bytes
```

MUST each yield two corresponding entries for verified acquisition.

The relationships are positional.

The implementation MUST NOT independently sort the three arrays before pairing them.

If ENA advertises file URLs but the corresponding checksum or byte arrays have incompatible cardinality, the representation SHALL be classified as:

```text
malformed
```

rather than:

```text
unavailable
```

This distinction is critical.

An upstream metadata inconsistency MUST NOT silently trigger fallback to another representation under the `archival`policy.

---

# 15. Inventory versus manifest

`files.tsv` and `manifest.tsv` have fundamentally different meanings.

```text
files.tsv
    =
what ENA reported as available

manifest.tsv
    =
what this acquisition policy selected
```

`files.tsv` SHALL be independent of acquisition policy.

Changing:

```text
--representation fastq
```

to:

```text
--representation submitted
```

MUST NOT change the underlying `files.tsv` produced from the same snapshot.

The manifest SHALL therefore be reproducible from:

```text
files.tsv + selection policy
```

without further network access.

---

# 16. Representation-selection policies

The CLI SHALL support:

```text
archival
submitted
fastq
sra
all
```

The default SHALL be:

```text
archival
```

## 16.1 `submitted`

For every Run, select all valid ENA-submitted files.

If any Run has no submitted representation, manifest creation SHALL fail.

No automatic fallback SHALL occur.

## 16.2 `fastq`

For every Run, select all valid ENA-generated FASTQ files.

If any Run lacks generated FASTQ, manifest creation SHALL fail.

No automatic fallback SHALL occur.

ENA-generated FASTQ may be absent for some native sequencing formats and specialized BAM/CRAM submissions; this condition is expected and SHALL be reported accurately rather than treated as an application error. ([ENA Documentation](https://ena-docs.readthedocs.io/en/latest/faq/archive-generated-files.html?utm_source=chatgpt.com "Archive Generated Run Files — ENA Documentation 1 documentation"))

## 16.3 `sra`

For every Run, select all valid SRA-representation files.

If any Run lacks an SRA representation, manifest creation SHALL fail.

## 16.4 `archival`

The default `archival` policy SHALL operate independently for every Run:

```text
submitted representation available and valid?
        │
       yes
        ↓
select ALL submitted files
        │
       no
        ↓
submitted truly unavailable?
        │
       yes
        ↓
SRA representation available and valid?
        │
       yes
        ↓
select SRA
        │
       no
        ↓
FASTQ representation available and valid?
        │
       yes
        ↓
select ALL generated FASTQ files
        │
       no
        ↓
manifest failure
```

A representation SHALL be considered valid for verified archival only when:

- at least one file is present;
    
- every file has a remote path;
    
- every file has a positive/valid byte count when ENA supplies byte information;
    
- every file has a syntactically valid repository MD5;
    
- URL/checksum/byte arrays have compatible cardinalities.
    

### Critical rule

If submitted files are **advertised but malformed**, the application SHALL fail that Run rather than silently treating the submitted representation as absent and falling back to SRA or FASTQ.

Fallback is permitted only when the preferred representation is genuinely unavailable.

The manifest SHALL record why fallback occurred.

Example:

```text
selection_policy = archival
representation   = sra
selection_reason = submitted_not_available_from_ena
```

This is particularly relevant for Runs originating at NCBI or DDBJ, for which ENA states that ENA-submitted originals are not available. ([ENA Documentation](https://ena-docs.readthedocs.io/en/latest/retrieval/file-download/sra-ftp-structure.html?utm_source=chatgpt.com "SRA FTP Structure — ENA Documentation 1 documentation"))

## 16.5 `all`

`all` SHALL select all complete valid representations available for every Run.

It SHALL NOT require every representation to exist.

Each Run MUST nevertheless have at least one valid representation.

This mode SHOULD be documented as storage-expensive and primarily intended for deliberate comparison or preservation work.

---

# 17. Manifest contract

`manifest.tsv` is the immutable acquisition contract.

One row SHALL correspond to one selected remote file.

Minimum v1 columns:

```text
schema_version
project_accession
study_accession
run_accession
experiment_accession
sample_accession
secondary_sample_accession
library_strategy
library_source
library_layout
instrument_platform
instrument_model
representation
selection_policy
selection_reason
file_index
file_name
size_bytes
md5
remote_url
local_relpath
```

Records SHALL be deterministically sorted by:

```text
run_accession
representation
file_index
```

`local_relpath` SHALL be explicit.

Examples:

```text
submitted/ERR123456/sample_A_R1.fastq.gz
submitted/ERR123456/sample_A_R2.fastq.gz

fastq/ERR123456/ERR123456_1.fastq.gz
fastq/ERR123456/ERR123456_2.fastq.gz

sra/ERR123456/ERR123456
```

The downloader SHALL consume paths from the manifest rather than independently recomputing storage paths.

---

# 18. Snapshot identifier

Every successful metadata snapshot SHALL receive an immutable identifier based on UTC time, for example:

```text
20260808T162700Z
```

If collision is possible, an additional deterministic suffix MAY be added.

The identifier SHALL be stored in `snapshot.json`.

It SHALL be used when archiving previous metadata states and superseded data objects.

---

# 19. `snapshot.json`

`snapshot.json` is the provenance ledger for the metadata transaction.

Minimum conceptual structure:

```json
{
  "schema_version": "...",
  "tool_version": "...",
  "snapshot_id": "...",
  "created_at": "...",
  "input_accession": "...",
  "project_accession": "...",
  "study_accession": "...",
  "source": "ENA",
  "status": "complete",
  "requests": [],
  "artifacts": [],
  "warnings": [],
  "errors": []
}
```

Every preserved raw or normalized metadata artifact SHALL be represented by at least:

```text
relative path
byte size
SHA-256
artifact type
```

SHA-256 here serves to verify the integrity of the **local metadata snapshot**, independently of ENA's MD5 values for sequence-data files.

Snapshot files SHALL be written atomically.

---

# 20. Metadata refresh

Existing metadata SHALL never be silently overwritten.

Running metadata acquisition against an existing current snapshot without:

```text
--refresh
```

SHALL fail or explicitly refuse replacement.

With:

```text
--refresh
```

the complete previous metadata state SHALL be preserved under:

```text
metadata/archive/<previous-snapshot-id>/
```

The previous manifest associated with that snapshot SHALL also be preserved there when applicable.

A refresh SHALL NOT automatically delete downloaded sequence files.

---

# 21. Detecting changed upstream sequence objects

Public repository records may occasionally be corrected or updated.

Suppose a new ENA snapshot refers to:

```text
fastq/ERR123456/ERR123456_1.fastq.gz
```

with a different MD5 from the manifest under which the current local file was previously verified.

The existing file SHALL NOT simply be labelled corrupt.

If it matches the checksum recorded in a previous local manifest, it is a valid historical object.

It SHALL instead be moved to:

```text
superseded/<snapshot-id>/<original-relative-path>
```

before downloading the newly referenced object.

The event SHALL be logged.

A file SHALL be labelled `.bad.<timestamp>` only when it fails to match both:

- the currently expected object;
    
- any recognized previous valid object relevant to that path.
    

This rule preserves the distinction between:

```text
corruption
```

and:

```text
repository revision
```

---

# 22. Download transaction

Every selected file SHALL be downloaded transactionally.

Conceptual sequence:

```text
remote object
      ↓
destination.part
      ↓
transfer completes
      ↓
verify byte count
      ↓
verify ENA MD5
      ↓
atomic rename
      ↓
final destination
```

The existence of a final filename SHALL NOT be sufficient evidence of completion.

A final file is complete only when it matches the manifest.

---

# 23. Resume behavior

Downloads SHALL be resumable where supported by the server and transport.

An interrupted download SHALL remain as:

```text
<filename>.part
```

A rerun SHALL attempt to resume rather than restart whenever safely possible.

A `.part` file MUST never be mistaken for a completed archival object.

---

# 24. Existing final files

Before downloading a file whose final destination already exists, the application SHALL:

1. compare its size with the manifest;
    
2. calculate its MD5;
    
3. skip the download if both match;
    
4. determine whether it represents a valid superseded object if the current checksum differs;
    
5. otherwise quarantine it before reacquisition.
    

This makes the command idempotent.

Running the same verified manifest repeatedly SHALL eventually perform no network transfers.

---

# 25. Checksum policy

ENA-provided MD5 SHALL be the authoritative content identity for sequence-data acquisition because it permits direct verification against the repository's advertised object. ENA uses MD5 during submission specifically to confirm that transferred files match the deposited files. ([ENA Documentation](https://ena-docs.readthedocs.io/en/latest/submit/fileprep/preparation.html?utm_source=chatgpt.com "Preparing A File For Upload — ENA Documentation 1 documentation"))

Byte size SHALL also be checked where available.

Data verification SHALL therefore use:

```text
expected byte count
+
expected MD5
```

The application MAY additionally calculate SHA-256 for long-term local integrity monitoring, but this SHALL NOT replace repository MD5 verification.

If local SHA-256 support is implemented, it SHOULD be written to a separate local checksum ledger rather than altering the immutable remote manifest after download.

---

# 26. Transport

Version 0.1 SHALL use `curl` as the external transfer engine unless a demonstrably superior dependency-free mechanism is selected.

HTTPS SHALL be preferred for routine transfer when the ENA object is reachable through HTTPS.

The raw ENA-provided remote path SHALL nevertheless be preserved in the inventory.

Potential future transports include:

```text
Aspera
Globus
```

They are explicitly outside the v0.1 acceptance requirements.

The manifest data model SHALL NOT make future alternative transports impossible.

---

# 27. Parallelism

Multiple independent remote files MAY be downloaded concurrently.

CLI:

```text
--jobs N
```

SHALL control maximum transfer concurrency.

Default concurrency SHOULD be conservative.

The application SHOULD prioritize predictable storage and network behavior over maximum transfer speed.

Concurrency MUST NOT compromise:

- independent `.part` files;
    
- checksum validation;
    
- atomic finalization;
    
- logging;
    
- recovery of individual failures.
    

A failure in one worker SHALL NOT automatically cancel unrelated valid downloads.

---

# 28. Failure collection and retry

A download failure SHALL be associated with its exact file and Run.

Other independent downloads SHALL be permitted to finish.

Retry logic SHOULD include:

- transient HTTP/network failures;
    
- interrupted connections;
    
- resumable partial transfers;
    
- bounded backoff.
    

Persistent failures SHALL be summarized in:

```text
logs/failed_accessions.txt
```

or an equivalent stable machine-readable failure report.

A partially successful download command SHALL return a non-zero exit status.

---

# 29. Dry run

The application SHALL provide:

```bash
ena-project download ... --dry-run
```

A dry run MUST NOT download sequence files.

It SHOULD report:

```text
input accession
canonical BioProject
ENA Study accession
number of Samples
number of Experiments
number of Runs

number of submitted files available
number of FASTQ files available
number of SRA files available

selection policy
representation chosen per Run
fallback counts and reasons

number of selected files
total selected bytes

destination path
available filesystem space
estimated remaining space after acquisition
```

For `archival`, a summary such as the following is desirable:

```text
187 runs

185  submitted representation
  2  SRA fallback
  0  FASTQ fallback

Fallback reasons:
2 submitted files unavailable because run originated outside ENA
```

A dry run SHALL perform enough metadata work to determine whether the intended manifest is valid.

---

# 30. CLI contract

The installed command SHALL be:

```text
ena-project
```

## 30.1 Metadata only

```bash
ena-project metadata PRJEB123456 \
    --outdir PATH
```

This SHALL:

- resolve accessions;
    
- retrieve raw metadata;
    
- retrieve complete remote file inventory;
    
- normalize metadata;
    
- write `files.tsv`;
    
- write `snapshot.json`;
    
- download no sequence data.
    

## 30.2 Snapshot

```bash
ena-project snapshot PRJEB123456 \
    --outdir PATH
```

This SHALL perform metadata acquisition and additionally construct:

```text
manifest.tsv
```

using the default `archival` policy.

Alternative:

```bash
ena-project snapshot PRJEB123456 \
    --outdir PATH \
    --representation fastq
```

## 30.3 Offline manifest generation

The application SHALL permit manifest construction without network access from an existing valid inventory.

Conceptually:

```bash
ena-project manifest metadata/derived/files.tsv \
    --representation archival \
    --output manifest.tsv
```

Any additional metadata required by the manifest MUST already be obtainable from the local snapshot.

## 30.4 Download from accession

```bash
ena-project download PRJEB123456 \
    --outdir PATH \
    --representation archival
```

This SHOULD create or use the necessary snapshot and manifest before transfer.

## 30.5 Download from existing manifest

```bash
ena-project download manifest.tsv \
    --outdir PATH
```

This SHALL perform no metadata rediscovery before downloading unless explicitly requested.

The manifest is the acquisition contract.

## 30.6 Validation

```bash
ena-project validate PATH
```

This SHALL validate the structural and integrity requirements of an existing archive.

## 30.7 Offline normalization

Equivalent functionality to:

```bash
ena-project metadata-normalize \
    --metadata-dir PATH/metadata
```

SHALL rebuild normalized metadata from preserved raw responses without contacting ENA.

---

# 31. Input inference

Input type inference SHALL be conservative.

Recognized project/study accession patterns MAY be inferred directly.

File inputs SHOULD be inferred only from documented extensions/content.

Ambiguous inputs SHALL cause a clear configuration error rather than being guessed.

---

# 32. Archive validation

`ena-project validate OUTDIR` SHALL check at least:

### Metadata integrity

- presence and syntax of `snapshot.json`;
    
- supported schema major version;
    
- existence of recorded metadata artifacts;
    
- artifact byte size;
    
- artifact SHA-256;
    
- relational consistency between normalized Study, Sample, Experiment and Run records.
    

### Inventory integrity

- valid representation values;
    
- unique file records;
    
- valid MD5 syntax;
    
- valid file sizes;
    
- absence of contradictory local paths;
    
- file-array explosion consistency.
    

### Manifest integrity

- supported schema;
    
- deterministic/valid fields;
    
- every manifest file must exist in `files.tsv`;
    
- every Run required by the snapshot must be represented according to the selected policy;
    
- local paths must remain inside the archive root;
    
- no path traversal.
    

### Downloaded data integrity

For every manifest object expected locally:

- file exists;
    
- size matches;
    
- MD5 matches.
    

Validation SHALL report all discovered problems where practical rather than stopping at the first error.

---

# 33. Security and filesystem safety

Remote filenames SHALL be treated as untrusted input.

The application MUST prevent:

```text
../
absolute-path injection
directory escape
control-character path manipulation
```

The final resolved destination of every downloaded object MUST remain underneath `OUTDIR`.

URLs SHALL only be taken from expected ENA/EBI sources unless the user explicitly enables another trusted source in a future version.

No shell command SHALL be constructed by unsafe string interpolation.

External commands SHOULD be executed using argument arrays.

---

# 34. Mounted-volume protection

The useful macOS safety behavior from the NCBI application SHOULD be retained.

Paths underneath:

```text
/Volumes/
```

SHOULD be checked to ensure that the expected volume is actually mounted before beginning a large acquisition.

The implementation MUST NOT accidentally create a normal directory beneath `/Volumes/<missing-volume>` and proceed to fill the system disk.

This check SHALL remain macOS-specific.

Ordinary filesystem behavior MUST remain portable to Linux.

---

# 35. Metadata and network politeness

The client SHALL identify itself appropriately where ENA permits or expects a user agent.

Repeated XML retrievals SHOULD use bounded concurrency and retry/backoff behavior.

The application SHALL NOT perform unnecessary repeated API requests when the same response already exists in the current transaction.

Large metadata workflows SHOULD remain considerate of repository infrastructure.

---

# 36. Logging

Important operational events SHALL be logged with timestamps.

At minimum:

```text
snapshot start/end
accession resolution
number of discovered Runs
inventory summary
selection policy
fallback selections
download start
download resume
download skip
checksum success/failure
quarantine
superseded-object handling
retry
persistent failure
validation result
```

Secrets or local credentials SHALL never be logged.

Normal progress SHALL be human-readable.

Machine-readable provenance SHALL remain in metadata/manifests rather than depending on log parsing.

---

# 37. Exit statuses

To retain semantic similarity with the NCBI sibling, v0.1 SHOULD use:

```text
0    complete success

1    general runtime failure

2    invalid input or configuration

3    required retrieval or download incomplete

4    optional metadata retrieval incomplete /
     snapshot usable but explicitly partial

5    normalization or validation failure

130  keyboard interruption
```

Exit statuses SHALL be documented and tested.

A command MUST NOT return `0` when required files failed verification.

---

# 38. Snapshot completeness

A snapshot SHALL have an explicit state such as:

```text
complete
partial
failed
```

A required inability to retrieve the Run inventory SHALL make the snapshot unusable and fail the command.

Failure to retrieve an optional linked resource MAY produce `partial`.

The implementation SHALL NOT fabricate empty metadata to conceal upstream errors.

A genuine ENA response indicating no records is distinct from a failed ENA request.

---

# 39. Schema versioning

Metadata schemas and manifest schemas SHALL be explicitly versioned.

Versions SHOULD conceptually follow:

```text
MAJOR.MINOR
```

Compatible additive changes MAY increment MINOR.

Breaking semantic changes MUST increment MAJOR.

Readers SHALL reject unsupported major versions.

Preserved raw responses MUST make migration or renormalization possible without reacquiring the sequencing data.

---

# 40. Determinism

Given:

```text
identical raw metadata
+
identical software version
+
identical representation policy
```

the following outputs SHALL be byte-for-byte deterministic where timestamps are not inherently part of the artifact:

```text
project.json
samples.tsv
sample_attributes.tsv
experiments.tsv
runs.tsv
files.tsv
manifest.tsv
```

Records SHALL therefore have defined sort orders.

JSON serialization intended to be deterministic SHOULD use stable key ordering and formatting.

---

# 41. Dependencies

Version 0.1 SHOULD have a deliberately modest dependency footprint.

Expected baseline:

```text
Python >= 3.9
curl
```

Additional Python dependencies MAY be introduced when justified.

The application SHALL NOT require SRA Toolkit merely to download ENA FASTQ files.

It SHALL NOT require:

```text
fasterq-dump
vdb-validate
pigz
```

for ordinary ENA FASTQ acquisition.

If SRA Toolkit validation is later offered for SRA representations, it SHOULD be optional.

This distinguishes ENA FASTQ acquisition from the NCBI workflow in which FASTQ may need to be generated locally from an SRA object.

---

# 42. Proposed Python package architecture

Recommended structure:

```text
ena-project-archiver/
├── pyproject.toml
├── README.md
├── LICENSE
├── CHANGELOG.md
├── docs/
├── examples/
├── tests/
└── src/
    └── ena_project/
        ├── __init__.py
        ├── __main__.py
        ├── cli.py
        ├── models.py
        ├── accession.py
        ├── ena_client.py
        ├── inventory.py
        ├── selection.py
        ├── manifest.py
        ├── downloader.py
        ├── validation.py
        └── metadata/
            ├── __init__.py
            ├── acquire.py
            ├── normalize.py
            ├── snapshot.py
            └── schemas.py
```

Responsibilities SHALL remain separated.

### `accession.py`

Accession recognition, validation and canonicalization.

### `ena_client.py`

ENA HTTP interfaces only.

It SHALL NOT contain archive-selection policy.

### `metadata/acquire.py`

Coordinate raw metadata retrieval and staging.

### `metadata/normalize.py`

Transform preserved raw responses into stable normalized products.

### `inventory.py`

Explode ENA file arrays into one-file-per-row inventory records and validate their internal consistency.

### `selection.py`

Pure representation-selection logic.

This module SHOULD be testable without network or filesystem access.

### `manifest.py`

Stable manifest serialization/deserialization and schema validation.

### `downloader.py`

Transfers, resume, verification, quarantine and supersession handling.

### `validation.py`

Whole-archive consistency checking.

### `cli.py`

Argument handling and orchestration only.

Business rules SHOULD NOT accumulate in the CLI module.

---

# 43. Internal data models

The implementation SHOULD define explicit typed models corresponding approximately to:

```text
ProjectRecord
SampleRecord
SampleAttribute
ExperimentRecord
RunRecord
RemoteFile
ManifestEntry
Snapshot
```

A `RemoteFile` MUST represent one physical remote object, not an entire semicolon-delimited ENA field.

Conceptually:

```text
RemoteFile
    run_accession
    representation
    file_index
    file_name
    remote_path
    download_url
    size_bytes
    md5
```

A `ManifestEntry` adds selection and local-destination information.

---

# 44. No hidden inference of biological semantics

The application SHALL preserve repository metadata but SHALL be conservative about biological inference.

For example, it SHALL NOT infer that:

```text
filename containing _1 = biological forward read
filename containing _2 = biological reverse read
```

unless that relationship is supported by ENA metadata.

File order and library layout SHALL be recorded separately.

The archiver is not a sequencing-analysis pipeline.

---

# 45. Run completeness

All files belonging to the selected representation of a Run SHALL be treated as one logical selection set.

For example, a paired experiment may expose:

```text
ERR123_1.fastq.gz
ERR123_2.fastq.gz
```

or potentially an additional singleton FASTQ.

ENA documents that generated FASTQ file counts depend on the application reads and may include paired and unpaired reads. ([ENA Documentation](https://ena-docs.readthedocs.io/en/latest/faq/archive-generated-files.html?utm_source=chatgpt.com "Archive Generated Run Files — ENA Documentation 1 documentation"))

The application MUST therefore select **all files in the chosen representation**, not assume exactly one or two FASTQ files.

---

# 46. Tests required for v0.1

The test suite SHALL contain both unit tests and fixture-driven integration-style tests that do not depend on live ENA availability.

At minimum the fixtures SHALL cover:

### Accessions

```text
PRJEB input
ERP input resolving to PRJEB
PRJNA dataset visible through ENA
invalid accession
empty/non-public accession
```

### File inventories

```text
single submitted FASTQ
paired submitted FASTQ
three generated FASTQ files
submitted BAM
multiple submitted files
SRA representation
```

### Missing representations

```text
Run without submitted files
Run without generated FASTQ
Run with only one usable representation
```

### Archival policy

```text
submitted preferred over SRA
SRA fallback when submitted genuinely unavailable
FASTQ fallback when submitted and SRA unavailable
failure when no representation exists
```

### Malformed upstream metadata

```text
two URLs but one MD5
two URLs but three byte counts
invalid MD5
empty URL element
non-numeric byte count
```

These MUST generate explicit errors rather than silent fallback.

### Filesystem

```text
duplicate submitted basenames in different Runs
.part recovery
existing valid final file
existing corrupted final file
path traversal attempt
missing macOS mounted volume
```

### Repository revision

```text
same local path + new ENA MD5
existing file matches previous manifest
existing file moved to superseded/
new file acquired and verified
```

### Refresh

```text
metadata exists without --refresh
successful --refresh
failed refresh leaves old current snapshot intact
previous snapshot remains verifiable
```

### Determinism

Repeated normalization of the same fixtures SHALL produce byte-identical normalized tables and manifests.

---

# 47. Live ENA smoke tests

A small set of live integration tests MAY run separately from the normal test suite.

They SHOULD use tiny stable ENA records.

Live tests SHALL NOT download large sequencing datasets.

They SHOULD verify:

```text
Portal API reachability
Browser API reachability
expected field names
file-report parsing
accession resolution
```

Ordinary unit-test success SHALL NOT depend on ENA being online.

---

# 48. Acceptance criteria for v0.1

Version 0.1 SHALL NOT be considered complete until the following end-to-end scenario succeeds:

```text
1. User supplies an ENA BioProject or Study accession.

2. Tool resolves its canonical project identity.

3. Tool retrieves and preserves raw ENA metadata.

4. Tool normalizes Study, Sample, Experiment and Run relationships.

5. Tool creates a complete one-row-per-file inventory of
   submitted, FASTQ and SRA representations exposed by ENA.

6. Tool generates a deterministic manifest using an explicit
   selection policy.

7. Dry-run correctly reports storage requirements and fallback
   behavior.

8. Tool downloads all manifest files into run-specific directories.

9. Every file is verified against ENA byte count and MD5.

10. Interrupted downloads can be rerun safely.

11. Existing valid files are skipped.

12. Corrupt files are quarantined.

13. Valid historical objects replaced upstream are preserved as
    superseded rather than misclassified as corrupt.

14. Archive validation succeeds.

15. The same preserved raw metadata can regenerate the normalized
    metadata and manifest offline.
```

---

# 49. Explicit anti-requirements

An implementation SHALL be rejected if it does any of the following:

```text
downloads FASTQ without preserving an ENA file inventory;

assumes every Run has exactly two FASTQ files;

assumes FASTQ is always the original deposited representation;

silently substitutes FASTQ when submitted-file metadata is malformed;

uses filenames alone to determine download completeness;

overwrites previous metadata snapshots without --refresh;

renames submitted files and thereby loses their original identities;

reconstructs ENA URLs from accession patterns when authoritative URLs
are already available from the API;

mixes files acquired from ENA and NCBI in the same provenance namespace;

discards arbitrary Sample attributes because they do not fit a fixed schema;

requires live ENA access to regenerate normalized metadata from an
existing snapshot;

deletes an older valid sequence object merely because ENA now advertises
a different checksum;

downloads linked assemblies or analyses merely because they are mentioned
by Study metadata.
```

---

# 50. Deferred features

The following are desirable but explicitly outside the v0.1 contract:

```text
Aspera transfer
Globus transfer

ENA Analysis objects
assemblies
annotated nucleotide sequences

run-only acquisition as a first-class user workflow
sample-level acquisition
query-based multi-project acquisition

controlled-access data

automatic SRA → FASTQ conversion
automatic BAM/CRAM → FASTQ conversion

content-level FASTQ/BAM validation beyond repository checksums

automatic integration with downstream Nextflow workflows

cross-repository NCBI ↔ ENA byte-level comparison

common library shared by the NCBI and ENA archivers

global BioProject catalogue/database

automatic deduplication across repository sources
```

Their future addition MUST preserve backward readability of v0.1 archives.

---

# 51. Long-term architectural direction

The ENA and NCBI applications should eventually form repository-specific acquisition front ends around a common conceptual archival model:

```text
                  ┌── NCBI adapter
                  │
BioProject ───────┤
                  │
                  └── ENA adapter
                         │
                         ↓
              repository evidence
                         ↓
                normalized metadata
                         ↓
                acquisition manifest
                         ↓
                  verified objects
```

A later shared library may therefore contain:

```text
atomic file operations
checksum verification
download transactions
snapshot versioning
manifest primitives
archive validation
mounted-volume safety
logging infrastructure
```

Repository-specific logic should remain outside that layer:

```text
NCBI Entrez
NCBI SRA XML semantics
SRA Normalized selection

ENA Portal API
ENA Browser XML
ENA representation inventory
submitted/FASTQ/SRA selection
```

This extraction SHALL occur only after both applications provide concrete evidence for the abstraction.

---

# 52. Archival philosophy

The application SHALL embody the following principle:

> A scientific data archive is not merely a directory containing files that can be analysed. It is a locally verifiable record of what a public repository reported, what acquisition decisions were made from that evidence, and which exact objects were subsequently obtained.

Accordingly:

```text
raw ENA responses
        ↓
preserved evidence

files.tsv
        ↓
repository inventory

manifest.tsv
        ↓
acquisition decision

downloaded files
        ↓
verified archived objects
```

These layers SHALL remain distinguishable.

A future researcher must be able to determine not only **what files are present**, but also:

```text
which ENA record they came from;
which version of ENA metadata was consulted;
which representations were available;
why a particular representation was selected;
whether fallback occurred;
which checksum ENA advertised;
whether the local object still matches it;
and whether ENA subsequently replaced that object.
```

That requirement is the central design constraint of `ena-project`.

---

# 53. Initial implementation milestone

The recommended first development milestone is deliberately smaller than the complete CLI.

The first milestone SHALL implement:

```text
accession resolution
        ↓
ENA file-report retrieval
        ↓
raw response preservation
        ↓
Run normalization
        ↓
one-file-per-row files.tsv
        ↓
representation selection
        ↓
manifest.tsv
```

using fixture-driven tests.

No sequence-data downloader should be implemented until this layer correctly handles:

```text
one-to-many files
missing representations
fallback logic
malformed ENA arrays
non-FASTQ submitted formats
cross-INSDC Runs
deterministic serialization
```

The second milestone SHALL add verified downloading and recovery.

The third SHALL complete XML metadata snapshots, refresh and whole-archive validation.

This ordering prevents transfer mechanics from obscuring errors in the more scientifically important accession, provenance and representation model.

---

## End of normative specification

This is now sufficiently specific to serve both as a design document and as the contract against which an AI coding agent's implementation can be reviewed. The particularly important additions over our initial discussion are the **transactional refresh model**, **malformed-vs-unavailable distinction**, **per-run storage**, and **superseded-object handling**—all of which matter if we truly mean “archive” rather than merely “downloader.”

---
