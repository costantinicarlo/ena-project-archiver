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
from .manifest import ManifestError, manifest_from_inventory, read_manifest, write_manifest
from .metadata.snapshot import create_snapshot, normalize_existing
from .selection import POLICIES, SelectionError
from .validation import validate_archive


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
    download.add_argument("--attempts", type=positive_integer, default=3)
    download.add_argument("--timeout", type=positive_integer, default=60)
    download.add_argument("--metadata-attempts", type=positive_integer, default=4)
    download.add_argument("--refresh", action="store_true")
    download.add_argument("--dry-run", action="store_true")
    download.add_argument("--verbose", action="store_true")
    download.set_defaults(handler=run_download)

    validate = subparsers.add_parser("validate", help="validate an existing ENA archive")
    validate.add_argument("path", type=Path)
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
        destination = outdir / "manifest.tsv"
        if source.resolve() != destination.resolve():
            if destination.exists() and destination.read_bytes() != source.read_bytes():
                raise FileExistsError(f"A different manifest already exists at {destination}")
            write_manifest(entries, destination)
        return entries
    accession = parse_accession(args.input)
    manifest = outdir / "manifest.tsv"
    if args.refresh or not manifest.is_file():
        create_snapshot(
            accession.value,
            outdir,
            client=EnaClient(timeout=args.timeout, attempts=args.metadata_attempts),
            refresh=args.refresh,
            policy=args.representation,
        )
    return read_manifest(manifest)


def _dry_run(entries, outdir: Path) -> None:
    runs = {entry.run_accession for entry in entries}
    representations = Counter(entry.representation for entry in entries)
    reasons = Counter(entry.selection_reason for entry in entries)
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
    print(f"Selected files: {len(entries)}")
    print(f"Selected bytes: {total}")
    for name in ("submitted", "fastq", "sra"):
        print(f"{name} files selected: {representations[name]}")
    for reason, count in sorted(reasons.items()):
        print(f"selection reason {reason}: {count}")
    print(f"Destination: {outdir}")
    print(f"Available bytes: {usage.free}")
    print(f"Estimated remaining bytes after acquisition: {max(0, usage.free - remaining)}")


def run_download(args: argparse.Namespace) -> int:
    outdir = validate_destination(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    configure_logging(outdir, args.verbose)
    entries = _load_download_input(args, outdir)
    if args.dry_run:
        _dry_run(entries, outdir)
        return 0
    failures = download_batch(entries, outdir, find_curl(), args.jobs, args.attempts)
    return 3 if failures else 0


def run_validate(args: argparse.Namespace) -> int:
    errors = validate_archive(args.path.resolve())
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 5
    print(f"Archive is valid: {args.path}")
    return 0


def run_normalize(args: argparse.Namespace) -> int:
    normalize_existing(args.metadata_dir)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
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
