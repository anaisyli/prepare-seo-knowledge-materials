#!/usr/bin/env python3
"""Open every inventoried document and record whether its content could be read.

The text goes to a working directory for triage only and never into the
package. A file that cannot be read gets a status the verifier enforces: it may
only be decided D, so nothing is excluded on its filename alone.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from package_common import load_json_object, long_path, write_json_file


WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
DRAWING = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
SHEET = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RELATIONSHIP = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

TEXT_EXTENSIONS = {
    ".md", ".markdown", ".txt", ".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml", ".xml",
    ".srt", ".vtt",
}
LEGACY_OFFICE = {".xls": "xlsx", ".doc": "docx", ".ppt": "pptx"}
MIN_PAGE_CHARACTERS = 20
CASE_WORDS = re.compile(r"(?i)合作案例|客户案例|成功案例|case stud(y|ies)|success stor(y|ies)|testimonial")
PRODUCT_WORDS = re.compile(
    r"(?i)description|fabric|composition|material|style\s*(no|#)|item\s*no|\b\d{2,3}\s?gsm\b|"
    r"面料|成分|克重|款号|款式|品名"
)
MAX_ROWS_PER_SHEET = 2000


def embedded_media(archive: zipfile.ZipFile) -> int:
    return sum(1 for name in archive.namelist() if "/media/" in name)


def docx_units(path: Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
    units = []
    with zipfile.ZipFile(path) as archive:
        body = ET.fromstring(archive.read("word/document.xml")).find(f"{WORD}body")
        index = 0
        for child in body if body is not None else []:
            index += 1
            if child.tag == f"{WORD}p":
                text = "".join(node.text or "" for node in child.iter(f"{WORD}t")).strip()
                if text:
                    units.append({"locator": f"para {index}", "text": text})
            elif child.tag == f"{WORD}tbl":
                rows = [
                    " | ".join(
                        "".join(node.text or "" for node in cell.iter(f"{WORD}t")).strip()
                        for cell in row.findall(f"{WORD}tc")
                    )
                    for row in child.findall(f"{WORD}tr")
                ]
                units.append({"locator": f"table at {index}", "text": "\n".join(rows)})
        return units, {"embedded_media": embedded_media(archive)}


def pptx_units(path: Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
    units = []
    with zipfile.ZipFile(path) as archive:
        slides = []
        for name in archive.namelist():
            match = re.fullmatch(r"ppt/(slides/slide|notesSlides/notesSlide)(\d+)\.xml", name)
            if match:
                slides.append(("notes" in name, int(match.group(2)), name))
        for is_notes, number, name in sorted(slides):
            root = ET.fromstring(archive.read(name))
            text = "\n".join(node.text for node in root.iter(f"{DRAWING}t") if node.text)
            if text.strip():
                prefix = "notes" if is_notes else "slide"
                units.append({"locator": f"{prefix} {number}", "text": text})
        return units, {"embedded_media": embedded_media(archive)}


def xlsx_units(path: Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
    units = []
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            for entry in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall(f"{SHEET}si"):
                shared.append("".join(node.text or "" for node in entry.iter(f"{SHEET}t")))
        targets = {}
        if "xl/_rels/workbook.xml.rels" in names:
            for relation in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels")):
                targets[relation.get("Id")] = relation.get("Target", "").lstrip("/")
        sheets = []
        for sheet in ET.fromstring(archive.read("xl/workbook.xml")).iter(f"{SHEET}sheet"):
            state = sheet.get("state") or "visible"
            sheets.append({"name": sheet.get("name"), "state": state})
            target = targets.get(sheet.get(f"{RELATIONSHIP}id"), "")
            target = target if target.startswith("xl/") else f"xl/{target}"
            if target not in names:
                continue
            rows = []
            for row in ET.fromstring(archive.read(target)).iter(f"{SHEET}row"):
                cells = []
                for cell in row.findall(f"{SHEET}c"):
                    value = cell.find(f"{SHEET}v")
                    inline = cell.find(f"{SHEET}is")
                    if cell.get("t") == "s" and value is not None and value.text:
                        position = int(value.text)
                        text = shared[position] if position < len(shared) else ""
                    elif inline is not None:
                        text = "".join(node.text or "" for node in inline.iter(f"{SHEET}t"))
                    else:
                        text = value.text if value is not None and value.text else ""
                    if text.strip():
                        cells.append(f"{cell.get('r')}={text.strip()}")
                if cells:
                    rows.append("; ".join(cells))
            if rows:
                units.append(
                    {
                        "locator": f"sheet {sheet.get('name')} ({state})",
                        "text": "\n".join(rows[:MAX_ROWS_PER_SHEET]),
                    }
                )
        return units, {"embedded_media": embedded_media(archive), "sheets": sheets}


def pdf_units(path: Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Read the text layer. Pages without one are reported for OCR, not guessed at."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise LookupError("needs_pdf_reader") from exc
    reader = PdfReader(str(path))
    units, ocr_pages = [], []
    for number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if len(text) < MIN_PAGE_CHARACTERS:
            ocr_pages.append(number)
        if text:
            units.append({"locator": f"page {number}", "text": text})
    return units, {"pages": len(reader.pages), "ocr_pages": ocr_pages}


def find_office_converter() -> str | None:
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        candidate = Path(root or "") / "LibreOffice" / "program" / "soffice.exe"
        if root and candidate.is_file():
            return str(candidate)
    return None


def convert_legacy(path: Path, target_format: str, work: Path, timeout: int) -> Path:
    converter = find_office_converter()
    if not converter:
        raise LookupError("unsupported")
    profile = (work / "office-profile").resolve().as_uri()
    outdir = Path(tempfile.mkdtemp(dir=work))
    subprocess.run(
        [
            converter,
            f"-env:UserInstallation={profile}",
            "--headless",
            "--convert-to",
            target_format,
            "--outdir",
            str(outdir),
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=timeout,
    )
    produced = list(outdir.glob(f"*.{target_format}"))
    if not produced:
        raise LookupError("failed")
    return produced[0]


def read_item(path: Path, extension: str, work: Path, timeout: int) -> dict[str, Any]:
    temporary = None
    try:
        if extension in LEGACY_OFFICE:
            temporary = convert_legacy(path, LEGACY_OFFICE[extension], work, timeout)
            path, extension = temporary, f".{LEGACY_OFFICE[extension]}"
        if extension == ".docx":
            units, facts = docx_units(path)
        elif extension == ".pptx":
            units, facts = pptx_units(path)
        elif extension == ".xlsx":
            units, facts = xlsx_units(path)
        elif extension == ".pdf":
            units, facts = pdf_units(path)
        elif extension in TEXT_EXTENSIONS:
            units = [{"locator": "file", "text": path.read_text(encoding="utf-8", errors="replace")}]
            facts = {}
        else:
            return {"status": "unsupported", "characters": 0}
    finally:
        if temporary:
            shutil.rmtree(temporary.parent, ignore_errors=True)

    characters = sum(len(unit["text"]) for unit in units)
    facts["product_signal"] = any(PRODUCT_WORDS.search(unit["text"]) for unit in units)
    facts["case_signal"] = any(CASE_WORDS.search(unit["text"]) for unit in units)
    status = "read_ok"
    if facts.get("ocr_pages"):
        status = "needs_ocr" if characters < MIN_PAGE_CHARACTERS else "partial"
    return {"status": status, "characters": characters, **facts, "units": units}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract working text and record per-file read status for triage."
    )
    parser.add_argument("inventory", help="inventory.json")
    parser.add_argument("--work", required=True, help="Working directory outside the package")
    parser.add_argument("--timeout", type=int, default=300, help="Seconds per legacy conversion")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    work = Path(args.work).resolve()
    text_directory = work / "text"
    text_directory.mkdir(parents=True, exist_ok=True)
    statuses: dict[str, Any] = {}

    for item in load_json_object(Path(args.inventory)).get("items", []):
        if item.get("asset_kind", "document") != "document":
            continue
        item_id = item["item_id"]
        try:
            result = read_item(
                Path(long_path(item["source_ref"])), item.get("extension") or "", work, args.timeout
            )
        except LookupError as exc:
            result = {"status": str(exc.args[0]), "characters": 0}
        except subprocess.TimeoutExpired:
            result = {"status": "failed", "error": "conversion_timeout", "characters": 0}
        except Exception as exc:  # A damaged file must become D, never stop the run.
            result = {"status": "failed", "error": type(exc).__name__, "characters": 0}
        units = result.pop("units", [])
        if units:
            write_json_file(text_directory / f"{item_id}.json", {"item_id": item_id, "units": units})
        statuses[item_id] = {"display_name": item.get("display_name"), **result}

    write_json_file(work / "extract-status.json", {"items": statuses})
    counts: dict[str, int] = {}
    for status in statuses.values():
        counts[status["status"]] = counts.get(status["status"], 0) + 1
    print(json.dumps({"documents": len(statuses), "status": counts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
