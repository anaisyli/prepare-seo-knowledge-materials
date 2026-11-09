#!/usr/bin/env python3
"""Create a deterministic, read-only inventory of local material files."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from package_common import asset_kind, long_path, plain_path


# Text an exporter leaves in a mail file when it did not save the attachments.
EXPORT_GAP_MARKERS = ("附件文件不在邮件导出数据中",)
MAIL_TEXT_EXTENSIONS = {".md", ".markdown", ".txt"}
MAX_GAP_SCAN_BYTES = 5 * 1024 * 1024
MAIL_FILE_EXTENSIONS = {".eml", ".msg", ".mbox"}
MAIL_HEAD_CHARACTERS = 2000
MAIL_FRONTMATTER = re.compile(r"\A---\s*\n(?=(?:.*\n)*?subject:)(?=(?:.*\n)*?date:)", re.I)
MAIL_SENDER_LINE = re.compile(r"(?mi)^[\s*#>]*(from|发件人|发件)[\s*]*[:：]")
MAIL_SUBJECT_LINE = re.compile(r"(?mi)^[\s*#>]*(subject|主题)[\s*]*[:：]")

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
    ".srt",
    ".tsv",
    ".txt",
    ".vtt",
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
    with open(long_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def is_link_like(path: Path) -> bool:
    if os.path.islink(long_path(path)):
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())


def walk_directory(root: Path) -> Iterable[Path]:
    # The long-path form reaches files deeper than Windows' 260-character limit.
    for current, directory_names, file_names in os.walk(long_path(root, always=True), followlinks=False):
        current_path = Path(plain_path(current))
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
        size = os.stat(long_path(path)).st_size
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
        "asset_kind": asset_kind(extension),
        "byte_size": size,
        "source_hash": content_hash,
        "supported_extension": extension in SUPPORTED_EXTENSIONS,
        "inventory_status": status,
    }
    if error:
        item["error"] = error
    return item


# Inline images the extractor chose not to keep: placeholders, separators, or
# images it was told to skip. They were never meant to arrive, so they are not missing.
FILTERED_INLINE = ("inline_small", "inline_skipped")


def link_mail_attachments(
    items: list[dict[str, object]], manifest_path: Path, filtered: list[int]
) -> list[dict[str, object]]:
    """Attach each saved file to its email and return the ones never saved."""
    by_path = {normalized_key(Path(str(item["source_ref"]))): item for item in items}
    by_name = {str(item["display_name"]).casefold(): item for item in items}

    def locate(reference: object) -> dict[str, object] | None:
        if not reference:
            return None
        path = Path(str(reference))
        return by_path.get(normalized_key(path)) or by_name.get(path.name.casefold())

    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing: list[dict[str, object]] = []
    for row in manifest.get("results", []):
        parent = locate(row.get("body_path"))
        if parent is not None:
            parent["mail_manifest_linked"] = True
        for attachment in row.get("attachments", []):
            if str(attachment.get("skipped") or "").startswith(FILTERED_INLINE):
                filtered[0] += 1
                continue
            # A repeated file is stored once; its saved_to points at that copy.
            child = locate(attachment.get("saved_to")) or locate(attachment.get("duplicate_of"))
            if child is None:
                missing.append(
                    {
                        "parent_id": parent["item_id"] if parent else None,
                        "attachment_name": attachment.get("filename"),
                        "reason": attachment.get("skipped") or "not_saved",
                    }
                )
                continue
            if parent is not None:
                child["parent_id"] = parent["item_id"]
                children = parent.setdefault("attachment_ids", [])
                children.append(child["item_id"])  # type: ignore[union-attr]
    return missing


def read_mail_head(item: dict[str, object]) -> str:
    path = Path(str(item["source_ref"]))
    try:
        with path.open(encoding="utf-8", errors="replace", newline=None) as handle:
            return handle.read(MAIL_HEAD_CHARACTERS)
    except OSError:
        return ""


def looks_like_mail(item: dict[str, object]) -> bool:
    if item["extension"] in MAIL_FILE_EXTENSIONS:
        return True
    if item["extension"] not in MAIL_TEXT_EXTENSIONS:
        return False
    head = read_mail_head(item)
    if MAIL_FRONTMATTER.search(head):
        return True
    return bool(MAIL_SENDER_LINE.search(head) and MAIL_SUBJECT_LINE.search(head))


def mark_mail(items: list[dict[str, object]]) -> None:
    for item in items:
        if looks_like_mail(item):
            item["is_mail"] = True


def find_unverified_mail(items: list[dict[str, object]]) -> list[object]:
    """Emails no manifest vouches for, so nothing shows their attachments arrived."""
    return [
        item["item_id"]
        for item in items
        if item.get("is_mail") and not item.get("mail_manifest_linked")
    ]


def find_export_gaps(items: list[dict[str, object]]) -> list[object]:
    gaps = []
    for item in items:
        if item["extension"] not in MAIL_TEXT_EXTENSIONS:
            continue
        if (item["byte_size"] or 0) > MAX_GAP_SCAN_BYTES:  # type: ignore[operator]
            continue
        try:
            text = Path(str(item["source_ref"])).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(marker in text for marker in EXPORT_GAP_MARKERS):
            gaps.append(item["item_id"])
    return gaps


def catalog_markdown(items: list[dict[str, object]], roots: list[str]) -> str:
    """Write a folder-by-folder directory for Obsidian from names and sizes only."""
    resolved_roots = [Path(root).expanduser().resolve() for root in roots]
    folders: dict[str, list[dict[str, object]]] = {}
    for item in items:
        path = Path(str(item["source_ref"]))
        parent = path.parent
        for root in resolved_roots:
            if path.is_relative_to(root):
                parent = path.parent.relative_to(root)
                break
        folders.setdefault(parent.as_posix(), []).append(item)

    total_bytes = sum(int(item["byte_size"] or 0) for item in items)  # type: ignore[call-overload]
    lines = [
        "# 资料目录",
        "",
        f"- 文件：{len(items)} 个，共 {total_bytes / 1048576:.1f} MB",
        "- 只记录文件名和大小，内容尚未读取或筛选。",
        "",
    ]
    for folder in sorted(folders):
        lines += [f"## {'根目录' if folder == '.' else folder}", ""]
        lines += ["| 文件 | 类型 | 大小 |", "|---|---|---|"]
        for item in sorted(folders[folder], key=lambda entry: str(entry["display_name"])):
            name = str(item["display_name"]).replace("|", "/")
            size = int(item["byte_size"] or 0) / 1048576  # type: ignore[call-overload]
            lines.append(f"| {name} | {item['asset_kind']} {item['extension']} | {size:.1f} MB |")
        lines.append("")
    return "\n".join(lines)


def add_relative_paths(items: list[dict[str, object]], inputs: list[str]) -> None:
    """Record where each file sat in the supplied folders, so the layout survives packaging."""
    roots = [Path(raw).expanduser().resolve() for raw in inputs]
    folders = [root for root in roots if root.is_dir()]
    for item in items:
        path = Path(str(item["source_ref"]))
        relative = Path(path.name)
        for root in folders:
            if path.is_relative_to(root):
                relative = path.relative_to(root)
                if len(folders) > 1:
                    relative = Path(root.name) / relative
                break
        item["source_relpath"] = relative.as_posix()


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
    parser.add_argument(
        "--mail-manifest",
        help="Mail search --json output, used to link attachments to their emails",
    )
    parser.add_argument(
        "--catalog",
        help="Also write a Markdown directory of the files, for Obsidian",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output).expanduser().resolve()
    files, warnings = collect_files(args.inputs, output_path)
    items = [inventory_item(path) for path in files]
    add_relative_paths(items, args.inputs)
    missing = []
    filtered = [0]
    if args.mail_manifest:
        missing = link_mail_attachments(items, Path(args.mail_manifest).expanduser(), filtered)
    mark_mail(items)
    document: dict[str, object] = {
        "inventory_version": "1.1",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "input_count": len(args.inputs),
        "input_roots": [str(Path(raw).expanduser().resolve()) for raw in args.inputs],
        "item_count": len(items),
        "items": items,
        "missing_attachments": missing,
        "filtered_inline_images": filtered[0],
        "attachment_export_gaps": find_export_gaps(items),
        "attachment_unverified": find_unverified_mail(items),
        "warnings": warnings,
    }
    write_json_atomic(output_path, document)
    if args.catalog:
        catalog_path = Path(args.catalog).expanduser()
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.write_text(catalog_markdown(items, args.inputs), encoding="utf-8")
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
