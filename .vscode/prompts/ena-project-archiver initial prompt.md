# ENA Project Archiver Initial Implementation Prompt

You are a senior Python software engineer and scientific-data infrastructure architect. Your task is to implement a new open-source CLI application for reproducible archival acquisition of raw sequencing data and metadata from the European Nucleotide Archive (ENA).

The application is the ENA sibling of:

`costantinicarlo/ncbi-sra-bioproject-downloader`

but it MUST be implemented as a **separate repository and separate Python package**. Do not add ENA functionality to the existing NCBI project.

The working repository name is:

```text
ena-project-archiver
```

The installed CLI command MUST be:

```text
ena-project
```

The Python package SHOULD be:

```text
ena_project
```

A complete normative specification follows this instruction. Treat that specification as the authoritative software contract.

# Governing rule

Implement the specification **verbatim in meaning and behavior**.

The specification uses normative terms such as MUST, SHALL, MUST NOT, SHOULD, SHOULD NOT and MAY. Interpret these according to normal RFC-style conventions:

- MUST / SHALL = mandatory;

- MUST NOT / SHALL NOT = prohibited;

- SHOULD = required unless a documented technical reason justifies deviation;

- MAY = optional.

Do not silently reinterpret, simplify, weaken, merge, omit or replace requirements.

If an implementation detail is genuinely unspecified, choose the simplest robust design consistent with:

1. provenance preservation;

2. deterministic outputs;

3. reproducibility;

4. filesystem safety;

5. interruption recovery;

6. long-term archival intelligibility;

7. portability between macOS and Linux.

If two requirements appear to conflict, inspect the surrounding specification carefully and resolve the conflict in favour of the more explicit archival or provenance-preserving requirement. Document the decision.

Do not change the contract merely because another implementation would be easier.

# Relationship with the existing NCBI application

Before implementing substantial code, inspect:

```text
https://github.com/costantinicarlo/ncbi-sra-bioproject-downloader
```

Use it as a reference implementation for architectural principles and proven mechanics, particularly:

- Python project structure;

- CLI design;

- metadata snapshots;

- raw versus derived metadata;

- deterministic TSV serialization;

- manifests;

- transactional downloads;

- `.part` files;

- `curl` resume behaviour;

- byte-count validation;

- checksum verification;

- quarantine of corrupt files;

- retry handling;

- worker failure collection;

- logging;

- mounted-volume protection on macOS;

- exit-status conventions;

- metadata refresh;

- validation;

- tests;

- documentation style.

However, DO NOT copy NCBI-specific assumptions into the ENA implementation.

In particular, ENA does not reduce naturally to “one SRA object per Run”. ENA may expose several physical files per Run and several alternative representations:

```text
submitted
fastq
sra
```

The new application's domain model MUST reflect that from the beginning.

Where code can reasonably be adapted from the NCBI repository, preserve its robust behaviour while making the implementation idiomatic for the new ENA data model.

Do not attempt to extract a shared library between the repositories at this stage.

Some duplication is explicitly acceptable.

# Primary architectural principle

Maintain a strict distinction between:

```text
raw repository evidence
        ↓
normalized repository inventory
        ↓
explicit representation-selection policy
        ↓
immutable acquisition manifest
        ↓
verified local files
```

In particular:

```text
files.tsv
```

and:

```text
manifest.tsv
```

MUST NOT be treated as equivalent.

`files.tsv` records what ENA reported as available.

`manifest.tsv` records what an explicit acquisition policy selected.

A change of acquisition policy MUST NOT alter the repository inventory generated from the same metadata snapshot.

# Critical ENA-specific rules

Pay particular attention to the following requirements. These are easy to implement incorrectly and are central to the application.

## One physical remote file per internal record

ENA frequently exposes several URLs, checksums and byte counts in semicolon-delimited fields.

Explode these into explicit one-file-per-record objects.

Do not store a semicolon-delimited ENA field as if it represented one downloadable object.

Maintain positional correspondence between:

```text
URL[i]
MD5[i]
bytes[i]
```

Do not sort those arrays independently.

## Malformed is not unavailable

A representation that ENA advertises but whose URL/checksum/byte arrays are inconsistent is:

```text
malformed
```

not:

```text
unavailable
```

Under the default archival policy, malformed preferred data MUST cause an explicit failure.

Do not silently fall back to another representation.

Fallback is only permitted when the preferred representation is genuinely unavailable.

## Archive all files belonging to a selected representation

Do not assume FASTQ means exactly two files.

A Run can legitimately expose:

- one FASTQ;

- two paired FASTQs;

- paired FASTQs plus singleton reads;

- more complex arrangements.

If a representation is selected, select every file belonging to that representation.

## Preserve submitted filenames

ENA submitted files are archival evidence.

Do not rename them merely to make them resemble Run accessions.

Store them beneath Run-specific directories so duplicate submitted basenames across Runs cannot collide.

## Never infer paired-read semantics from filenames alone

Do not interpret `_1`, `_2`, `R1`, `R2`, etc. biologically unless ENA metadata supports the relationship.

This program archives sequencing data; it is not an analysis pipeline.

## Repository revision is not corruption

If a path previously represented an ENA object with checksum A and a refreshed ENA snapshot now advertises checksum B:

- if the existing local file matches the old manifest, it is a valid historical object;

- move it into `superseded/<snapshot-id>/...`;

- then acquire the new object.

Do NOT quarantine it as corrupt.

Use `.bad.<timestamp>` only when a file fails to match both the current expected object and a recognized historical manifest.

# Implementation strategy

Work incrementally.

Do not attempt to implement the entire specification in one uncontrolled pass.

Use the following milestones.

## Milestone 1 — repository foundation

Create or normalize the repository structure.

At minimum establish:

```text
pyproject.toml
README.md
LICENSE
CHANGELOG.md
.gitignore

src/ena_project/
tests/
docs/
examples/
```

Use modern Python packaging.

Target:

```text
Python >= 3.9
```

Expose:

```text
ena-project
```

as the console command.

Use an MIT License unless the repository already contains a different explicit licensing decision.

Keep runtime dependencies deliberately modest.

Do not introduce a large framework where the Python standard library or a lightweight dependency is sufficient.

## Milestone 2 — accession and ENA client

Implement:

```text
accession.py
ena_client.py
```

Support the project/study accession families required by the contract.

Implement canonical PRJ* resolution without deriving relationships from accession-string manipulation.

Use ENA APIs as authoritative sources.

Keep network access isolated behind the client layer so parsers and normalizers are fixture-testable offline.

Implement:

- sensible timeouts;

- retries for transient failures;

- bounded backoff;

- explicit HTTP errors;

- user-agent identification where appropriate.

Do not let API-specific parsing leak throughout the codebase.

## Milestone 3 — raw file inventory

Implement:

```text
inventory.py
```

This milestone is extremely important.

Parse the ENA file-report response into explicit typed `RemoteFile` records.

For each representation:

```text
submitted
fastq
sra
```

validate:

- URL count;

- MD5 count;

- byte-count count;

- positional consistency;

- valid checksum syntax;

- valid numeric byte sizes;

- empty elements.

Produce deterministic:

```text
metadata/derived/files.tsv
```

with one physical remote object per row.

Preserve the raw ENA response separately under:

```text
metadata/raw/portal/
```

Unit-test this layer heavily before implementing downloads.

## Milestone 4 — normalized biological metadata

Implement typed records approximately corresponding to:

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

Implement:

```text
metadata/acquire.py
metadata/normalize.py
metadata/schemas.py
```

Generate deterministic:

```text
project.json
samples.tsv
sample_attributes.tsv
experiments.tsv
runs.tsv
files.tsv
```

Preserve raw Browser API XML separately by Study, Sample, Experiment and Run accession.

Arbitrary sample attributes MUST survive normalization through the long-form attributes table.

Do not discard fields simply because they do not fit the stable wide tables.

## Milestone 5 — pure representation-selection engine

Implement:

```text
selection.py
```

as a mostly pure, independently testable layer.

Implement policies:

```text
archival
submitted
fastq
sra
all
```

Default:

```text
archival
```

Implement the exact fallback semantics from the specification.

For every selected file, generate an explicit reason explaining the choice.

Do not embed selection policy in the downloader.

## Milestone 6 — manifest

Implement:

```text
manifest.py
```

`manifest.tsv` MUST be deterministic and satisfy the exact schema specified in the contract.

The manifest MUST contain explicit:

```text
remote_url
local_relpath
representation
selection_policy
selection_reason
```

The downloader MUST later obey `local_relpath` from the manifest.

It must not reconstruct its own independent destination path.

Implement offline manifest generation from an existing valid local metadata snapshot.

## Milestone 7 — metadata snapshot transactions

Implement:

```text
metadata/snapshot.py
```

Snapshots MUST be transactional.

Never leave a mixture of previous and newly retrieved metadata as the current snapshot.

Implement:

```text
--refresh
```

as specified.

Existing metadata MUST NOT be silently overwritten.

Every raw and derived artifact referenced by `snapshot.json` MUST have:

```text
relative path
byte size
SHA-256
artifact type
```

Use atomic writes.

## Milestone 8 — downloader

Only after the inventory and manifest layers are robust, implement:

```text
downloader.py
```

Use `curl` unless there is a compelling and documented technical reason not to.

Implement:

```text
remote
   ↓
filename.part
   ↓
transfer/resume
   ↓
size validation
   ↓
ENA MD5 validation
   ↓
atomic rename
   ↓
final object
```

A successful subprocess exit is not evidence of a valid archive object.

A filename existing is not evidence of a valid archive object.

Implement:

- resumable `.part` files;

- idempotent reruns;

- verification of existing final files;

- quarantine of corrupt files;

- bounded retries;

- parallel independent downloads;

- conservative default concurrency;

- failure collection;

- persistent failure reporting.

Do not let one failed Run arbitrarily abort already-running unrelated transfers.

## Milestone 9 — superseded-object handling

Implement the repository-revision logic specified by the contract.

Historical valid objects must be distinguishable from corruption.

Use previous manifests as evidence.

Preserve superseded objects below:

```text
superseded/<snapshot-id>/
```

with their original relative path hierarchy.

Test this explicitly.

## Milestone 10 — archive validation

Implement:

```text
validation.py
```

and:

```bash
ena-project validate PATH
```

Validation must inspect the entire archive, not merely test whether files exist.

Check:

- snapshot schema;

- metadata SHA-256;

- normalized relational integrity;

- inventory consistency;

- manifest consistency;

- safe paths;

- representation values;

- byte sizes;

- MD5;

- expected downloaded objects.

Accumulate multiple validation problems where practical and report them together.

## Milestone 11 — CLI

Implement the specified commands:

```bash
ena-project metadata ...
ena-project snapshot ...
ena-project manifest ...
ena-project download ...
ena-project validate ...
ena-project metadata-normalize ...
```

The CLI should orchestrate domain modules rather than contain substantial business logic.

Implement the exit statuses from the contract and test them.

Provide useful `--help` output.

## Milestone 12 — dry-run and operational safety

Implement:

```bash
ena-project download ... --dry-run
```

It must report enough information to make a storage and archival decision before sequence transfer begins.

Implement the macOS `/Volumes` protection inherited conceptually from the NCBI application.

Never create `/Volumes/<missing-volume>` and accidentally fill the system disk.

Maintain ordinary Linux portability.

# Filesystem safety

Treat every remote filename as untrusted input.

Prevent:

```text
../
absolute path injection
path traversal
directory escape
control-character abuse
```

Every resolved target MUST remain under `OUTDIR`.

Do not execute external processes with unsafe interpolated shell strings.

Prefer argument arrays with `subprocess`.

Do not use `shell=True` unless an exceptional reason is documented and safely handled.

# Determinism

Given identical raw metadata, tool version and acquisition policy, normalized data and manifests must be deterministic.

Define stable:

- column order;

- row order;

- serialization;

- JSON formatting where appropriate.

Add tests that regenerate artifacts twice and compare bytes.

Do not embed current timestamps into artifacts that are supposed to be deterministic except where the specification explicitly defines timestamps as provenance.

# Testing requirements

Use fixture-driven tests extensively.

Normal tests MUST NOT depend on ENA being online.

Create realistic ENA fixtures covering every case listed in the specification, particularly:

```text
single submitted FASTQ
paired submitted FASTQ
three generated FASTQ files
submitted BAM
multiple submitted files
SRA-only Run
Run without submitted files
Run without generated FASTQ
cross-INSDC Run
malformed file arrays
invalid checksums
invalid byte counts
duplicate submitted basenames across Runs
path traversal
.part recovery
valid existing destination
corrupt existing destination
metadata refresh
failed metadata refresh
superseded objects
deterministic normalization
deterministic manifest
```

Use dependency injection, mocks, local HTTP fixtures or equivalent techniques so downloader behavior can be tested without large real downloads.

A small opt-in live ENA smoke-test suite MAY exist separately.

Normal CI MUST remain independent of ENA availability.

# Documentation

Create documentation appropriate for a scientific open-source repository.

At minimum provide:

```text
README.md
docs/design.md
docs/troubleshooting.md
```

Also prepare an end-to-end tutorial comparable in spirit and readability to the tutorial in `ncbi-sra-bioproject-downloader`.

The documentation must clearly explain:

- why ENA submitted files differ conceptually from generated FASTQ;

- what `archival` means;

- what fallback means;

- why `files.tsv` differs from `manifest.tsv`;

- why MD5 is used to verify the repository object;

- why metadata artifacts additionally use SHA-256 locally;

- how interruption/resume works;

- how `--refresh` works;

- how superseded objects are handled;

- why ENA and NCBI sources are kept in separate provenance directories.

Write for biologists and bioinformaticians, not only software engineers.

Avoid documentation that resembles a slide deck composed almost entirely of bullet points.

# Git discipline

Work on a dedicated feature branch if this is an existing Git repository.

Make logically coherent commits.

Do not mix unrelated refactors into the implementation.

Do not rewrite working unrelated files merely for stylistic preferences.

Before finishing:

```text
git status
```

must be understood and intentional.

Do not commit:

- downloaded sequencing data;

- large fixture binaries unless strictly necessary;

- temporary files;

- virtual environments;

- secrets;

- machine-specific paths.

# Do not over-engineer

Do not introduce:

- databases;

- workflow engines;

- containers;

- distributed execution frameworks;

- plugin systems;

- asynchronous frameworks;

- generic archive abstraction layers;

unless the normative specification explicitly requires them.

The v0.1 goal is a robust command-line scientific archiver, not a framework.

Likewise, do not prematurely build a common NCBI/ENA library.

# Dependency policy

Prefer the Python standard library where practical.

Every third-party dependency must have a clear justification.

Do not require SRA Toolkit for routine ENA FASTQ downloads.

The expected baseline remains approximately:

```text
Python >= 3.9
curl
```

Optional future SRA validation must not become an undeclared mandatory dependency.

# Error-handling philosophy

Never turn uncertainty into silent success.

Distinguish carefully between:

```text
record genuinely absent
optional metadata absent
upstream request failed
upstream response malformed
selected representation unavailable
download failed
checksum failed
archive inconsistent
repository object revised
```

These conditions have different archival meanings and should remain distinguishable in code, logs, metadata state and exit behavior.

# Work protocol

Proceed autonomously.

Do not stop after producing an implementation plan.

After understanding the specification:

1. inspect the existing NCBI repository;

2. inspect the current ENA repository workspace, if any;

3. implement the software incrementally;

4. run tests frequently;

5. fix regressions;

6. perform a final end-to-end audit against every MUST and SHALL requirement in the contract;

7. update documentation;

8. run the complete test suite;

9. report the final repository state.

If a requirement appears difficult, implement the safest specification-compliant version rather than asking to weaken it.

If a feature cannot be completed, leave the repository in a coherent, tested state and explicitly identify the unmet normative clauses.

Do not claim a requirement is complete unless it is implemented and tested.

# Final verification

Before declaring the implementation complete, create a compliance matrix mapping every numbered section of the specification to:

```text
implemented
partially implemented
not applicable
not implemented
```

For every implemented section identify the principal:

```text
module(s)
test(s)
documentation
```

Any mandatory clause marked anything other than `implemented` must be highlighted prominently.

Run at minimum:

```bash
python -m pytest
```

plus any configured linting/type-checking/test commands present in the repository.

Verify installation into a clean virtual environment if practical.

Verify:

```bash
ena-project --help
```

works from the installed package.

Perform at least one small real ENA metadata/snapshot smoke test if network access is available.

Do NOT download a large sequencing project merely to demonstrate functionality.

# Expected final report

At completion, report:

1. repository and branch used;

2. implementation summary;

3. CLI commands implemented;

4. test results;

5. small live ENA smoke-test results, if performed;

6. significant architectural choices;

7. any deviations from SHOULD requirements and their justification;

8. any unresolved mandatory requirements;

9. compliance-matrix location;

10. recommended next step toward the first release.

Do not provide only a prose claim that the software is complete. Ground the report in tests and repository state.

---

# AUTHORITATIVE SPECIFICATION

The document in .vscode/instructions/ena-project-archiver contract.md is the normative contract.

Do not summarize it before implementation.

Do not replace it with this prompt.

Do not treat this prompt as overriding any more specific requirement below.

Implement the contract exactly.
