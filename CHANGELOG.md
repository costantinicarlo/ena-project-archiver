# Changelog

All notable changes to this project are documented here.

## 0.2.0 - 2026-08-08

### Added

- Strict manifest trust preflight and accession/policy-safe offline reuse.
- Metadata-only structural validation before snapshot promotion.
- Collision-safe snapshot and superseded-object history handling.
- Per-Run dry-run accounting, IEC capacity output, and `--batch-attempts`.
- Snapshot runtime provenance, opt-in ENA schema smoke testing, CI, citation metadata, and expanded fixtures.

### Changed

- Snapshot schema is 1.1; independent artifact schemas now evolve separately.
- Multi-Study project reports and conflicting biological identities fail explicitly.
- `--attempts` on `download` remains temporarily available as a deprecated alias.

## 0.1.0 - 2026-08-08

### Added

- ENA Portal and Browser API acquisition with preserved raw evidence.
- Deterministic Study, Sample, Experiment, Run, and one-file-per-row inventory products.
- Pure submitted, FASTQ, SRA, archival, and all representation policies.
- Transactional metadata refresh and offline normalization or manifest generation.
- Resumable curl downloads with size and MD5 verification, quarantine, and supersession history.
- Whole-archive validation, dry-run storage reporting, macOS volume protection, and semantic exits.
