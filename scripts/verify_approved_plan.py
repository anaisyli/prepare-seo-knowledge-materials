#!/usr/bin/env python3
"""Verify approved B-cleanup actions, plan integrity, and local source hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


HASH_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
ACTION_BY_DECISION = {
    "A": {"copy_original"},
    "B": {"copy_then_remove"},
    "C": {"extract_knowledge_point"},
    "D": {"record_pending"},
    "E": {"record_exclusion"},
}


class VerificationError(Exception):
    pass


def load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"Cannot read {label}: {exc.__class__.__name__}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{label} must be a JSON object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise VerificationError(f"{field} must be a non-empty string")
    return value


def require_string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise VerificationError(f"{field} must be a list of non-empty strings")
    if len(value) != len(set(value)):
        raise VerificationError(f"{field} contains duplicates")
    return value


def same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))


def verify(plan_path: Path, approval_path: Path) -> dict[str, Any]:
    plan = load_object(plan_path, "processing plan")
    approval = load_object(approval_path, "approval record")

    if plan.get("plan_version") != "1.0":
        raise VerificationError("Unsupported plan_version")
    if approval.get("approval_version") != "1.0":
        raise VerificationError("Unsupported approval_version")
    if plan.get("approval_status") != "pending":
        raise VerificationError("The immutable processing plan must retain approval_status=pending")
    if approval.get("decision") != "approved":
        raise VerificationError("Approval record decision is not approved")

    plan_run_id = require_string(plan.get("run_id"), "plan.run_id")
    approval_run_id = require_string(approval.get("run_id"), "approval.run_id")
    if plan_run_id != approval_run_id:
        raise VerificationError("Plan and approval run_id do not match")

    expected_plan_hash = require_string(approval.get("plan_sha256"), "approval.plan_sha256")
    if not HASH_PATTERN.fullmatch(expected_plan_hash):
        raise VerificationError("approval.plan_sha256 must be a SHA-256 hex digest")
    actual_plan_hash = sha256_file(plan_path)
    if actual_plan_hash.casefold() != expected_plan_hash.casefold():
        raise VerificationError("Processing plan hash does not match the approval record")

    approved_ids = require_string_list(
        approval.get("approved_action_ids"), "approval.approved_action_ids"
    )
    if not approved_ids:
        raise VerificationError("approval.approved_action_ids must contain a B-cleanup action")
    denied_ids = require_string_list(
        approval.get("denied_action_ids", []), "approval.denied_action_ids"
    )
    if set(approved_ids) & set(denied_ids):
        raise VerificationError("An action cannot be both approved and denied")

    raw_items = plan.get("items")
    if not isinstance(raw_items, list):
        raise VerificationError("plan.items must be a list")

    actions: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for item_index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            raise VerificationError(f"plan.items[{item_index}] must be an object")
        decision = require_string(raw_item.get("decision"), f"plan.items[{item_index}].decision")
        if decision not in ACTION_BY_DECISION:
            raise VerificationError(f"Unsupported decision: {decision}")
        raw_actions = raw_item.get("actions")
        if not isinstance(raw_actions, list):
            raise VerificationError(f"plan.items[{item_index}].actions must be a list")
        for action_index, raw_action in enumerate(raw_actions):
            if not isinstance(raw_action, dict):
                raise VerificationError(
                    f"plan.items[{item_index}].actions[{action_index}] must be an object"
                )
            action_id = require_string(
                raw_action.get("action_id"),
                f"plan.items[{item_index}].actions[{action_index}].action_id",
            )
            if action_id in actions:
                raise VerificationError(f"Duplicate action_id: {action_id}")
            action_type = require_string(raw_action.get("type"), f"action {action_id}.type")
            if action_type not in ACTION_BY_DECISION[decision]:
                raise VerificationError(
                    f"Action {action_id} type {action_type} is invalid for decision {decision}"
                )
            actions[action_id] = (raw_item, raw_action)

    unknown_ids = sorted(set(approved_ids) - set(actions))
    if unknown_ids:
        raise VerificationError(f"Approval references unknown actions: {', '.join(unknown_ids)}")

    verified_local_source_ids: set[str] = set()
    nonlocal_source_ids: set[str] = set()
    for action_id in approved_ids:
        item, action = actions[action_id]
        if item.get("decision") != "B" or action.get("type") != "copy_then_remove":
            raise VerificationError(
                f"Approval may contain only B copy_then_remove actions: {action_id}"
            )
        if action.get("execution_supported") is not True:
            raise VerificationError(f"Approved action is not marked execution_supported: {action_id}")

        source_kind = require_string(item.get("source_kind"), f"action {action_id} source_kind")
        if source_kind == "local_file":
            source_ref = require_string(item.get("source_ref"), f"action {action_id} source_ref")
            expected_source_hash = require_string(
                item.get("source_hash"), f"action {action_id} source_hash"
            )
            if not HASH_PATTERN.fullmatch(expected_source_hash):
                raise VerificationError(f"Invalid source hash for action {action_id}")

            source_path = Path(source_ref).expanduser()
            if source_path.is_symlink() or not source_path.is_file():
                raise VerificationError(f"Source is missing, not a file, or a symbolic link: {action_id}")
            actual_source_hash = sha256_file(source_path)
            if actual_source_hash.casefold() != expected_source_hash.casefold():
                raise VerificationError(f"Source changed after audit: {action_id}")

            destination = action.get("destination")
            if destination is not None:
                destination_path = Path(
                    require_string(destination, f"action {action_id} destination")
                ).expanduser()
                if same_path(source_path, destination_path):
                    raise VerificationError(f"Action would overwrite its source: {action_id}")

        source_id = require_string(item.get("item_id"), f"action {action_id} item_id")
        if source_kind == "local_file":
            verified_local_source_ids.add(source_id)
        else:
            nonlocal_source_ids.add(source_id)

    return {
        "verified": True,
        "run_id": plan_run_id,
        "plan_sha256": actual_plan_hash,
        "approved_action_ids": approved_ids,
        "approved_action_count": len(approved_ids),
        "verified_local_source_count": len(verified_local_source_ids),
        "nonlocal_source_count": len(nonlocal_source_ids),
        "nonlocal_source_note": (
            "Non-local versions must be reverified by their source adapters before execution."
            if nonlocal_source_ids
            else None
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify B-cleanup approval, plan integrity, and source hashes before execution."
    )
    parser.add_argument("plan", help="Path to immutable B-cleanup plan")
    parser.add_argument("approval", help="Path to approval-record.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = verify(Path(args.plan).resolve(), Path(args.approval).resolve())
    except VerificationError as exc:
        print(json.dumps({"verified": False, "error": str(exc)}), file=sys.stderr)
        return 2
    except OSError as exc:
        print(
            json.dumps({"verified": False, "error": f"Filesystem error: {exc.__class__.__name__}"}),
            file=sys.stderr,
        )
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
