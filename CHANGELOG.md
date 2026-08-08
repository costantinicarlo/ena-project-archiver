# Changelog

All notable changes to this project are documented here. No `0.2.0` release was published; that label appeared only in pre-release development history.

## 0.1.2 - 2026-08-08

### Fixed

- Apply macOS `/Volumes` mount validation after resolving relative and symlinked destinations.

## 0.1.1 - 2026-08-08

Patch release tightening archive safety and provenance validation.

### Fixed

- Enforced true mount-point validation for macOS `/Volumes` destinations so ordinary writable directories are rejected.
- Rejected explicit manifest inputs that conflict with the existing archive snapshot to avoid cross-project contamination.
- Strengthened metadata validation to compare the full regenerated manifest content against the manifest on disk, including provenance fields.

## 0.1.0 - 2026-08-08

First public release, including the initial implementation and its pre-release hardening.

### Added

- ENA Portal and Browser API acquisition with preserved raw evidence.
- Deterministic Study, Sample, Experiment, Run, and one-file-per-row inventory products.
- Pure submitted, FASTQ, SRA, archival, and all representation policies.
- Transactional metadata refresh and offline normalization or manifest generation.
- Resumable curl downloads with size and MD5 verification, quarantine, and supersession history.
- Whole-archive validation, dry-run storage reporting, macOS volume protection, and semantic exits.
- Strict manifest trust preflight and accession/policy-safe offline reuse.
- Metadata-only structural validation before snapshot promotion.
- Collision-safe snapshot and superseded-object history handling.
- Per-Run dry-run accounting, IEC capacity output, and `--batch-attempts`.
- Snapshot runtime provenance, opt-in ENA schema smoke testing, CI, citation metadata, and expanded fixtures.

### Changed

- Snapshot schema is 1.1; independent artifact schemas now evolve separately.
- Multi-Study project reports and conflicting biological identities fail explicitly.
- `--attempts` on `download` is a temporary deprecated alias for `--batch-attempts`.
