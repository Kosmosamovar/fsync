from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def skip_unavailable(path: Path) -> None:
    print(f"Skipping unavailable file: {path}", file=sys.stderr)


def scan_source(root: Path, skip_ext: set[str] | None = None) -> Dict[str, dict]:
    skip_ext = skip_ext or set()
    manifest: Dict[str, dict] = {}

    for path in sorted(root.rglob("*")):
        try:
            if path.is_dir():
                continue
        except (FileNotFoundError, OSError, PermissionError):
            skip_unavailable(path)
            continue

        if path.suffix.lower().lstrip(".") in {ext.lower().lstrip(".") for ext in skip_ext}:
            continue

        try:
            rel_path = relative_path(path, root)
            stat = path.stat()
        except (FileNotFoundError, OSError, PermissionError):
            skip_unavailable(path)
            continue

        try:
            file_hash = sha256_file(path)
        except (FileNotFoundError, OSError, PermissionError):
            skip_unavailable(path)
            continue

        manifest[rel_path] = {
            "hash": file_hash,
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }

    return manifest


def build_index(root: Path, index_path: Path, skip_ext: set[str] | None = None) -> dict:
    manifest = {"version": 1, "files": scan_source(root, skip_ext=skip_ext)}
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
    return manifest


def load_index(index_path: Path) -> dict:
    if not index_path.exists():
        return {"version": 1, "files": {}}
    with index_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return {"version": 1, "files": {}}
    files = data.get("files", {})
    return {"version": data.get("version", 1), "files": files if isinstance(files, dict) else {}}


def hash_file(path: Path) -> str:
    try:
        return sha256_file(path)
    except (FileNotFoundError, OSError, PermissionError):
        skip_unavailable(path)
        raise


def list_new_or_changed(source_dir: Path, index_path: Path, skip_ext: set[str] | None = None) -> List[str]:
    source_dir = source_dir.resolve()
    index_data = load_index(index_path)
    skip_ext = skip_ext or set()
    normalized_skip = {ext.lower().lstrip(".") for ext in skip_ext}
    changed: List[str] = []

    for file_path in sorted(source_dir.rglob("*")):
        if file_path.is_dir():
            continue

        if file_path.suffix.lower().lstrip(".") in normalized_skip:
            continue

        try:
            rel_path = relative_path(file_path, source_dir)
            source_hash = hash_file(file_path)
        except (FileNotFoundError, OSError, PermissionError):
            skip_unavailable(file_path)
            continue

        record = index_data.get("files", {}).get(rel_path)
        if record is None or source_hash != record.get("hash"):
            changed.append(rel_path)

    return changed


def copy_new_files(
    source_dir: Path,
    destination_dir: Path,
    index_path: Path,
    skip_ext: set[str] | None = None,
    dry_run: bool = False,
) -> List[str]:
    source_dir = source_dir.resolve()
    destination_dir = destination_dir.resolve()
    index_data = load_index(index_path)
    skip_ext = skip_ext or set()
    normalized_skip = {ext.lower().lstrip(".") for ext in skip_ext}
    copied: List[str] = []

    for file_path in sorted(source_dir.rglob("*")):
        if file_path.is_dir():
            continue

        if file_path.suffix.lower().lstrip(".") in normalized_skip:
            continue

        try:
            rel_path = relative_path(file_path, source_dir)
            source_hash = hash_file(file_path)
            destination_path = destination_dir / rel_path
            record = index_data.get("files", {}).get(rel_path)

            if record is not None and source_hash == record.get("hash"):
                if destination_path.exists():
                    try:
                        if hash_file(destination_path) == record.get("hash"):
                            continue
                    except (FileNotFoundError, OSError, PermissionError):
                        pass

            if destination_path.exists():
                try:
                    if hash_file(destination_path) == source_hash:
                        continue
                except (FileNotFoundError, OSError, PermissionError):
                    pass

            if dry_run:
                copied.append(rel_path)
                continue

            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, destination_path)
            copied.append(rel_path)

            index_data.setdefault("files", {})[rel_path] = {
                "hash": source_hash,
                "size": file_path.stat().st_size,
                "mtime_ns": file_path.stat().st_mtime_ns,
            }
        except (FileNotFoundError, OSError, PermissionError):
            skip_unavailable(file_path)
            continue

    if not dry_run and copied:
        with index_path.open("w", encoding="utf-8") as handle:
            json.dump({"version": 1, "files": index_data.get("files", {})}, handle, ensure_ascii=False, indent=2, sort_keys=True)

    return copied


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Copy only new or changed files using a hash index.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Create an index file for the source directory")
    scan_parser.add_argument("source", type=Path, help="Folder to scan")
    scan_parser.add_argument("--index", type=Path, default=Path("sync_index.json"), help="Path to the JSON index file")
    scan_parser.add_argument("--skip-ext", nargs="*", default=[], help="Extensions to skip, e.g. tmp log")

    copy_parser = subparsers.add_parser("copy", help="Copy files from source to destination using the index")
    copy_parser.add_argument("source", type=Path, help="Folder with files")
    copy_parser.add_argument("destination", type=Path, help="Folder where to copy new files")
    copy_parser.add_argument("--index", type=Path, default=Path("sync_index.json"), help="Path to the JSON index file")
    copy_parser.add_argument("--dry-run", action="store_true", help="List files that would be copied without copying them")
    copy_parser.add_argument("--skip-ext", nargs="*", default=[], help="Extensions to skip, e.g. tmp log")

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.command == "scan":
        manifest = build_index(args.source, args.index, skip_ext=set(args.skip_ext))
        print(f"Indexed {len(manifest['files'])} files into {args.index}")
        return

    if not args.source.exists() or not args.source.is_dir():
        raise SystemExit(f"Source directory not found: {args.source}")

    copied = copy_new_files(args.source, args.destination, args.index, skip_ext=set(args.skip_ext), dry_run=args.dry_run)
    print(f"{'Would copy' if args.dry_run else 'Copied'} {len(copied)} files")
    for rel in copied:
        print(rel)


if __name__ == "__main__":
    main()
