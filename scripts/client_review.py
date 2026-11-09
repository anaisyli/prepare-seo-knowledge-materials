#!/usr/bin/env python3
"""Write and read the client's review workbook, using only the standard library."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from package_common import link_path


WORKBOOK_NAME = "客户确认表.xlsx"
CHOICES = ("保留", "不用", "需要修改")
REVIEW_HEADERS = ("序号", "内容摘要", "来自哪个文件", "在文件里的位置", "需要您确认什么", "您的选择", "备注", "编号")
HELD_HEADERS = ("文件（在您资料里的位置）", "说明")
HEADER_ROW = 3
CHOICE_COLUMN = "F"
ID_COLUMN = "H"
REVIEW_WIDTHS = (6, 48, 44, 18, 40, 12, 28, 10)
SOURCE_COLUMN = 2
HELD_WIDTHS = (56, 40)
MAX_ROWS = 5000
SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
HYPERLINK_TYPE = f"{REL_NS}/hyperlink"

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    "</Types>"
)
ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    "</Relationships>"
)
WORKBOOK = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<workbook xmlns="{SHEET_NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<sheets><sheet name="需要您确认的内容" sheetId="1" r:id="rId1"/>'
    '<sheet name="没有带走的文件" sheetId="2" r:id="rId2"/></sheets></workbook>'
)
WORKBOOK_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
    '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    "</Relationships>"
)
# Style 1: wrapped body. Style 2: header. Style 3: instruction line. Style 4: link.
STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<styleSheet xmlns="{SHEET_NS}">'
    '<fonts count="3"><font><sz val="11"/><name val="微软雅黑"/></font>'
    '<font><b/><sz val="11"/><name val="微软雅黑"/></font>'
    '<font><u/><sz val="11"/><color rgb="FF0563C1"/><name val="微软雅黑"/></font></fonts>'
    '<fills count="3"><fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFE8EEF4"/></patternFill></fill></fills>'
    '<borders count="2"><border/><border><left style="thin"><color rgb="FFC8D0D8"/></left>'
    '<right style="thin"><color rgb="FFC8D0D8"/></right><top style="thin"><color rgb="FFC8D0D8"/></top>'
    '<bottom style="thin"><color rgb="FFC8D0D8"/></bottom></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="5"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1" applyBorder="1">'
    '<alignment vertical="top" wrapText="1"/></xf>'
    '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
    '<alignment vertical="center" wrapText="1"/></xf>'
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1">'
    '<alignment vertical="top" wrapText="1"/></xf>'
    '<xf numFmtId="0" fontId="2" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1">'
    '<alignment vertical="top" wrapText="1"/></xf></cellXfs>'
    "</styleSheet>"
)


def clean(value: Any) -> str:
    """Drop control characters that make an .xlsx refuse to open."""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value if value is not None else ""))


def column_name(index: int) -> str:
    return chr(ord("A") + index)


def cell(column: int, row: int, value: Any, style: int) -> str:
    reference = f"{column_name(column)}{row}"
    text = clean(value)
    if not text:
        return f'<c r="{reference}" s="{style}"/>'
    return (
        f'<c r="{reference}" s="{style}" t="inlineStr"><is><t xml:space="preserve">'
        f"{escape(text)}</t></is></c>"
    )


def sheet_row(
    number: int,
    values: tuple[Any, ...],
    style: int,
    height: int | None = None,
    styles: dict[int, int] | None = None,
) -> str:
    height_attribute = f' ht="{height}" customHeight="1"' if height else ""
    cells = "".join(
        cell(index, number, value, (styles or {}).get(index, style)) for index, value in enumerate(values)
    )
    return f'<row r="{number}"{height_attribute}>{cells}</row>'


def columns_xml(widths: tuple[int, ...], hidden: set[int]) -> str:
    entries = "".join(
        f'<col min="{index + 1}" max="{index + 1}" width="{width}" customWidth="1"'
        f'{" hidden=" + chr(34) + "1" + chr(34) if index in hidden else ""}/>'
        for index, width in enumerate(widths)
    )
    return f"<cols>{entries}</cols>"


def worksheet(body: str, widths: tuple[int, ...], freeze_row: int, tail: str, hidden: set[int] | None = None) -> str:
    pane = (
        f'<sheetViews><sheetView workbookViewId="0"><pane ySplit="{freeze_row}" '
        f'topLeftCell="A{freeze_row + 1}" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{SHEET_NS}" xmlns:r="{REL_NS}">{pane}{columns_xml(widths, hidden or set())}'
        f"<sheetData>{body}</sheetData>{tail}</worksheet>"
    )


def review_sheet(rows: list[dict[str, Any]], company: str) -> tuple[str, str]:
    """Return the sheet and its relationships, which hold the file links."""
    title = f"{company}资料确认表".strip()
    instruction = (
        "请在“您的选择”一列下拉选择：保留 / 不用 / 需要修改。需要修改或有疑问时，写在“备注”里。"
        "\n“来自哪个文件”是文件在您资料里的位置；这张表和资料包放在一起时，点蓝色的路径可以直接打开文件。"
    )
    parts = [
        sheet_row(1, (title,), 3, 24),
        sheet_row(2, (instruction,), 3, 54),
        sheet_row(HEADER_ROW, REVIEW_HEADERS, 2, 28),
    ]
    links: list[tuple[str, str]] = []
    for number, row in enumerate(rows, start=1):
        line = HEADER_ROW + number
        if row.get("link"):
            links.append((f"{column_name(SOURCE_COLUMN)}{line}", str(row["link"])))
        values = (
            number,
            row.get("summary"),
            row.get("source"),
            row.get("location"),
            row.get("question"),
            row.get("choice", ""),
            row.get("note", ""),
            row.get("id"),
        )
        parts.append(sheet_row(line, values, 1, styles={SOURCE_COLUMN: 4} if row.get("link") else None))
    last = HEADER_ROW + max(len(rows), 1)
    merges = '<mergeCells count="2"><mergeCell ref="A1:G1"/><mergeCell ref="A2:G2"/></mergeCells>'
    options = ",".join(CHOICES)
    validation = (
        '<dataValidations count="1"><dataValidation type="list" allowBlank="1" showErrorMessage="1" '
        f'errorTitle="请从下拉框选择" error="请选择：{options}" '
        f'sqref="{CHOICE_COLUMN}{HEADER_ROW + 1}:{CHOICE_COLUMN}{last}">'
        f'<formula1>"{options}"</formula1></dataValidation></dataValidations>'
    )
    hyperlinks = "".join(
        f'<hyperlink ref="{reference}" r:id="rIdLink{index}"/>' for index, (reference, _) in enumerate(links, 1)
    )
    tail = merges + validation + (f"<hyperlinks>{hyperlinks}</hyperlinks>" if links else "")
    relationships = "".join(
        f'<Relationship Id="rIdLink{index}" Type="{HYPERLINK_TYPE}" '
        f'Target="{escape(link_path(target))}" TargetMode="External"/>'
        for index, (_, target) in enumerate(links, 1)
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{relationships}</Relationships>"
    )
    return worksheet("".join(parts), REVIEW_WIDTHS, HEADER_ROW, tail, {7}), rels


def held_sheet(rows: list[dict[str, Any]]) -> str:
    parts = [
        sheet_row(1, ("这些文件只记录了位置和文件名，没有复制或带走。",), 3, 24),
        sheet_row(2, HELD_HEADERS, 2, 28),
    ]
    for number, row in enumerate(rows, start=3):
        parts.append(sheet_row(number, (row.get("name"), row.get("note")), 1))
    return worksheet("".join(parts), HELD_WIDTHS, 2, '<mergeCells count="1"><mergeCell ref="A1:B1"/></mergeCells>')


def write_workbook(
    path: Path,
    review_rows: list[dict[str, Any]],
    held_rows: list[dict[str, Any]],
    company: str = "",
) -> None:
    if len(review_rows) > MAX_ROWS:
        raise ValueError(f"Too many review rows: {len(review_rows)}")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", ROOT_RELS)
        archive.writestr("xl/workbook.xml", WORKBOOK)
        archive.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        archive.writestr("xl/styles.xml", STYLES)
        sheet, links = review_sheet(review_rows, company)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
        archive.writestr("xl/worksheets/_rels/sheet1.xml.rels", links)
        archive.writestr("xl/worksheets/sheet2.xml", held_sheet(held_rows))


def read_review_rows(path: Path) -> list[dict[str, str]]:
    """Return one row per reviewed entry, with the client's choice and note."""
    namespace = f"{{{SHEET_NS}}}"
    shared: list[str] = []
    with zipfile.ZipFile(path) as archive:
        # Excel rewrites inline text into shared strings when the client saves.
        if "xl/sharedStrings.xml" in archive.namelist():
            for entry in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall(f"{namespace}si"):
                shared.append("".join(node.text or "" for node in entry.iter(f"{namespace}t")))
        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))

    rows = []
    for row in root.iter(f"{namespace}row"):
        if int(row.get("r", "0")) <= HEADER_ROW:
            continue
        values: dict[str, str] = {}
        for item in row.findall(f"{namespace}c"):
            column = re.sub(r"\d", "", item.get("r", ""))
            inline = item.find(f"{namespace}is")
            value = item.find(f"{namespace}v")
            if inline is not None:
                text = "".join(node.text or "" for node in inline.iter(f"{namespace}t"))
            elif item.get("t") == "s" and value is not None and value.text:
                text = shared[int(value.text)]
            else:
                text = value.text if value is not None and value.text else ""
            values[column] = text
        if values.get(ID_COLUMN):
            rows.append(
                {
                    "id": values[ID_COLUMN],
                    "summary": values.get("B", ""),
                    "source": values.get("C", ""),
                    "location": values.get("D", ""),
                    "question": values.get("E", ""),
                    "choice": values.get(CHOICE_COLUMN, ""),
                    "note": values.get("G", ""),
                }
            )
    return rows
