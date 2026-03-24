---
name: collin-county-court-monitor
description: Scrape public Collin County court cases from a CSV list of cause numbers, append newly found docket events to per-case CSV files, generate attorney-ready "new events" reports grouped by attorney and cause number, and route those reports through desktop Outlook. Use when Codex needs to monitor Collin County Judicial Online Search cases, refresh case-event histories from an Excel-friendly case list, prepare daily update reports, create Outlook drafts, send reports to a firm email address, or set up this workflow from a GitHub-installed skill.
---

# Collin County Court Monitor

Use the bundled scripts to run the same repeatable workflow each time:

1. Prepare a CSV file matching the shape in [references/input-csv-example.csv](references/input-csv-example.csv).
2. Run `scripts/court_case_scraper.py` to scrape every case with `scrape_flag=Y`.
3. Run `scripts/generate_new_events_report.py` to produce a Markdown and CSV report for a scrape date.
4. Run `scripts/send_outlook_report.py` when you want Outlook drafts or sent emails.
5. Use `scripts/run_daily_cycle.py` when you want scraping, reporting, and optional Outlook delivery to run back to back.

Before running the workflow for another user, ask for:

- the working folder that should hold the case list, case CSV output, and report output
- the path to the case-list CSV if it is not in the working folder
- whether email routing should come from the `attorney_email` column or from one override email address
- whether the user wants Outlook drafts or immediate sends

## Quick Start

Install dependencies:

```powershell
python -m pip install -r .\scripts\requirements.txt
```

Run the full cycle:

```powershell
python .\scripts\run_daily_cycle.py --input-csv .\cases.csv --case-output-dir .\court_scraper_output --report-output-dir .\court_scraper_reports --email-mode draft
```

Run the scraper only:

```powershell
python .\scripts\court_case_scraper.py --input-csv .\cases.csv --output-dir .\court_scraper_output
```

Generate the latest report only:

```powershell
python .\scripts\generate_new_events_report.py --input-dir .\court_scraper_output --output-dir .\court_scraper_reports
```

Create Outlook drafts using `attorney_email` from the case-list CSV:

```powershell
python .\scripts\send_outlook_report.py --case-list-csv .\cases.csv --input-dir .\court_scraper_output --output-dir .\court_scraper_reports --mode draft
```

Send a combined report to one override address:

```powershell
python .\scripts\send_outlook_report.py --case-list-csv .\cases.csv --input-dir .\court_scraper_output --output-dir .\court_scraper_reports --mode send --email-to reports@yourfirm.com
```

## Workflow Notes

- Support only the public Collin County site and the `Case` tab event table.
- Require Chrome to be installed locally because Selenium drives a real browser.
- Require desktop Outlook on Windows for draft/send automation.
- Update `last_scraped_on` in the input CSV after a successful scrape.
- Use `Y` or `N` in `scrape_flag` so colleagues can maintain the list easily in Excel.
- Support an optional `attorney_email` column in the case-list CSV for per-attorney Outlook routing.
- Write one CSV per cause number and append only unseen docket rows.
- Include both `scraped_date` and `scraped_on_utc` in each event row so later reports can filter by scrape day or exact timestamp.
- Default the report generator to the latest `scraped_date` present in the case CSVs when `--report-date` is omitted.
- Default the Outlook sender to drafts unless the user clearly asks to send immediately.

## Resources

### scripts/

- `court_case_scraper.py`: scrape flagged cause numbers from the CSV file and update per-case CSVs.
- `generate_new_events_report.py`: create attorney-grouped Markdown and CSV reports for a scrape date.
- `send_outlook_report.py`: create Outlook drafts or send Outlook emails with report attachments.
- `send_outlook_mail.ps1`: PowerShell helper that drives the local Outlook desktop application.
- `run_daily_cycle.py`: run scraping, reporting, and optional Outlook delivery in one command.
- `requirements.txt`: minimal Python dependency list.

### references/

- `input-csv-example.csv`: example case-list payload for new matters.

## Maintenance

- Inspect selectors in `scripts/court_case_scraper.py` if the Collin County site changes its markup or navigation flow.
- Keep county-specific assumptions inside the scraper; do not silently reuse this skill for other counties without adapting selectors and routing.
