# Discovery Statement Compliance Codex Skill

Created by *Thomas J. Daley*.

## What This Skill Does

`discovery-compliance` helps process statement productions for discovery review.

It supports two document types:
- bank account statements
- credit card statements

It performs the workflow in two phases:
1. Extract statement metadata into reviewable Excel and CSV files.
2. After human cleanup, generate compliance matrices in Markdown and Excel.

The skill is designed so a paralegal can supply:
- the bank statement folder
- the credit card statement folder
- the output folder
- the Bates-number regular expression for the matter
- the year range for the compliance matrices

## What It Produces

During extraction, the skill creates:
- `bank_statement_index.csv`
- `bank_statement_index.xlsx`
- `credit_card_statement_index.csv`
- `credit_card_statement_index.xlsx`

After cleanup, the skill creates:
- `bank_compliance_matrices.md`
- `credit_card_compliance_matrices.md`
- `compliance_matrices.xlsx`

## Install The Skill

### Option 1: Copy The Skill Folder Into Codex

Copy the `discovery-compliance` folder into your local Codex skills directory.

Typical location on Windows:

```text
%USERPROFILE%\.codex\skills\discovery-compliance
```

### Option 2: Install From This Repository

If your Codex setup supports skill installation from a repo, install the `discovery-compliance` folder from this repository into your local Codex skills directory.

If you are unsure which method to use, use Option 1.

## Skill Location

The skill lives here in this repository:

```text
discovery-compliance/
```

## Requirements

This skill is intended for Windows and uses PowerShell for OCR fallback.

Python dependencies:

```powershell
python -m pip install pypdf openpyxl pymupdf pillow
```

## How To Run It

Use the wrapper script:

```powershell
python <skill-dir>\scripts\run_matter.py ...
```

`<skill-dir>` is the path to the installed `discovery-compliance` skill folder on your machine.

### Phase 1: Extract Statements For Review

Run:

```powershell
python <skill-dir>\scripts\run_matter.py --phase extract --bank-folder "<bank-folder>" --credit-folder "<credit-folder>" --output-dir "<output-folder>" --bates-regex "<matter-regex>"
```

Example:

```powershell
python %USERPROFILE%\.codex\skills\discovery-compliance\scripts\run_matter.py --phase extract --bank-folder "C:\Work\Matter123\Bank Accts" --credit-folder "C:\Work\Matter123\CCs" --output-dir "C:\Work\Matter123\Outputs" --bates-regex "JF0+\d{4}"
```

This creates cleaned-starting-point spreadsheets and CSVs for human review.

### Review Step

Before building matrices, review the CSV files and make any needed corrections.

Common cleanup tasks:
- remove obvious OCR junk from `Account Holder(s) Name(s)`
- fill missing beginning dates where the correct date is clear
- normalize account numbers when the same account appears in short and long form

Treat the cleaned CSVs as the source of truth for matrix generation.

### Phase 2: Build Compliance Matrices

Run:

```powershell
python <skill-dir>\scripts\run_matter.py --phase matrices --output-dir "<output-folder>" --year-start 2020 --year-end 2026
```

Example:

```powershell
python %USERPROFILE%\.codex\skills\discovery-compliance\scripts\run_matter.py --phase matrices --output-dir "C:\Work\Matter123\Outputs" --year-start 2020 --year-end 2026
```

This creates:
- Markdown compliance matrices for bank accounts
- Markdown compliance matrices for credit cards
- one Excel workbook with separate bank and credit-card sheets

## Bates Regex

The Bates pattern changes by matter.

Always provide the correct regex for the matter during extraction. Example:

```powershell
--bates-regex "JF0+\d{4}"
```

## How To Use In Codex

Once the skill is installed, you can also invoke it by name inside Codex.

Example prompt:

```text
Use $discovery-compliance to extract metadata from these bank and credit card folders, then help me build compliance matrices for 2020 through 2026.
```

## Skill Files

Main files in the skill:
- `SKILL.md`: instructions Codex uses
- `scripts/run_matter.py`: main wrapper for paralegals
- `scripts/extract_bank_statements.py`: bank extractor
- `scripts/extract_credit_card_statements.py`: credit-card extractor
- `scripts/generate_compliance_matrices.py`: matrix builder
- `scripts/ocr_image.ps1`: OCR helper

## Recommended Team Workflow

1. Install the skill once.
2. Run extraction for a matter.
3. Review and clean the CSVs.
4. Run matrix generation.
5. Save the final outputs to the matter workspace.

## Support Notes

If the wrapper script reports missing Python packages, install the dependencies listed above and rerun the command.

If OCR results are messy on a few files, correct the exported CSV manually before generating matrices.
