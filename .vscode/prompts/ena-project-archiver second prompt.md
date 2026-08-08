# Post-implementation audit and corrective task for `ena-project-archiver`

You are working on:

```text
costantinicarlo/ena-project-archiver
```

Primary target repository:

```text
costantinicarlo/ena-project-archiver
```

Read-only architectural reference:

```text
costantinicarlo/ncbi-sra-bioproject-downloader
```

Your task is to perform a corrective hardening and harmonisation pass on the ENA repository.

Do **not** rewrite the application from scratch. The present implementation gets the central architecture right: raw ENA evidence, normalized inventory, explicit representation selection, immutable manifest, transactional downloads, MD5 verification, supersession history, and separate ENA provenance should all be retained.

The purpose of this task is to correct specific contract-compliance gaps found during an independent source audit, strengthen tests, and harmonize user-facing conventions with the NCBI sibling where doing so does not weaken the ENA design.

Do not modify `ncbi-sra-bioproject-downloader` during this task. Treat it as a read-only reference. At the end, report changes that would be worth backporting to the NCBI application separately.

The authoritative contract remains the 53-section document:

```text
ENA Project Archiver — Formal Design and Implementation Specification
```

Do not replace that contract with `docs/compliance-matrix.md`.

Before changing code, inspect current HEAD because some findings may already have been corrected after this audit. If a finding has already been fixed, verify it with tests rather than reimplementing it.

---

## Overall audit conclusion

The implementation is substantially correct, but `docs/compliance-matrix.md` currently overstates compliance by claiming that all mandatory clauses are implemented.

Do not preserve that claim merely for continuity.

Correct the implementation first, rerun the audit, and then update the matrix to reflect demonstrated behavior.

Treat the following tasks in priority order.

---

## P0 — Fix the manifest trust boundary before any further release

The downloader must not trust arbitrary TSV content merely because it has the correct column names.

Currently, `read_manifest()` performs only limited path checking. A manually created manifest can provide an arbitrary `remote_url`, and `download_one()` will pass it directly to curl.

This violates the contract requirement that downloads originate from expected ENA/EBI sources unless an alternative trusted source is explicitly enabled.

Refactor URL validation into a reusable helper shared by inventory parsing and manifest parsing.

For v0.1-generated sequence objects, accept only the transport/source combinations actually supported by this application. In practice, generated manifests currently use HTTPS access to ENA objects such as:

```text
https://ftp.sra.ebi.ac.uk/...
```

Do not permit:

```text
file://
http://localhost/
arbitrary https hosts
relative URLs
SSH/SFTP URLs
```

or any other untrusted source merely because it appears in a TSV.

A user-supplied manifest must undergo complete preflight validation **before curl can be invoked**.

At minimum, `read_manifest()` or an immediately adjacent strict validation layer must reject:

```text
unsupported schema major version
unknown representation
unknown selection policy
non-positive file_index
non-positive size_bytes
invalid MD5
unsafe run accession
unsafe filename
unsafe local_relpath
remote URL on an unapproved host
remote URL using an unsupported protocol
duplicate canonical file identities
duplicate local_relpath values
```

Validate that a manifest's canonical local path is structurally compatible with:

```text
representation/run_accession/file_name
```

The downloader must still obey the manifest's explicit `local_relpath`; do not move destination-path policy into the downloader. Validation of the manifest format and execution of the manifest are separate responsibilities.

Add adversarial tests including a manifest containing:

```text
file:///etc/passwd
https://example.org/file.fastq.gz
../escape
negative byte counts
schema_version=99.0
unknown representation
duplicate local destinations
```

No network/process invocation may occur for a manifest that fails preflight.

---

## P0 — Bind accession-driven downloads to the requested project and policy

Correct `_load_download_input()` and related CLI logic.

The following operation must never silently succeed by using an unrelated existing manifest:

```bash
ena-project download PRJEB_NEW \
    --outdir /archive/PRJEB_OLD/sources/ena
```

Before reusing an existing snapshot or manifest for accession-driven download, establish that the local provenance belongs to the requested accession.

Check the requested accession against the current snapshot's:

```text
input_accession
project_accession
study_accession
```

using the correct alias semantics.

A PRJ accession may legitimately correspond to the stored canonical project while an ERP/SRP/DRP accession may correspond to the stored Study identity. Do not require literal equality across identifier namespaces.

If the requested accession does not identify the local snapshot, stop with exit status 2 and a clear message.

Do not silently refresh, replace, or repurpose the directory.

Likewise, do not ignore:

```bash
--representation fastq
```

merely because an existing `manifest.tsv` was generated with:

```text
selection_policy=archival
```

If the requested representation policy differs from the existing manifest policy and the current metadata snapshot is valid, rebuild the manifest **offline** from:

```text
metadata/derived/files.tsv
metadata/derived/runs.tsv
```

using the requested policy.

Do not contact ENA merely to change selection policy.

If an existing metadata snapshot matches the requested accession but no manifest exists, `download ACCESSION` should generate the required manifest offline rather than failing with “use --refresh”.

The expected state machine is approximately:

```text
requested accession
        ↓
current metadata exists?
        │
       yes
        ↓
identity matches?
   no → fail safely
        │
       yes
        ↓
valid inventory exists?
   no → fail / explicit refresh needed
        │
       yes
        ↓
manifest exists with requested policy?
        │
   yes ─┴─> use it
        │
       no
        ↓
rebuild manifest offline
        ↓
download
```

Add tests for:

```text
correct accession + existing matching manifest
wrong accession + existing manifest
correct accession + wrong manifest policy
metadata-only snapshot followed by accession download
PRJ alias versus ERP alias for same snapshot
```

---

## P0 — Handle multi-Study BioProjects explicitly

ENA permits one `PRJ*` BioProject to be linked to more than one Study.

The current normalization logic collects all secondary Study accessions but effectively chooses:

```python
study_accessions[0]
```

and subsequently writes that one Study identity into normalized records.

This can silently falsify provenance.

Do not retain this behavior.

For v0.1, the preferred conservative solution is:

**reject a project-level file report containing more than one distinct secondary Study accession.**

Raise a clear error such as:

```text
BioProject PRJ... contains multiple ENA Studies (ERP..., ERP...).
v0.1 archives one Study acquisition unit at a time.
Repeat the command using a specific ERP/SRP/DRP accession.
```

Do not discard the raw response before reporting the problem if the transaction architecture can retain diagnostic evidence safely.

A future release may support a true one-project-to-many-studies model, but do not implement that casually because it requires schema changes throughout Project, Experiment, Run and manifest normalization.

Also reject contradictory cases where a supposedly single acquisition contains multiple incompatible canonical project accessions.

Verify that the user-supplied accession is actually represented by the returned ENA project/Study identities. Do not merely assume that a successful HTTP response corresponds to the requested object.

Add fixtures for:

```text
one PRJ + one ERP
one PRJ + multiple ERPs
PRJNA + SRP
PRJDB + DRP
returned accession inconsistent with requested accession
```

---

## P0 — Validate the staged metadata snapshot before promotion

The contract requires:

```text
retrieve into staging
        ↓
validate staging
        ↓
archive previous state
        ↓
promote new state
```

At present, normalization errors prevent some malformed snapshots, but there is no complete structural snapshot validation pass before promotion.

Refactor validation into two layers.

Create a metadata/snapshot structural validator that can run before sequence files exist.

It must verify at least:

```text
snapshot schema
snapshot provenance identity
artifact ledger
normalized table headers
unique Sample accessions
unique Experiment accessions
unique Run accessions
Sample → Experiment relationships
Experiment → Run relationships
SampleAttribute → Sample relationships
inventory → Run/Experiment/Sample relationships
unique inventory file identity
manifest → inventory identity
selection-policy consistency
canonical local paths
snapshot record counts
```

Invoke this validator against the staged acquisition **before** replacing the current snapshot.

A malformed staged snapshot must never become current.

If refresh validation fails, the previous current snapshot and manifest must remain byte-for-byte unchanged.

Add a test that creates a deliberately inconsistent staged dataset and proves that refresh refuses promotion.

Do not use full downloaded-data validation for this stage because no sequence files need exist yet.

---

## P1 — Make pre-download and post-download validation semantics unambiguous

The current documentation recommends:

```bash
ena-project snapshot ...
ena-project validate ...
ena-project download ...
```

but the current full validator considers manifest objects missing before they have been downloaded.

Do not weaken full archive validation merely to make the tutorial pass.

Preserve this semantic:

```bash
ena-project validate OUTDIR
```

means full archive validation and therefore checks expected downloaded objects whenever a manifest exists.

Add a clearly named metadata-only validation mode, for example:

```bash
ena-project validate OUTDIR --metadata-only
```

or an equivalently unambiguous interface.

That mode should call the same structural validator used before snapshot promotion.

Then update README and tutorial to use:

```text
snapshot
→ metadata-only validation
→ dry-run
→ download
→ full validation
```

This also restores conceptual harmony with the NCBI sibling, whose `validate` command is principally useful before sequence acquisition, without weakening the ENA contract.

Document the distinction explicitly.

---

## P1 — Harden uniqueness and relational validation

Do not use sets of whole dataclass records as a substitute for checking uniqueness of biological accessions.

During normalization, handle records by primary identity.

For:

```text
sample_accession
experiment_accession
run_accession
```

allow repeated identical upstream records to collapse deterministically if necessary, but reject conflicting metadata for the same accession.

Do not emit two rows with the same biological accession merely because another column differs.

This is important for both correctness and determinism.

For example, instead of:

```text
set(SampleRecord(...))
```

use keyed normalization with explicit conflict detection.

A conflicting repeated accession must generate a useful normalization error.

The validator must also detect duplicates even if a hand-edited TSV bypasses normalization.

For `files.tsv`, uniqueness must not be defined using the whole tuple:

```text
run
representation
file_index
URL
MD5
size
```

because two contradictory records with the same logical file index but different URLs would evade that test.

At minimum, treat:

```text
(run_accession, representation, file_index)
```

as the logical positional identity and reject contradictory duplicate definitions.

Also validate that inventory rows reference the same:

```text
experiment_accession
sample_accession
project/study identity
```

as the normalized Run model.

---

## P1 — Make snapshot identifiers collision-safe

Current snapshot identifiers have second-level precision:

```text
YYYYMMDDTHHMMSSZ
```

A refresh performed within the same second can therefore collide with the current or archived snapshot identifier.

Capture the transaction time once and derive both:

```text
snapshot_id
created_at
```

from that same value.

Guarantee uniqueness.

Acceptable approaches include:

```text
UTC timestamp with microseconds
```

or a deterministic collision suffix when the timestamp identifier already exists.

Do not generate two logically distinct snapshots with the same ID.

Add a regression test for two successful snapshots/refreshes occurring within the same nominal second.

---

## P1 — Fix manifest lifecycle during metadata-only acquisition

Review `create_snapshot()` carefully.

A top-level `manifest.tsv` is currently moved aside whenever a snapshot transaction occurs, including cases where no previous metadata snapshot exists.

A metadata-only command must never silently destroy an orphan/pre-existing manifest.

Use conservative provenance semantics.

If:

```text
metadata/snapshot.json does not exist
```

but:

```text
manifest.tsv exists
```

do not guess what that manifest belongs to.

Fail clearly and ask the user to resolve the provenance conflict, or implement an explicit verified adoption pathway. Do not silently delete it.

For a genuine metadata refresh where both current metadata and its current manifest exist:

```text
ena-project metadata ... --refresh
```

archive the old manifest together with the old snapshot.

Because the new metadata-only snapshot has no newly selected acquisition decision, the stale top-level manifest should not remain masquerading as current.

That removal is legitimate only because its provenance has first been preserved under the archived previous snapshot.

Log this event clearly.

Add tests for both situations.

---

## P1 — Validate the exact file-report schema returned by ENA

The ENA client explicitly requests `FILEREPORT_FIELDS`, which is good.

However, do not assume that ENA returned every requested field simply because the request returned HTTP 200.

Before normalization, validate the file-report header against the fields the implementation requires.

ENA documents that explicitly requested fields are returned as requested and in request order, so unexpected omissions or schema changes should fail conspicuously rather than become empty normalized columns.

Add tests for:

```text
missing requested field
unexpected duplicate header
missing run_accession
changed/unknown mandatory field
```

Keep the current explicit-field request.

In addition, satisfy the specification's `returnFields` robustness recommendation without adding a schema-discovery call to every normal transaction.

Add an **opt-in live schema smoke test** that queries ENA's `returnFields?result=read_run` endpoint and asserts that every required field used by `FILEREPORT_FIELDS` still exists.

Normal unit tests and CI must remain capable of running offline.

---

## P1 — Correct dry-run accounting

Dry-run currently counts selection reasons per **file**.

Fallback is conceptually a **per-Run decision**.

If a FASTQ fallback Run has three generated FASTQ files, the user should see one fallback Run, not three fallback events.

Report both quantities separately.

For example:

```text
Runs: 187

Representation selected by Run:
185 submitted
  2 sra
  0 fastq

Selected physical files:
370 submitted
  2 sra
  0 fastq

Fallback Runs:
2 submitted_not_available_from_ena

Selected bytes:
...
```

Also add an explicit warning when remaining required bytes exceed available filesystem space.

Do not fail the dry run merely because space is insufficient unless a future explicit option requests strict capacity enforcement.

For usability and harmonisation with `sra-bioproject`, report both exact bytes and human-readable IEC units where practical.

---

## P1 — Align retry option naming with the NCBI sibling

The two sibling CLIs currently use different terminology for transfer retry passes.

NCBI uses:

```text
--batch-attempts
```

whereas ENA download currently uses:

```text
--attempts
```

for the same high-level batch concept, while `--attempts` elsewhere means HTTP request attempts.

This is unnecessarily confusing.

Introduce:

```text
--batch-attempts
```

for ENA download retry passes.

If backwards compatibility with released 0.1.0 matters, retain:

```text
--attempts
```

as a deprecated alias for one release.

Do not create two independent values.

Document clearly:

```text
metadata/snapshot --attempts
    = ENA HTTP request attempts

download --batch-attempts
    = retry passes for files still failing
```

Keep `--metadata-attempts` if accession-driven download needs independent metadata request retry control.

---

## P1 — Put the actual specification under version control

The repository currently contains:

```text
docs/compliance-matrix.md
```

but not the authoritative specification against which that matrix claims compliance.

Add:

```text
docs/SPECIFICATION.md
```

containing the complete 53-section:

```text
ENA Project Archiver — Formal Design and Implementation Specification
```

**verbatim**.

Do not reconstruct the specification from the compliance matrix.

Do not paraphrase it.

If the authoritative contract is not present in your task context, stop and obtain the original document rather than inventing one.

Update the compliance matrix to link explicitly to `SPECIFICATION.md`.

Record the Git commit SHA against which each formal compliance audit is performed.

Do not label a mandatory section `implemented` merely because a similarly named module exists. The behavior must be implemented and tested.

---

## P1 — Expand the fixture corpus to meet the actual contract

The current repository has only a very small number of persisted fixture files and synthesizes many edge cases directly in Python tests.

That is useful unit testing, but it does not fully satisfy the contract's fixture-driven coverage requirement.

Add small deterministic fixture datasets representing at least:

```text
PRJEB + ERP
PRJNA + SRP
PRJDB + DRP

cross-INSDC run with submitted files unavailable

single submitted FASTQ
paired submitted FASTQ
three generated FASTQs
submitted BAM
SRA-only Run

missing submitted representation
missing generated FASTQ
only one usable representation

malformed URL/MD5 cardinality
malformed URL/byte cardinality
invalid MD5
invalid byte count
empty file-array member

multi-Study PRJ project
duplicate conflicting Sample
duplicate conflicting Experiment
duplicate conflicting Run
duplicate inventory file index

malicious manifest URL
path traversal
unsupported manifest schema

snapshot-ID collision
failed staged refresh
```

Fixtures should remain tiny text/XML/TSV resources.

Do not add real sequencing files of meaningful size to Git.

---

## P2 — Improve superseded-history scaling and collision safety

`historical_entries()` currently rescans archived manifests repeatedly for individual files.

For a project containing hundreds or thousands of Run files and several metadata revisions, this can become unnecessarily expensive.

Build a historical manifest index once per download transaction, keyed by at least:

```text
local_relpath
```

and make it available to workers safely.

Do not repeatedly parse every archived manifest for every file.

Also protect `superseded/<snapshot-id>/...` from accidental overwrite.

If a superseded destination already exists:

1. verify whether it contains the same historical object;

2. reuse/skip it if identical;

3. otherwise choose a collision-safe preservation path or fail explicitly.

Never overwrite one valid historical object with another merely because their intended supersession paths collide.

Correctness takes priority over optimization.

---

## P2 — Harmonise repository-level scientific software metadata

The NCBI sibling already contains:

```text
CITATION.cff
THIRD_PARTY_NOTICES.md
```

Add equivalent files to `ena-project-archiver`.

`CITATION.cff` should describe:

```text
ENA Project Archiver
Carlo Costantini
MIT
current application version
repository URL
ENA / genomics / archival-data keywords
```

Do not copy the NCBI title or version.

`THIRD_PARTY_NOTICES.md` should explain that the MIT license applies to this repository's original software/documentation and does not relicense:

```text
ENA metadata
ENA/INSDC sequence files
curl
example repository responses/fixtures derived from ENA
other externally sourced scientific material
```

Harmonize `pyproject.toml` where sensible by explicitly declaring:

```toml
license-files = ["LICENSE"]
dependencies = []
```

Retain the ENA repository's useful Ruff development configuration; harmonisation does not mean deleting improvements that the older sibling lacks.

---

## P2 — Improve snapshot provenance to match the stronger parts of the NCBI sibling

The ENA snapshot currently records the essential source transaction, but the NCBI sibling records useful execution-environment provenance that would also benefit ENA.

Without changing the fundamental schema casually, consider adding compatible provenance fields such as:

```text
application
application_version
python_version
platform
sanitized command invocation
```

Continue recording API request URLs/statuses.

Never record credentials, tokens or other secrets.

If adding fields is compatible with schema 1.x, increment the appropriate minor schema version rather than pretending the schema is unchanged.

This leads into the next task.

---

## P2 — Decouple schema versions

The current ENA implementation uses one global:

```text
SCHEMA_VERSION = "1.0"
```

for multiple logically distinct artifacts.

Separate schema constants for independently evolving artifacts, for example:

```text
SNAPSHOT_SCHEMA_VERSION
PROJECT_SCHEMA_VERSION
INVENTORY_SCHEMA_VERSION
MANIFEST_SCHEMA_VERSION
```

and, if useful:

```text
NORMALIZED_TABLE_SCHEMA_VERSION
```

Do not increment unrelated formats merely because one representation changes.

All readers must reject unsupported **major** versions.

Compatible additive changes should increment minor versions.

Provide centralized helpers for parsing/comparing schema versions so snapshot, inventory and manifest readers do not implement subtly different rules.

Preserved v1.0 files must remain readable.

---

## P2 — Bring the ENA tutorial to the documentation standard of the NCBI sibling

The ENA tutorial is presently much shorter than the handbook-style NCBI tutorial.

Expand it substantially.

Write for a biologist or budding bioinformatician who starts with a project or Study accession found in a publication and wants to create a durable local archive.

Cover end to end:

```text
finding/understanding accession types
PRJ versus ERP/SRP/DRP
choosing sources/ena directory
installation
snapshot
metadata inspection
files.tsv versus manifest.tsv
archival policy
submitted versus generated FASTQ versus SRA
metadata-only validation
dry run
capacity planning
download
monitoring
interruption/resume
full validation
refresh
superseded objects
offline policy changes
metadata normalization
common failure recovery
```

Make the prose readable and continuous rather than a presentation-like series of terse bullets.

Explicitly explain that ENA-generated FASTQ is not necessarily the original submitted representation.

Correct the currently invalid pre-download `validate` workflow when the metadata-only validation mode is introduced.

---

## P2 — Add continuous integration

There is currently no repository-level CI visible in the project root.

Add a modest GitHub Actions workflow that runs:

```text
python -m pytest
ruff check src tests
```

on push and pull request.

Test at least:

```text
the minimum claimed Python version
one representative modern Python version
```

If practical, include the current stable Python version as well.

Do not make normal CI depend on live ENA services.

Keep live ENA smoke tests explicitly opt-in or separately scheduled/manual.

If the project continues to claim:

```text
Python >= 3.9
```

the minimum-version job must actually exercise Python 3.9 until that support claim is intentionally changed in a future release.

---

## Preserve these existing design decisions

Do **not** regress the following correct behavior while implementing the fixes:

```text
separate ENA repository
separate ENA provenance namespace
one physical remote object per RemoteFile
positional URL/MD5/byte pairing
malformed ≠ unavailable
submitted > SRA > FASTQ archival fallback
all files of selected representation
run-specific destination directories
preservation of submitted filenames
no filename-based biological inference
curl .part downloads
size + ENA MD5 verification
atomic finalization
idempotent existing-file verification
corrupt-file quarantine
valid repository revision → superseded/, not .bad
transactional refresh
raw Browser/Portal response preservation
long-form arbitrary Sample attributes
offline manifest generation
offline metadata normalization
macOS /Volumes safety
no mandatory SRA Toolkit dependency
no premature shared NCBI/ENA library
```

Do not weaken ENA functionality merely to make its code look more like the older NCBI repository.

Harmonise user concepts and mature operational conventions, not historical weaknesses.

---

## Suggested NCBI backports — report only, do not implement here

At completion, identify changes from this audit that should later be considered for `ncbi-sra-bioproject-downloader`.

Likely candidates include:

```text
CI
stronger manifest trust/preflight
more transactional refresh behavior
schema-version helpers
provenance consistency
download-incomplete exit-status harmonisation
dry-run/reporting conventions
```

Do not modify that repository in this task.

---

## Required regression tests

In addition to existing tests, there must be explicit regression tests proving all of these statements:

```text
An arbitrary remote URL in a manifest cannot reach curl.

A manifest with a future unsupported major schema is rejected.

An accession download cannot reuse another project's manifest.

A requested FASTQ policy cannot silently use an archival manifest.

A metadata-only snapshot can later generate the requested manifest offline.

A PRJ with multiple secondary Studies is not silently collapsed.

Conflicting duplicate biological accessions fail normalization.

Conflicting duplicate file indexes fail validation.

A staged inconsistent refresh cannot replace the current snapshot.

Two refreshes in the same second receive distinct snapshot IDs.

An orphan manifest is not silently deleted by metadata acquisition.

Dry-run fallback counts are Run counts, not file counts.

Metadata-only validation succeeds before download.

Full validation fails when manifest data objects are missing.

Full validation succeeds after verified objects are present.

Malformed or hostile paths remain inside OUTDIR or are rejected.

Superseded historical data cannot be silently overwritten.
```

Keep normal tests offline and deterministic.

---

## Compliance-matrix correction

After implementation, audit the repository afresh against every one of the 53 sections.

Update:

```text
docs/compliance-matrix.md
```

Do not preserve the existing statuses automatically.

For each section, record:

```text
implemented
partially implemented
not applicable
not implemented
```

and identify the exact modules and tests.

Include:

```text
audit date
audited Git commit SHA
test-suite result
lint result
live smoke-test result, if one was deliberately run
```

Document any remaining SHOULD deviation.

Any mandatory clause that is not fully implemented must remain visibly marked.

---

## Final verification

Before finishing, run at minimum:

```bash
python -m pytest
ruff check src tests
```

Perform a clean installation test:

```bash
python3 -m venv <temporary-venv>
<temporary-venv>/bin/python -m pip install .
<temporary-venv>/bin/ena-project --help
```

Exercise a complete fixture-based lifecycle:

```text
snapshot
→ metadata-only validate
→ dry run
→ simulated/local verified download
→ full validate
→ refresh
→ supersession scenario
```

If network access is available, run one **small metadata-only** live ENA smoke test.

Do not download a large public sequencing project merely for validation.

Check repository state deliberately before reporting completion.

---

## Final report

Return a concise engineering report containing:

```text
branch and commit
issues corrected
files changed
new regression tests
pytest result
ruff result
clean-install result
live ENA smoke result, if performed
updated contract compliance status
remaining SHOULD deviations
remaining known limitations
recommended NCBI backports
recommended release version
```

Do not claim complete compliance unless the corrected compliance matrix is supported by executable tests and the actual implementation.

Given the scope of these fixes, if `0.1.0` has already been publicly tagged/released, do not rewrite that release. Prepare the changes as a new patch release for strictly corrective backward-compatible hardening, or as a future minor release if CLI/schema-visible changes are substantial.
