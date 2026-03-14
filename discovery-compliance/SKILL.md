---
name: discovery-compliance
description: Extract metadata from bank-account and credit-card statement PDFs, output reviewable CSV/XLSX indexes, and build month-by-month compliance matrices for discovery productions. Use when Codex needs to process statement folders, capture issuer/account/date/Bates metadata from the first page with limited second-page fallback, pause for human cleanup of the exported CSVs, and then generate bank and credit-card compliance matrices for a specified year range.
---

# Discovery Compliance

## Overview

Use this skill to turn statement productions into two deliverables:
- reviewable bank and credit-card index spreadsheets/CSVs
- bank and credit-card compliance matrices in markdown and Excel

Use `scripts/run_matter.py` as the main entry point. Keep the workflow in two phases so a paralegal can clean the extracted CSVs before matrix generation.

## Main Entry Point

### Phase 1: Extract For Review

```powershell
python <skill-dir>\scripts\run_matter.py --phase extract --bank-folder "<bank-folder>" --credit-folder "<credit-folder>" --output-dir "<output-folder>" --bates-regex "<matter-regex>"
```

This creates:
- `<output-folder>\bank\bank_statement_index.csv`
- `<output-folder>\bank\bank_statement_index.xlsx`
- `<output-folder>\credit\credit_card_statement_index.csv`
- `<output-folder>\credit\credit_card_statement_index.xlsx`

### Phase 2: Build Matrices After Cleanup

```powershell
python <skill-dir>\scripts\run_matter.py --phase matrices --output-dir "<output-folder>" --year-start 2020 --year-end 2026
```

This creates:
- `<output-folder>\bank_compliance_matrices.md`
- `<output-folder>\credit_card_compliance_matrices.md`
- `<output-folder>\compliance_matrices.xlsx`

### Convenience Mode

`--phase all` runs extraction and then stops with a reminder to clean the CSVs before matrix generation. It does not auto-build matrices.

## Workflow Details

### Extraction

Bank extraction uses:
- `scripts/extract_bank_statements.py`

Credit-card extraction uses:
- `scripts/extract_credit_card_statements.py`

Both extractors:
- walk folders recursively
- read page 1 first and page 2 only when needed
- use `ocr_image.ps1` when text extraction is insufficient
- accept a matter-specific Bates regex with `--bates-regex`

### Human Cleanup

Treat the cleaned CSVs as the source of truth for compliance matrices.

Conservative cleanup is appropriate:
- remove obvious OCR junk from `Account Holder(s) Name(s)`
- fill missing beginning dates when the inference is reliable
  usually use prior statement ending date plus one day when the same account has continuous statements
  if the production clearly uses month-end statements and no better source exists, first-of-month is acceptable
- normalize account numbers when the same account appears in both abbreviated and full form
  prefer one consistent display form within the matter, usually the folder-style short form or visible last four

Do not normalize across accounts unless the relationship is unambiguous.

### Matrix Generation

Matrix generation uses:
- `scripts/generate_compliance_matrices.py`

The matrix builder:
- creates one account block per account label
- creates a row for every requested year
- places Bates numbers into each month touched by a statement's coverage period
- writes markdown plus a two-sheet Excel workbook

## Expected Inputs

Expect the user to provide:
- a bank statement folder
- a credit-card statement folder
- an output folder
- a matter-specific Bates regex
- a year range for the matrix phase

If the user provides only one statement folder type, run only that extraction piece.

## Dependencies

If imports fail, install:

```powershell
python -m pip install pypdf openpyxl pymupdf pillow
```

These scripts rely on Windows PowerShell for OCR fallback.

## Files

### `scripts/run_matter.py`

Use as the main workflow entry point for paralegals.

### `scripts/extract_bank_statements.py`

Use for bank-account productions.

### `scripts/extract_credit_card_statements.py`

Use for credit-card productions.

### `scripts/generate_compliance_matrices.py`

Use after CSV review to generate markdown and Excel matrices.

### `scripts/ocr_image.ps1`

Use only as the OCR helper called by the Python extractors.
