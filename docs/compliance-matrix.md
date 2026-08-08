# Contract Compliance Matrix

Audit date: 2026-08-08

Authoritative contract: [SPECIFICATION.md](SPECIFICATION.md)

Audited release: `v0.1.1` (`42cf1a2`)

Offline tests: `79 passed, 1 skipped` on Python 3.9, 3.12, and 3.13

Lint: `ruff check src tests` passed

Live smoke: ENA schema probe passed; PRJEB2772 metadata snapshot was structurally valid and explicitly partial because one optional Browser XML alias timed out

Status describes demonstrated behavior, not the presence of a similarly named module.

| Section | Status | Evidence |
| ---: | --- | --- |
| 1 | implemented | `cli.py`, snapshot-to-validation tests, README |
| 2 | implemented | versioned normative specification and this audit |
| 3 | implemented | `inventory.py`, `selection.py`, representation fixtures |
| 4 | implemented | `accession.py`, CLI scope, accession tests |
| 5 | implemented | separate ENA package and provenance namespace |
| 6 | implemented | `normalize.py`, identity fixtures, snapshot tests |
| 7 | implemented | exact `--outdir`, destination tests, tutorial |
| 8 | implemented | explicit Portal fields, Browser XML preservation, opt-in `returnFields` test |
| 9 | implemented | staged validation and atomic promotion in `snapshot.py` |
| 10 | implemented | run-specific manifest paths and downloader tests |
| 11 | implemented | raw Portal/XML acquisition and artifact ledger tests |
| 12 | implemented | deterministic normalized schemas and conflict tests |
| 13 | implemented | one-object-per-row inventory and representation fixtures |
| 14 | implemented | positional cardinality validation and malformed fixtures |
| 15 | implemented | policy-independent inventory and offline manifest generation |
| 16 | implemented | all five policies, per-Run fallback, selection tests |
| 17 | implemented | strict deterministic manifest reader/writer and trust tests |
| 18 | implemented | microsecond IDs plus deterministic collision suffix tests |
| 19 | implemented | snapshot 1.1 provenance and SHA-256 artifact validation |
| 20 | implemented | refresh refusal/archive/promotion and stale-manifest tests |
| 21 | implemented | indexed manifest history and collision-safe supersession tests |
| 22 | implemented | `.part`, size/MD5 verification, atomic finalization tests |
| 23 | implemented | curl resume behavior and partial-file tests |
| 24 | implemented | verified skip, supersession, and quarantine tests |
| 25 | implemented | ENA MD5 plus byte-count verification |
| 26 | implemented | curl argument arrays, approved ENA HTTPS, raw-path retention |
| 27 | implemented | bounded thread pool and independent failure collection |
| 28 | implemented | batch retry passes and stable failure report tests |
| 29 | implemented | per-Run/file accounting, IEC sizes, capacity warning tests |
| 30 | implemented | all specified commands plus metadata-only validation mode |
| 31 | implemented | conservative accession/file inference and semantic errors |
| 32 | implemented | structural, relational, manifest, and downloaded-object validation |
| 33 | implemented | centralized URL/path trust and adversarial manifest tests |
| 34 | implemented | macOS `/Volumes` mount guard and portability tests |
| 35 | partially implemented | identifying retry client; XML retrieval is bounded but sequential rather than concurrent |
| 36 | partially implemented | timestamped operational logs exist, but not every listed summary event has a dedicated log record |
| 37 | implemented | documented/tested semantic exits and incomplete-download status |
| 38 | implemented | complete/partial status and required-vs-optional retrieval handling |
| 39 | implemented | independent schema constants and centralized major compatibility checks |
| 40 | implemented | stable ordering/serialization and determinism tests |
| 41 | implemented | Python 3.9+, empty runtime dependencies, external curl only |
| 42 | implemented | separated package responsibilities; trust helper is adjacent support |
| 43 | partially implemented | typed biological/file/manifest models exist; snapshot remains validated JSON rather than a dataclass |
| 44 | implemented | no filename-derived biological semantics |
| 45 | implemented | every file in a selected representation, including three-FASTQ fixture |
| 46 | partially implemented | broad persisted scenario corpus and 74 offline tests; some lifecycle fixtures are still constructed in tests |
| 47 | implemented | offline suite skips network; live schema and metadata smoke paths are opt-in |
| 48 | implemented | complete fixture lifecycle covered across snapshot/download/validation tests |
| 49 | implemented | anti-requirements enforced by architecture and adversarial tests |
| 50 | not applicable | deferred transports/object classes were not introduced |
| 51 | not applicable | no premature shared NCBI/ENA library extraction |
| 52 | implemented | evidence, inventory, decision, and verified-object layers remain distinct |
| 53 | implemented | inventory/selection correctness preceded and remains separate from transfer mechanics |

## Remaining SHOULD deviations

- Browser XML retrieval is sequential. It has bounded attempts/backoff, but no bounded concurrent fetch pool.
- Logging records transactions and transfer events but does not emit every summary named in section 36.
- Snapshot provenance is explicit validated JSON rather than an additional typed `Snapshot` model.
- The fixture corpus is persisted and substantially broader, but a few lifecycle corruptions are created by test code from persisted base fixtures.
- Live ENA checks are deliberately opt-in and do not run in ordinary CI.

## Known limitations

- Version 0.1 rejects multi-Study project-level reports and asks the user to archive a specific Study.
- Only HTTPS objects on the approved ENA host are accepted; alternative transports are deferred.
- Browser XML failures produce an explicit partial snapshot rather than making the required Portal inventory unusable.
- Validation verifies repository size and MD5, not format-level FASTQ/BAM/SRA semantics.

## Live smoke details

The opt-in ENA `returnFields?result=read_run` test passed. A metadata-only PRJEB2772 acquisition
resolved PRJEB2772/ERP001030 and normalized 5 Samples, 5 Experiments, 5 Runs, 10 remote files,
and 55 canonicalized Sample attributes. One optional Browser XML alias timed out; the transaction
recorded that warning, returned partial status, promoted a coherent snapshot, and passed
`validate --metadata-only`. No sequence objects were downloaded.
