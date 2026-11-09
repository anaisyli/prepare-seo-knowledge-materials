# Classification and Admission Policy

## Unit-first evaluation

Evaluate the smallest reliable semantic unit available in the source format: paragraph, heading section, table row, spreadsheet range, slide, page, message, or structured record. Then roll unit decisions up into an A-E material-item decision.

Do not classify from filenames alone. Filenames may raise risk but cannot establish safe content.

One exception covers media the company sorted itself. In a website kit or a product folder, the folder names say what the images and videos show, so a folder can be judged as a group after looking at samples, through a folder rule. Media in it can be A. Media from emails, chat exports, or loose unsorted folders is judged file by file, and unseen or unheard media there is D. Documents are always judged on their own content. See the format-handling reference.

## Two classification layers

R0-R4 are content-disposition codes for the smallest reliable semantic units. They are not a severity scale and do not describe the final file operation.

A-E are mutually exclusive handling decisions for the complete material item. Assign them only after all relevant content units have R codes.

## Business tag

After the A-E decision, give every item one `resource_type`. It sorts the material for the business; it does not change the decision.

| `resource_type` | Meaning |
|---|---|
| `marketing` | Company profiles, catalogs, brochures, exhibition and promotional material |
| `business_scenario` | Training material, FAQs, product learning, customer cases |
| `product` | Product lists, specifications, materials, technical sheets, certificates |
| `competitor` | Competitor and third-party material, kept separately |
| `seo_ops` | Keyword libraries and writing or page guidelines, for the team's use |
| `transaction` | Excluded quotation, order, sample, and shipment communication |
| `pricing` | Excluded price lists with no product knowledge once prices are removed |
| `finance` | Accounts, contracts, invoices, receipts, and customer ledgers. Recorded, not copied |
| `noise` | Greetings, chasers, signatures, logos |
| `unknown` | Not yet determined |

`restricted` means recorded but not copied. Use it only with `finance`; a quotation or a mixed sheet is not restricted, even when it names customers. A workbook typed `finance` that has product wording and images needs `no_product_rows: true`, set only after checking it has no reusable product rows. A workbook with product columns or embedded product images cannot be `pricing`: make it B.

Set `pending_client_review: true` when the client must decide whether the content can be used: customer cases, and content whose publication suitability is unclear. The item stays in the package, and the client decides during the post-triage review.

The mark covers the whole file by default. When only part of a file waits, such as three cases in a company profile, also set `pending_scope: "part"`. The rest of the file stays usable, and each `client_review_items` entry must give its location, so those parts are held back until the client decides.

Write `client_review_items` for each thing the client must decide, one entry per decision, in words a business owner understands:

```json
{"summary": "某北美客户的合作案例", "location": "第 12 页", "question": "这个案例可以写进官网吗？需要隐去客户名称吗？"}
```

Use page numbers or section titles the client can find, never codes such as R2, B, or paragraph indexes. A file with three cases gets three entries. A knowledge point awaiting the client uses `client_location` and `client_question` for the same purpose.

## R0-R4 content codes

### R0 - Retainable

Content is R0 only when all conditions are true:

1. It describes the company's own general knowledge, capability, product, material, technical detail, process, terminology, or stable policy.
2. It remains true outside any single customer, supplier, inquiry, quotation, order, shipment, contract, project, or communication. Appearing in such a document does not fail this condition; only the transaction or project specifics do. A specification of a company product passes; a specification made only for one customer's project does not.
3. It contains no personal data, account data, non-public commercial terms, internal financial data, confidential detail, or reconstructable identifiers.
4. It is not competitor or third-party information. That material is kept separately; see Competitor information.
5. Its meaning remains accurate without hidden context and does not generalize a one-off event.
6. It has concrete knowledge value for SEO/GEO, website, CRM, marketing, or training work.

Unclear publication suitability does not fail R0. Keep the content and set `pending_client_review: true`.

Light technical cleanup such as removing duplicate pages, repeated headers/footers, obvious encoding artifacts, or meaningless formatting does not change R0 meaning.

### R1 - Abstractable company knowledge

R1 comes from the company's own process, capability, product, material, or technical description, including what its staff say in emails and chats. Even a few useful sentences in a transactional message qualify. Its original wording or context cannot be retained, but it can support a general point without sensitive details. During triage, a faithful summary becomes a formal knowledge point and does not require a separate extraction approval or second review cycle.

Competitor material is not R1. Do not extract knowledge points about the company from it.

### R2 - Mandatory removal

R2 is a localized unit that must not appear in retained content. It includes:

- names, email addresses, phone numbers, detailed addresses, signatures, account IDs, and contact details;
- customer or supplier identities and lists;
- inquiries, quotations, discounts, special pricing, orders, quantities, payment, delivery, shipment, and transaction records;
- specifications made only for one customer's project, and project dates, geography, drawings, solutions, promises, and communication context;
- competitor passages inside company material; whole competitor documents are kept under Competitor information;
- any combination of otherwise ordinary details that can re-identify a party or event.

R2 may support B only when every prohibited unit and its reconstructable context can be removed precisely and the remainder independently passes R0.

### R3 - Whole-section or whole-item exclusion

Use R3 when prohibited or high-risk material dominates a coherent section or item, including contracts, NDAs, customer drawings, customer-specific solutions, internal cost/profit/commission data, confidential strategy, or internal discussion.

Transaction content alone is not R3. Do not rewrite R3 material into a retained document. Record an exclusion reason without quoting the content.

### R4 - Uncertain

Use R4 when content, declared processing scope, evidence status, deletion boundaries, or readability cannot be judged reliably. Examples include corrupt files, severe encoding problems, PDF pages that remain unreliable after OCR, images nobody has looked at, ambiguous structured fields, and statements whose general applicability cannot be established.

Authorization validity is an upstream responsibility and is not evaluated by this classification policy. This policy only checks whether the declared processing scope is present and clear.

Do not use R4 merely because a file contains many images when the readable text is sufficient. OCR-derived PDF text may support classification only when page coverage, recognition quality, and reading order are reliable enough for the decision; otherwise use R4 rather than guessing.

## A-E item decisions

Use this roll-up mapping:

- A: all substantive units are R0, or the item is competitor material kept whole.
- B: the item contains R0 plus localized R2/R3; every prohibited unit can be removed precisely, no unresolved R4 affects the result, and the remainder independently passes R0.
- C: the source cannot be retained, but at least one company-owned R1 unit can produce a useful, non-sensitive formal knowledge point.
- D: an R4 uncertainty prevents a reliable A, B, C, or E decision.
- E: R3 dominates, no useful R0/R1 remains, or the item has no knowledge value.

### A - Original retention

Every substantive unit passes R0, or the item is competitor material. The build script copies the source byte-for-byte. Do not summarize it.

### B - Retention after local removal

The item contains R0 plus removable R2/R3 units. Use B only when:

- every removal has an exact locator;
- the format supports a reliable edit at that boundary;
- removal eliminates reconstructable context;
- the remainder is coherent and every substantive remaining unit passes R0;
- the work copy can be verified after editing.

Otherwise choose C, D, or E.

Spreadsheets qualify, and quotation sheets are product material with prices attached. Removing columns, rows, or sheets is a valid boundary: keep item number, product name, description, composition, weight, construction, and images; remove every price column, customer and contact blocks, dates, order references, and customer-specific notes. Check hidden sheets, comments, and metadata. A table of orders or shipments is not a product table; when its rows only make sense as transactions, use E.

### C - Formal knowledge-point extraction

The original item cannot be retained, but at least one company-owned R1 unit can produce one or more useful, non-sensitive knowledge points. The source is copied to `C-知识点/来源文件/` for traceability only and is never imported. The knowledge point is created during triage, is formal, importable, and usable as enterprise knowledge without another review. Competitor material produces no extracted content.

### D - Cannot process reliably

Use D for R4 conditions. State the uncertainty in `summary` and what is needed in `required_follow_up`. The build script copies the file to `D-待定/` and records any copy failure. Do not persist raw connector or inline content merely because it is D; the input contract's persistence limits still apply.

### E - Excluded

Use E when the item is dominated by R3, lacks useful knowledge, or yields no formal knowledge point. Mostly transactional content is not by itself a reason: look for usable R0 and R1 units first, and use E only when none remain. An excluded email needs `mail_review` set to `full` or `candidates`, so a one-line digest or keyword match does not count as reading it. Every E item needs `content_read: true` and a specific reason code. The build script copies it to `E-排除/<标签>/`, except restricted items.

## Removal rules

- Remove a complete semantic unit, not only a matched word or identifier.
- Include surrounding context when it can reconstruct the prohibited fact.
- Do not replace a name with `Customer A` while leaving distinctive country, dates, quantities, product, or outcome details.
- If removal changes the meaning of nearby content, remove the larger enclosing unit or do not produce a cleaned version.
- In a table, remove all prohibited columns and identifying blocks, then confirm the remaining columns cannot re-identify a party or a transaction.

## Formal knowledge-point rules

A knowledge point is a concise, faithful summary of eligible company-owned R1 content. It is formal enterprise knowledge even though the original file or passage cannot be retained.

Knowledge points must:

- preserve the evidence scope without adding capabilities, guarantees, or generality;
- contain no customer, supplier, competitor, transaction, project, personal, internal-financial, or confidential details;
- omit original excerpts and prohibited values, including every price;
- retain a safe source ID and the locator of the company message or page it came from. What a customer wrote is not company knowledge;
- be created during triage from an eligible company-owned R1 unit and never be routed through the B-cleanup approval gate;
- state its `scope`: `general` for the company as a whole, `style` for one product or style, or `single_communication` for something seen once. A point from a single email is never `general`;
- use the following state in the execution output:

```yaml
record_type: "knowledge_point"
status: "approved"
scope: "style"
importable: true
usable_as_fact: true
```

A point from a customer case, or one whose publication suitability is unclear, also sets `pending_client_review: true`; it stays importable and is not usable as a fact until the client confirms it.

Write a style-level fact as that style's fact, such as a named item's fabric and weight. Do not widen `style` or `single_communication` content into a statement about the whole company.

Do not turn a single quotation, order, project, or communication into a standard MOQ, lead time, price, specification, certification, capacity, or guarantee. If a faithful and useful general point cannot be written without overgeneralizing, do not create one.

## Competitor information

Competitor and third-party material is kept separately with `resource_type: competitor`, whether public or not. It may inform positioning and research.

- It is never usable as a fact about the company, and its claims must not be attributed to the company.
- It produces no knowledge points about the company.
- A document that claims the company matches a reference supplier does not make that supplier's parameters company facts.

## Customer cases

Customer cases, testimonials, reviews, and project histories are kept, with `pending_client_review: true`. The client decides during the post-triage review whether each can be used and whether it must be anonymized.

- Keep the case unit in place in A and B items; do not remove it during triage. A case inside a longer document uses `pending_scope: "part"`, and a file that is all case stays pending as a whole.
- A knowledge point from a case omits the customer's identity and also sets `pending_client_review: true`.
- Disputes and complaints remain R3.

Example: if a source states that a named customer received a specific quantity of customized units within a specific period, keep the case for client review. Do not derive a standard capability, MOQ, or lead time from it.
