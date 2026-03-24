from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import date, datetime
from html import escape
from pathlib import Path
import re


REPORT_FIELDNAMES = [
    "cause_number",
    "county",
    "attorney_in_charge",
    "scraped_date",
    "scraped_on_utc",
    "case_url",
    "result_tab",
    "result_count",
    "styled",
    "date_filed",
    "status",
    "event_date",
    "event_time",
    "event_name",
    "cancelled_reason",
    "judge",
    "comments",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a new-events report from the per-case CSV files created by the court case scraper."
        )
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("court_scraper_output"),
        help="Directory containing the per-case CSV files.",
    )
    parser.add_argument(
        "--report-date",
        help="Scraped date to report in YYYY-MM-DD format. Defaults to the latest scraped_date found.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("court_scraper_reports"),
        help="Directory where the report files will be written.",
    )
    parser.add_argument(
        "--event-date-after",
        help=(
            "Include only rows whose event_date is after this date. "
            "Use YYYY-MM-DD format."
        ),
    )
    return parser.parse_args()


def load_rows(input_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for csv_path in sorted(input_dir.glob("*.csv")):
        with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            if set(REPORT_FIELDNAMES).issubset(set(fieldnames)):
                for row in reader:
                    rows.append({key: (value or "").strip() for key, value in row.items()})
                continue

        with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
            plain_reader = csv.reader(handle)
            for record in plain_reader:
                if not record:
                    continue
                padded = record[: len(REPORT_FIELDNAMES)] + [""] * max(0, len(REPORT_FIELDNAMES) - len(record))
                rows.append(dict(zip(REPORT_FIELDNAMES, (value.strip() for value in padded))))
    return rows


def resolve_report_date(rows: list[dict[str, str]], requested_date: str | None) -> str:
    if requested_date:
        date.fromisoformat(requested_date)
        return requested_date

    scraped_dates = sorted({row.get("scraped_date", "") for row in rows if row.get("scraped_date", "")})
    if not scraped_dates:
        raise ValueError("No scraped_date values were found in the CSV files.")
    return scraped_dates[-1]


def parse_event_date(value: str) -> date | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None

    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        return None


def filter_rows_by_event_cutoff(
    rows: list[dict[str, str]],
    event_date_after: str | None,
) -> list[dict[str, str]]:
    if not event_date_after:
        return rows

    cutoff = date.fromisoformat(event_date_after)
    filtered_rows: list[dict[str, str]] = []
    for row in rows:
        event_date = parse_event_date(row.get("event_date", ""))
        if event_date and event_date > cutoff:
            filtered_rows.append(row)
    return filtered_rows


def sort_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        rows,
        key=lambda row: (
            row.get("attorney_in_charge", ""),
            row.get("cause_number", ""),
            row.get("event_date", ""),
            row.get("event_time", ""),
            row.get("event_name", ""),
        ),
    )


def group_rows_by_attorney(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    attorney_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        attorney_groups[row.get("attorney_in_charge", "Unassigned") or "Unassigned"].append(row)
    return dict(attorney_groups)


def group_rows_by_case(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    case_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        case_groups[row.get("cause_number", "")].append(row)
    return dict(case_groups)


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned.strip("._") or "report"


def build_markdown(report_date: str, rows: list[dict[str, str]]) -> str:
    attorney_groups = group_rows_by_attorney(rows)

    lines: list[str] = []
    lines.append(f"# New Events Report")
    lines.append("")
    lines.append(f"Report date: {report_date}")
    lines.append(f"Total new events: {len(rows)}")
    lines.append("")

    for attorney in sorted(attorney_groups):
        attorney_rows = attorney_groups[attorney]
        lines.append(f"## {attorney}")
        lines.append("")
        lines.append(f"New events: {len(attorney_rows)}")
        lines.append("")

        case_groups = group_rows_by_case(attorney_rows)

        for cause_number in sorted(case_groups):
            case_rows = sorted(
                case_groups[cause_number],
                key=lambda row: (
                    row.get("event_date", ""),
                    row.get("event_time", ""),
                    row.get("event_name", ""),
                ),
            )
            first = case_rows[0]
            lines.append(f"### {cause_number}")
            lines.append("")
            lines.append(f"Styled: {first.get('styled', '')}")
            lines.append(f"Status: {first.get('status', '')}")
            lines.append(f"Date filed: {first.get('date_filed', '')}")
            lines.append("")
            lines.append("| Event Date | Time | Event | Comments |")
            lines.append("| --- | --- | --- | --- |")
            for row in case_rows:
                comment_parts = [
                    row.get("comments", ""),
                    f"Cancelled: {row.get('cancelled_reason', '')}" if row.get("cancelled_reason", "") else "",
                    f"Judge: {row.get('judge', '')}" if row.get("judge", "") else "",
                ]
                comments = " | ".join(part for part in comment_parts if part)
                event_name = row.get("event_name", "").replace("\n", " ")
                lines.append(
                    f"| {row.get('event_date', '')} | {row.get('event_time', '')} | {event_name} | {comments} |"
                )
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def build_html(report_date: str, rows: list[dict[str, str]]) -> str:
    attorney_groups = group_rows_by_attorney(rows)

    parts: list[str] = []
    parts.append("<html><body style='font-family:Segoe UI,Arial,sans-serif;'>")
    parts.append(f"<h1>New Events Report</h1>")
    parts.append(f"<p><strong>Report date:</strong> {escape(report_date)}<br>")
    parts.append(f"<strong>Total new events:</strong> {len(rows)}</p>")

    for attorney in sorted(attorney_groups):
        attorney_rows = attorney_groups[attorney]
        parts.append(f"<h2>{escape(attorney)}</h2>")
        parts.append(f"<p><strong>New events:</strong> {len(attorney_rows)}</p>")

        case_groups = group_rows_by_case(attorney_rows)
        for cause_number in sorted(case_groups):
            case_rows = sorted(
                case_groups[cause_number],
                key=lambda row: (
                    row.get("event_date", ""),
                    row.get("event_time", ""),
                    row.get("event_name", ""),
                ),
            )
            first = case_rows[0]
            parts.append(f"<h3>{escape(cause_number)}</h3>")
            parts.append("<p>")
            parts.append(f"<strong>Styled:</strong> {escape(first.get('styled', ''))}<br>")
            parts.append(f"<strong>Status:</strong> {escape(first.get('status', ''))}<br>")
            parts.append(f"<strong>Date filed:</strong> {escape(first.get('date_filed', ''))}")
            parts.append("</p>")
            parts.append(
                "<table border='1' cellspacing='0' cellpadding='6' "
                "style='border-collapse:collapse;'>"
            )
            parts.append(
                "<tr><th>Event Date</th><th>Time</th><th>Event</th><th>Comments</th></tr>"
            )
            for row in case_rows:
                comment_parts = [
                    row.get("comments", ""),
                    f"Cancelled: {row.get('cancelled_reason', '')}" if row.get("cancelled_reason", "") else "",
                    f"Judge: {row.get('judge', '')}" if row.get("judge", "") else "",
                ]
                comments = " | ".join(part for part in comment_parts if part)
                parts.append(
                    "<tr>"
                    f"<td>{escape(row.get('event_date', ''))}</td>"
                    f"<td>{escape(row.get('event_time', ''))}</td>"
                    f"<td>{escape(row.get('event_name', '').replace(chr(10), ' '))}</td>"
                    f"<td>{escape(comments)}</td>"
                    "</tr>"
                )
            parts.append("</table>")
    parts.append("</body></html>")
    return "".join(parts)


def write_filtered_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    rows = load_rows(args.input_dir)
    if not rows:
        raise SystemExit(f"No case CSV files were found in {args.input_dir}.")

    report_date = resolve_report_date(rows, args.report_date)
    filtered_rows = [row for row in rows if row.get("scraped_date", "") == report_date]
    filtered_rows = filter_rows_by_event_cutoff(filtered_rows, args.event_date_after)
    if not filtered_rows:
        cutoff_suffix = (
            f" and event_date>{args.event_date_after}" if args.event_date_after else ""
        )
        raise SystemExit(f"No events were found for scraped_date={report_date}{cutoff_suffix}.")

    filtered_rows = sort_rows(filtered_rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = args.output_dir / f"new_events_report_{report_date}.md"
    csv_path = args.output_dir / f"new_events_report_{report_date}.csv"

    markdown_path.write_text(build_markdown(report_date, filtered_rows), encoding="utf-8")
    write_filtered_csv(csv_path, filtered_rows)

    print(f"Wrote {markdown_path}")
    print(f"Wrote {csv_path}")
    print(f"Report date: {report_date}")
    print(f"Total events: {len(filtered_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
