# v0.1 Compliance Matrix

Status was audited against the authoritative 53-section contract on 2026-08-08.

| Section | Status | Principal implementation, tests, documentation |
| ---: | --- | --- |
| 1 | implemented | package workflow; full test suite; README |
| 2 | implemented | normative handling throughout; this matrix |
| 3 | implemented | models, selection; selection tests; design |
| 4 | implemented | accession, ENA client; inventory tests; README |
| 5 | implemented | separate package/repository; design |
| 6 | implemented | accession, normalize, snapshot; snapshot tests |
| 7 | implemented | exact `--outdir`; CLI tests; tutorial |
| 8 | implemented | ena_client, acquire; snapshot tests; design |
| 9 | implemented | metadata/snapshot; refresh tests; design |
| 10 | implemented | manifest and downloader paths; tests; README |
| 11 | implemented | metadata/acquire; snapshot tests; design |
| 12 | implemented | metadata/normalize and schemas; determinism tests |
| 13 | implemented | inventory; inventory tests; design |
| 14 | implemented | inventory cardinality checks; malformed tests |
| 15 | implemented | inventory versus manifest modules; deterministic tests |
| 16 | implemented | selection; policy/fallback tests; README |
| 17 | implemented | manifest; manifest tests; design |
| 18 | implemented | metadata/snapshot; refresh tests |
| 19 | implemented | snapshot artifact ledger; validation tests |
| 20 | implemented | staged refresh/archive; refresh tests; tutorial |
| 21 | implemented | downloader history matching; supersession test |
| 22 | implemented | downloader transaction; downloader tests |
| 23 | implemented | curl resume and `.part`; resume test; troubleshooting |
| 24 | implemented | downloader existing-file verification; tests |
| 25 | implemented | size plus MD5; downloader/validation tests; design |
| 26 | implemented | curl and HTTPS conversion; inventory/downloader tests |
| 27 | implemented | thread pool with `--jobs`; batch retry test |
| 28 | implemented | failure collection/report; downloader tests |
| 29 | implemented | CLI dry-run; CLI tests; tutorial |
| 30 | implemented | cli command handlers; CLI tests; README |
| 31 | implemented | accession and `.tsv` inference; CLI tests |
| 32 | implemented | validation; archive validation tests |
| 33 | implemented | host/path checks and argument arrays; safety tests |
| 34 | implemented | validate_destination; macOS safety test |
| 35 | implemented | identifying retry client; client/snapshot tests |
| 36 | implemented | snapshot and downloader logging; troubleshooting |
| 37 | implemented | CLI status mapping; CLI tests; README |
| 38 | implemented | snapshot status and retrieval failures; snapshot tests |
| 39 | implemented | schema constants and major rejection; validation tests |
| 40 | implemented | stable serializers; byte determinism tests |
| 41 | implemented | standard-library runtime plus curl; pyproject; design |
| 42 | implemented | required package modules and separated responsibilities |
| 43 | implemented | typed dataclasses; inventory/manifest tests |
| 44 | implemented | no filename biological inference; design |
| 45 | implemented | select complete representation sets; three-file test |
| 46 | implemented | offline unit and fixture-driven integration tests |
| 47 | implemented | manual live metadata smoke test; offline CI remains independent |
| 48 | implemented | snapshot-to-validation behavior covered across tests |
| 49 | implemented | anti-requirements enforced by module boundaries/tests |
| 50 | not applicable | explicitly deferred features were not introduced |
| 51 | not applicable | long-term direction documented; no premature shared library |
| 52 | implemented | evidence/inventory/decision/object layers; design |
| 53 | implemented | fixture-first metadata/selection before downloader |

## Documented SHOULD deviation

Section 8 recommends consulting ENA `returnFields`. v0.1 instead requests an explicit field list and
uses fixture and opt-in live smoke validation to expose upstream schema changes. This avoids an
additional request in every transaction. No mandatory clause is unresolved.

## Live smoke result

On 2026-08-08, installed `ena-project metadata PRJEB2772` resolved `ERP001030`, preserved and
normalized 5 Samples, 5 Experiments, 5 Runs, 10 remote files, and 110 Sample attributes, produced a
`complete` snapshot, and passed `ena-project validate`. No sequence objects were downloaded.
