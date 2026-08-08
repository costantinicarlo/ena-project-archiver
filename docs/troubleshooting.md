# Troubleshooting

## A snapshot already exists

Metadata is intentionally immutable by default. Inspect and validate the current state, then use
`--refresh` only when a new ENA view is desired:

```bash
ena-project snapshot PRJEB123 --outdir "$OUTDIR" --refresh
```

The previous state remains under `metadata/archive/`. If retrieval fails, rerun later; the current
snapshot was not replaced.

## Download interruption

Rerun the same manifest command. Keep `.part` files: curl resumes them where supported. Completed
objects are checked by byte count and MD5 and skipped, so reruns concentrate on unfinished files.

```bash
ena-project download "$OUTDIR/manifest.tsv" --outdir "$OUTDIR" \
    --jobs 1 --batch-attempts 3
cat "$OUTDIR/logs/failed_accessions.txt"
```

Lowering jobs can help an unstable network or a slow destination disk. Curl exit 35 usually means
a TLS transport interruption; exit 60 indicates certificate-chain validation failure. Correct the
host trust path rather than disabling TLS verification.

## Bad and superseded files

`.bad.<timestamp>` means the bytes matched neither the current manifest nor recognized history.
Preserve the file while investigating storage or transport failures, then rerun acquisition.

`superseded/<snapshot-id>/...` has a different meaning: those bytes matched an older manifest and
remain valid evidence of an earlier ENA object. They should not be deleted as corruption.

## macOS volumes

For destinations below `/Volumes`, the named volume must already exist and be writable. Check its
exact name before launching a large acquisition:

```bash
ls -la /Volumes
df -h /Volumes/Research
```

The program will not create `/Volumes/<missing-name>` because that could fill the system disk.

## Validation failures

Before downloading sequence objects, use `ena-project validate "$OUTDIR" --metadata-only` to check
snapshot structure and relationships. Full validation intentionally reports missing manifest
objects until acquisition completes.

Run `ena-project validate "$OUTDIR"` to collect metadata checksums, relationships, inventory,
manifest, path, size, and MD5 problems in one report. Restore metadata from a verified archived
snapshot or reacquire a failed sequence object; do not edit checksums merely to silence validation.
