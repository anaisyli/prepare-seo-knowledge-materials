#!/usr/bin/env python3
"""Unpack chosen archives into a new materials folder, to screen as a supplementary package.

Archives are not unpacked into a package. When some of them hold material worth
screening, such as product pictures or drawings, this script unpacks just those into
a separate folder that mirrors where each archive sat. That folder then goes through
the normal steps (inventory, triage, build, verify) as a small package of its own, and
the knowledge base reads it with a second --package.

The sources are only read. Files whose content the main package already holds are not
written again, and nested archives stay packed, recorded for a later round if needed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from package_common import MANIFEST_NAME, is_system_file, load_json_object, long_path, sha256_file


ARCHIVE_SUFFIXES = {".zip", ".rar", ".7z"}
UTF8_FLAG = 0x800


def member_name(info: zipfile.ZipInfo) -> str:
    """ZIPs made on Chinese Windows store names in GBK without saying so."""
    name = info.filename
    if not info.flag_bits & UTF8_FLAG:
        try:
            name = name.encode("cp437").decode("gbk")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return name.replace("\\", "/")


def safe_parts(name: str) -> list[str] | None:
    """The member's path as folder names, or None when it would leave the folder."""
    path = PurePosixPath(name)
    parts = [part for part in path.parts if part not in {"", "."}]
    if path.is_absolute() or not parts or ".." in parts or ":" in parts[0]:
        return None
    return parts


def known_hashes(package: Path | None) -> set[str]:
    if not package:
        return set()
    assets = load_json_object(package / MANIFEST_NAME).get("assets", [])
    return {str(a.get("source_hash")).casefold() for a in assets if a.get("copy_status") == "copied"}


class Extraction:
    def __init__(self, target: Path, known: set[str], limit: int) -> None:
        self.target, self.known, self.limit = target, known, limit
        self.written: list[str] = []
        self.already_in_package: list[str] = []
        self.nested: list[str] = []
        self.unsafe: list[str] = []
        self.size = 0

    def place(self, parts: list[str], stream: Any) -> None:
        """Copy one member through a hash, keeping it only when it is new."""
        relative = "/".join(parts)
        if is_system_file(parts[-1]):
            return
        destination = self.target.joinpath(*parts)
        os.makedirs(long_path(destination.parent, always=True), exist_ok=True)
        partial = destination.with_name(destination.name + ".partial")
        digest = hashlib.sha256()
        with open(long_path(partial), "wb") as handle:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                self.size += len(block)
                if self.size > self.limit:
                    handle.close()
                    os.remove(long_path(partial))
                    raise ValueError(f"解压内容超过上限 {self.limit // 1024 ** 3} GB，停止：{self.target}")
                digest.update(block)
                handle.write(block)
        if digest.hexdigest() in self.known:
            # Already in the main package, or written from an archive earlier in this run.
            os.remove(long_path(partial))
            self.already_in_package.append(relative)
            return
        os.replace(long_path(partial), long_path(destination))
        self.known.add(digest.hexdigest())
        self.written.append(relative)
        if destination.suffix.casefold() in ARCHIVE_SUFFIXES:
            self.nested.append(relative)

    def report(self) -> dict[str, Any]:
        return {"written": len(self.written), "already_in_package": len(self.already_in_package),
                "nested_archives": self.nested, "unsafe_names_skipped": self.unsafe}


def extract_zip(archive: Path, run: Extraction) -> None:
    with zipfile.ZipFile(long_path(archive)) as handle:
        for info in handle.infolist():
            if info.is_dir():
                continue
            name = member_name(info)
            parts = safe_parts(name)
            if parts is None:
                run.unsafe.append(name)
                continue
            with handle.open(info) as stream:
                run.place(parts, stream)


def extract_with_tool(archive: Path, run: Extraction, extractor: str, scratch: Path) -> None:
    """RAR and 7z need an external tool; unpack to scratch, then place file by file."""
    temporary = Path(tempfile.mkdtemp(prefix="unpack-", dir=long_path(scratch)))
    try:
        if "7z" in Path(extractor).name.casefold():
            command = [extractor, "x", "-y", f"-o{temporary}", str(archive)]
        else:  # Bandizip's bz.exe
            command = [extractor, "x", "-y", f"-o:{temporary}", str(archive)]
        result = subprocess.run(command, capture_output=True, timeout=3600)
        if result.returncode != 0:
            raise ValueError(f"解压失败（退出码 {result.returncode}）：{archive}")
        root = long_path(temporary, always=True)
        for current, _, names in os.walk(root):
            for name in sorted(names):
                relative = Path(os.path.relpath(os.path.join(current, name), root)).as_posix()
                parts = safe_parts(relative)
                if parts is None:
                    run.unsafe.append(relative)
                    continue
                with open(os.path.join(current, name), "rb") as stream:
                    run.place(parts, stream)
    finally:
        shutil.rmtree(long_path(temporary, always=True), ignore_errors=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source-root", required=True, help="The client's materials folder the archives are in")
    parser.add_argument("--archive", action="append", required=True,
                        help="Archive path below --source-root; repeat for each archive")
    parser.add_argument("--out", required=True, help="New, empty folder for the unpacked materials")
    parser.add_argument("--record", required=True, help="JSON record to write, outside --out")
    parser.add_argument("--known-package", help="Main package; files it already holds are not written again")
    parser.add_argument("--extractor", help="bz.exe (Bandizip) or 7z.exe, needed for RAR and 7z")
    parser.add_argument("--max-gb", type=float, default=5.0, help="Stop when one archive unpacks to more than this")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root, out, record = (Path(p).resolve() for p in (args.source_root, args.out, args.record))
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"--out 必须是新的空文件夹：{out}")
    if out.is_relative_to(root) or root.is_relative_to(out):
        raise SystemExit("--out 不能放在客户资料文件夹里面，也不能包含它")
    if record.is_relative_to(out):
        raise SystemExit("--record 不能放在 --out 里面，否则会被当成资料筛选")
    package = Path(args.known_package).resolve() if args.known_package else None
    known = known_hashes(package)
    out.mkdir(parents=True, exist_ok=True)
    limit = int(args.max_gb * 1024 ** 3)
    results = []
    for raw in args.archive:
        relative = PurePosixPath(raw.replace("\\", "/"))
        archive = root.joinpath(*relative.parts)
        if not os.path.isfile(long_path(archive)):
            raise SystemExit(f"找不到压缩包：{archive}")
        suffix = archive.suffix.casefold()
        # Mirror the archive's place: 产品/X100/图纸.zip unpacks into 产品/X100/图纸/.
        target = out.joinpath(*relative.parent.parts, archive.stem)
        run = Extraction(target, known, limit)
        if suffix == ".zip":
            extract_zip(archive, run)
        elif suffix in {".rar", ".7z"}:
            if not args.extractor:
                raise SystemExit(f"RAR 和 7z 需要 --extractor（bz.exe 或 7z.exe）：{archive}")
            extract_with_tool(archive, run, args.extractor, out.parent)
        else:
            raise SystemExit(f"不是 ZIP、RAR 或 7z：{archive}")
        results.append({"archive": relative.as_posix(), "archive_sha256": sha256_file(archive),
                        "unpacked_to": target.relative_to(out).as_posix(), **run.report()})
    summary = {"source_root": str(root), "out": str(out), "known_package": str(package) if package else None,
               "archives": results}
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"archives": len(results), "written": sum(r["written"] for r in results),
                      "already_in_package": sum(r["already_in_package"] for r in results),
                      "nested_archives": sum(len(r["nested_archives"]) for r in results),
                      "unsafe_names_skipped": sum(len(r["unsafe_names_skipped"]) for r in results),
                      "next": "对 --out 运行 inventory_materials.py，筛成补充初筛包"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
