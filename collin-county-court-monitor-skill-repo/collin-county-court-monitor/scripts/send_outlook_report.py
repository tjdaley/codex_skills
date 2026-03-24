from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

from generate_new_events_report import (
    build_html,
    build_markdown,
    load_rows,
    resolve_report_date,
    slugify,
    sort_rows,
    write_filtered_csv,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create Outlook draft emails or send attorney new-events reports."
    )
    parser.add_argument(
        "--case-list-csv",
        required=True,
        type=Path,
        help="Case list CSV used by the scraper. May include an attorney_email column.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("court_scraper_output"),
        help="Directory containing the per-case CSV files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("court_scraper_reports"),
        help="Directory where email packet files will be written.",
    )
    parser.add_argument(
        "--report-date",
        help="Scraped date to email in YYYY-MM-DD format. Defaults to the latest scraped_date found.",
    )
    parser.add_argument(
        "--email-to",
        help=(
            "Optional override recipient list, comma separated. If omitted, the script reads "
            "attorney_email from the case-list CSV."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["draft", "send"],
        default="draft",
        help="Create Outlook drafts or immediately send through Outlook desktop.",
    )
    parser.add_argument(
        "--subject",
        help="Optional custom subject. Defaults to 'New Court Events Report - YYYY-MM-DD'.",
    )
    return parser.parse_args()


def load_case_list_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("Case list CSV must include a header row.")
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def split_recipients(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def group_rows_by_recipient(
    rows: list[dict[str, str]],
    case_rows: list[dict[str, str]],
    override_recipients: list[str],
) -> dict[str, list[dict[str, str]]]:
    if override_recipients:
        return {recipient: rows[:] for recipient in override_recipients}

    cause_to_email = {
        row.get("cause_number", "").strip(): row.get("attorney_email", "").strip()
        for row in case_rows
        if row.get("cause_number", "").strip()
    }

    missing_causes = sorted(
        {
            row.get("cause_number", "")
            for row in rows
            if not cause_to_email.get(row.get("cause_number", ""), "")
        }
    )
    if missing_causes:
        raise ValueError(
            "Missing attorney_email values for cause numbers: "
            + ", ".join(cause for cause in missing_causes if cause)
        )

    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        recipient = cause_to_email[row.get("cause_number", "")]
        grouped.setdefault(recipient, []).append(row)
    return grouped


def create_email_packet(
    base_dir: Path,
    recipient: str,
    report_date: str,
    rows: list[dict[str, str]],
) -> tuple[Path, Path, Path]:
    packet_dir = base_dir / report_date / slugify(recipient)
    packet_dir.mkdir(parents=True, exist_ok=True)

    markdown_path = packet_dir / f"new_events_report_{report_date}.md"
    csv_path = packet_dir / f"new_events_report_{report_date}.csv"
    html_path = packet_dir / f"new_events_report_{report_date}.html"

    markdown_path.write_text(build_markdown(report_date, rows), encoding="utf-8")
    write_filtered_csv(csv_path, rows)
    html_path.write_text(build_html(report_date, rows), encoding="utf-8")
    return markdown_path, csv_path, html_path


def send_via_outlook(
    recipient: str,
    subject: str,
    html_body_path: Path,
    attachments: list[Path],
    mode: str,
    script_path: Path,
) -> None:
    attachment_value = ";".join(str(path) for path in attachments)
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-To",
            recipient,
            "-Subject",
            subject,
            "-HtmlBodyPath",
            str(html_body_path),
            "-Attachments",
            attachment_value,
            "-Mode",
            mode,
        ],
        check=True,
    )


def main() -> int:
    args = parse_args()
    rows = load_rows(args.input_dir)
    if not rows:
        raise SystemExit(f"No case CSV files were found in {args.input_dir}.")

    report_date = resolve_report_date(rows, args.report_date)
    filtered_rows = sort_rows([row for row in rows if row.get("scraped_date", "") == report_date])
    if not filtered_rows:
        raise SystemExit(f"No events were found for scraped_date={report_date}.")

    override_recipients = split_recipients(args.email_to) if args.email_to else []
    case_rows = load_case_list_rows(args.case_list_csv)
    grouped_rows = group_rows_by_recipient(filtered_rows, case_rows, override_recipients)

    packet_root = args.output_dir / "outlook_packets"
    ps_script = Path(__file__).resolve().parent / "send_outlook_mail.ps1"
    subject = args.subject or f"New Court Events Report - {report_date}"
    mode_label = {"draft": "Drafted", "send": "Sent"}[args.mode]

    for recipient, recipient_rows in grouped_rows.items():
        markdown_path, csv_path, html_path = create_email_packet(
            packet_root,
            recipient,
            report_date,
            recipient_rows,
        )
        send_via_outlook(
            recipient=recipient,
            subject=subject,
            html_body_path=html_path,
            attachments=[markdown_path, csv_path],
            mode=args.mode,
            script_path=ps_script,
        )
        print(f"{mode_label} Outlook email for {recipient}")

    print(f"Report date: {report_date}")
    print(f"Recipient count: {len(grouped_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
