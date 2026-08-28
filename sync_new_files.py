from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Dict, List

APP_VERSION = "1.0.2"


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


def is_index_file(path: Path, index_path: Path | None) -> bool:
    if index_path is None:
        return False
    try:
        return path.resolve() == index_path.resolve()
    except (FileNotFoundError, OSError, PermissionError):
        return False


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def emit_progress(stage: str, current: int, total: int, path: Path | None = None) -> None:
    if total <= 0:
        return
    percent = (current / total) * 100
    file_label = "" if path is None else f" - {path}"
    print(f"[{stage}] {current}/{total} ({percent:.1f}%){file_label}")


def scan_source(root: Path, index_path: Path | None = None, exclude_paths: set[Path] | None = None) -> Dict[str, dict]:
    manifest: Dict[str, dict] = {}
    files: List[Path] = []
    excluded = set() if exclude_paths is None else set(exclude_paths)
    for path in sorted(root.rglob("*")):
        try:
            if path.is_dir():
                continue
        except (FileNotFoundError, OSError, PermissionError):
            skip_unavailable(path)
            continue
        if is_index_file(path, index_path):
            continue
        try:
            if any(path.resolve() == candidate.resolve() for candidate in excluded):
                continue
        except (FileNotFoundError, OSError, PermissionError):
            pass
        files.append(path)

    total = len(files)
    for index, path in enumerate(files, start=1):
        emit_progress("scan", index, total, path.relative_to(root))
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


def build_index(root: Path, index_path: Path) -> dict:
    manifest = {"version": APP_VERSION, "files": scan_source(root, index_path=index_path, exclude_paths={index_path})}
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
    return manifest


def load_index(index_path: Path) -> dict:
    if not index_path.exists():
        return {"version": APP_VERSION, "files": {}}
    with index_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return {"version": APP_VERSION, "files": {}}
    files = data.get("files", {})
    return {"version": data.get("version", APP_VERSION), "files": files if isinstance(files, dict) else {}}


def file_matches_index(source_file: Path, rel_path: str, index_data: dict) -> bool:
    record = index_data.get("files", {}).get(rel_path)
    if record is None:
        return False
    try:
        return sha256_file(source_file) == record.get("hash")
    except (FileNotFoundError, OSError, PermissionError):
        skip_unavailable(source_file)
        return False


def size_matches_index(source_file: Path, rel_path: str, index_data: dict) -> bool:
    record = index_data.get("files", {}).get(rel_path)
    if record is None:
        return False
    try:
        return source_file.stat().st_size == record.get("size")
    except (FileNotFoundError, OSError, PermissionError):
        skip_unavailable(source_file)
        return False


def hash_file(path: Path) -> str:
    try:
        return sha256_file(path)
    except (FileNotFoundError, OSError, PermissionError):
        skip_unavailable(path)
        raise


def copy_new_files(source_dir: Path, destination_dir: Path, index_path: Path, dry_run: bool = False, simple_mode: bool = False) -> List[str]:
    source_dir = source_dir.resolve()
    destination_dir = destination_dir.resolve()

    if destination_dir == source_dir or is_within(destination_dir, source_dir):
        print(f"Skipping copy because destination is inside source: {destination_dir}", file=sys.stderr)
        return []

    index_data = load_index(index_path)
    copied: List[str] = []
    files: List[Path] = []
    for path in sorted(source_dir.rglob("*")):
        try:
            if path.is_dir():
                continue
        except (FileNotFoundError, OSError, PermissionError):
            skip_unavailable(path)
            continue
        if is_index_file(path, index_path):
            continue
        files.append(path)

    total = len(files)

    for index, file_path in enumerate(files, start=1):
        try:
            rel_path = relative_path(file_path, source_dir)
        except (ValueError, OSError):
            skip_unavailable(file_path)
            continue

        emit_progress("copy", index, total, rel_path)

        try:
            source_stat = file_path.stat()
            source_size = source_stat.st_size
            destination_path = destination_dir / rel_path
            record = index_data.get("files", {}).get(rel_path)

            if simple_mode:
                # only the index decides "known"; physical destination content is irrelevant
                if record is not None and source_size == record.get("size"):
                    continue

                if dry_run:
                    copied.append(rel_path)
                    continue

                destination_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, destination_path)
                copied.append(rel_path)

                index_data.setdefault("files", {})[rel_path] = {
                    "hash": sha256_file(file_path),
                    "size": source_size,
                    "mtime_ns": source_stat.st_mtime_ns,
                }
                continue

            source_hash = hash_file(file_path)

            if record is not None and source_hash == record.get("hash"):
                continue

            if dry_run:
                copied.append(rel_path)
                continue

            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, destination_path)
            copied.append(rel_path)

            index_data.setdefault("files", {})[rel_path] = {
                "hash": source_hash,
                "size": source_size,
                "mtime_ns": source_stat.st_mtime_ns,
            }
        except (FileNotFoundError, OSError, PermissionError):
            skip_unavailable(file_path)
            continue

    if not dry_run and copied:
        with index_path.open("w", encoding="utf-8") as handle:
            json.dump({"version": APP_VERSION, "files": index_data.get("files", {})}, handle, ensure_ascii=False, indent=2, sort_keys=True)

    return copied


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Folder Sync by Index v{APP_VERSION}")
    parser.add_argument("--version", action="version", version=f"%(prog)s {APP_VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Create an index file for the source directory")
    scan_parser.add_argument("source", type=Path, help="Folder to scan")
    scan_parser.add_argument("--index", type=Path, default=Path("sync_index.json"), help="Path to the JSON index file")

    copy_parser = subparsers.add_parser("copy", help="Copy files from source to destination using the index")
    copy_parser.add_argument("source", type=Path, help="Folder with files")
    copy_parser.add_argument("destination", type=Path, help="Folder where to copy new files")
    copy_parser.add_argument("--index", type=Path, default=Path("sync_index.json"), help="Path to the JSON index file")
    copy_parser.add_argument("--dry-run", action="store_true", help="List files that would be copied without copying them")
    copy_parser.add_argument("--simple-mode", action="store_true", help="Compare by relative path and file size before hash")

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.command == "scan":
        manifest = build_index(args.source, args.index)
        print(f"Folder Sync by Index v{APP_VERSION}")
        print(f"Indexed {len(manifest['files'])} files into {args.index}")
        return

    if not args.source.exists() or not args.source.is_dir():
        raise SystemExit(f"Source directory not found: {args.source}")

    copied = copy_new_files(args.source, args.destination, args.index, dry_run=args.dry_run, simple_mode=args.simple_mode)
    print(f"Folder Sync by Index v{APP_VERSION}")
    print(f"{'Would copy' if args.dry_run else 'Copied'} {len(copied)} files")
    for rel in copied:
        print(rel)


if __name__ == "__main__":
    main()
