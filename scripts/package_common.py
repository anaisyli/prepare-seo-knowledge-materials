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


SYSTEM_FILE_NAMES = {"thumbs.db", "ehthumbs.db", ".ds_store", "desktop.ini"}
MEDIA_KINDS = {"image", "video", "audio"}
# What a folder rule may set. Client review is handled apart: one question per folder.
FOLDER_RULE_FIELDS = (
    "decision", "resource_type", "summary", "reason_codes", "business_tags", "required_follow_up",
)
FOLDER_QUESTION = "这个文件夹里的图片和视频可以用在官网和宣传上吗？"


def is_system_file(name: str) -> bool:
    name = name.casefold()
    return name in SYSTEM_FILE_NAMES or name.startswith(("~$", "._"))


def plain_path(text: str) -> str:
    """Drop the long-path prefix before a path is shown or stored."""
    if text.startswith("\\\\?\\UNC\\"):
        return "\\\\" + text[8:]
    return text[4:] if text.startswith("\\\\?\\") else text


def make_dirs(path: Path | str) -> None:
    os.makedirs(long_path(path), exist_ok=True)


def expand_triage(
    header: dict[str, Any], items: list[dict[str, Any]], inventory_items: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Turn folder rules and system files into one decision per item.

    A folder of product photos or videos can be judged as a group after looking
    at some of them. Documents always need their own decision.
    """
    problems: list[str] = []
    by_relpath = {str(item.get("source_relpath")): item for item in inventory_items}
    rules = []
    for rule in header.get("folder_rules", []):
        folder = str(rule.get("folder", "")).replace("\\", "/").strip("/")
        samples = [str(sample).replace("\\", "/") for sample in rule.get("checked_samples", [])]
        decision = rule.get("decision")
        if not folder or decision not in {"A", "D", "E"}:
            problems.append(f"Folder rule needs a folder and decision A, D or E: {folder}")
            continue
        if decision in {"A", "E"} and not (
            samples and all(s.startswith(folder + "/") and s in by_relpath for s in samples)
        ):
            problems.append(f"Folder rule needs checked samples inside its folder: {folder}")
            continue
        if decision == "E" and not rule.get("reason_codes"):
            problems.append(f"Folder rule excluding files needs a reason: {folder}")
            continue
        if rule.get("pending_client_review") is True and (decision != "A" or not rule.get("summary")):
            problems.append(f"Folder rule for the client needs decision A and a summary: {folder}")
            continue
        rules.append((folder, rule))
    rules.sort(key=lambda entry: -len(entry[0]))

    decided = {item.get("item_id") for item in items}
    expanded = list(items)
    for entry in inventory_items:
        if entry["item_id"] in decided:
            continue
        if is_system_file(str(entry.get("display_name", ""))):
            expanded.append({
                "item_id": entry["item_id"], "decision": "E", "resource_type": "noise",
                "reason_codes": ["system_file"], "summary": "系统自动生成的文件，没有内容。",
                "content_read": True, "from_rule": "system_file",
            })
            continue
        if entry.get("asset_kind") not in MEDIA_KINDS:
            continue
        relpath = str(entry.get("source_relpath", ""))
        match = next(((f, r) for f, r in rules if relpath.startswith(f + "/")), None)
        if match:
            folder, rule = match
            decision = {key: rule[key] for key in FOLDER_RULE_FIELDS if key in rule}
            if rule.get("pending_client_review") is True:
                # The client answers once for the folder, not once per picture.
                decision.update({
                    "pending_client_review": True,
                    "review_group": folder,
                    "client_review_items": [{
                        "summary": rule["summary"],
                        "location": "整个文件夹",
                        "question": rule.get("client_question") or FOLDER_QUESTION,
                    }],
                })
            expanded.append({
                "item_id": entry["item_id"], **decision,
                "content_read": rule["decision"] != "D", "from_folder_rule": folder,
            })
    return expanded, problems


def long_path(path: Path | str, always: bool = False) -> str:
    """Return a path that survives the Windows 260-character limit.

    A directory walk needs `always`: it starts short and grows past the limit.
    """
    text = os.path.abspath(plain_path(str(path)))
    if os.name == "nt" and (always or len(text) >= 240):
        if text.startswith("\\\\"):
            return "\\\\?\\UNC\\" + text[2:]
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
