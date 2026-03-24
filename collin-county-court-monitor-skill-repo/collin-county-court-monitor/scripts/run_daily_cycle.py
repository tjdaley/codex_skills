from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Collin County case scraper and then generate a new-events report."
        )
    )
    parser.add_argument("--input-csv", required=True, type=Path)
    parser.add_argument(
        "--case-output-dir",
        type=Path,
        default=Path("court_scraper_output"),
    )
    parser.add_argument(
        "--report-output-dir",
        type=Path,
        default=Path("court_scraper_reports"),
    )
    parser.add_argument("--report-date")
    parser.add_argument(
        "--email-mode",
        choices=["none", "draft", "send"],
        default="none",
    )
    parser.add_argument(
        "--email-to",
        help=(
            "Optional override recipient list, comma separated. If omitted, the workflow reads "
            "attorney_email from the case-list CSV."
        ),
    )
    parser.add_argument("--headful", action="store_true")
    return parser.parse_args()


def run_command(args: list[str]) -> None:
    subprocess.run(args, check=True)


def main() -> int:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent

    scraper_args = [
        sys.executable,
        str(script_dir / "court_case_scraper.py"),
        "--input-csv",
        str(args.input_csv),
        "--output-dir",
        str(args.case_output_dir),
    ]
    if args.headful:
        scraper_args.append("--headful")

    report_args = [
        sys.executable,
        str(script_dir / "generate_new_events_report.py"),
        "--input-dir",
        str(args.case_output_dir),
        "--output-dir",
        str(args.report_output_dir),
    ]
    if args.report_date:
        report_args.extend(["--report-date", args.report_date])

    run_command(scraper_args)
    run_command(report_args)
    if args.email_mode != "none":
        email_args = [
            sys.executable,
            str(script_dir / "send_outlook_report.py"),
            "--case-list-csv",
            str(args.input_csv),
            "--input-dir",
            str(args.case_output_dir),
            "--output-dir",
            str(args.report_output_dir),
            "--mode",
            args.email_mode,
        ]
        if args.report_date:
            email_args.extend(["--report-date", args.report_date])
        if args.email_to:
            email_args.extend(["--email-to", args.email_to])
        run_command(email_args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
