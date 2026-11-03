#!/usr/bin/env python3
"""Copy triaged source files into the preparation package and write its lists.

Decisions come only from the triage file, never from this script. Sources are
opened read-only; every copy is hash-verified before it is recorded.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from client_review import WORKBOOK_NAME, write_workbook
from package_common import (
    AUDIT_DIRECTORY,
    DECISIONS,
    LARGE_FILE_BYTES,
    MANIFEST_NAME,
    RESOURCE_LABELS,
    SCOPES,
    SCRIPT_VERSION,
    asset_kind,
    is_restricted,
    load_jsonl,
    load_json_object,
    load_triage,
    long_path,
    sanitize_component,
    sha256_file,
    usable_as_fact,
)


DECISION_DIRECTORIES = {
    "A": "A-原文保留",
    "B": "B-待清理",
    "C": "C-知识点/来源文件",
    "D": "D-待定",
    "E": "E-排除",
}
DECISION_LABELS = {
    "A": "原文保留",
    "B": "待清理",
    "C": "提取知识点",
    "D": "待定",
    "E": "排除",
}
MEDIA_LABELS = {"video": "视频，待转写", "audio": "音频，待转写", "image": "图片，待看"}
SCOPE_LABELS = {"general": "通用", "style": "某个款式", "single_communication": "某次沟通"}


class BuildError(Exception):
    pass


def normalized_item(raw: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    item = dict(raw)
    resource_type = item.get("resource_type")
    if resource_type not in RESOURCE_LABELS:
        if resource_type is not None:
            warnings.append(f"Unknown resource_type on {item.get('item_id')}: treated as unknown")
        item["resource_type"] = "unknown"
    return item


def target_directory(item: dict[str, Any]) -> str:
    decision = item["decision"]
    if decision in {"A", "E"}:
        return f"{DECISION_DIRECTORIES[decision]}/{RESOURCE_LABELS[item['resource_type']]}"
    return DECISION_DIRECTORIES[decision]


def unique_destination(package: Path, directory: str, name: str, taken: set[str]) -> str:
    stem, suffix = os.path.splitext(name)
    candidate = f"{directory}/{name}"
    counter = 1
    while candidate.casefold() in taken or os.path.exists(long_path(package / candidate)):
        candidate = f"{directory}/{stem}_{counter}{suffix}"
        counter += 1
    taken.add(candidate.casefold())
    return candidate


def copy_verified(source: Path, destination: Path, expected_hash: str | None) -> str:
    """Copy through a temporary name so a failed copy never looks finished."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.part")
    shutil.copyfile(long_path(source), long_path(temporary))
    output_hash = sha256_file(temporary)
    if expected_hash and output_hash.casefold() != expected_hash.casefold():
        os.remove(long_path(temporary))
        raise BuildError("hash_mismatch")
    os.replace(long_path(temporary), long_path(destination))
    return output_hash


def pending_units(item: dict[str, Any]) -> list[str]:
    """Where in the file the client still has to decide, when only part of it waits."""
    if item.get("pending_client_review") is not True or item.get("pending_scope") != "part":
        return []
    return [str(entry.get("location")) for entry in item.get("client_review_items", [])]


def base_record(
    item: dict[str, Any], inventory_item: dict[str, Any] | None, kind: str
) -> dict[str, Any]:
    decision = item["decision"]
    return {
        "item_id": item["item_id"],
        "decision": decision,
        "resource_type": item["resource_type"],
        "pending_client_review": item.get("pending_client_review") is True,
        "pending_units": pending_units(item),
        "business_tags": item.get("business_tags", []),
        "display_name": (inventory_item or {}).get("display_name", item.get("title", "")),
        "asset_kind": kind,
        "source_hash": (inventory_item or {}).get("source_hash"),
        "byte_size": (inventory_item or {}).get("byte_size"),
        "parent_id": (inventory_item or {}).get("parent_id"),
        "path": None,
        "importable": decision == "A" and not is_restricted(item),
        "usable_as_fact": usable_as_fact(item),
    }


def place_items(
    package: Path,
    inventory_items: dict[str, dict[str, Any]],
    triage_items: dict[str, dict[str, Any]],
    include_restricted: bool,
    withheld: set[str],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    taken: set[str] = set()
    placed: dict[tuple[str, str], str] = {}

    for item_id in sorted(inventory_items):
        inventory_item = inventory_items[item_id]
        extension = inventory_item.get("extension") or ""
        kind = inventory_item.get("asset_kind") or asset_kind(extension)
        item = triage_items.get(item_id)
        if item is None:
            records.append(
                {
                    "item_id": item_id,
                    "decision": None,
                    "display_name": inventory_item.get("display_name"),
                    "asset_kind": kind,
                    "path": None,
                    "copy_status": "missing_decision",
                    "importable": False,
                    "usable_as_fact": False,
                }
            )
            continue

        record = base_record(item, inventory_item, kind)
        records.append(record)
        size = inventory_item.get("byte_size") or 0

        if item_id in withheld or inventory_item.get("display_name") in withheld:
            record["copy_status"] = "withheld_by_client"
            record["importable"] = record["usable_as_fact"] = False
            continue
        if is_restricted(item) and not include_restricted:
            record["copy_status"] = "not_copied_restricted"
            continue
        source_ref = inventory_item.get("source_ref")
        if inventory_item.get("source_kind", "local_file") != "local_file" or not source_ref:
            record["copy_status"] = "not_persisted"
            continue

        source = Path(source_ref)
        expected = inventory_item.get("source_hash")
        directory = target_directory(item)
        record["large_file"] = size > LARGE_FILE_BYTES

        key = (expected or item_id, directory)
        if key in placed:
            record["copy_status"] = "duplicate"
            record["duplicate_of"] = placed[key]
            record["importable"] = False
            continue

        try:
            if not source.is_file() or source.is_symlink():
                raise BuildError("source_missing")
            if expected and sha256_file(source).casefold() != expected.casefold():
                raise BuildError("source_changed")
            name = sanitize_component(
                str(inventory_item.get("display_name") or source.name), item_id
            )
            relative = unique_destination(package, directory, name, taken)
            record["output_hash"] = copy_verified(source, package / relative, expected)
        except (BuildError, OSError) as exc:
            record["copy_status"] = "copy_failed"
            record["copy_error"] = str(exc) if isinstance(exc, BuildError) else type(exc).__name__
            record["importable"] = record["usable_as_fact"] = False
            continue

        record["path"] = relative
        record["copy_status"] = "copied"
        record["verification_status"] = "hash_verified"
        placed[key] = item_id
    return records


def normalized_knowledge_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Points are formal knowledge unless the client still has to decide on them."""
    output = []
    for point in points:
        pending = point.get("pending_client_review") is True
        if point.get("scope") not in SCOPES:
            raise BuildError(f"Knowledge point needs a valid scope: {point.get('knowledge_id')}")
        output.append(
            {
                **point,
                "record_type": "knowledge_point",
                "pending_client_review": pending,
                "status": "pending_client_review" if pending else "approved",
                "importable": True,
                "usable_as_fact": not pending,
            }
        )
    return output


def relative_link(list_file: str, target: str) -> str:
    return Path(os.path.relpath(target, os.path.dirname(list_file) or ".")).as_posix()


def file_link(list_file: str, record: dict[str, Any]) -> str:
    name = str(record.get("display_name") or record["item_id"]).replace("|", "/")
    if not record.get("path"):
        return name
    return f"[{name}](<{relative_link(list_file, record['path'])}>)"


def text_of(item: dict[str, Any] | None, key: str) -> str:
    return " ".join(str((item or {}).get(key) or "").split()).replace("|", "/")


def write_text(package: Path, relative: str, text: str, generated: list[str]) -> None:
    destination = package / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8", newline="\n")
    generated.append(relative)


def keep_list(package: Path, relative: str, title: str, lines: list[str], generated: list[str]) -> None:
    write_text(package, relative, "\n".join([f"# {title}", "", *lines, ""]), generated)


def pending_label(record: dict[str, Any]) -> str:
    if record.get("pending_units"):
        return "部分：" + "、".join(record["pending_units"]).replace("|", "/")
    return "是" if record.get("pending_client_review") else "否"


def write_decision_lists(
    package: Path,
    records: list[dict[str, Any]],
    triage_items: dict[str, dict[str, Any]],
    generated: list[str],
) -> None:
    by_decision: dict[str, list[dict[str, Any]]] = {key: [] for key in DECISIONS}
    for record in records:
        if record.get("decision") in by_decision:
            by_decision[record["decision"]].append(record)

    list_file = "A-原文保留/A-清单.md"
    rows = ["| 文件 | 标签 | 可当公司事实 | 待客户审核 | 状态 |", "|---|---|---|---|---|"]
    for record in by_decision["A"]:
        rows.append(
            f"| {file_link(list_file, record)} | {RESOURCE_LABELS[record['resource_type']]} "
            f"| {'是' if record.get('usable_as_fact') else '否'} "
            f"| {pending_label(record)} "
            f"| {record['copy_status']} |"
        )
    keep_list(package, list_file, f"A 类 — 原文保留（{len(by_decision['A'])} 项）", rows, generated)

    list_file = "B-待清理/B-清单.md"
    rows = [
        "清理并验证前不能入库。文件尚未修改。",
        "",
        "| 文件 | 类型 | 需删除位置 | 说明 |",
        "|---|---|---|---|",
    ]
    for record in by_decision["B"]:
        item = triage_items[record["item_id"]]
        locators = [
            str(locator)
            for action in item.get("actions", [])
            for locator in action.get("locators", [])
        ]
        rows.append(
            f"| {file_link(list_file, record)} | {RESOURCE_LABELS[record['resource_type']]} "
            f"| {'; '.join(locators).replace('|', '/')} | {text_of(item, 'summary')} |"
        )
    keep_list(package, list_file, f"B 类 — 待清理（{len(by_decision['B'])} 项）", rows, generated)

    list_file = "D-待定/D-清单.md"
    rows = ["消除不确定性并重新分类前不能入库。", "", "| 文件 | 原因 | 需要补充 |", "|---|---|---|"]
    for record in by_decision["D"]:
        item = triage_items[record["item_id"]]
        rows.append(
            f"| {file_link(list_file, record)} | {text_of(item, 'summary')} "
            f"| {text_of(item, 'required_follow_up')} |"
        )
    keep_list(package, list_file, f"D 类 — 待定（{len(by_decision['D'])} 项）", rows, generated)

    list_file = "C-知识点/来源文件清单.md"
    rows = ["这些原件只用于追溯知识点，不能入库。", ""]
    rows += [f"- {file_link(list_file, record)}" for record in by_decision["C"]]
    keep_list(package, list_file, f"C 类 — 来源文件（{len(by_decision['C'])} 项）", rows, generated)

    reasons: Counter[str] = Counter()
    relative = "E-排除/E-完整清单.csv"
    (package / "E-排除").mkdir(parents=True, exist_ok=True)
    with (package / relative).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["文件", "类型", "原因代码", "说明", "搬运状态", "包内位置"])
        for record in by_decision["E"]:
            item = triage_items[record["item_id"]]
            codes = ";".join(str(code) for code in item.get("reason_codes", []))
            reasons[codes or "未写原因"] += 1
            writer.writerow(
                [
                    record.get("display_name"),
                    RESOURCE_LABELS[record["resource_type"]],
                    codes,
                    text_of(item, "summary"),
                    record["copy_status"],
                    record.get("path") or "",
                ]
            )
    generated.append(relative)
    rows = ["完整明细见 `E-完整清单.csv`。", "", "## 排除原因分布", ""]
    rows += [f"- {code}：{count}" for code, count in reasons.most_common()]
    keep_list(package, "E-排除/E-清单.md", f"E 类 — 排除（{len(by_decision['E'])} 项）", rows, generated)


def point_line(point: dict[str, Any]) -> str:
    return f"[{SCOPE_LABELS[point['scope']]}] {point.get('knowledge_point')}"


def write_knowledge_points(
    package: Path, points: list[dict[str, Any]], generated: list[str]
) -> None:
    relative = "C-知识点/knowledge-points.jsonl"
    write_text(
        package,
        relative,
        "".join(json.dumps(point, ensure_ascii=False) + "\n" for point in points),
        generated,
    )
    formal = [p for p in points if not p["pending_client_review"]]
    pending = [p for p in points if p["pending_client_review"]]
    rows = [f"正式知识点 {len(formal)} 条，待客户审核 {len(pending)} 条。", "", "## 正式知识点", ""]
    rows += [f"- {point_line(p)}（{p.get('locator')}）" for p in formal]
    rows += ["", "## 待客户审核", ""]
    rows += [f"- {point_line(p)}（{p.get('locator')}）" for p in pending]
    keep_list(package, "C-知识点/C-清单.md", f"C 类 — 知识点（{len(points)} 条）", rows, generated)


def review_rows(
    records: list[dict[str, Any]],
    triage_items: dict[str, dict[str, Any]],
    points: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """One row per thing the client decides, in the triage's plain wording."""
    rows: list[dict[str, Any]] = []
    names = {record["item_id"]: record.get("display_name") for record in records}
    for record in records:
        # A repeated file was already listed; the client should not answer twice.
        if not record.get("pending_client_review") or record.get("copy_status") == "duplicate":
            continue
        item = triage_items[record["item_id"]]
        entries = item.get("client_review_items") or [{}]
        for index, entry in enumerate(entries, start=1):
            rows.append(
                {
                    "id": f"{record['item_id']}#{index}",
                    "summary": entry.get("summary") or item.get("summary"),
                    "source": record.get("display_name"),
                    "location": entry.get("location", "整份文件"),
                    "question": entry.get("question", "这份内容可以使用吗？"),
                }
            )
    for point in points:
        if point["pending_client_review"]:
            rows.append(
                {
                    "id": str(point.get("knowledge_id")),
                    "summary": point.get("knowledge_point"),
                    "source": names.get(point.get("source_id")),
                    "location": point.get("client_location") or str(point.get("locator", "")).lstrip("# "),
                    "question": point.get("client_question", "这条内容可以使用吗？"),
                }
            )
    return rows


def write_client_review(
    package: Path,
    records: list[dict[str, Any]],
    triage_items: dict[str, dict[str, Any]],
    points: list[dict[str, Any]],
    company: str,
    generated: list[str],
) -> int:
    rows = review_rows(records, triage_items, points)
    notes = {"not_copied_restricted": "财务、合同或账户类资料", "withheld_by_client": "您要求不带走"}
    held = [
        {"name": record.get("display_name"), "note": notes[record["copy_status"]]}
        for record in records
        if record.get("copy_status") in notes
    ]
    write_workbook(package / WORKBOOK_NAME, rows, held, company)
    generated.append(WORKBOOK_NAME)
    return len(rows)


def media_section(records: list[dict[str, Any]]) -> list[str]:
    """Gather the audio, video, and unseen images, so they are not lost among D items."""
    waiting = [
        record
        for record in records
        if record.get("decision") == "D"
        and record.get("asset_kind") in MEDIA_LABELS
        and record.get("copy_status") == "copied"
    ]
    rows = ["## 待转写/待看", ""]
    if not waiting:
        return [*rows, "无", ""]
    rows += ["| 文件 | 类型 | 大小 |", "|---|---|---|"]
    for record in sorted(waiting, key=lambda entry: (entry["asset_kind"], str(entry.get("display_name")))):
        size = (record.get("byte_size") or 0) / (1024 * 1024)
        link = file_link("00_总清单.md", record)
        rows.append(f"| {link} | {MEDIA_LABELS[record['asset_kind']]} | {size:.1f} MB |")
    return [*rows, ""]


def write_summary(
    package: Path,
    records: list[dict[str, Any]],
    points: list[dict[str, Any]],
    inventory: dict[str, Any],
    review_count: int,
    generated: list[str],
) -> None:
    decisions = Counter(str(record.get("decision")) for record in records)
    statuses = Counter(str(record.get("copy_status")) for record in records)
    types = Counter(RESOURCE_LABELS.get(str(r.get("resource_type")), "未归类") for r in records)
    attachments = sum(1 for record in records if record.get("parent_id"))
    missing = inventory.get("missing_attachments", [])
    gaps = inventory.get("attachment_export_gaps", [])
    unverified = inventory.get("attachment_unverified", [])

    rows = [f"- 条目总数：{len(records)}", f"- 知识点：{len(points)} 条", "", "## 分类", ""]
    rows += ["| 分类 | 数量 |", "|---|---|"]
    for key in sorted(DECISIONS):
        rows.append(f"| {key} {DECISION_LABELS[key]} | {decisions.get(key, 0)} |")
    rows += ["", "## 资料类型", "", "| 类型 | 数量 |", "|---|---|"]
    rows += [f"| {label} | {count} |" for label, count in types.most_common()]
    rows += ["", "## 文件搬运", "", "| 状态 | 数量 |", "|---|---|"]
    rows += [f"| {status} | {count} |" for status, count in statuses.most_common()]
    rows += [
        "",
        "## 附件",
        "",
        f"- 已关联到邮件的附件：{attachments}",
        f"- 取料时未保存的附件：{len(missing)}",
        f"- 导出时未带附件的邮件：{len(gaps)}",
        f"- 无法确认附件是否完整的邮件：{len(unverified)}",
        "",
        "## 客户确认",
        "",
        f"- `{WORKBOOK_NAME}` 里有 {review_count} 项等客户确认。",
        "",
        *media_section(records),
        "## 超过 50MB 的文件",
        "",
    ]
    large = [record for record in records if record.get("large_file")]
    rows += [f"- {file_link('00_总清单.md', record)}" for record in large] or ["无"]
    rows += ["", "源文件未被修改，B 类删除尚未执行。整理包内部受限，不要整包转发。"]
    keep_list(package, "00_总清单.md", "整理包总清单", rows, generated)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy triaged files into the preparation package and write its lists."
    )
    parser.add_argument("--inventory", required=True, help="inventory.json")
    parser.add_argument("--triage", required=True, help="triage-results.json")
    parser.add_argument("--output", required=True, help="New, empty package directory")
    parser.add_argument("--knowledge-points", help="knowledge-points.jsonl from triage")
    parser.add_argument("--company", default="", help="Client name shown on the review workbook")
    parser.add_argument(
        "--include-restricted",
        action="store_true",
        help="Also copy finance, contract, and account items, which are otherwise only recorded",
    )
    parser.add_argument(
        "--withhold",
        help="Text file of file names or item IDs the client does not allow to leave site, one per line",
    )
    return parser.parse_args()


def build(args: argparse.Namespace) -> dict[str, Any]:
    package = Path(args.output).expanduser().resolve()
    inventory_path = Path(args.inventory).resolve()
    triage_path = Path(args.triage).resolve()

    inventory = load_json_object(inventory_path)
    inventory_items = {item["item_id"]: item for item in inventory.get("items", [])}
    header, raw_items = load_triage(triage_path)

    scope = header.get("scope_confirmation") or {}
    if scope.get("confirmed") is not True:
        raise BuildError("Triage has no confirmed scope_confirmation")
    if package.exists() and any(package.iterdir()):
        raise BuildError("Output directory must be new or empty")
    for root in inventory.get("input_roots", []):
        resolved_root = Path(root).resolve()
        if package.is_relative_to(resolved_root) or resolved_root.is_relative_to(package):
            raise BuildError("Output directory must stay separate from the source directories")

    warnings: list[str] = []
    triage_items: dict[str, dict[str, Any]] = {}
    for raw in raw_items:
        item = normalized_item(raw, warnings)
        if item.get("decision") not in DECISIONS:
            raise BuildError(f"Invalid decision on {item.get('item_id')}")
        if item["item_id"] not in inventory_items:
            raise BuildError(f"Triage item is not in the inventory: {item['item_id']}")
        if item["item_id"] in triage_items:
            raise BuildError(f"Duplicate triage item: {item['item_id']}")
        if item.get("pending_scope") == "part" and not all(
            entry.get("location") for entry in item.get("client_review_items") or [{}]
        ):
            raise BuildError(f"Partial client review needs a location per entry: {item['item_id']}")
        triage_items[item["item_id"]] = item

    withheld: set[str] = set()
    if args.withhold:
        withheld = {
            line.strip()
            for line in Path(args.withhold).read_text(encoding="utf-8").splitlines()
            if line.strip()
        }

    points = []
    if args.knowledge_points:
        points = normalized_knowledge_points(load_jsonl(Path(args.knowledge_points)))

    package.mkdir(parents=True, exist_ok=True)
    generated: list[str] = []
    records = place_items(
        package,
        inventory_items,
        triage_items,
        args.include_restricted,
        withheld,
    )
    for directory in ("A-原文保留", "B-待清理", "C-知识点", "D-待定", "E-排除"):
        (package / directory).mkdir(parents=True, exist_ok=True)
    write_decision_lists(package, records, triage_items, generated)
    write_knowledge_points(package, points, generated)
    review_count = write_client_review(package, records, triage_items, points, args.company, generated)
    write_summary(package, records, points, inventory, review_count, generated)

    audit = package / AUDIT_DIRECTORY
    audit.mkdir(exist_ok=True)
    shutil.copyfile(inventory_path, audit / "inventory.json")
    shutil.copyfile(triage_path, audit / "triage-results.json")

    manifest = {
        "package_version": SCRIPT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "run_id": header.get("run_id"),
        "scope_confirmed": True,
        "assets": records,
        "knowledge_point_count": len(points),
        "generated_files": generated,
        "include_restricted": args.include_restricted,
        "client_review_count": review_count,
        "missing_attachments": inventory.get("missing_attachments", []),
        "attachment_export_gaps": inventory.get("attachment_export_gaps", []),
        "attachment_unverified": inventory.get("attachment_unverified", []),
        "warnings": warnings,
    }
    (package / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    statuses = Counter(str(record.get("copy_status")) for record in records)
    return {
        "output": str(package),
        "item_count": len(records),
        "copy_status": dict(statuses),
        "knowledge_point_count": len(points),
        "warning_count": len(warnings),
    }


def main() -> int:
    args = parse_args()
    try:
        result = build(args)
    except (BuildError, ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"built": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    failed = {"copy_failed", "missing_decision"} & set(result["copy_status"])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
