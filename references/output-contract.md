# Output Contract

## Triage mode

Create a knowledge-base preparation package without editing source files:

```text
SEO-Knowledge-Triage/<run-id>/
|-- knowledge-assets/
|   |-- formal-knowledge/
|   |   |-- 01_原始保留/
|   |   |-- 03_提取知识/
|   |   `-- 04_处理记录/
|   `-- package-manifest.json
|-- review-assets/
|   |-- 02_B待清理源文件/
|   `-- 03_D待定源文件/
|-- review-only/
|   |-- 01_待删除/
|   |-- 02_待定/
|   `-- 03_排除/
|-- inventory.json
|-- triage-results.jsonl
|-- B类待处理清单.md
|-- 待定文件清单.md
|-- 初筛清单.md
`-- 文件处理报告.md
```

`knowledge-assets/` is the formal knowledge package for later knowledge-base import. It contains copied A source files, formal C knowledge points, and sanitized processing records. B copies belong only in `review-assets/02_B待清理源文件/` and are explicitly pending cleanup; D copies belong only in `review-assets/03_D待定源文件/` and are explicitly pending review. Neither may be imported before the required follow-up decision and verification. The root-level `B类待处理清单.md` and `待定文件清单.md` are the human-readable entry points for B and D review; machine-readable records remain in `review-only/01_待删除/deletion-review.jsonl` and `review-only/02_待定/pending-items.jsonl`. Do not copy E source files or standalone images into the package by default. Prohibited content must never enter `knowledge-assets/`; unchanged B/D review copies may contain prohibited or uncertain content and must be treated as restricted, non-importable material. Never import the whole output package indiscriminately.

The `review-only/` lists contain decisions and locations only. Do not include persistent full-text extractions or prohibited values. The human-readable list should name risk categories and locations, not quote sensitive content.

## Inventory

`inventory.json` records every supplied item, including unsupported files. For local files include SHA-256, byte size, media type, source reference, and supported-extension status. For connectors use an opaque source reference and stable version/etag/hash when available.

## Triage result

Use this logical structure. Additional format-specific locator fields are allowed.

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
      "source_ref": "D:/input/example.docx",
      "source_hash": "sha256-hex",
      "decision": "B",
      "content_codes": ["R0", "R2"],
      "reason_codes": ["customer_identity", "transaction_detail"],
      "summary": "Useful general product material with localized prohibited content.",
      "actions": [
        {
          "action_id": "action-0001",
          "type": "copy_then_remove",
          "locators": ["Customer Projects > paragraph 2"],
          "reason_codes": ["customer_case"],
          "execution_supported": true
        }
      ]
    }
  ]
}
```

Each item must state its item-level triage decision, concise non-sensitive reasoning, proposed action, and exact or broad locators where applicable. `content_codes` records the R0-R4 codes found at the content-unit layer; `decision` records the A-E triage result for the complete item. For PDFs, add sanitized extraction metadata when OCR was used: `text_extraction` (`native`, `ocr`, or `mixed`), `ocr_pages`, and `ocr_verification`; include engine/version and language only when available. Do not persist the OCR transcript. `approval_status: pending` refers only to optional B cleanup, not to A copying or C extraction. A completed triage package may still contain B items awaiting cleanup approval. C items include the formal knowledge point and its source locator in triage output; they do not require a second approval cycle. B items include proposed deletion actions and locators, but none is executed in triage mode. D items state the failure and needed review. E items state exclusion reason codes. Competitor and customer-case content must not have extraction actions.

## Human review list

`B类待处理清单.md` is the first human-facing view for every B item. It must be written at the package root and include one entry per B source with:

- safe source label and `item_id`;
- path of the isolated copy under `review-assets/02_B待清理源文件/`;
- source hash;
- decision `B` and a short reason code;
- exact page, slide, paragraph, heading, sheet/range, row, or JSON-path locations to remove;
- the type of prohibited content at each location, without quoting its value;
- whether the proposed boundary is technically executable in a later cleanup step;
- a clear statement that the copy is not importable until cleaned and verified.

Do not put customer names, contact details, prices, quantities, competitor names, case narratives, or other prohibited values in this list.

`待定文件清单.md` is the first human-facing view for every D item. It must be written at the package root and include one entry per D source with:

- safe source label and `item_id`;
- link to the verified isolated copy under `review-assets/03_D待定源文件/`, or an explicit copy failure if unavailable;
- source hash;
- decision `D` and the precise uncertainty or processing failure;
- locator or affected page/section when known;
- the specific information needed to re-evaluate the item;
- a clear statement that the copy is not importable until the uncertainty is resolved and the result is re-verified.

Do not put sensitive source values, customer names, contact details, prices, quantities, competitor names, or case narratives in this list.

Always create `待定文件清单.md`; write “无待定文件” when there are no D items. Use safe, collision-free copy names such as `<item_id>.pdf`, preserving the extension without leaking sensitive original filenames. Copy available local D sources byte-for-byte and compare their SHA-256 with the inventory hash. If the source changed, copying failed, or verification failed, record that status without presenting a copy as verified. D copies do not authorize raw connector/inline persistence or attachment retrieval beyond the input contract.

`review-only/02_待定/pending-items.jsonl` contains one sanitized record per D item, including those without a copy. For example:

```json
{
  "item_id": "local-kl12mn34-4",
  "decision": "D",
  "asset_type": "source_file_pending_review",
  "source_hash": "sha256-hex",
  "output_path": "review-assets/03_D待定源文件/local-kl12mn34-4.pdf",
  "output_hash": "sha256-hex",
  "locators": ["page 3"],
  "reason_codes": ["unreliable_ocr"],
  "required_follow_up": "Provide a readable replacement for page 3.",
  "execution_status": "pending_review",
  "copy_status": "copied",
  "verification_status": "hash_verified",
  "review_status": "pending",
  "importable": false,
  "usable_as_fact": false
}
```

Record paths relative to the package root in pending records. If copying fails or raw persistence is not permitted, use an appropriate `copy_status` such as `copy_failed` or `not_persisted`, record a safe failure reason, and omit nonexistent output paths/hashes. If source hashing is unavailable, record that fact rather than inventing a hash. Never mark an unverified copy importable or usable as a fact.

`初筛清单.md` must include:

- run ID and source scope;
- counts by A-E decision;
- one entry per item with filename or safe source label, decision, reason, and proposed action;
- exact removal locators for B;
- formal knowledge points and source locators for C;
- failure reason for D;
- exclusion reason for E;
- a clear statement that no source file has been modified and B deletions have not occurred.

The triage stage may copy A source files, copy B and available local D source files into their separate review-assets areas, and create C knowledge points directly from eligible company-owned R1 content. It must stop before editing B files or changing the classification of D files.

## Preparation package manifest

`knowledge-assets/package-manifest.json` must list every file placed in the preparation package:

```json
{
  "package_version": "1.0",
  "run_id": "20260909T120000Z-ab12cd34",
  "assets": [
    {
      "asset_id": "asset-0001",
      "item_id": "local-ab12cd34-1",
      "asset_type": "source_file",
      "decision": "A",
      "path": "formal-knowledge/01_原始保留/example.docx",
      "source_hash": "sha256-hex",
      "importable": true,
      "usable_as_fact": true
    },
    {
      "asset_id": "asset-0002",
      "item_id": "local-ef56gh78-2",
      "asset_type": "source_file_pending_cleanup",
      "decision": "B",
      "path": "../review-assets/02_B待清理源文件/example.pdf",
      "source_hash": "sha256-hex",
      "importable": false,
      "usable_as_fact": false,
      "deletion_review_path": "../review-only/01_待删除/deletion-review.jsonl"
    },
    {
      "asset_id": "asset-0003",
      "item_id": "local-kl12mn34-4",
      "asset_type": "source_file_pending_review",
      "decision": "D",
      "path": "../review-assets/03_D待定源文件/local-kl12mn34-4.pdf",
      "source_hash": "sha256-hex",
      "output_hash": "sha256-hex",
      "verification_status": "hash_verified",
      "review_status": "pending",
      "importable": false,
      "usable_as_fact": false,
      "pending_review_path": "../review-only/02_待定/pending-items.jsonl"
    },
    {
      "asset_id": "asset-0004",
      "item_id": "local-ij90kl12-3",
      "asset_type": "knowledge_point",
      "decision": "C",
      "path": "formal-knowledge/03_提取知识/knowledge-points.jsonl",
      "importable": true,
      "usable_as_fact": true
    }
  ]
}
```

`importable` means eligible for the next knowledge-base import step, not that this skill writes to the production system. B source copies remain `importable: false` until cleaned and verified. D source copies remain `importable: false` until their uncertainty is resolved, the item is re-evaluated, and the resulting asset is verified.

## Processing records

`knowledge-assets/formal-knowledge/04_处理记录/processing-records.jsonl` contains one sanitized record per A/B/C asset or decision. It must include `item_id`, `decision`, `asset_type`, source hash, output path or knowledge-point ID, locators, execution status, and verification status. It must not quote sensitive values or prohibited source content.

Example processing record:

```json
{
  "record_id": "record-0001",
  "item_id": "local-ab12cd34-1",
  "decision": "A",
  "asset_type": "source_file",
  "source_hash": "sha256-hex",
  "output_path": "formal-knowledge/01_原始保留/example.docx",
  "locators": [],
  "execution_status": "copied",
  "verification_status": "hash_verified",
  "importable": true,
  "usable_as_fact": true
}
```

For B, use `asset_type: source_file_pending_cleanup`, `execution_status: pending_deletion_review`, and `importable: false`. For C, use `asset_type: knowledge_point`, `execution_status: extracted`, and `importable: true`. D records belong in `review-only/02_待定/pending-items.jsonl`, not in formal processing records; their copies are indexed as non-importable in the package manifest only when actually produced.

## Optional B cleanup approval

If the user later asks to clean B files, create a separate approval record for the deletion actions so the triage package remains immutable:

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

Never infer approval from file presence, silence, or an earlier general request. The approval record may be written only after an explicit approval message identifying all deletion actions or a clear subset.

## Optional B cleanup output

After approved and verified B cleanup, add to the same preparation package:

```text
knowledge-assets/formal-knowledge/02_清理后保留/<cleaned-files>
execution-manifest.json
文件处理报告.md
```

After verification, cleaned B files replace their pending-cleanup status in the manifest and become importable. The original B source remains outside the formal knowledge package unless the user explicitly requests a protected archive.

Do not copy raw E files or images by default. Available local D source copies belong only in `review-assets/03_D待定源文件/`, marked pending and non-importable. If the user explicitly requests a protected E or image archive, keep it outside `knowledge-assets/formal-knowledge/` and mark every file non-importable.

## Formal knowledge-point object

Do not include an original excerpt. The triage decision is the acceptance basis for a C knowledge point; no second review is required after the point is written and its source locator is recorded.

```json
{
  "knowledge_id": "knowledge-0001",
  "record_type": "knowledge_point",
  "knowledge_point": "The company reviews custom dimensional requirements before confirming feasibility.",
  "source_id": "local-ab12cd34-1",
  "locator": "Customization Process > Review, paragraph 2",
  "derivation": "abstracted_from_company_r1",
  "status": "approved",
  "removed_detail_types": ["internal_process_detail"],
  "importable": true,
  "usable_as_fact": true
}
```

Knowledge points from eligible company-owned R1 content appear under `knowledge-assets/formal-knowledge/03_提取知识/knowledge-points.jsonl` during triage, with a safe source ID and precise locator. They are formal, importable knowledge assets and do not require a second approval cycle. The B-cleanup approval verifier must reject C extraction actions because C extraction has already occurred during triage.

## Execution manifest and report

The manifest must list produced artifacts, source IDs, executed action IDs, source hashes, output hashes, verification status, `record_type`, `importable`, and `usable_as_fact` where applicable. It must not contain prohibited values.

The report must include counts, assets placed in the package, B files awaiting cleanup, formal knowledge points, items not included, competitor/customer-case exclusions, standalone-image/non-processable counts, PDFs and page counts processed with OCR, OCR verification failures, changed-source failures, and remaining human decisions. Describe excluded content by reason code and locator, not by quoting or summarizing it.
