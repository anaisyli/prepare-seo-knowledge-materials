#!/usr/bin/env python3
"""Shared taxonomy and helpers for the package builder and verifier."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any


SCRIPT_VERSION = "2.0"

# Fixed labels, so a free-text category can never become a directory path.
RESOURCE_LABELS = {
    "marketing": "营销宣传",
    "business_scenario": "业务场景",
    "product": "产品资料",
    "competitor": "竞对资料",
    "seo_ops": "SEO运营资料",
    "transaction": "交易往来",
    "pricing": "价格",
    "finance": "财务",
    "noise": "无知识价值",
    "unknown": "未归类",
}
SCOPES = {"general", "style", "single_communication"}
DECISIONS = {"A", "B", "C", "D", "E"}

# Kept in the package, but never facts about the company.
NON_FACT_TYPES = {"competitor", "seo_ops"}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".heic"}
VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".webm", ".m4v", ".flv", ".mpg", ".mpeg", ".3gp", ".m2ts",
}
AUDIO_EXTENSIONS = {
    ".mp3", ".m4a", ".wav", ".aac", ".ogg", ".amr", ".flac", ".wma", ".m4b", ".opus",
}
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z", ".tar", ".gz"}

AUDIT_DIRECTORY = "审计记录"
MANIFEST_NAME = "审计记录/package-manifest.json"
LARGE_FILE_BYTES = 50 * 1024 * 1024

WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}
MAX_NAME_LENGTH = 120


def asset_kind(extension: str) -> str:
    extension = extension.casefold()
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in VIDEO_EXTENSIONS:
        return "video"
    if extension in AUDIO_EXTENSIONS:
        return "audio"
    if extension in ARCHIVE_EXTENSIONS:
        return "archive"
    return "document"


def is_restricted(item: dict[str, Any]) -> bool:
    return item.get("restricted") is True or item.get("resource_type") == "finance"


def whole_file_pending(item: dict[str, Any]) -> bool:
    """A case inside a longer document holds back that case, not the document."""
    return item.get("pending_client_review") is True and item.get("pending_scope") != "part"


def usable_as_fact(item: dict[str, Any]) -> bool:
    return (
        item.get("decision") == "A"
        and item.get("resource_type") not in NON_FACT_TYPES
        and not whole_file_pending(item)
        and not is_restricted(item)
    )


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with open(long_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def long_path(path: Path | str) -> str:
    """Return a path that survives the Windows 260-character limit."""
    text = os.path.abspath(str(path))
    if os.name == "nt" and len(text) >= 240 and not text.startswith("\\\\?\\"):
        return "\\\\?\\" + text
    return text


def sanitize_component(name: str, fallback: str = "file") -> str:
    """Turn an untrusted name into one safe path component."""
    leaf = re.split(r"[\\/]", name)[-1]
    leaf = re.sub(r"^[A-Za-z]:", "", leaf)
    leaf = re.sub(r'[<>:"|?*\x00-\x1f]', "_", leaf).strip(" .")
    if not leaf:
        leaf = fallback
    stem, suffix = os.path.splitext(leaf)
    if stem.split(".")[0].upper() in WINDOWS_RESERVED:
        stem = f"_{stem}"
    if len(stem) + len(suffix) > MAX_NAME_LENGTH:
        stem = stem[: MAX_NAME_LENGTH - len(suffix)].rstrip(" .")
    return f"{stem}{suffix}"


def load_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def load_triage(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read a triage file written as one JSON object or as JSONL item records."""
    text = path.read_text(encoding="utf-8")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
        header = next((r for r in records if "items" not in r and "item_id" not in r), {})
        items = [r for r in records if "item_id" in r]
        return header, items
    if isinstance(value, list):
        return {}, value
    if not isinstance(value, dict) or not isinstance(value.get("items"), list):
        raise ValueError("Triage result must contain an items list")
    return {key: val for key, val in value.items() if key != "items"}, value["items"]


def write_json_file(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
