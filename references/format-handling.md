# Format Handling

Use structured parsers and format-aware editing. Extract text for judgment, but do not flatten sources in ways that lose page, slide, heading, cell, record, or message locations.

## Images

- Images are materials. The build script copies every image into the package.
- An image nobody has looked at is D with `content_read: false`.
- Look at images when you can. A product or catalog image is A or D by what it shows; a signature, logo, or screenshot of a chat is E noise.
- A knowledge point read from an image states its `scope` like any other. Do not infer specifications or capabilities from how a product looks.

## Organised media folders

Website kits, brand folders, and product folders are usually sorted by the company: `X100/产品视频/`, `官网/首页Banner/`. Their folder and file names already say what the media shows.

- Judge such a folder with a folder rule after looking at a few samples. Images and video in it can be A without each being opened. See the folder rules in the output contract.
- Look at enough samples to cover the folder: at least two, and one from each sub-folder the rule covers. For video, check that the file names and a frame or the poster image, when one can be seen, match the folder.
- Video and audio kept this way are A, and `00_总清单.md` still lists them under 待转写/待看 as 已保留，内容待转写. What they say is not yet knowledge: no knowledge point comes from them until a transcript or subtitles are read.
- When the samples show customers' sites, logos, or faces, keep the folder A and send it to the client as one question with `pending_client_review: true` on the rule.
- This is only for folders the company sorted. Media from email attachments, chat exports, phone dumps, or a loose folder of unnamed files stays D until someone looks at or listens to it.

## Video and audio

- Outside an organised folder, record them as D. They are not transcribed during triage; state in `required_follow_up` that transcription is pending. `00_总清单.md` lists them under 待转写/待看.
- A video or audio attached to an email is A only when its transcript or subtitles were read; set `transcript_read: true`.
- Read a `.srt` or `.vtt` file beside a video as text. It can settle the video's content without transcription.

## Archives

- Do not unpack archives during triage. Record them as D and list their member names when the format allows.

## DOC and DOCX

- Preserve paragraph, heading, table, header, footer, comment, and note boundaries when readable.
- For B, delete only explicit paragraphs, heading sections, table rows, or other structurally reliable units from a work copy.
- Check headers, footers, comments, tracked changes, document properties, embedded objects, and relationship targets for prohibited data when the chosen tool exposes them.
- Do not mark a DOCX as clean when hidden revisions or metadata have not been checked.
- Treat legacy DOC as read/convert only when a reliable local converter is available. Convert to a temporary working representation; never replace the source.

## PDF

- Try the embedded text layer first and preserve page locators. `extract_text.py` uses `pypdf` when installed and lists pages without text in `ocr_pages`.
- Use OCR when the embedded text is absent, garbled, or materially incomplete. Prefer OCR only on affected pages rather than the full PDF. Catalogs and company profiles are often image-only, so run OCR before leaving them in D; if no OCR engine is available, say so in `required_follow_up`.
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
- Quotation sheets are product material with prices attached. Follow the B rules in the classification policy and keep their embedded images.
- `extract_text.py` reports `embedded_media`. Note the count in the summary, because the images are often the only product photos.
- `extract_text.py` converts legacy XLS through LibreOffice. When it reports `unsupported` or `failed`, classify the item D; do not exclude it on its filename.

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
