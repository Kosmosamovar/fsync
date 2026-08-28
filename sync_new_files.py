from __future__ import annotations

import argparse
import hashlib
import json
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


def skip_unavailable(path: Path) -> None:
    print(f"Skipping unavailable file: {path}", file=sys.stderr)


def scan_source(root: Path) -> Dict[str, dict]:
    manifest: Dict[str, dict] = {}
    for path in sorted(root.rglob("*")):
        try:
            if path.is_dir():
                continue
        except (FileNotFoundError, OSError, PermissionError):
            skip_unavailable(path)
            continue

        try:
            rel_path = path.relative_to(root).as_posix()
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


def build_index(root: Path, index_path: Path) -> dict:
    manifest = {"version": 1, "files": scan_source(root)}
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


def file_matches_index(source_file: Path, rel_path: str, index_data: dict) -> bool:
    record = index_data.get("files", {}).get(rel_path)
    if record is None:
        return False
    try:
        return sha256_file(source_file) == record.get("hash")
    except (FileNotFoundError, OSError, PermissionError):
        skip_unavailable(source_file)
        return False


def copy_new_files(source_dir: Path, destination_dir: Path, index_path: Path, dry_run: bool = False) -> List[str]:
    source_dir = source_dir.resolve()
    destination_dir = destination_dir.resolve()
    index_data = load_index(index_path)
    copied: List[str] = []

    for file_path in sorted(source_dir.rglob("*")):
        if file_path.is_dir():
            continue

        try:
            rel_path = file_path.relative_to(source_dir).as_posix()
        except (ValueError, OSError):
            skip_unavailable(file_path)
            continue

        try:
            if file_path.exists():
                destination_path = destination_dir / rel_path
                if destination_path.exists() and file_matches_index(file_path, rel_path, index_data):
                    continue

                if dry_run:
                    copied.append(rel_path)
                    continue

                destination_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, destination_path)
                copied.append(rel_path)
        except (FileNotFoundError, OSError, PermissionError):
            skip_unavailable(file_path)
            continue

    return copied


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Copy only new or changed files using a hash index.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Create an index file for the source directory")
    scan_parser.add_argument("source", type=Path, help="Folder to scan")
    scan_parser.add_argument("--index", type=Path, default=Path("sync_index.json"), help="Path to the JSON index file")

    copy_parser = subparsers.add_parser("copy", help="Copy files from source to destination using the index")
    copy_parser.add_argument("source", type=Path, help="Folder with files")
    copy_parser.add_argument("destination", type=Path, help="Folder where to copy new files")
    copy_parser.add_argument("--index", type=Path, default=Path("sync_index.json"), help="Path to the JSON index file")
    copy_parser.add_argument("--dry-run", action="store_true", help="List files that would be copied without copying them")

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.command == "scan":
        manifest = build_index(args.source, args.index)
        print(f"Indexed {len(manifest['files'])} files into {args.index}")
        return

    if not args.source.exists() or not args.source.is_dir():
        raise SystemExit(f"Source directory not found: {args.source}")

    copied = copy_new_files(args.source, args.destination, args.index, dry_run=args.dry_run)
    print(f"{'Would copy' if args.dry_run else 'Copied'} {len(copied)} files")
    for rel in copied:
        print(rel)


if __name__ == "__main__":
    main()
