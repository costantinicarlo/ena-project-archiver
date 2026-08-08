# From an ENA Study to a Verifiable Local Archive

Choose a durable location that makes repository provenance visible. For a BioProject available
through several repositories, a useful structure is
`BIOPROJECTS/PRJEB123456/sources/ena`. The directory passed to `--outdir` is exactly the ENA unit;
the program does not invent a global archive root.

Start with a snapshot, not a sequence transfer:

```bash
PROJECT=PRJEB123456
OUTDIR=/path/to/BIOPROJECTS/$PROJECT/sources/ena
ena-project snapshot "$PROJECT" --outdir "$OUTDIR"
```

The raw Portal report and Browser XML are evidence of what ENA returned. The derived tables make
that evidence easier to inspect. Review `project.json`, `samples.tsv`, `experiments.tsv`, and
`runs.tsv`. Arbitrary Sample fields remain in `sample_attributes.tsv` instead of being discarded.

Next compare `files.tsv` with `manifest.tsv`. The first answers "what representations did ENA
advertise?" The second answers "what did the archival policy choose, and why?" Submitted files are
original repository objects. Generated FASTQ is standardized for analysis and may not be the
submitter's original format. Fallback reasons make that distinction visible for each Run.

Validate metadata and measure the acquisition before transferring data:

```bash
ena-project validate "$OUTDIR"
ena-project download "$OUTDIR/manifest.tsv" --outdir "$OUTDIR" --dry-run
```

The dry run reports project identity, record and representation counts, selected bytes, destination
capacity, and policy reasons. Leave headroom for partial files and filesystem overhead.

Start conservatively:

```bash
ena-project download "$OUTDIR/manifest.tsv" --outdir "$OUTDIR" --jobs 2
```

An interruption is not a failed archive. Rerun the same command; verified finals are skipped and
partials resume. After acquisition, validate again. ENA MD5 confirms that sequence bytes match the
advertised repository objects, while SHA-256 protects local metadata artifacts.

When ENA metadata changes, refresh without erasing history:

```bash
ena-project snapshot "$PROJECT" --outdir "$OUTDIR" --refresh
```

Compare the archived and current manifests. If ENA replaced an object at an existing path, the
next download preserves bytes matching the old manifest under `superseded/` and acquires the new
object. This is repository revision, not corruption.

Derived products can be rebuilt without ENA:

```bash
ena-project metadata-normalize --metadata-dir "$OUTDIR/metadata"
ena-project manifest "$OUTDIR/metadata/derived/files.tsv" \
  --representation archival --output "$OUTDIR/manifest.tsv"
```

That offline path is why raw evidence, inventory, policy, manifest, and downloaded bytes remain
separate throughout the archive.
