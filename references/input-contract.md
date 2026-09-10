# Input Contract

## Principle

The core workflow must not depend on a particular folder layout, connector, email product, or API response. An adapter may read an already-authorized source, but it must normalize the result into material items before classification.

Retrieval is upstream. This skill must not request credentials, expand the authorized date range, crawl linked systems, download an entire mailbox, or decide whether the user has permission to process the data.

## Run-level scope gate

Before reading source content or classifying any item, the run must include a scope confirmation:

```yaml
scope_confirmation:
  confirmed: true
  confirmed_at: "2026-09-10"
  declared_scope: "The supplied enterprise knowledge materials for this run"
  confirmation_source: "current_request"
```

An explicit instruction to process a specific path, file set, record range, or connector query for this knowledge-base triage is sufficient to set `confirmed: true`. The caller does not need to use the word "confirm" or identify a confirmer. If no such scoped instruction exists, stop before content extraction and classification and ask the caller to state what this run may process. Do not infer confirmation from file delivery, folder access, silence, or an unscoped general request. The gate records process scope only; it does not decide whether authorization is legally valid.

`confirmation_source` records where the explicit scope statement came from, not who is legally authorized. Use a value such as `current_request` or an opaque upstream confirmation-record ID. Do not invent a person's identity or role. `confirmed_at` is recorded by the run when the confirmation is received; the caller does not need to type YAML or a date.

## Canonical material item

Represent each logical item with these fields. Omit optional fields rather than invent values.

```yaml
schema_version: "1.0"
item_id: "stable-within-this-run"
source_kind: "local_file | inline_text | structured_export | connector"
source_ref: "local path or opaque upstream reference"
media_type: "application/pdf"
title: "optional display title"
content: "optional readable text or structured value"
metadata: {}
parent_id: "optional parent material item"
locator_scheme: "page | slide | heading | paragraph | sheet_cell | row | json_path | record"
source_hash: "sha256 for local files or stable upstream version when available"
```

`source_ref` is for audit traceability. Do not repeat it in public or importable outputs when it contains personal, customer, competitor, or transaction information.

## Adapter behavior

### Local files

- Accept one or more explicit files or directories.
- Inventory unsupported files as unreadable/unsupported rather than silently skipping them.
- Exclude `.git`, review/output directories, temporary files, and symbolic-link traversal.
- Hash source bytes before content analysis.
- Preserve the absolute source path only in restricted review artifacts, not in importable manifests.

### Inline text

- Treat each explicitly supplied block as one material item unless the user provides reliable boundaries.
- Use a generated item ID and preserve the conversation or request reference as an opaque source locator when available.
- Do not infer sender, recipient, date, or document type from prose unless the text explicitly establishes it.

### Connector or API results

- Keep authentication, pagination, filtering, and retrieval in a source-specific adapter outside the core classification logic.
- Prefer an in-memory mapping to the canonical item. Do not persist a second raw copy unless required and approved.
- Carry an opaque record ID and stable version/etag/hash when the interface provides one.
- Before a later execution phase, have the adapter confirm that the stable version or content hash still matches. If the interface supplies neither, keep the captured item immutable and complete approval/execution in the same session or re-audit it.
- Process only the explicitly returned scope. Do not follow links or fetch attachments automatically.
- If the API schema is unknown, inspect field names and types, propose mappings for content, metadata, identifiers, and child records, then stop for confirmation when the mapping is ambiguous.
- Treat connector metadata such as sender, recipient, subject, account name, folder, timestamp, and thread participants as potentially sensitive.

## Exported Markdown

Parse Markdown structurally rather than treating it as an undifferentiated string.

- Parse YAML frontmatter as metadata, not body content.
- Use heading paths as locators, for example `Product > Installation > Limits`.
- Preserve table row/column coordinates and block types such as quote or code.
- Treat links and attachment paths as references only. Do not open them automatically.
- Split email or chat exports into child items only when record boundaries are explicit and deterministic.
- When a separator could be ordinary body text, keep the export as one item and use headings/line ranges as locators.
- Never assume an exported Markdown file is already sanitized.

## Other structured exports

Use a real parser for JSON, JSONL, YAML, CSV, TSV, or XML. Do not use regular expressions to parse these formats.

- A top-level array, JSONL row, CSV row, or explicit record collection may become child material items.
- Preserve exact structural locators such as `records[12].body`, `row 18`, or `orders[3].notes`.
- Do not flatten away field names; they provide necessary context for risk decisions.
- Do not treat unrecognized fields as safe or discard them silently.
- If fields contain nested attachments, URLs, binary data, or image payloads, record their presence but do not fetch or inspect them.
- If record boundaries or field meanings are ambiguous, produce a mapping proposal with representative field names and data types. Do not reproduce sensitive sample values in that proposal.

## Working data

- Prefer streaming or temporary extraction over durable full-text caches.
- Keep working extraction outside the formal output folders.
- Final reports must contain risk types and locations, not the sensitive original values.
- Do not copy D/E raw material into the final output by default.
