# Output Contract

## Package layout

`scripts/build_package.py` creates this layout. Do not create or edit it by hand.

```text
<package>/
|-- 00_总清单.md
|-- 原目录对照.md
|-- 客户确认表.xlsx
|-- A-原文保留/
|   |-- A-清单.md
|   `-- <标签>/<原来的子文件夹>/
|-- B-待清理/
|   `-- B-清单.md
|-- C-知识点/
|   |-- C-清单.md
|   |-- knowledge-points.jsonl
|   |-- 来源文件清单.md
|   `-- 来源文件/
|-- D-待定/
|   `-- D-清单.md
|-- E-排除/
|   |-- E-清单.md
|   |-- E-完整清单.csv
|   `-- <标签>/<原来的子文件夹>/
`-- 审计记录/
    |-- package-manifest.json
    |-- inventory.json
    |-- triage-results.json
    `-- 校验结果.json
```

- `<标签>` is the fixed Chinese label of the `resource_type`. Competitor material sits in `A-原文保留/竞对资料/`.
- Every file keeps the sub-folders it had in the source, below its decision folder: `产品/X100/渲染图/1.png` decided A as product lands at `A-原文保留/产品资料/产品/X100/渲染图/1.png`. With several input folders, each input folder's name is the first sub-folder. B, C, and D work the same way.
- `原目录对照.md` lists the original folders and where each file went. Ten or more media files in one folder with the same decision collapse to one line with a link to their new folder.
- Links in the lists are relative paths with spaces, brackets, `#`, and `%` percent-escaped and no angle brackets, so Obsidian, VS Code, Typora, and other Markdown viewers all open them. Chinese names stay as they are.
- Images, video, and files of any size go in the folder of their A-E decision. `00_总清单.md` lists files above 50MB, because they affect transfer, and under 待转写/待看 the video, audio, and images in D, plus A video and audio not yet transcribed.
- `客户确认表.xlsx` is the only file for the client. One sheet holds everything awaiting a decision, with a dropdown of 保留 / 不用 / 需要修改. The other lists what was recorded but not taken. Its hidden 编号 column links each row back to its item. 来自哪个文件 shows the file's path in the client's own materials (`source_relpath`) and links to its copy in the package, or to the package folder for a folder row; the links are relative, so they open while the workbook stays in the package.
- The package is internal and restricted; never forward it whole. Only assets marked `importable: true` go to the next step, and `审计记录/` holds absolute source paths.

## Inputs to the build

### Inventory

`inventory.json` records every supplied item, including unsupported files. For local files include SHA-256, byte size, media type, `asset_kind`, source reference, `source_relpath` (the path below the input folder, with `/`), and `parent_id` for linked attachments. For connectors use an opaque source reference and stable version/etag/hash when available.

### Triage result

Write `triage-results.json`. One object per inventory item; no item may be left out, except media covered by a folder rule and system files, which the build fills in itself.

```json
{
  "plan_version": "1.0",
  "run_id": "20260909T120000Z-ab12cd34",
  "created_at": "2026-09-09T12:00:00Z",
  "triage_status": "completed",
  "approval_status": "pending",
  "scope_confirmation": {
    "confirmed": true,
    "confirmed_at": "2026-09-09T11:55:00Z",
    "declared_scope": "D:/input",
    "confirmation_source": "current_request"
  },
  "items": [
    {
      "item_id": "local-ab12cd34-1",
      "source_kind": "local_file",
      "source_ref": "D:/input/quotation.xlsx",
      "source_hash": "sha256-hex",
      "decision": "B",
      "resource_type": "product",
      "business_tags": ["website", "seo_geo"],
      "content_read": true,
      "content_codes": ["R0", "R2"],
      "reason_codes": ["price_columns", "customer_block"],
      "summary": "Product and fabric table with prices and a customer block.",
      "actions": [
        {
          "action_id": "action-0001",
          "type": "copy_then_remove",
          "locators": ["Sheet1!A1:F8", "Sheet1!E:E"],
          "reason_codes": ["price_columns"],
          "execution_supported": true
        }
      ]
    }
  ]
}
```

Required on every item: `item_id`, `decision`, `resource_type`, `content_read`, `summary`.

- `content_read: true` means the content was actually opened. A, B, C, and E items need it; `verify_package.py` rejects them otherwise, and also rejects them when `extract_text.py` could not read the file.
- E items need a specific `reason_codes` value. A bare `E` is rejected.
- Excluded emails need `mail_review`: `full` if read in full, or `candidates` if every statement sentence from `mail_candidates.py` was read.
- D items state the failure in `summary` and the need in `required_follow_up`.
- Set `restricted: true` on items holding finance, contract, or account data that are not typed `finance`.
- `approval_status: pending` refers only to optional B cleanup.
- Items awaiting the client add `pending_client_review: true` and `client_review_items`. When only part of the file waits, also add `pending_scope: "part"`; every entry then needs a `location`:

```json
{
  "pending_client_review": true,
  "pending_scope": "part",
  "client_review_items": [
    {"summary": "某北美客户的合作案例", "location": "第 4 章 4.1", "question": "这个案例可以写进官网吗？"}
  ]
}
```
- For PDFs add `text_extraction` (`native`, `ocr`, or `mixed`), `ocr_pages`, and `ocr_verification`. Do not persist the OCR transcript.
- Set `transcript_read: true` on a video or audio item when its transcript or subtitles were actually read. A video or audio attached to an email cannot be A without it.

#### Folder rules

A folder of images, video, or audio that the company organised can be decided as a group. Add `folder_rules` beside `items`:

```json
{
  "folder_rules": [
    {
      "folder": "建站资料/X100/产品视频",
      "decision": "A",
      "resource_type": "product",
      "summary": "X100 的产品介绍视频",
      "checked_samples": ["建站资料/X100/产品视频/01-外观.mp4", "建站资料/X100/产品视频/03-安装.mp4"]
    }
  ]
}
```

- `folder` is a `source_relpath` folder. The rule covers every image, video, and audio file below it that has no decision of its own; the deepest matching rule wins. Documents in the folder always need their own decision.
- A and E rules need `checked_samples`: files inside that folder that were actually looked at. E rules also need `reason_codes`. A D rule needs neither.
- A rule may set `decision`, `resource_type`, `summary`, `reason_codes`, `business_tags`, and `required_follow_up`.
- When the client must decide about the whole folder, such as photos taken at customer sites that show their logos, add `pending_client_review: true` to an A rule, and optionally a plain `client_question`. `客户确认表.xlsx` then gets one row for the folder, with the rule's `summary` and the number of files, instead of one row per picture. Its 编号 is `folder:<folder>`, and the client's answer applies to every file the rule covers. Until then none of them is usable as a fact.
- System files (`Thumbs.db`, `ehthumbs.db`, `.DS_Store`, `desktop.ini`, and names starting with `~$` or `._`) without a decision become E with `reason_codes: ["system_file"]`.

### Knowledge points

Write one JSON object per line for `--knowledge-points`. Do not include an original excerpt.

```json
{
  "knowledge_id": "knowledge-0001",
  "knowledge_point": "The company reviews custom dimensional requirements before confirming feasibility.",
  "source_id": "local-ab12cd34-1",
  "locator": "Customization Process > Review, paragraph 2",
  "derivation": "abstracted_from_company_r1",
  "scope": "style",
  "removed_detail_types": ["internal_process_detail"]
}
```

`scope` is required: `general`, `style`, or `single_communication`. A point is `approved` and usable as a fact without a second review. Set `pending_client_review: true` on points from customer cases or with unclear publication suitability; they become `pending_client_review` and are not usable as facts until the client confirms them. Add `client_location` and `client_question` so the workbook row reads plainly.

## Manifest

`审计记录/package-manifest.json` is the single record of the package. Each asset has:

| Field | Meaning |
|---|---|
| `item_id`, `display_name`, `asset_kind` | Identity |
| `decision`, `resource_type`, `pending_client_review`, `business_tags` | Triage result |
| `pending_units` | Locations held back when only part of the file awaits the client |
| `path` | Location inside the package, or null |
| `copy_status` | `copied`, `duplicate`, `redundant_archive`, `not_copied_restricted`, `withheld_by_client`, `not_persisted`, `copy_failed`, `missing_decision` |
| `archive_member_hashes` | For a `redundant_archive` ZIP: the hashes of its files, each kept elsewhere in the package |
| `duplicate_of` | The item holding the same bytes in the same folder |
| `source_hash`, `output_hash`, `verification_status` | Copy proof |
| `parent_id` | The email an attachment belongs to |
| `source_relpath` | Path below the input folder; the package keeps these sub-folders |
| `transcript_read` | Video or audio whose transcript or subtitles were read |
| `review_group`, `review_question` | The folder whose single client question covers this file, and that question |
| `folder_rule` | The folder rule that decided this file, when one did |
| `large_file` | Above 50MB; listed in `00_总清单.md` |
| `importable` | True only for A items not restricted or withheld |
| `usable_as_fact` | True for A items, except competitor, SEO-operations, restricted, and wholly pending items. With `pending_units`, those locations stay held back |

`importable` means eligible for the next knowledge-base step, not that this skill writes to the production system. B items stay `importable: false` until cleaned and verified. D items stay false until the uncertainty is resolved and the item is re-classified.

## Verification

`scripts/verify_package.py <package> --extract-status <file>` must report `"verified": true` before the run is called complete. It fails when:

- an inventory item has no decision, or a decision has no inventory item;
- a listed file is missing, or differs from its source hash;
- a file is in the package but not in the manifest;
- a list contains `file:///` or a local absolute path;
- an item is wrongly marked usable as a company fact, or importable without being A;
- an A, B, C, or E item was not read, or an E item has no real reason;
- an email was excluded without `mail_review`;
- a quotation with product content was excluded as pricing or hidden as finance, a finance-named file was kept as A or B, or a non-finance item is restricted;
- a B item has no exact location;
- a folder rule has no checked samples inside its folder, or a video or audio from an email is A without `transcript_read`;
- customer cases were not sent for client review, or a partial question holds back the whole file;
- a knowledge point from one email is marked `general`, contains a price, or does not cite a company message;
- a knowledge point has no valid source, locator, or scope, or comes from competitor material;
- anything awaiting the client is missing from `客户确认表.xlsx`, or a row has no summary or question;
- attachments are missing, or emails have no mail manifest, and the gap was not accepted with `--accept-attachment-gaps`.

## Optional B cleanup approval

If the user later asks to clean B files, create a separate approval record for the deletion actions so the triage result remains immutable:

```json
{
  "approval_version": "1.0",
  "run_id": "20260909T120000Z-ab12cd34",
  "decision": "approved",
  "approved_at": "2026-09-09T12:30:00Z",
  "plan_sha256": "hash-of-exact-triage-results-file",
  "approved_action_ids": ["action-0001"],
  "denied_action_ids": [],
  "notes": "User approved the listed action."
}
```

Never infer approval from file presence, silence, or an earlier general request. The approval record may be written only after an explicit approval message identifying all deletion actions or a clear subset. Check it with `scripts/verify_approved_plan.py`.

## Optional B cleanup output

Write cleaned copies to a separate directory and verify them as described in the format-handling reference. The B copy in the package stays unchanged. After verification, a cleaned file becomes an importable asset of the later knowledge-base step.

## Report

Summarize in the final message: counts by decision and type, files placed, B files awaiting cleanup, knowledge points by scope, items awaiting the client, restricted and withheld items, attachment gaps, PDFs and pages processed with OCR, OCR failures, and remaining human decisions. Describe excluded content by reason code and location, not by quoting it.
