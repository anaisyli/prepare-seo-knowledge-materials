# Format Handling

Use structured parsers and format-aware editing. Extract text for judgment, but do not flatten sources in ways that lose page, slide, heading, cell, record, or message locations.

## Images

- Treat standalone image files and image-only attachments as `image_no_process`.
- Inventory them for counting and exclusion reporting, but do not OCR, describe, classify, copy, or extract knowledge from them.
- Keep only a sanitized record in `review-only/03_排除/`; never place image files in `knowledge-assets/formal-knowledge/`.

## DOC and DOCX

- Preserve paragraph, heading, table, header, footer, comment, and note boundaries when readable.
- For B, delete only explicit paragraphs, heading sections, table rows, or other structurally reliable units from a work copy.
- Check headers, footers, comments, tracked changes, document properties, embedded objects, and relationship targets for prohibited data when the chosen tool exposes them.
- Do not mark a DOCX as clean when hidden revisions or metadata have not been checked.
- Treat legacy DOC as read/convert only when a reliable local converter is available. Convert to a temporary working representation; never replace the source.

## PDF

- Try the embedded text layer first and preserve page locators.
- Use OCR when the embedded text is absent, garbled, or materially incomplete. Prefer OCR only on affected pages rather than the full PDF.
- OCR recognizes text for classification; it does not authorize describing photographs, interpreting diagrams, or inferring facts from visual appearance.
- Keep OCR output as temporary working data. Do not place a full OCR transcript in formal knowledge, review lists, filenames, or logs.
- Record `text_extraction: ocr` or `mixed`, the OCR page numbers, language setting, engine/version when available, and whether recognition and reading order were verified. If confidence values are available, retain them in restricted processing metadata.
- OCR-derived text can support A-E classification only when all relevant pages have adequate coverage and the recognized text and reading order are reliable. If important text, tables, labels, or page boundaries remain uncertain, use R4/D.
- V0.1 may remove complete pages from a work copy.
- Do not attempt precise in-page text deletion, raster redaction, or layout reconstruction unless a tool can verify that the underlying content is actually removed.
- Visual covering is not deletion. If text remains extractable under a rectangle, the result fails.
- After B page removal, verify both the remaining text layer and any OCR-readable page content. OCR used for triage does not itself modify or sanitize the PDF.

## PPT and PPTX

- Preserve slide, notes, table, chart-label, comment, and metadata locations when readable.
- V0.1 may delete complete slides from a work copy.
- A slide containing mixed safe and prohibited content is not eligible for partial cleanup unless the prohibited objects and related notes can be removed and verified reliably.
- Treat legacy PPT as read/convert only when a reliable converter is available.

## XLS and XLSX

- Inspect visible and hidden worksheets, cells, formulas, comments/notes, defined names, external links, hidden rows/columns, and workbook metadata when supported.
- Use sheet and cell/range locators such as `Pricing!B4:F19`.
- For B, modify only exact sheets, rows, columns, or ranges when the change can be verified without corrupting formulas or workbook behavior.
- Do not assume hidden content is irrelevant or safe.
- Treat legacy XLS as read/convert only when a reliable converter is available.

## TXT and Markdown

- Preserve line ranges and, for Markdown, heading paths and block types.
- Parse frontmatter separately from body text.
- Remove a complete paragraph, list item, table row, fenced block, quote block, or heading section rather than token-masking mixed prose.
- For exported communications, do not infer record boundaries from an ambiguous visual separator.

## JSON, JSONL, YAML, CSV, TSV, and XML

- Use an appropriate parser and preserve field paths or row/column coordinates.
- Keep field names during classification because keys such as `price`, `recipient`, or `internal_notes` change risk interpretation.
- When a field is removed from a record, verify that sibling fields do not reconstruct the prohibited event.
- Unknown schemas require a field-mapping proposal when content and metadata roles cannot be determined reliably.

## Direct text and connector content

- Do not persist the raw response unless the user explicitly requests it and provides a protected location.
- Preserve stable record IDs or version tokens as source locators when available.
- Do not follow URLs, open attachments, expand date ranges, or request additional connector records during this skill's core workflow.

## Output verification

For every B artifact:

1. Reopen the produced file with a format-aware reader.
2. Confirm each approved removal is absent from visible and extractable content.
3. Search metadata, notes, comments, hidden structures, and relationships when supported.
4. Confirm retained content and basic file integrity remain usable.
5. If verification is incomplete, do not mark the artifact importable; record it as D with the failed check.
