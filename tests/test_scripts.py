from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_SCRIPT = SKILL_ROOT / "scripts" / "inventory_materials.py"
VERIFY_SCRIPT = SKILL_ROOT / "scripts" / "verify_approved_plan.py"


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class InventoryTests(unittest.TestCase):
    def test_inventory_includes_supported_and_unsupported_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            root = Path(raw_directory)
            (root / "allowed.md").write_text("# Product\n", encoding="utf-8")
            (root / "unknown.bin").write_bytes(b"binary")
            output = root / "review" / "inventory.json"

            completed = subprocess.run(
                [sys.executable, "-B", str(INVENTORY_SCRIPT), str(root), "--output", str(output)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            inventory = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(inventory["item_count"], 2)
            by_name = {item["display_name"]: item for item in inventory["items"]}
            self.assertTrue(by_name["allowed.md"]["supported_extension"])
            self.assertFalse(by_name["unknown.bin"]["supported_extension"])
            self.assertRegex(by_name["allowed.md"]["source_hash"], r"^[0-9a-f]{64}$")


class ApprovalVerificationTests(unittest.TestCase):
    def make_plan(self, root: Path, *, destination: Path | None = None) -> tuple[Path, Path, Path]:
        source = root / "source.md"
        source.write_text("General company process.\n", encoding="utf-8")
        action: dict[str, object] = {
            "action_id": "action-0001",
            "type": "copy_then_remove",
            "execution_supported": True,
        }
        if destination is not None:
            action["destination"] = str(destination)
        plan = {
            "plan_version": "1.0",
            "run_id": "test-run",
            "approval_status": "pending",
            "items": [
                {
                    "item_id": "item-0001",
                    "source_kind": "local_file",
                    "source_ref": str(source),
                    "source_hash": sha256(source),
                    "decision": "B",
                    "actions": [action],
                }
            ],
        }
        plan_path = root / "processing-plan.json"
        write_json(plan_path, plan)
        approval = {
            "approval_version": "1.0",
            "run_id": "test-run",
            "decision": "approved",
            "plan_sha256": sha256(plan_path),
            "approved_action_ids": ["action-0001"],
            "denied_action_ids": [],
        }
        approval_path = root / "approval-record.json"
        write_json(approval_path, approval)
        return source, plan_path, approval_path

    def run_verifier(self, plan: Path, approval: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(VERIFY_SCRIPT), str(plan), str(approval)],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_matching_plan_and_source_are_verified(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            root = Path(raw_directory)
            _, plan, approval = self.make_plan(root, destination=root / "output" / "source.md")
            completed = self.run_verifier(plan, approval)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(json.loads(completed.stdout)["verified"])

    def test_changed_source_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            root = Path(raw_directory)
            source, plan, approval = self.make_plan(root)
            source.write_text("Changed after approval.\n", encoding="utf-8")
            completed = self.run_verifier(plan, approval)
            self.assertEqual(completed.returncode, 2)
            self.assertIn("Source changed after audit", completed.stderr)

    def test_source_overwrite_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            root = Path(raw_directory)
            source = root / "source.md"
            source.write_text("General company process.\n", encoding="utf-8")
            _, plan, approval = self.make_plan(root, destination=source)
            completed = self.run_verifier(plan, approval)
            self.assertEqual(completed.returncode, 2)
            self.assertIn("overwrite its source", completed.stderr)

    def test_excluded_item_cannot_enter_b_cleanup_approval(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            root = Path(raw_directory)
            source = root / "competitor-review.md"
            source.write_text("Excluded competitor research.\n", encoding="utf-8")
            plan = {
                "plan_version": "1.0",
                "run_id": "exclusion-run",
                "approval_status": "pending",
                "items": [
                    {
                        "item_id": "item-0002",
                        "source_kind": "local_file",
                        "source_ref": str(source),
                        "source_hash": sha256(source),
                        "decision": "E",
                        "actions": [
                            {
                                "action_id": "action-0002",
                                "type": "record_exclusion",
                                "execution_supported": True,
                            }
                        ],
                    }
                ],
            }
            plan_path = root / "processing-plan.json"
            write_json(plan_path, plan)
            approval = {
                "approval_version": "1.0",
                "run_id": "exclusion-run",
                "decision": "approved",
                "plan_sha256": sha256(plan_path),
                "approved_action_ids": ["action-0002"],
                "denied_action_ids": [],
            }
            approval_path = root / "approval-record.json"
            write_json(approval_path, approval)

            completed = self.run_verifier(plan_path, approval_path)

            self.assertEqual(completed.returncode, 2)
            self.assertIn("only B copy_then_remove actions", completed.stderr)

    def test_c_item_cannot_enter_b_cleanup_approval(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            root = Path(raw_directory)
            source = root / "company-process-notes.md"
            source.write_text("Internal process context.\n", encoding="utf-8")
            plan = {
                "plan_version": "1.0",
                "run_id": "c-knowledge-point-run",
                "approval_status": "pending",
                "items": [
                    {
                        "item_id": "item-0003",
                        "source_kind": "local_file",
                        "source_ref": str(source),
                        "source_hash": sha256(source),
                        "decision": "C",
                        "actions": [
                            {
                                "action_id": "action-0003",
                                "type": "extract_knowledge_point",
                                "execution_supported": True,
                            }
                        ],
                    }
                ],
            }
            plan_path = root / "processing-plan.json"
            write_json(plan_path, plan)
            approval = {
                "approval_version": "1.0",
                "run_id": "c-knowledge-point-run",
                "decision": "approved",
                "plan_sha256": sha256(plan_path),
                "approved_action_ids": ["action-0003"],
                "denied_action_ids": [],
            }
            approval_path = root / "approval-record.json"
            write_json(approval_path, approval)

            completed = self.run_verifier(plan_path, approval_path)

            self.assertEqual(completed.returncode, 2)
            self.assertIn("only B copy_then_remove actions", completed.stderr)


if __name__ == "__main__":
    unittest.main()
