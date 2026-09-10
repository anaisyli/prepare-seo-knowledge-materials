#!/usr/bin/env python3
"""Create a deterministic, read-only inventory of local material files."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


SUPPORTED_EXTENSIONS = {
    ".csv",
    ".doc",
    ".docx",
    ".json",
    ".jsonl",
    ".md",
    ".markdown",
    ".pdf",
    ".ppt",
    ".pptx",
    ".rtf",
    ".tsv",
    ".txt",
    ".xls",
    ".xlsx",
    ".xml",
    ".yaml",
    ".yml",
}

EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".svn",
    "__pycache__",
    "seo-knowledge-triage",
    "seo-knowledge-output",
    "seo-knowledge-review",
}

MIME_OVERRIDES = {
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def is_link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())


def walk_directory(root: Path) -> Iterable[Path]:
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name.casefold() not in EXCLUDED_DIRECTORY_NAMES
            and not is_link_like(current_path / name)
        )
        for name in sorted(file_names):
            candidate = current_path / name
            if not is_link_like(candidate):
                yield candidate


def collect_files(inputs: list[str], output_path: Path | None) -> tuple[list[Path], list[str]]:
    files: dict[str, Path] = {}
    warnings: list[str] = []
    output_key = normalized_key(output_path) if output_path else None

    for raw_input in inputs:
        candidate = Path(raw_input).expanduser()
        if is_link_like(candidate):
            warnings.append(f"Symbolic-link or junction input skipped: {candidate}")
            continue
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            warnings.append(f"Input unavailable: {candidate} ({exc.__class__.__name__})")
            continue

        if resolved.is_file():
            key = normalized_key(resolved)
            if key != output_key:
                files[key] = resolved
            continue
        if resolved.is_dir():
            for path in walk_directory(resolved):
                key = normalized_key(path)
                if key != output_key:
                    files[key] = path
            continue
        warnings.append(f"Unsupported input type: {resolved}")

    return [files[key] for key in sorted(files)], warnings


def inventory_item(path: Path) -> dict[str, object]:
    extension = path.suffix.casefold()
    try:
        size = path.stat().st_size
        content_hash = sha256_file(path)
        path_hash = hashlib.sha256(normalized_key(path).encode("utf-8")).hexdigest()
        item_id = f"local-{content_hash[:12]}-{path_hash[:8]}"
        status = "inventoried"
        error = None
    except OSError as exc:
        size = None
        content_hash = None
        path_hash = hashlib.sha256(normalized_key(path).encode("utf-8")).hexdigest()
        item_id = f"local-unreadable-{path_hash[:12]}"
        status = "hash_error"
        error = exc.__class__.__name__

    media_type = MIME_OVERRIDES.get(extension)
    if not media_type:
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    item: dict[str, object] = {
        "item_id": item_id,
        "source_kind": "local_file",
        "source_ref": str(path),
        "display_name": path.name,
        "extension": extension,
        "media_type": media_type,
        "byte_size": size,
        "source_hash": content_hash,
        "supported_extension": extension in SUPPORTED_EXTENSIONS,
        "inventory_status": status,
    }
    if error:
        item["error"] = error
    return item


def write_json_atomic(destination: Path, value: dict[str, object]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="\n",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
    temporary.replace(destination)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a read-only JSON inventory for supplied files or directories."
    )
    parser.add_argument("inputs", nargs="+", help="Files or directories to inventory")
    parser.add_argument("--output", required=True, help="Destination inventory.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output).expanduser().resolve()
    files, warnings = collect_files(args.inputs, output_path)
    items = [inventory_item(path) for path in files]
    document: dict[str, object] = {
        "inventory_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "input_count": len(args.inputs),
        "item_count": len(items),
        "items": items,
        "warnings": warnings,
    }
    write_json_atomic(output_path, document)
    print(
        json.dumps(
            {
                "output": str(output_path),
                "item_count": len(items),
                "warning_count": len(warnings),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
