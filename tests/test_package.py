from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from client_review import read_review_rows  # noqa: E402

SCOPE = {
    "confirmed": True,
    "confirmed_at": "2026-11-02",
    "declared_scope": "D:/ClientMaterials",
    "confirmation_source": "current_request",
}


def run_script(name: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPTS / name), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PackageCase(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.sources = self.root / "sources"
        self.sources.mkdir()
        self.package = self.root / "package"

    def add_source(self, name: str, content: bytes | str = b"content") -> Path:
        path = self.sources / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
        return path

    def inventory(self, *extra: str) -> dict[str, dict[str, Any]]:
        self.inventory_path = self.root / "inventory.json"
        completed = run_script(
            "inventory_materials.py", str(self.sources), "--output", str(self.inventory_path), *extra
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        document = json.loads(self.inventory_path.read_text(encoding="utf-8"))
        return {item["display_name"]: item for item in document["items"]}

    def decisions(
        self, items: dict[str, dict[str, Any]], overrides: dict[str, dict[str, Any]]
    ) -> None:
        """Default every item to a well-formed E, then apply per-file overrides."""
        records = []
        for name, item in items.items():
            record = {
                "item_id": item["item_id"],
                "decision": "E",
                "resource_type": "noise",
                "reason_codes": ["no_knowledge_value"],
                "summary": "No reusable knowledge.",
                "content_read": True,
                "mail_review": "full",
            }
            record.update(overrides.get(name, {}))
            records.append(record)
        self.triage_path = self.root / "triage-results.json"
        self.triage_path.write_text(
            json.dumps({"run_id": "test", "scope_confirmation": SCOPE, "items": records}),
            encoding="utf-8",
        )

    def build(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return run_script(
            "build_package.py",
            "--inventory",
            str(self.inventory_path),
            "--triage",
            str(self.triage_path),
            "--output",
            str(self.package),
            *extra,
        )

    def verify(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return run_script("verify_package.py", str(self.package), *extra)

    def manifest(self) -> dict[str, Any]:
        return json.loads((self.package / "审计记录" / "package-manifest.json").read_text(encoding="utf-8"))

    def asset(self, name: str) -> dict[str, Any]:
        return next(a for a in self.manifest()["assets"] if a["display_name"] == name)

    def assert_built_and_verified(self, *extra: str) -> None:
        built = self.build(*extra)
        self.assertEqual(built.returncode, 0, built.stderr + built.stdout)
        verified = self.verify()
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)


class PlacementTests(PackageCase):
    def test_every_decision_lands_in_its_folder_with_matching_bytes(self) -> None:
        sources = {
            name: self.add_source(name, name)
            for name in ("a.pdf", "b.xlsx", "c.md", "d.docx", "e.xlsx", "pic.png", "clip.mp4")
        }
        before = {name: sha256(path) for name, path in sources.items()}
        items = self.inventory()
        self.decisions(
            items,
            {
                "a.pdf": {"decision": "A", "resource_type": "marketing"},
                "b.xlsx": {"decision": "B", "resource_type": "product"},
                "c.md": {"decision": "C", "resource_type": "business_scenario"},
                "d.docx": {"decision": "D", "resource_type": "unknown", "content_read": False},
                "e.xlsx": {"resource_type": "transaction", "reason_codes": ["transaction_detail"]},
                "pic.png": {"decision": "D", "resource_type": "unknown", "content_read": False},
                "clip.mp4": {"decision": "D", "resource_type": "unknown", "content_read": False},
            },
        )
        self.assert_built_and_verified()

        expected = {
            "a.pdf": "A-原文保留/营销宣传/a.pdf",
            "b.xlsx": "B-待清理/b.xlsx",
            "c.md": "C-知识点/来源文件/c.md",
            "d.docx": "D-待定/d.docx",
            "e.xlsx": "E-排除/交易往来/e.xlsx",
            "pic.png": "D-待定/pic.png",
            "clip.mp4": "D-待定/clip.mp4",
        }
        for name, relative in expected.items():
            self.assertEqual(self.asset(name)["path"], relative)
            self.assertEqual(sha256(self.package / relative), sha256(sources[name]))
        self.assertEqual(before, {name: sha256(path) for name, path in sources.items()})

    def test_same_name_never_overwrites(self) -> None:
        self.add_source("one/report.pdf", "first")
        self.add_source("two/report.pdf", "second")
        document = self.inventory()
        items = json.loads(self.inventory_path.read_text(encoding="utf-8"))["items"]
        self.assertEqual(len(items), 2)
        self.assertEqual(len(document), 1)
        records = [
            {
                "item_id": item["item_id"],
                "decision": "E",
                "resource_type": "noise",
                "reason_codes": ["no_knowledge_value"],
                "summary": "x",
                "content_read": True,
            }
            for item in items
        ]
        self.triage_path = self.root / "triage-results.json"
        self.triage_path.write_text(
            json.dumps({"scope_confirmation": SCOPE, "items": records}), encoding="utf-8"
        )
        self.assert_built_and_verified()
        texts = sorted(p.read_text() for p in (self.package / "E-排除" / "无知识价值").glob("report*"))
        self.assertEqual(texts, ["first", "second"])

    def test_category_with_slash_does_not_create_nested_folders(self) -> None:
        self.add_source("doc.md", "x")
        items = self.inventory()
        self.decisions(items, {"doc.md": {"resource_type": "其他(图片/索引/内部)"}})
        self.assert_built_and_verified()
        self.assertEqual(self.asset("doc.md")["path"], "E-排除/未归类/doc.md")

    def test_identical_copies_are_stored_once(self) -> None:
        self.add_source("sign1.png", "same")
        self.add_source("sign2.png", "same")
        self.decisions(self.inventory(), {})
        self.assert_built_and_verified()
        statuses = sorted(a["copy_status"] for a in self.manifest()["assets"])
        self.assertEqual(statuses, ["copied", "duplicate"])

    def test_large_file_stays_in_its_folder_and_is_listed(self) -> None:
        self.add_source("big.pdf", b"x")
        items = self.inventory()
        document = json.loads(self.inventory_path.read_text(encoding="utf-8"))
        document["items"][0]["byte_size"] = 60 * 1024 * 1024
        self.inventory_path.write_text(json.dumps(document), encoding="utf-8")
        self.decisions(items, {"big.pdf": {"decision": "A", "resource_type": "marketing"}})
        self.assert_built_and_verified()
        self.assertEqual(self.asset("big.pdf")["path"], "A-原文保留/营销宣传/big.pdf")
        self.assertTrue(self.asset("big.pdf")["large_file"])
        self.assertIn("big.pdf", (self.package / "00_总清单.md").read_text(encoding="utf-8"))

    def test_refuses_output_that_is_not_empty_or_contains_sources(self) -> None:
        self.add_source("a.md", "x")
        self.decisions(self.inventory(), {})
        self.package.mkdir()
        (self.package / "old.txt").write_text("old", encoding="utf-8")
        self.assertEqual(self.build().returncode, 2)
        self.package = self.sources / "package"
        self.assertEqual(self.build().returncode, 2)


class RestrictedTests(PackageCase):
    def setUp(self) -> None:
        super().setUp()
        self.add_source("contract.pdf", "secret")
        self.items = self.inventory()
        self.decisions(
            self.items,
            {"contract.pdf": {"resource_type": "finance", "reason_codes": ["finance_record"]}},
        )

    def test_finance_is_recorded_but_not_copied(self) -> None:
        self.assert_built_and_verified()
        self.assertEqual(self.asset("contract.pdf")["copy_status"], "not_copied_restricted")
        self.assertEqual(list(self.package.rglob("contract.pdf")), [])

    def test_explicit_flag_copies_into_restricted_folder(self) -> None:
        self.assert_built_and_verified("--include-restricted")
        self.assertEqual(self.asset("contract.pdf")["path"], "E-排除/财务/contract.pdf")

    def test_client_withheld_item_stays_behind(self) -> None:
        withheld = self.root / "withhold.txt"
        withheld.write_text(self.items["contract.pdf"]["item_id"], encoding="utf-8")
        self.assert_built_and_verified("--include-restricted", "--withhold", str(withheld))
        self.assertEqual(self.asset("contract.pdf")["copy_status"], "withheld_by_client")


class VerificationGateTests(PackageCase):
    def built_package(self) -> None:
        self.add_source("a.pdf", "a")
        self.add_source("e.md", "e")
        self.decisions(
            self.inventory(),
            {"a.pdf": {"decision": "A", "resource_type": "marketing"}},
        )
        self.assert_built_and_verified()

    def assert_rejected(self, fragment: str) -> None:
        verified = self.verify()
        self.assertEqual(verified.returncode, 2, verified.stdout)
        self.assertIn(fragment, verified.stdout)

    def test_missing_copy_is_rejected(self) -> None:
        self.built_package()
        (self.package / "A-原文保留" / "营销宣传" / "a.pdf").unlink()
        self.assert_rejected("Listed file is not in the package")

    def test_changed_copy_is_rejected(self) -> None:
        self.built_package()
        (self.package / "A-原文保留" / "营销宣传" / "a.pdf").write_text("edited", encoding="utf-8")
        self.assert_rejected("differs from its source")

    def test_file_added_by_hand_is_rejected(self) -> None:
        self.built_package()
        (self.package / "E-排除" / "extra.xlsx").write_text("x", encoding="utf-8")
        self.assert_rejected("not in manifest")

    def test_local_machine_link_in_a_list_is_rejected(self) -> None:
        self.built_package()
        listing = self.package / "A-原文保留" / "A-清单.md"
        listing.write_text("[x](file:///C:/Users/Someone/Desktop/x.pdf)", encoding="utf-8")
        self.assert_rejected("Local machine path")

    def test_item_without_decision_is_rejected(self) -> None:
        self.add_source("a.md", "a")
        self.add_source("b.md", "b")
        items = self.inventory()
        self.decisions(items, {})
        triage = json.loads(self.triage_path.read_text(encoding="utf-8"))
        triage["items"] = triage["items"][:1]
        self.triage_path.write_text(json.dumps(triage), encoding="utf-8")
        self.assertEqual(self.build().returncode, 1)
        self.assert_rejected("No decision for inventory item")

    def test_excluding_unread_file_is_rejected(self) -> None:
        self.add_source("catalog.pdf", "x")
        self.decisions(self.inventory(), {"catalog.pdf": {"content_read": False}})
        self.assertEqual(self.build().returncode, 0)
        self.assert_rejected("without reading the content")

    def test_excluding_file_that_failed_to_open_is_rejected(self) -> None:
        self.add_source("damaged.docx", b"not a zip")
        items = self.inventory()
        self.decisions(items, {})
        work = self.root / "work"
        self.assertEqual(run_script("extract_text.py", str(self.inventory_path), "--work", str(work)).returncode, 0)
        self.assertEqual(self.build().returncode, 0)
        verified = self.verify("--extract-status", str(work / "extract-status.json"))
        self.assertEqual(verified.returncode, 2)
        self.assertIn("extraction status is failed", verified.stdout)

    def test_item_awaiting_client_must_be_in_the_workbook(self) -> None:
        self.add_source("case.pdf", "x")
        self.decisions(
            self.inventory(),
            {"case.pdf": {"decision": "A", "resource_type": "marketing", "pending_client_review": True}},
        )
        self.assert_built_and_verified()
        (self.package / "客户确认表.xlsx").unlink()
        self.assert_rejected("Client review workbook is missing")

    def test_copied_restricted_file_is_rejected(self) -> None:
        self.add_source("contract.pdf", "secret")
        self.decisions(self.inventory(), {"contract.pdf": {"resource_type": "finance", "reason_codes": ["contract"]}})
        self.assertEqual(self.build("--include-restricted").returncode, 0)
        manifest = self.package / "审计记录" / "package-manifest.json"
        document = json.loads(manifest.read_text(encoding="utf-8"))
        document["include_restricted"] = False
        manifest.write_text(json.dumps(document), encoding="utf-8")
        self.assert_rejected("Restricted item was copied")

    def test_exclusion_needs_a_real_reason(self) -> None:
        self.add_source("a.xlsx", "x")
        self.decisions(self.inventory(), {"a.xlsx": {"reason_codes": ["E"]}})
        self.assertEqual(self.build().returncode, 0)
        self.assert_rejected("no real reason code")

    def test_missing_scope_confirmation_stops_the_build(self) -> None:
        self.add_source("a.md", "x")
        self.decisions(self.inventory(), {})
        triage = json.loads(self.triage_path.read_text(encoding="utf-8"))
        del triage["scope_confirmation"]
        self.triage_path.write_text(json.dumps(triage), encoding="utf-8")
        self.assertEqual(self.build().returncode, 2)


class AttachmentTests(PackageCase):
    def mail_manifest(self, attachments: list[dict[str, Any]]) -> Path:
        path = self.root / "raw.json"
        body = str(self.sources / "mail.md")
        path.write_text(
            json.dumps({"results": [{"body_path": body, "attachments": attachments}]}),
            encoding="utf-8",
        )
        return path

    def test_attachment_is_linked_to_its_email(self) -> None:
        self.add_source("mail.md", "see attachment")
        saved = self.add_source("price.xlsx", "x")
        manifest = self.mail_manifest([{"filename": "price.xlsx", "saved_to": str(saved)}])
        items = self.inventory("--mail-manifest", str(manifest))
        self.assertEqual(items["price.xlsx"]["parent_id"], items["mail.md"]["item_id"])
        self.decisions(items, {})
        self.assert_built_and_verified()
        self.assertEqual(self.asset("price.xlsx")["parent_id"], items["mail.md"]["item_id"])

    def test_unsaved_attachment_blocks_completion_until_accepted(self) -> None:
        self.add_source("mail.md", "see attachment")
        manifest = self.mail_manifest([{"filename": "huge.zip", "skipped": "too_large"}])
        self.decisions(self.inventory("--mail-manifest", str(manifest)), {})
        self.assertEqual(self.build().returncode, 0)
        verified = self.verify()
        self.assertEqual(verified.returncode, 2)
        self.assertIn("Attachments incomplete: 1 not saved", verified.stdout)
        accepted = self.verify("--accept-attachment-gaps", "client refused")
        self.assertEqual(accepted.returncode, 0, accepted.stdout)

    def test_export_without_attachments_is_detected(self) -> None:
        self.add_source("mail.md", "注：附件文件不在邮件导出数据中，如有请对照原邮箱。")
        self.decisions(self.inventory(), {})
        self.assertEqual(self.build().returncode, 0)
        verified = self.verify()
        self.assertEqual(verified.returncode, 2)
        self.assertIn("1 emails exported without attachments", verified.stdout)


class ReviewRuleTests(PackageCase):
    MAIL = "---\ndate: 2026-03-17\nsubject: \"Quilted shirt\"\n---\n\nHello\n"

    def status_file(self, item_id: str, **facts: Any) -> Path:
        path = self.root / "status.json"
        path.write_text(json.dumps({"items": {item_id: {"status": "read_ok", **facts}}}), encoding="utf-8")
        return path

    def test_quotation_with_product_columns_cannot_be_excluded_as_pricing(self) -> None:
        self.add_source("quote.xlsx", "x")
        items = self.inventory()
        self.decisions(items, {"quote.xlsx": {"resource_type": "pricing", "reason_codes": ["quotation_only"]}})
        self.assertEqual(self.build().returncode, 0)
        status = self.status_file(items["quote.xlsx"]["item_id"], product_signal=True)
        verified = self.verify("--extract-status", str(status))
        self.assertEqual(verified.returncode, 2)
        self.assertIn("excluded as pricing", verified.stdout)

    def test_quotation_with_images_cannot_be_excluded_as_pricing(self) -> None:
        self.add_source("quote.xlsx", "x")
        items = self.inventory()
        self.decisions(items, {"quote.xlsx": {"resource_type": "pricing", "reason_codes": ["quotation_only"]}})
        self.assertEqual(self.build().returncode, 0)
        status = self.status_file(items["quote.xlsx"]["item_id"], embedded_media=12)
        self.assertEqual(self.verify("--extract-status", str(status)).returncode, 2)

    def test_plain_price_list_can_be_excluded(self) -> None:
        self.add_source("prices.xlsx", "x")
        items = self.inventory()
        self.decisions(items, {"prices.xlsx": {"resource_type": "pricing", "reason_codes": ["quotation_only"]}})
        self.assertEqual(self.build().returncode, 0)
        status = self.status_file(items["prices.xlsx"]["item_id"], product_signal=False, embedded_media=0)
        self.assertEqual(self.verify("--extract-status", str(status)).returncode, 0)

    def test_only_finance_may_be_restricted(self) -> None:
        self.add_source("quote.xlsx", "x")
        self.decisions(self.inventory(), {"quote.xlsx": {"resource_type": "transaction", "restricted": True}})
        self.assertEqual(self.build().returncode, 0)
        verified = self.verify()
        self.assertEqual(verified.returncode, 2)
        self.assertIn("Only finance items may be restricted", verified.stdout)

    def test_email_cannot_be_excluded_without_review(self) -> None:
        self.add_source("mail.md", self.MAIL)
        self.decisions(self.inventory(), {"mail.md": {"mail_review": None}})
        self.assertEqual(self.build().returncode, 0)
        verified = self.verify("--accept-attachment-gaps", "test")
        self.assertEqual(verified.returncode, 2)
        self.assertIn("without reviewing", verified.stdout)

    def test_point_from_one_email_cannot_be_general(self) -> None:
        self.add_source("mail.md", self.MAIL)
        items = self.inventory()
        self.decisions(items, {"mail.md": {"decision": "C", "resource_type": "business_scenario"}})
        path = self.root / "points.jsonl"
        path.write_text(
            json.dumps({"knowledge_id": "k1", "knowledge_point": "x", "source_id": items["mail.md"]["item_id"], "locator": "m1", "scope": "general"}),
            encoding="utf-8",
        )
        self.assertEqual(self.build("--knowledge-points", str(path)).returncode, 0)
        verified = self.verify("--accept-attachment-gaps", "test")
        self.assertEqual(verified.returncode, 2)
        self.assertIn("cannot be general", verified.stdout)

    def test_repeated_file_gets_one_row_for_the_client(self) -> None:
        self.add_source("one/profile.pdf", "same")
        self.add_source("two/profile.pdf", "same")
        self.inventory()
        items = json.loads(self.inventory_path.read_text(encoding="utf-8"))["items"]
        records = [
            {"item_id": i["item_id"], "decision": "A", "resource_type": "marketing", "summary": "简介", "content_read": True, "pending_client_review": True}
            for i in items
        ]
        self.triage_path = self.root / "triage-results.json"
        self.triage_path.write_text(json.dumps({"scope_confirmation": SCOPE, "items": records}), encoding="utf-8")
        self.assert_built_and_verified()
        self.assertEqual(len(read_review_rows(self.package / "客户确认表.xlsx")), 1)


class MailCandidateTests(PackageCase):
    def run_candidates(self, *extra: str) -> list[dict[str, Any]]:
        self.inventory()
        work = self.root / "work"
        done = run_script("mail_candidates.py", str(self.inventory_path), "--work", str(work), *extra)
        self.assertEqual(done.returncode, 0, done.stderr)
        lines = (work / "mail-candidates.jsonl").read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines]

    def test_keeps_what_the_company_wrote_and_drops_the_rest(self) -> None:
        self.add_source(
            "mail.md",
            "---\ndate: 2026-01-01\nsubject: x\n---\n\n"
            "### 邮件1 (2026-01-01) 收\n\nOur factory can only make 500gsm fleece for your brand here.\n\n"
            "### 邮件2 (2026-01-02) 发\n\nWe usually wash the fabric first to control shrinkage in garments.\n"
            "Please confirm the sample today and send the tracking number to me.\n",
        )
        sentences = [r["sentence"] for r in self.run_candidates("--sent-marker", "发")]
        self.assertEqual(sentences, ["We usually wash the fabric first to control shrinkage in garments."])

    def test_statements_are_marked_for_reading_in_full(self) -> None:
        self.add_source(
            "mail.md",
            "---\ndate: 2026-01-01\nsubject: x\n---\n\n"
            "We usually wash the fabric first to control shrinkage.\n"
            "The hood lining fabric looks softer than the sleeve one.\n",
        )
        tiers = {r["sentence"][:9]: r["tier"] for r in self.run_candidates()}
        self.assertEqual(tiers, {"We usuall": "statement", "The hood ": "other"})

    def test_repeated_sentences_are_listed_once(self) -> None:
        body = "---\ndate: 2026-01-01\nsubject: x\n---\n\nWe can offer OEKO-TEX certified fabric for all fleece styles.\n"
        self.add_source("a.md", body)
        self.add_source("b.md", body + "second")
        self.assertEqual(len(self.run_candidates()), 1)


class UnverifiedMailTests(PackageCase):
    EXPORTED = "---\ndate: 2026-03-17\nsubject: \"Quilted shirt\"\ntags: [\"订单\"]\n---\n\n# Quilted shirt\n\nHello\n"

    def test_email_without_a_manifest_needs_a_reason(self) -> None:
        self.add_source("mail.md", self.EXPORTED)
        self.decisions(self.inventory(), {})
        self.assertEqual(self.build().returncode, 0)
        verified = self.verify()
        self.assertEqual(verified.returncode, 2)
        self.assertIn("1 emails have no mail manifest", verified.stdout)
        accepted = self.verify("--accept-attachment-gaps", "只拿到了邮件正文")
        self.assertEqual(accepted.returncode, 0, accepted.stdout)
        self.assertIn("只拿到了邮件正文", accepted.stdout)

    def test_email_in_the_manifest_passes(self) -> None:
        self.add_source("mail.md", self.EXPORTED)
        manifest = self.root / "raw.json"
        manifest.write_text(
            json.dumps({"results": [{"body_path": str(self.sources / "mail.md"), "attachments": []}]}),
            encoding="utf-8",
        )
        self.decisions(self.inventory("--mail-manifest", str(manifest)), {})
        self.assert_built_and_verified()

    def test_email_outside_the_manifest_is_still_flagged(self) -> None:
        self.add_source("listed.md", self.EXPORTED)
        self.add_source("other-tool.md", self.EXPORTED + "other")
        manifest = self.root / "raw.json"
        manifest.write_text(
            json.dumps({"results": [{"body_path": str(self.sources / "listed.md"), "attachments": []}]}),
            encoding="utf-8",
        )
        items = self.inventory("--mail-manifest", str(manifest))
        document = json.loads(self.inventory_path.read_text(encoding="utf-8"))
        self.assertEqual(document["attachment_unverified"], [items["other-tool.md"]["item_id"]])

    def test_mail_shapes_are_recognised(self) -> None:
        self.add_source("saved.eml", "binary")
        self.add_source("forwarded.txt", "发件人: 张三\n主题: 报价\n\n内容")
        self.add_source("sop-export.md", "---\ndate: 2026-05-07 15:53\nsubject: 通知\nfolder: INBOX\nuid: 2\n---\n正文")
        self.inventory()
        document = json.loads(self.inventory_path.read_text(encoding="utf-8"))
        self.assertEqual(len(document["attachment_unverified"]), 3)

    def test_ordinary_documents_are_not_flagged(self) -> None:
        self.add_source("notes.md", "# 产品说明\n\n主题：面料\n\n这是一份普通文档。")
        self.add_source("post.md", "---\ntitle: 文章\ndate: 2026-01-01\n---\n正文")
        self.add_source("catalog.pdf", "From: x\nSubject: y")
        self.inventory()
        document = json.loads(self.inventory_path.read_text(encoding="utf-8"))
        self.assertEqual(document["attachment_unverified"], [])


class KnowledgePointTests(PackageCase):
    def source(self) -> str:
        self.add_source("mail.md", "x")
        items = self.inventory()
        self.decisions(items, {"mail.md": {"decision": "C", "resource_type": "business_scenario"}})
        return items["mail.md"]["item_id"]

    def write_points(self, *points: dict[str, Any]) -> Path:
        path = self.root / "points.jsonl"
        path.write_text(
            "\n".join(json.dumps(p, ensure_ascii=False) for p in points), encoding="utf-8"
        )
        return path

    def test_points_are_formal_and_keep_their_scope(self) -> None:
        source_id = self.source()
        points = self.write_points(
            {"knowledge_id": "k1", "knowledge_point": "某款的面料", "source_id": source_id, "locator": "line 3", "scope": "style"},
            {"knowledge_id": "k2", "knowledge_point": "案例内容", "source_id": source_id, "locator": "line 9", "scope": "general", "pending_client_review": True},
        )
        self.assert_built_and_verified("--knowledge-points", str(points))
        written = [
            json.loads(line)
            for line in (self.package / "C-知识点" / "knowledge-points.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertEqual(written[0]["status"], "approved")
        self.assertTrue(written[0]["usable_as_fact"])
        self.assertEqual(written[1]["status"], "pending_client_review")
        self.assertFalse(written[1]["usable_as_fact"])
        listing = (self.package / "C-知识点" / "C-清单.md").read_text(encoding="utf-8")
        self.assertIn("[某个款式] 某款的面料", listing)
        rows = read_review_rows(self.package / "客户确认表.xlsx")
        self.assertEqual([row["summary"] for row in rows], ["案例内容"])
        self.assertEqual(rows[0]["source"], "mail.md")
        self.assertEqual(rows[0]["location"], "line 9")

    def test_point_without_scope_stops_the_build(self) -> None:
        source_id = self.source()
        points = self.write_points(
            {"knowledge_id": "k1", "knowledge_point": "x", "source_id": source_id, "locator": "line 1"}
        )
        self.assertEqual(self.build("--knowledge-points", str(points)).returncode, 2)

    def test_point_from_competitor_material_is_rejected(self) -> None:
        self.add_source("rival.pdf", "x")
        items = self.inventory()
        self.decisions(items, {"rival.pdf": {"decision": "A", "resource_type": "competitor"}})
        points = self.write_points(
            {"knowledge_id": "k1", "knowledge_point": "x", "source_id": items["rival.pdf"]["item_id"], "locator": "p1", "scope": "general"}
        )
        self.assertEqual(self.build("--knowledge-points", str(points)).returncode, 0)
        verified = self.verify()
        self.assertEqual(verified.returncode, 2)
        self.assertIn("competitor material", verified.stdout)


class ClientWorkbookTests(PackageCase):
    def build_review(self) -> None:
        self.add_source("own.pdf", "own")
        self.add_source("rival.pdf", "rival")
        self.add_source("cases.docx", "cases")
        self.add_source("contract.pdf", "secret")
        self.decisions(
            self.inventory(),
            {
                "own.pdf": {"decision": "A", "resource_type": "product"},
                "rival.pdf": {"decision": "A", "resource_type": "competitor"},
                "contract.pdf": {"resource_type": "finance", "reason_codes": ["contract"]},
                "cases.docx": {
                    "decision": "A",
                    "resource_type": "business_scenario",
                    "pending_client_review": True,
                    "summary": "含两个客户案例",
                    "client_review_items": [
                        {"summary": "北美客户合作案例", "location": "第 3 页", "question": "这个案例可以写进官网吗？"},
                        {"summary": "欧洲客户合作案例", "location": "第 4 页", "question": "需要匿名吗？"},
                    ],
                },
            },
        )
        self.assert_built_and_verified("--company", "测试公司")

    def test_each_item_for_the_client_gets_its_own_row(self) -> None:
        self.build_review()
        rows = read_review_rows(self.package / "客户确认表.xlsx")
        self.assertEqual([row["summary"] for row in rows], ["北美客户合作案例", "欧洲客户合作案例"])
        self.assertEqual(rows[1]["location"], "第 4 页")
        self.assertEqual(rows[1]["question"], "需要匿名吗？")
        self.assertEqual({row["choice"] for row in rows}, {""})

    def test_workbook_has_dropdown_title_and_held_files(self) -> None:
        self.build_review()
        with zipfile.ZipFile(self.package / "客户确认表.xlsx") as archive:
            review = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
            held = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
        self.assertIn('"保留,不用,需要修改"', review)
        self.assertIn("测试公司资料确认表", review)
        self.assertIn("contract.pdf", held)
        self.assertIn("财务、合同或账户类资料", held)

    def test_competitor_is_kept_separately_and_not_a_fact(self) -> None:
        self.build_review()
        self.assertEqual(self.asset("rival.pdf")["path"], "A-原文保留/竞对资料/rival.pdf")
        self.assertFalse(self.asset("rival.pdf")["usable_as_fact"])
        self.assertTrue(self.asset("own.pdf")["usable_as_fact"])
        self.assertFalse(self.asset("cases.docx")["usable_as_fact"])
        self.assertTrue(self.asset("cases.docx")["importable"])

    def test_choices_survive_a_save_by_excel(self) -> None:
        """Excel moves text into shared strings; the reader must still find every row."""
        self.build_review()
        path = self.package / "客户确认表.xlsx"
        with zipfile.ZipFile(path) as archive:
            parts = {name: archive.read(name) for name in archive.namelist()}
        sheet = parts["xl/worksheets/sheet1.xml"].decode("utf-8")
        shared: list[str] = []

        def to_shared(match: re.Match[str]) -> str:
            shared.append(match.group(2))
            return f'{match.group(1)} t="s"><v>{len(shared) - 1}</v></c>'

        sheet = re.sub(r'(<c r="[A-H]\d+" s="\d")(?: t="inlineStr")><is><t xml:space="preserve">(.*?)</t></is></c>', to_shared, sheet)
        sheet = sheet.replace('<c r="F4" s="1"/>', '<c r="F4" s="1" t="s"><v>%d</v></c>' % len(shared))
        shared.append("保留")
        strings = "".join(f"<si><t>{text}</t></si>" for text in shared)
        parts["xl/worksheets/sheet1.xml"] = sheet.encode("utf-8")
        parts["xl/sharedStrings.xml"] = (
            f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">{strings}</sst>'
        ).encode("utf-8")
        with zipfile.ZipFile(path, "w") as archive:
            for name, data in parts.items():
                archive.writestr(name, data)
        rows = read_review_rows(path)
        self.assertEqual(rows[0]["choice"], "保留")
        self.assertEqual(rows[1]["summary"], "欧洲客户合作案例")


class PartialReviewTests(PackageCase):
    CASE = {"summary": "北美客户案例", "location": "第 4 章", "question": "可以用吗？"}

    def build_with(self, **extra: Any) -> subprocess.CompletedProcess[str]:
        self.add_source("profile.docx", "x")
        self.decisions(
            self.inventory(),
            {"profile.docx": {"decision": "A", "resource_type": "marketing", "pending_client_review": True, **extra}},
        )
        return self.build()

    def test_a_case_holds_back_only_its_own_part(self) -> None:
        built = self.build_with(pending_scope="part", client_review_items=[self.CASE])
        self.assertEqual(built.returncode, 0, built.stderr)
        self.assertEqual(self.verify().returncode, 0)
        asset = self.asset("profile.docx")
        self.assertTrue(asset["usable_as_fact"])
        self.assertEqual(asset["pending_units"], ["第 4 章"])
        listing = (self.package / "A-原文保留" / "A-清单.md").read_text(encoding="utf-8")
        self.assertIn("部分：第 4 章", listing)
        self.assertEqual(read_review_rows(self.package / "客户确认表.xlsx")[0]["summary"], "北美客户案例")

    def test_a_whole_file_stays_pending_by_default(self) -> None:
        self.assertEqual(self.build_with(client_review_items=[self.CASE]).returncode, 0)
        self.assertFalse(self.asset("profile.docx")["usable_as_fact"])
        self.assertEqual(self.asset("profile.docx")["pending_units"], [])

    def test_partial_review_needs_a_location(self) -> None:
        entry = {"summary": "案例", "question": "可以用吗？"}
        self.assertEqual(self.build_with(pending_scope="part", client_review_items=[entry]).returncode, 2)


class WithholdTests(PackageCase):
    def test_client_can_withhold_by_file_name(self) -> None:
        self.add_source("private.xlsx", "x")
        self.decisions(self.inventory(), {})
        withheld = self.root / "withhold.txt"
        withheld.write_text("private.xlsx\n", encoding="utf-8")
        self.assert_built_and_verified("--withhold", str(withheld))
        self.assertEqual(self.asset("private.xlsx")["copy_status"], "withheld_by_client")
        self.assertEqual(list(self.package.rglob("private.xlsx")), [])
        with zipfile.ZipFile(self.package / "客户确认表.xlsx") as archive:
            self.assertIn("private.xlsx", archive.read("xl/worksheets/sheet2.xml").decode("utf-8"))


class WorkbookWordingTests(PackageCase):
    def test_knowledge_point_uses_plain_location_and_question(self) -> None:
        self.add_source("mail.md", "x")
        items = self.inventory()
        self.decisions(items, {"mail.md": {"decision": "C", "resource_type": "business_scenario"}})
        path = self.root / "points.jsonl"
        path.write_text(
            json.dumps(
                {
                    "knowledge_id": "k1", "knowledge_point": "案例", "source_id": items["mail.md"]["item_id"],
                    "locator": "### 邮件3 (2024-03-27)", "scope": "general", "pending_client_review": True,
                    "client_location": "2024 年 3 月 27 日的邮件", "client_question": "这段内容可以使用吗？",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.assert_built_and_verified("--knowledge-points", str(path))
        row = read_review_rows(self.package / "客户确认表.xlsx")[0]
        self.assertEqual(row["location"], "2024 年 3 月 27 日的邮件")
        self.assertEqual(row["question"], "这段内容可以使用吗？")


class CatalogTests(PackageCase):
    def test_catalog_lists_every_folder_without_reading_content(self) -> None:
        self.add_source("产品/catalog.pdf", "SECRET-BODY")
        self.add_source("root.md", "x")
        catalog = self.root / "目录.md"
        self.inventory("--catalog", str(catalog))
        text = catalog.read_text(encoding="utf-8")
        self.assertIn("## 产品", text)
        self.assertIn("catalog.pdf", text)
        self.assertIn("## 根目录", text)
        self.assertNotIn("SECRET-BODY", text)


class ExtractionTests(PackageCase):
    def test_reads_word_and_excel_and_counts_embedded_images(self) -> None:
        docx = self.sources / "guide.docx"
        with zipfile.ZipFile(docx, "w") as archive:
            archive.writestr(
                "word/document.xml",
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>Company overview</w:t></w:r></w:p></w:body></w:document>",
            )
        xlsx = self.sources / "quote.xlsx"
        with zipfile.ZipFile(xlsx, "w") as archive:
            archive.writestr(
                "xl/workbook.xml",
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="Quote" sheetId="1" r:id="rId1"/></sheets></workbook>',
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
            )
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>220GSM fleece</t></is></c></row>'
                "</sheetData></worksheet>",
            )
            archive.writestr("xl/media/image1.png", b"png")
        self.inventory()
        work = self.root / "work"
        completed = run_script("extract_text.py", str(self.inventory_path), "--work", str(work))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        status = json.loads((work / "extract-status.json").read_text(encoding="utf-8"))["items"]
        by_name = {value["display_name"]: value for value in status.values()}
        self.assertEqual(by_name["guide.docx"]["status"], "read_ok")
        self.assertEqual(by_name["quote.xlsx"]["status"], "read_ok")
        self.assertEqual(by_name["quote.xlsx"]["embedded_media"], 1)
        texts = " ".join(p.read_text(encoding="utf-8") for p in (work / "text").glob("*.json"))
        self.assertIn("Company overview", texts)
        self.assertIn("220GSM fleece", texts)


if __name__ == "__main__":
    unittest.main()
