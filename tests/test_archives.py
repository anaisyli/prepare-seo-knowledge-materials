#!/usr/bin/env python3
"""Archives: a ZIP that only repeats loose files is left out; chosen archives are
unpacked into a new folder and screened as a supplementary package."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from test_package import PackageCase, run_script, sha256


class RedundantZipTests(PackageCase):
    def test_zip_that_repeats_loose_files_is_left_out(self) -> None:
        self.add_source("产品/X100/白底图/1.jpg", "picture one")
        self.add_source("产品/X100/白底图/2.jpg", "picture two")
        with zipfile.ZipFile(self.add_source("产品/X100/白底图.zip", b""), "w") as archive:
            archive.writestr("白底图/1.jpg", "picture one")
            archive.writestr("白底图/2.jpg", "picture two")
            archive.writestr("白底图/Thumbs.db", "cache")
        with zipfile.ZipFile(self.add_source("产品/X100/详情页.zip", b""), "w") as archive:
            archive.writestr("详情页.jpg", "only here")
        self.decisions(self.inventory(), {
            "1.jpg": {"decision": "A", "resource_type": "product"},
            "2.jpg": {"decision": "A", "resource_type": "product"},
            "白底图.zip": {"decision": "D", "resource_type": "product", "content_read": False},
            "详情页.zip": {"decision": "D", "resource_type": "product", "content_read": False},
        })
        self.assert_built_and_verified()
        repeated = self.asset("白底图.zip")
        self.assertEqual(repeated["copy_status"], "redundant_archive")
        self.assertIsNone(repeated["path"])
        self.assertEqual(len(repeated["archive_member_hashes"]), 2)
        self.assertEqual(self.asset("详情页.zip")["copy_status"], "copied")
        self.assertFalse(list(self.package.rglob("白底图.zip")))
        tree = (self.package / "原目录对照.md").read_text(encoding="utf-8")
        self.assertIn("白底图.zip → D 待定，压缩包未保留，内容已有相同散件", tree)

    def test_zip_kept_when_a_member_is_missing_from_the_package(self) -> None:
        self.add_source("a.jpg", "a")
        with zipfile.ZipFile(self.add_source("ab.zip", b""), "w") as archive:
            archive.writestr("a.jpg", "a")
            archive.writestr("b.jpg", "b")
        self.decisions(self.inventory(), {"a.jpg": {"decision": "A", "resource_type": "product"},
                                          "ab.zip": {"decision": "D", "resource_type": "product", "content_read": False}})
        self.assert_built_and_verified()
        self.assertEqual(self.asset("ab.zip")["copy_status"], "copied")

    def test_left_out_zip_whose_file_disappears_is_rejected(self) -> None:
        self.add_source("a.jpg", "a")
        with zipfile.ZipFile(self.add_source("a.zip", b""), "w") as archive:
            archive.writestr("a.jpg", "a")
        self.decisions(self.inventory(), {"a.jpg": {"decision": "A", "resource_type": "product"},
                                          "a.zip": {"decision": "D", "resource_type": "product", "content_read": False}})
        self.assert_built_and_verified()
        path = self.package / "审计记录/package-manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["assets"] = [a for a in manifest["assets"] if a["display_name"] != "a.jpg"]
        path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        verified = self.verify()
        self.assertIn("Archive has a member without a retained copy", verified.stdout)


class SystemFileTests(PackageCase):
    def test_thumbs_db_excluded_without_a_reader(self) -> None:
        self.add_source("图片/Thumbs.db", b"\xd0\xcf\x11\xe0 not readable as text")
        items = self.inventory()
        self.decisions(items, {"Thumbs.db": {"decision": "E", "resource_type": "unknown",
                                             "reason_codes": ["thumbnail_cache"]}})
        work = self.root / "work"
        self.assertEqual(run_script("extract_text.py", str(self.inventory_path), "--work", str(work)).returncode, 0)
        self.assertEqual(self.build().returncode, 0)
        verified = self.verify("--extract-status", str(work / "extract-status.json"))
        self.assertEqual(verified.returncode, 0, verified.stdout)


class EarlierArchiveUpdateTests(PackageCase):
    """Packages built with archive members unpacked inside them still verify."""

    def build_with_member(self) -> tuple[Path, dict]:
        with zipfile.ZipFile(self.add_source("kit.zip", b""), "w") as archive:
            archive.writestr("readme.txt", "kit")
        self.decisions(self.inventory(), {"kit.zip": {"decision": "D", "resource_type": "product", "content_read": False}})
        self.assert_built_and_verified()
        member = self.package / "D-待定/压缩包解压资料/kit/readme.txt"
        member.parent.mkdir(parents=True)
        member.write_text("kit", encoding="utf-8")
        path = self.package / "审计记录/package-manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        kit = self.asset("kit.zip")
        manifest["archive_expansions"] = [{"parent_id": kit["item_id"], "archive_hash": kit["source_hash"],
                                           "files": [{"path": "D-待定/压缩包解压资料/kit/readme.txt", "sha256": sha256(member)}]}]
        path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        return member, manifest

    def test_unpacked_members_listed_in_the_manifest_verify(self) -> None:
        member, _ = self.build_with_member()
        verified = self.verify()
        self.assertEqual(verified.returncode, 0, verified.stdout)
        member.write_text("changed", encoding="utf-8")
        self.assertIn("Archive member differs", self.verify().stdout)


class SupplementaryPackageTests(PackageCase):
    def test_chosen_archive_becomes_a_package_of_its_own(self) -> None:
        self.add_source("产品/X100/白底图/1.jpg", "picture one")
        with zipfile.ZipFile(self.add_source("产品/X100/上架资料.zip", b""), "w") as archive:
            archive.writestr("白底图/1.jpg", "picture one")
            archive.writestr("尺寸图/X100 尺寸.pdf", "drawing")
            archive.writestr("尺寸图/Thumbs.db", "cache")
            archive.writestr("../escape.txt", "outside")
            archive.writestr("源文件.zip", "nested")
        self.decisions(self.inventory(), {
            "1.jpg": {"decision": "A", "resource_type": "product"},
            "上架资料.zip": {"decision": "D", "resource_type": "product", "content_read": False},
        })
        self.assert_built_and_verified()
        main_package = self.package

        unpacked, record = self.root / "补充资料", self.root / "work/压缩包解压记录.json"
        result = run_script("extract_archives.py", "--source-root", str(self.sources), "--archive",
                            "产品/X100/上架资料.zip", "--out", str(unpacked), "--record", str(record),
                            "--known-package", str(main_package))
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual((summary["written"], summary["already_in_package"], summary["unsafe_names_skipped"]), (2, 1, 1))
        self.assertTrue((unpacked / "产品/X100/上架资料/尺寸图/X100 尺寸.pdf").is_file())
        self.assertFalse((unpacked / "产品/X100/上架资料/白底图/1.jpg").exists())
        self.assertFalse((self.root / "escape.txt").exists())
        self.assertEqual(json.loads(record.read_text(encoding="utf-8"))["archives"][0]["nested_archives"],
                         ["源文件.zip"])
        self.assertEqual(sha256(self.sources / "产品/X100/上架资料.zip"),
                         json.loads(record.read_text(encoding="utf-8"))["archives"][0]["archive_sha256"])

        # The unpacked folder goes through the normal steps as a small package.
        self.sources, self.package = unpacked, self.root / "补充初筛包"
        items = self.inventory()
        self.assertEqual({item["source_relpath"] for item in items.values()},
                         {"产品/X100/上架资料/尺寸图/X100 尺寸.pdf", "产品/X100/上架资料/源文件.zip"})
        self.decisions(items, {"X100 尺寸.pdf": {"decision": "A", "resource_type": "product"},
                               "源文件.zip": {"decision": "D", "resource_type": "unknown", "content_read": False}})
        self.assert_built_and_verified()
        self.assertEqual(self.asset("X100 尺寸.pdf")["path"], "A-原文保留/产品资料/产品/X100/上架资料/尺寸图/X100 尺寸.pdf")

    def test_out_inside_the_client_folder_is_refused(self) -> None:
        with zipfile.ZipFile(self.add_source("a.zip", b""), "w") as archive:
            archive.writestr("a.txt", "a")
        result = run_script("extract_archives.py", "--source-root", str(self.sources), "--archive", "a.zip",
                            "--out", str(self.sources / "解压"), "--record", str(self.root / "r.json"))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.sources / "解压").exists())


if __name__ == "__main__":
    import unittest

    unittest.main()
