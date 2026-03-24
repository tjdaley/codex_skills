# Collin County Court Monitor Skill

This repository packages the `collin-county-court-monitor` Codex skill.

## Repo Layout

```text
collin-county-court-monitor-skill-repo/
  README.md
  .gitignore
  collin-county-court-monitor/
    SKILL.md
    agents/
    references/
    scripts/
```

## Install From GitHub

Point the Codex skill installer at the `collin-county-court-monitor` folder in this repository.

```text
Use $skill-installer to install the skill from https://github.com/tjdaley/codex_skills/tree/main/collin-county-court-monitor-skill-repo/collin-county-court-monitor
```

## What The Skill Does

- scrape flagged Collin County cause numbers from an Excel-friendly case-list CSV
- append new case events to one CSV per case
- generate attorney-grouped new-events reports
- create Outlook drafts or send Outlook emails with those reports

## Notes

- The installable skill itself is the `collin-county-court-monitor` folder.
- Keep generated outputs like `court_scraper_output/`, `court_scraper_reports/`, and case-list working files outside the skill folder.
