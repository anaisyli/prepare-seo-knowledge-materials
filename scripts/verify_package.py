#!/usr/bin/env python3
"""Refuse to call a package finished unless its files and records agree."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from client_review import WORKBOOK_NAME, read_review_rows
from package_common import (
    AUDIT_DIRECTORY,
    MANIFEST_NAME,
    SCOPES,
    is_restricted,
    load_jsonl,
    load_json_object,
    load_triage,
    long_path,
    sha256_file,
    usable_as_fact,
)


FINANCE_NAME = re.compile(r"(?i)收汇|发票|invoice|合同|contract|工资|银行|外汇|对账|账户")
EXACT_LOCATOR = re.compile(r"(?i)\b[A-Z]{1,3}\d*:[A-Z]{1,3}\d*\b|\b[A-Z]{1,3}\d+\b|第\s*\d|page\s*\d|slide\s*\d|para\s*\d|paragraph\s*\d")
PRICE_VALUE = re.compile(r"(?i)[$￥¥€]\s?\d|\d\s?(美元|美金|元)|\d\s?(usd|rmb|cny|eur)\b|\b(usd|rmb|cny)\s?\d")
CASE_ENTRY = re.compile(r"(?i)案例|case|客户|testimonial")
LOCAL_PATH_PATTERN = re.compile(r"file:///|(?<![A-Za-z0-9])[A-Za-z]:[\\/]")
UNREADABLE_STATES = {"failed", "needs_ocr", "needs_pdf_reader", "unsupported"}
COPIED_STATES = {"copied"}
RECORD_ONLY_STATES = {"not_copied_restricted", "withheld_by_client", "not_persisted", "duplicate"}


WHOLE_ITEM = {"整份文件", "整张图", "全文", "whole file"}


def package_files(package: Path) -> set[str]:
    return {
        path.relative_to(package).as_posix()
        for path in package.rglob("*")
        if path.is_file() and path.relative_to(package).parts[0] != AUDIT_DIRECTORY
    }


def check_coverage(
    inventory_ids: set[str], triage_ids: set[str], errors: list[str]
) -> None:
    for item_id in sorted(inventory_ids - triage_ids):
        errors.append(f"No decision for inventory item: {item_id}")
    for item_id in sorted(triage_ids - inventory_ids):
        errors.append(f"Decision for unknown item: {item_id}")


def check_assets(package: Path, assets: list[dict[str, Any]], errors: list[str]) -> set[str]:
    listed: set[str] = set()
    for asset in assets:
        item_id = asset.get("item_id")
        status = asset.get("copy_status")
        path = asset.get("path")
        if status in COPIED_STATES:
            target = package / str(path)
            if not path or not Path(long_path(target)).is_file():
                errors.append(f"Listed file is not in the package: {item_id}")
                continue
            listed.add(str(path))
            expected = asset.get("source_hash")
            if expected and sha256_file(target).casefold() != str(expected).casefold():
                errors.append(f"Copied file differs from its source: {item_id}")
        elif status not in RECORD_ONLY_STATES:
            errors.append(f"Item was not placed ({status}): {item_id}")
    return listed


def check_rules(
    assets: list[dict[str, Any]],
    triage_items: dict[str, dict[str, Any]],
    extraction: dict[str, Any],
    include_restricted: bool,
    mail_ids: set[str],
    errors: list[str],
) -> None:
    for asset in assets:
        item_id = str(asset.get("item_id"))
        item = triage_items.get(item_id)
        if item is None:
            continue
        decision = item.get("decision")
        restricted = is_restricted(item)

        if asset.get("usable_as_fact") and not usable_as_fact(item):
            errors.append(f"Marked usable as a company fact wrongly: {item_id}")
        if asset.get("importable") and decision != "A":
            errors.append(f"Only A items may be importable: {item_id}")
        if restricted and asset.get("path") and not include_restricted:
            errors.append(f"Restricted item was copied: {item_id}")
        if item.get("restricted") is True and item.get("resource_type") != "finance":
            errors.append(f"Only finance items may be restricted: {item_id}")
        status = extraction.get(item_id) or {}
        if (
            item.get("resource_type") == "finance"
            and status.get("product_signal")
            and status.get("embedded_media")
            and item.get("no_product_rows") is not True
        ):
            errors.append(f"Workbook with product images marked as finance: {item_id}")
        name = str(asset.get("display_name") or "")
        if decision in {"A", "B"} and FINANCE_NAME.search(name):
            errors.append(f"Finance-named file kept as {decision}: {item_id}")
        if decision == "B":
            locators = [
                str(locator)
                for action in item.get("actions", [])
                for locator in action.get("locators", [])
            ]
            if not any(EXACT_LOCATOR.search(locator) for locator in locators):
                errors.append(f"B item has no exact removal location: {item_id}")
        if decision in {"A", "B"} and status.get("case_signal"):
            entries = item.get("client_review_items", [])
            if not item.get("pending_client_review") or not any(
                CASE_ENTRY.search(str(entry.get("summary"))) for entry in entries
            ):
                errors.append(f"Customer cases not sent for client review: {item_id}")
        if (
            item.get("pending_client_review") is True
            and item.get("pending_scope") != "part"
            and item.get("client_review_items")
            and all(
                entry.get("location") and entry.get("location") not in WHOLE_ITEM
                for entry in item["client_review_items"]
            )
        ):
            errors.append(f"Only part of the file awaits the client, use pending_scope: {item_id}")
        if (
            decision == "E"
            and item.get("resource_type") == "pricing"
            and (status.get("product_signal") or status.get("embedded_media"))
        ):
            errors.append(f"Quotation with product content excluded as pricing: {item_id}")
        if (
            decision == "E"
            and item_id in mail_ids
            and item.get("mail_review") not in {"full", "candidates"}
        ):
            errors.append(f"Email excluded without reviewing its content: {item_id}")
        if decision == "E" and not [c for c in item.get("reason_codes", []) if c not in {"E", ""}]:
            errors.append(f"E item has no real reason code: {item_id}")
        if decision in {"A", "B", "C", "E"} and item.get("content_read") is not True:
            errors.append(f"Decided {decision} without reading the content: {item_id}")
        state = (extraction.get(item_id) or {}).get("status")
        if decision in {"A", "B", "C", "E"} and state in UNREADABLE_STATES:
            errors.append(f"Decided {decision} but extraction status is {state}: {item_id}")


def check_points(
    points: list[dict[str, Any]],
    triage_items: dict[str, dict[str, Any]],
    mail_ids: set[str],
    candidates: dict[str, set[str]] | None,
    errors: list[str],
) -> None:
    for point in points:
        knowledge_id = point.get("knowledge_id")
        if PRICE_VALUE.search(str(point.get("knowledge_point"))):
            errors.append(f"Knowledge point contains a price: {knowledge_id}")
        source = point.get("source_id")
        if candidates is not None and source in mail_ids:
            if str(point.get("locator")) not in candidates.get(source, set()):
                errors.append(f"Knowledge point location is not a company message: {knowledge_id}")
        if point.get("source_id") not in triage_items:
            errors.append(f"Knowledge point has an unknown source: {knowledge_id}")
        if not point.get("locator"):
            errors.append(f"Knowledge point has no locator: {knowledge_id}")
        if point.get("scope") not in SCOPES:
            errors.append(f"Knowledge point has no valid scope: {knowledge_id}")
        if point.get("scope") == "general" and point.get("source_id") in mail_ids:
            errors.append(f"Point from one email cannot be general: {knowledge_id}")
        if point.get("usable_as_fact") and point.get("pending_client_review"):
            errors.append(f"Knowledge point awaiting the client marked as fact: {knowledge_id}")
        source = triage_items.get(point.get("source_id")) or {}
        if source.get("resource_type") == "competitor":
            errors.append(f"Knowledge point taken from competitor material: {knowledge_id}")


def check_local_paths(package: Path, files: set[str], errors: list[str]) -> None:
    """Check generated lists only; source copies are allowed to mention paths."""
    relatives = [r for r in sorted(files) if r.endswith(("清单.md", "清单.csv", ".jsonl"))]
    for relative in [*relatives, MANIFEST_NAME]:
        text = (package / relative).read_text(encoding="utf-8", errors="replace")
        if LOCAL_PATH_PATTERN.search(text):
            errors.append(f"Local machine path in {relative}")


def check_client_review(
    package: Path,
    assets: list[dict[str, Any]],
    points: list[dict[str, Any]],
    errors: list[str],
) -> None:
    """Everything awaiting the client must appear in the workbook, with a real sentence."""
    path = package / WORKBOOK_NAME
    if not path.is_file():
        errors.append("Client review workbook is missing")
        return
    rows = read_review_rows(path)
    listed = {str(row["id"]).split("#")[0] for row in rows}
    expected = {
        str(a["item_id"])
        for a in assets
        if a.get("pending_client_review") and a.get("copy_status") != "duplicate"
    }
    expected |= {str(p.get("knowledge_id")) for p in points if p.get("pending_client_review")}
    for missing in sorted(expected - listed):
        errors.append(f"Awaiting the client but not in the workbook: {missing}")
    for row in rows:
        if not row["summary"].strip() or not row["question"].strip():
            errors.append(f"Workbook row has no summary or question: {row['id']}")


def verify(
    package: Path,
    extract_status: Path | None,
    gap_reason: str | None,
    mail_candidates: Path | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    manifest = load_json_object(package / MANIFEST_NAME)
    assets = manifest.get("assets", [])
    inventory = load_json_object(package / AUDIT_DIRECTORY / "inventory.json")
    header, raw_items = load_triage(package / AUDIT_DIRECTORY / "triage-results.json")
    triage_items = {item["item_id"]: item for item in raw_items}
    inventory_ids = {item["item_id"] for item in inventory.get("items", [])}

    if (header.get("scope_confirmation") or {}).get("confirmed") is not True:
        errors.append("Scope confirmation is missing")
    check_coverage(inventory_ids, set(triage_items), errors)

    listed = check_assets(package, assets, errors)
    files = package_files(package)
    expected = listed | set(manifest.get("generated_files", [])) | {MANIFEST_NAME}
    for relative in sorted(files - expected):
        errors.append(f"File in package but not in manifest: {relative}")

    extraction: dict[str, Any] = {}
    if extract_status:
        extraction = load_json_object(extract_status).get("items", {})
    mail_ids = {item["item_id"] for item in inventory.get("items", []) if item.get("is_mail")}
    check_rules(assets, triage_items, extraction, manifest.get("include_restricted") is True, mail_ids, errors)

    points_path = package / "C-知识点" / "knowledge-points.jsonl"
    points = load_jsonl(points_path) if points_path.exists() else []
    candidates = None
    if mail_candidates:
        candidates = {}
        for row in load_jsonl(mail_candidates):
            candidates.setdefault(row["item_id"], set()).add(row["locator"])
        # Short messages hold no candidate sentence but can still hold a fact.
        messages = mail_candidates.with_name("mail-messages.json")
        if messages.exists():
            for item_id, headings in load_json_object(messages).items():
                candidates.setdefault(item_id, set()).update(headings)
    check_points(points, triage_items, mail_ids, candidates, errors)
    check_local_paths(package, files, errors)
    check_client_review(package, assets, points, errors)

    missing = manifest.get("missing_attachments", [])
    gaps = manifest.get("attachment_export_gaps", [])
    unverified = manifest.get("attachment_unverified", [])
    if (missing or gaps) and not gap_reason:
        errors.append(
            f"Attachments incomplete: {len(missing)} not saved, "
            f"{len(gaps)} emails exported without attachments"
        )
    if unverified and not gap_reason:
        errors.append(
            f"Cannot confirm attachments: {len(unverified)} emails have no mail manifest"
        )

    result = {
        "verified": not errors,
        "item_count": len(assets),
        "files_in_package": len(listed),
        "knowledge_point_count": len(points),
        "attachment_gap_accepted": gap_reason if (missing or gaps or unverified) else None,
        "error_count": len(errors),
        "errors": errors[:200],
    }
    (package / AUDIT_DIRECTORY / "校验结果.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check that a preparation package is complete before reporting it done."
    )
    parser.add_argument("package", help="Package directory")
    parser.add_argument("--extract-status", help="extract-status.json from extract_text.py")
    parser.add_argument("--mail-candidates", help="mail-candidates.jsonl from mail_candidates.py")
    parser.add_argument(
        "--accept-attachment-gaps",
        metavar="REASON",
        help="Record why missing attachments are acceptable for this run",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = verify(
            Path(args.package).resolve(),
            Path(args.extract_status).resolve() if args.extract_status else None,
            args.accept_attachment_gaps,
            Path(args.mail_candidates).resolve() if args.mail_candidates else None,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"verified": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verified"] else 2


if __name__ == "__main__":
    sys.exit(main())
