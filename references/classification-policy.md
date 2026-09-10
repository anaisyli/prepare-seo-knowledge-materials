# Classification and Admission Policy

## Unit-first evaluation

Evaluate the smallest reliable semantic unit available in the source format: paragraph, heading section, table row, spreadsheet range, slide, page, message, or structured record. Then roll unit decisions up into an A-E material-item decision.

Do not classify from filenames alone. Filenames may raise risk but cannot establish safe content.

## Two classification layers

R0-R4 are content-disposition codes for the smallest reliable semantic units. They are not a severity scale and do not describe the final file operation.

A-E are mutually exclusive handling decisions for the complete material item. Assign them only after all relevant content units have R codes.

## R0-R4 content codes

### R0 - Retainable

Content is R0 only when all conditions are true:

1. It describes the company's own general knowledge, capability, product, process, terminology, or stable policy.
2. It is not tied to a customer, supplier, competitor, inquiry, quotation, order, shipment, contract, project, or individual communication.
3. It contains no personal data, account data, non-public commercial terms, internal financial data, confidential detail, or reconstructable identifiers.
4. It contains no competitor information or customer case, including public or anonymized examples.
5. Its meaning remains accurate without hidden context and does not generalize a one-off event.
6. It has concrete knowledge value for later SEO work.
7. Its publication suitability is clear from the supplied evidence. Uncertainty fails R0.

Light technical cleanup such as removing duplicate pages, repeated headers/footers, obvious encoding artifacts, or meaningless formatting does not change R0 meaning.

### R1 - Abstractable company knowledge

R1 comes from the company's own process or capability description. Its original wording or context cannot be retained, but it can support a general point without sensitive details. During triage, a faithful summary becomes a formal knowledge point and does not require a separate extraction approval or second review cycle.

Competitor material and customer cases are R2 or R3, not R1. Do not extract any summary, topic, or knowledge point from them.

### R2 - Mandatory removal

R2 is a localized unit that must not appear in retained content. It includes:

- names, email addresses, phone numbers, detailed addresses, signatures, account IDs, and contact details;
- customer or supplier identities and lists;
- inquiries, quotations, discounts, special pricing, orders, quantities, payment, delivery, shipment, and transaction records;
- project-specific specifications, dates, geography, drawings, solutions, promises, and communication context;
- competitor companies, brands, products, models, specifications, pricing, positioning, market share, copied pages, screenshots, links, and comparative statements;
- customer cases, testimonials, reviews, project histories, outcomes, photos, before/after accounts, and anonymized cases;
- any combination of otherwise ordinary details that can re-identify a party or event.

R2 may support B only when every prohibited unit and its reconstructable context can be removed precisely and the remainder independently passes R0.

### R3 - Whole-section or whole-item exclusion

Use R3 when prohibited or high-risk material dominates a coherent section or item, including competitor research/comparison, customer case studies, contracts, NDAs, customer drawings, customer-specific solutions, internal cost/profit/commission data, confidential strategy, or internal discussion.

Do not rewrite R3 material into a retained document. Record an exclusion reason without quoting the content.

### R4 - Uncertain

Use R4 when content, declared processing scope, evidence status, deletion boundaries, or readability cannot be judged reliably. Examples include corrupt files, severe encoding problems, PDF pages that remain unreliable after OCR, standalone image-only content, ambiguous structured fields, and statements whose general applicability cannot be established.

Authorization validity is an upstream responsibility and is not evaluated by this classification policy. This policy only checks whether the declared processing scope is present and clear.

Do not use R4 merely because a file contains many images when the readable text is sufficient. OCR-derived PDF text may support classification only when page coverage, recognition quality, and reading order are reliable enough for the decision; otherwise use R4 rather than guessing.

## A-E item decisions

Use this roll-up mapping:

- A: all substantive units are R0.
- B: the item contains R0 plus localized R2/R3; every prohibited unit can be removed precisely, no unresolved R4 affects the result, and the remainder independently passes R0.
- C: the source cannot be retained, but at least one company-owned R1 unit can produce a useful, non-sensitive formal knowledge point.
- D: an R4 uncertainty prevents a reliable A, B, C, or E decision.
- E: R3 dominates, no useful R0/R1 remains, or the item has no knowledge value. E items produce exclusion records only.

### A - Original retention

Every substantive unit passes R0. Copy the source byte-for-byte during triage after the scope gate passes. Do not summarize it.

### B - Retention after local removal

The item contains R0 plus removable R2/R3 units. Use B only when:

- every removal has an exact locator;
- the format supports a reliable edit at that boundary;
- removal eliminates reconstructable context;
- the remainder is coherent and every substantive remaining unit passes R0;
- the work copy can be verified after editing.

Otherwise choose C, D, or E.

### C - Formal knowledge-point extraction

The original item cannot be retained, but at least one company-owned R1 unit can produce one or more useful, non-sensitive knowledge points. The original is not copied into formal knowledge assets. The knowledge point is created during triage, is formal, importable, and usable as enterprise knowledge without another review. Competitor- or customer-case-dominated items remain E and produce no extracted content.

### D - Cannot process reliably

Use D for R4 conditions. Do not edit or duplicate the raw source by default. Record the reason and the action needed for a future review.

### E - Excluded

Use E when the item is dominated by R3, lacks useful knowledge, or yields no formal knowledge point. Record filename/source ID and reason codes without reproducing sensitive content. Do not create derivative output from excluded competitor or customer-case material.

## Removal rules

- Remove a complete semantic unit, not only a matched word or identifier.
- Include surrounding context when it can reconstruct the prohibited fact.
- Do not replace a name with `Customer A` while leaving distinctive country, dates, quantities, product, or outcome details.
- Do not preserve public competitor or customer-case material; the prohibition is content-based, not secrecy-based.
- If removal changes the meaning of nearby content, remove the larger enclosing unit or do not produce a cleaned version.
- A list or table with mixed safe and prohibited columns is not safe merely because one identifier column was removed.

## Formal knowledge-point rules

A knowledge point is a concise, faithful summary of eligible company-owned R1 content. It is formal enterprise knowledge even though the original file or passage cannot be retained.

Knowledge points must:

- preserve the evidence scope without adding capabilities, guarantees, or generality;
- contain no customer, supplier, competitor, transaction, project, personal, internal-financial, or confidential details;
- omit original excerpts and prohibited values;
- retain a safe source ID and precise locator;
- be created during triage from an eligible company-owned R1 unit and never be routed through the B-cleanup approval gate;
- use the following state in the execution output:

```yaml
record_type: "knowledge_point"
status: "approved"
importable: true
usable_as_fact: true
```

Do not turn a single quotation, order, project, or communication into a standard MOQ, lead time, price, specification, certification, capacity, or guarantee. If a faithful and useful general point cannot be written without overgeneralizing, do not create one.

## Competitor and customer-case exclusion

Competitor information and customer cases are input-screening signals only. They must not produce summaries, generalized topics, derivative records, or formal knowledge points.

- For B items, remove the complete competitor or customer-case unit and its reconstructable context. Keep only the independently valid R0 remainder.
- For E items, record only the safe source label, exclusion reason code, and locator needed for audit.
- Do not preserve names, numbers, comparisons, outcomes, or anonymized case narratives in reports.
- Public availability, anonymization, or removal of identifiers does not change this exclusion.

Example: if a source states that a named customer received a specific quantity of customized units within a specific period, exclude the case content. Do not derive a capability statement, verification question, or reusable topic from it.
