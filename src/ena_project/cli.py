"""Command-line orchestration for ENA project archival workflows."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from collections import Counter
from pathlib import Path

from .accession import AccessionError, parse_accession
from .downloader import (
    download_batch,
    find_curl,
    safe_destination,
    validate_destination,
    verify_file,
)
from .ena_client import EnaClient, EnaRequestError
from .inventory import InventoryError, read_inventory
from .manifest import (
    ManifestError,
    manifest_from_inventory,
    read_manifest,
    write_manifest,
)
from .metadata.snapshot import create_snapshot, normalize_existing
from .selection import POLICIES, SelectionError
from .validation import validate_archive, validate_metadata


def positive_integer(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def configure_logging(outdir: Path | None, verbose: bool) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if outdir is not None:
        log_path = outdir / "logs" / "download.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
        force=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ena-project",
        description="Preserve ENA metadata and acquire verified raw-read files.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("metadata", "retrieve and normalize ENA metadata"),
        ("snapshot", "retrieve metadata and create an acquisition manifest"),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("accession")
        command.add_argument("--outdir", type=Path, required=True)
        command.add_argument("--refresh", action="store_true")
        command.add_argument("--timeout", type=positive_integer, default=60)
        command.add_argument("--attempts", type=positive_integer, default=4)
        command.add_argument("--verbose", action="store_true")
        if name == "snapshot":
            command.add_argument("--representation", choices=POLICIES, default="archival")
        command.set_defaults(handler=run_metadata)

    manifest = subparsers.add_parser("manifest", help="build a manifest from local files.tsv")
    manifest.add_argument("inventory", type=Path)
    manifest.add_argument("--representation", choices=POLICIES, default="archival")
    manifest.add_argument("--output", type=Path, required=True)
    manifest.set_defaults(handler=run_manifest)

    download = subparsers.add_parser("download", help="download from an accession or manifest")
    download.add_argument("input")
    download.add_argument("--outdir", type=Path, required=True)
    download.add_argument("--representation", choices=POLICIES, default="archival")
    download.add_argument("--jobs", type=positive_integer, default=2)
    download.add_argument(
        "--batch-attempts",
        "--attempts",
        dest="batch_attempts",
        type=positive_integer,
        default=3,
        help="retry passes for failed files (--attempts is a deprecated alias)",
    )
    download.add_argument("--timeout", type=positive_integer, default=60)
    download.add_argument("--metadata-attempts", type=positive_integer, default=4)
    download.add_argument("--refresh", action="store_true")
    download.add_argument("--dry-run", action="store_true")
    download.add_argument("--verbose", action="store_true")
    download.set_defaults(handler=run_download)

    validate = subparsers.add_parser("validate", help="validate an existing ENA archive")
    validate.add_argument("path", type=Path)
    validate.add_argument(
        "--metadata-only",
        action="store_true",
        help="validate snapshot structure without requiring downloaded sequence objects",
    )
    validate.set_defaults(handler=run_validate)

    normalize = subparsers.add_parser("metadata-normalize", help="rebuild derived metadata offline")
    normalize.add_argument("--metadata-dir", type=Path, required=True)
    normalize.set_defaults(handler=run_normalize)
    return parser


def run_metadata(args: argparse.Namespace) -> int:
    outdir = validate_destination(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    configure_logging(outdir, args.verbose)
    policy = args.representation if args.command == "snapshot" else None
    _, partial = create_snapshot(
        args.accession,
        outdir,
        client=EnaClient(timeout=args.timeout, attempts=args.attempts),
        refresh=args.refresh,
        policy=policy,
        invocation=args.invocation,
    )
    return 4 if partial else 0


def run_manifest(args: argparse.Namespace) -> int:
    if not args.inventory.is_file():
        raise FileNotFoundError(args.inventory)
    manifest_from_inventory(args.inventory, args.output, args.representation)
    return 0


def _load_download_input(args: argparse.Namespace, outdir: Path):
    source = Path(args.input)
    if source.is_file():
        if source.suffix.lower() != ".tsv":
            raise ValueError("Manifest input must use the .tsv extension")
        entries = read_manifest(source)
        snapshot_path = outdir / "metadata" / "snapshot.json"
        if snapshot_path.is_file():
            try:
                snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"Unable to read existing snapshot metadata: {exc}") from exc
            expected_project = str(snapshot.get("project_accession", ""))
            expected_study = str(snapshot.get("study_accession", ""))
            manifest_projects = {entry.project_accession for entry in entries}
            manifest_studies = {entry.study_accession for entry in entries}
            if expected_project and manifest_projects != {expected_project}:
                raise ValueError("Manifest input is incompatible with the existing archive snapshot")
            if expected_study and manifest_studies != {expected_study}:
                raise ValueError("Manifest input is incompatible with the existing archive snapshot")
        destination = outdir / "manifest.tsv"
        if source.resolve() != destination.resolve():
            if destination.exists() and destination.read_bytes() != source.read_bytes():
                raise FileExistsError(f"A different manifest already exists at {destination}")
            write_manifest(entries, destination)
        return entries
    accession = parse_accession(args.input)
    snapshot_path = outdir / "metadata" / "snapshot.json"
    manifest = outdir / "manifest.tsv"
    if args.refresh or not snapshot_path.is_file():
        create_snapshot(
            accession.value,
            outdir,
            client=EnaClient(timeout=args.timeout, attempts=args.metadata_attempts),
            refresh=args.refresh,
            policy=args.representation,
            invocation=args.invocation,
        )
        return read_manifest(manifest)
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    aliases = {
        str(snapshot.get("input_accession", "")),
        str(snapshot.get("project_accession", "")),
        str(snapshot.get("study_accession", "")),
    }
    if accession.value not in aliases:
        raise ValueError(
            f"Requested accession {accession.value} does not identify the local snapshot "
            f"({', '.join(sorted(value for value in aliases if value))})"
        )
    metadata_errors = validate_metadata(outdir)
    if metadata_errors:
        raise ManifestError(
            "Local metadata snapshot is invalid; use explicit --refresh after preserving "
            "diagnostic evidence:\n" + "\n".join(metadata_errors)
        )
    existing = read_manifest(manifest) if manifest.is_file() else []
    policies = {entry.selection_policy for entry in existing}
    if existing and policies == {args.representation}:
        return existing
    files_path = outdir / "metadata" / "derived" / "files.tsv"
    if not files_path.is_file():
        raise ValueError(
            "Matching metadata snapshot has no valid files.tsv; use --refresh to reacquire metadata"
        )
    logging.info("Building %s manifest offline from current metadata", args.representation)
    return manifest_from_inventory(files_path, manifest, args.representation)


def _dry_run(entries, outdir: Path) -> None:
    runs = {entry.run_accession for entry in entries}
    representations = Counter(entry.representation for entry in entries)
    run_decisions = {
        (entry.run_accession, entry.representation, entry.selection_reason) for entry in entries
    }
    run_representations = Counter(representation for _, representation, _ in run_decisions)
    fallback_runs = Counter(reason for _, _, reason in run_decisions if "not_available" in reason)
    total = sum(entry.size_bytes for entry in entries)
    remaining = sum(
        entry.size_bytes
        for entry in entries
        if not verify_file(safe_destination(outdir, entry.local_relpath), entry)
    )
    usage = shutil.disk_usage(outdir)
    snapshot_path = outdir / "metadata" / "snapshot.json"
    snapshot = (
        json.loads(snapshot_path.read_text(encoding="utf-8")) if snapshot_path.is_file() else {}
    )
    counts = snapshot.get("record_counts", {})
    inventory_path = outdir / "metadata" / "derived" / "files.tsv"
    available = (
        Counter(item.representation for item in read_inventory(inventory_path))
        if inventory_path.is_file()
        else Counter()
    )
    if snapshot:
        print(f"Input accession: {snapshot.get('input_accession', '')}")
        print(f"Canonical BioProject: {snapshot.get('project_accession', '')}")
        print(f"ENA Study accession: {snapshot.get('study_accession', '')}")
        print(f"Samples: {counts.get('samples', 0)}")
        print(f"Experiments: {counts.get('experiments', 0)}")
    print(f"Runs: {len(runs)}")
    for name in ("submitted", "fastq", "sra"):
        print(f"{name} files available: {available[name]}")
    print(f"Selection policy: {entries[0].selection_policy if entries else ''}")
    print("Representation selected by Run:")
    for name in ("submitted", "sra", "fastq"):
        print(f"  {run_representations[name]} {name}")
    print("Selected physical files:")
    for name in ("submitted", "fastq", "sra"):
        print(f"  {representations[name]} {name}")
    print(f"Selected files: {len(entries)}")
    print(f"Selected bytes: {total} ({_iec_size(total)})")
    print("Fallback Runs:")
    if fallback_runs:
        for reason, count in sorted(fallback_runs.items()):
            print(f"  {count} {reason}")
    else:
        print("  0")
    print(f"Destination: {outdir}")
    print(f"Remaining required bytes: {remaining} ({_iec_size(remaining)})")
    print(f"Available bytes: {usage.free} ({_iec_size(usage.free)})")
    print(
        "Estimated free bytes after acquisition: "
        f"{max(0, usage.free - remaining)} ({_iec_size(max(0, usage.free - remaining))})"
    )
    if remaining > usage.free:
        print("WARNING: remaining required bytes exceed available filesystem space")


def _iec_size(size: int) -> str:
    value = float(size)
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def run_download(args: argparse.Namespace) -> int:
    outdir = validate_destination(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    configure_logging(outdir, args.verbose)
    entries = _load_download_input(args, outdir)
    if args.dry_run:
        _dry_run(entries, outdir)
        return 0
    failures = download_batch(entries, outdir, find_curl(), args.jobs, args.batch_attempts)
    return 3 if failures else 0


def run_validate(args: argparse.Namespace) -> int:
    validator = validate_metadata if args.metadata_only else validate_archive
    errors = validator(args.path.resolve())
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 5
    kind = "Metadata snapshot" if args.metadata_only else "Archive"
    print(f"{kind} is valid: {args.path}")
    return 0


def run_normalize(args: argparse.Namespace) -> int:
    normalize_existing(args.metadata_dir)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        args.invocation = ["ena-project", *(argv if argv is not None else sys.argv[1:])]
        return int(args.handler(args))
    except KeyboardInterrupt:
        return 130
    except EnaRequestError as exc:
        logging.error("Required ENA retrieval incomplete: %s", exc)
        return 3
    except (InventoryError, ManifestError, SelectionError) as exc:
        logging.error("Normalization or validation failed: %s", exc)
        return 5
    except (AccessionError, FileNotFoundError, FileExistsError, PermissionError, ValueError) as exc:
        logging.error("Invalid input or configuration: %s", exc)
        return 2
    except Exception as exc:
        logging.error("Runtime failure: %s", exc)
        return 1


def entrypoint() -> None:
    raise SystemExit(main())
