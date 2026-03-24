from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


SEARCH_URL = "https://apps2.collincountytx.gov/JudicialOnlineSearch2/global"
SUPPORTED_COUNTY_NAMES = {"collin", "collin county", "collin county tx", "collin county texas"}
TAB_NAME_MAP = {
    "Inmate": "Inmate",
    "Case": "Case",
    "Warrants": "Warrants",
    "Civil Paper": "Civil Paper",
}
CSV_FIELDNAMES = [
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


@dataclass
class CaseConfig:
    cause_number: str
    county: str
    attorney_in_charge: str
    scrape_flag: bool
    last_scraped_on: str | None = None


class ScrapeError(RuntimeError):
    """Raised when a case cannot be scraped successfully."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scrape public Collin County case details for the flagged cause numbers in a CSV "
            "document and append new docket events to one CSV per case."
        )
    )
    parser.add_argument(
        "--input-csv",
        required=True,
        type=Path,
        help="Path to the CSV file containing the case list.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("court_scraper_output"),
        help="Directory where per-case CSV files will be stored.",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Show the Chrome browser while scraping.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="Maximum time to wait for page elements.",
    )
    parser.add_argument(
        "--pause-after-search",
        type=float,
        default=4.0,
        help="Extra pause after typing the cause number before parsing result counts.",
    )
    parser.add_argument(
        "--pause-after-click",
        type=float,
        default=2.5,
        help="Extra pause after clicking a tab or result row.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )
    return parser.parse_args()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def parse_scrape_flag(value: str) -> bool:
    return normalize_text(value).casefold() in {"y", "yes", "true", "1"}


def load_case_configs(path: Path) -> tuple[list[CaseConfig], list[dict[str, str]], list[str]]:
    cases: list[CaseConfig] = []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("Input CSV must include a header row.")

        fieldnames = list(reader.fieldnames)
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]

    for index, item in enumerate(rows):
        cause_number = item.get("cause_number", "").strip()
        county = item.get("county", "").strip()
        attorney_in_charge = item.get("attorney_in_charge", "").strip()
        scrape_flag = parse_scrape_flag(item.get("scrape_flag", ""))
        last_scraped_on = item.get("last_scraped_on", "").strip()
        last_scraped_on_text = None if last_scraped_on == "" else last_scraped_on

        if not cause_number:
            raise ValueError(f"Case entry {index} is missing cause_number.")

        cases.append(
            CaseConfig(
                cause_number=cause_number,
                county=county,
                attorney_in_charge=attorney_in_charge,
                scrape_flag=scrape_flag,
                last_scraped_on=last_scraped_on_text,
            )
        )

    return cases, rows, fieldnames


def build_driver(headful: bool) -> webdriver.Chrome:
    options = ChromeOptions()
    options.add_argument("--window-size=1600,1400")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    if not headful:
        options.add_argument("--headless=new")
    return webdriver.Chrome(options=options)


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned.strip("._") or "case"


def normalize_text(value: str) -> str:
    return " ".join(value.split())


def event_identity(row: dict[str, str]) -> tuple[str, ...]:
    return (
        normalize_text(row["cause_number"]).casefold(),
        normalize_text(row["event_date"]).casefold(),
        normalize_text(row["event_time"]).casefold(),
        normalize_text(row["event_name"]).casefold(),
        normalize_text(row["cancelled_reason"]).casefold(),
        normalize_text(row["judge"]).casefold(),
        normalize_text(row["comments"]).casefold(),
    )


def existing_event_keys(csv_path: Path) -> set[tuple[str, ...]]:
    return {event_identity(row) for row in read_csv_rows(csv_path)}


def read_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []

    with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows: list[dict[str, str]] = []
        if set(CSV_FIELDNAMES).issubset(set(fieldnames)):
            for row in reader:
                normalized_row = {field: row.get(field, "") or "" for field in CSV_FIELDNAMES}
                if not normalized_row["scraped_date"] and normalized_row["scraped_on_utc"]:
                    normalized_row["scraped_date"] = normalized_row["scraped_on_utc"][:10]
                rows.append(normalized_row)
            return rows

    with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
        plain_reader = csv.reader(handle)
        for record in plain_reader:
            if not record:
                continue
            padded = record[: len(CSV_FIELDNAMES)] + [""] * max(0, len(CSV_FIELDNAMES) - len(record))
            normalized_row = dict(zip(CSV_FIELDNAMES, padded))
            if not normalized_row["scraped_date"] and normalized_row["scraped_on_utc"]:
                normalized_row["scraped_date"] = normalized_row["scraped_on_utc"][:10]
            rows.append(normalized_row)
    return rows


def rewrite_csv(csv_path: Path, rows: list[dict[str, str]]) -> None:
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def append_new_events(csv_path: Path, rows: list[dict[str, str]]) -> tuple[int, int]:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists()
    existing_rows = read_csv_rows(csv_path)
    existing_keys = {event_identity(row) for row in existing_rows}
    if file_exists:
        rewrite_csv(csv_path, existing_rows)
    new_rows: list[dict[str, str]] = []

    for row in rows:
        key = event_identity(row)
        if key in existing_keys:
            continue
        existing_keys.add(key)
        new_rows.append(row)

    if new_rows:
        with csv_path.open("a", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
            if not file_exists:
                writer.writeheader()
            writer.writerows(new_rows)
    elif not file_exists:
        rewrite_csv(csv_path, [])

    return len(new_rows), len(rows)


def wait_for_page_ready(driver: webdriver.Chrome, timeout_seconds: int) -> None:
    WebDriverWait(driver, timeout_seconds).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def open_search_page(driver: webdriver.Chrome, timeout_seconds: int) -> None:
    driver.get(SEARCH_URL)
    wait_for_page_ready(driver, timeout_seconds)
    WebDriverWait(driver, timeout_seconds).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder='Search']"))
    )


def search_for_cause_number(
    driver: webdriver.Chrome,
    cause_number: str,
    timeout_seconds: int,
    pause_after_search: float,
) -> dict[str, int]:
    search = WebDriverWait(driver, timeout_seconds).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "input[placeholder='Search']"))
    )
    search.click()
    search.send_keys(Keys.CONTROL, "a")
    search.send_keys(Keys.DELETE)
    search.send_keys(cause_number)
    time.sleep(pause_after_search)

    def tabs_loaded(current_driver: webdriver.Chrome) -> bool:
        tabs = current_driver.find_elements(By.CSS_SELECTOR, "div.mud-tab p.nav-menu-button")
        return len(tabs) >= 4 and any("(" in tab.text for tab in tabs)

    WebDriverWait(driver, timeout_seconds).until(tabs_loaded)
    return read_tab_counts(driver)


def read_tab_counts(driver: webdriver.Chrome) -> dict[str, int]:
    counts: dict[str, int] = {}
    tab_labels = driver.find_elements(By.CSS_SELECTOR, "div.mud-tab p.nav-menu-button")
    for label in tab_labels:
        text = normalize_text(label.text)
        match = re.match(r"^(?P<name>.+?)\s*\((?P<count>\d+)\)$", text)
        if not match:
            continue
        name = match.group("name")
        if name in TAB_NAME_MAP:
            counts[TAB_NAME_MAP[name]] = int(match.group("count"))
    return counts


def click_tab(driver: webdriver.Chrome, tab_name: str, pause_after_click: float, timeout_seconds: int) -> None:
    tab = WebDriverWait(driver, timeout_seconds).until(
        EC.element_to_be_clickable(
            (By.XPATH, f"//div[contains(@class,'mud-tab')]//p[normalize-space()='{tab_name} ({read_tab_counts(driver).get(tab_name, 0)})']/ancestor::div[contains(@class,'mud-tab')][1]")
        )
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tab)
    driver.execute_script("arguments[0].click();", tab)
    time.sleep(pause_after_click)


def extract_case_search_result(
    driver: webdriver.Chrome,
    cause_number: str,
    timeout_seconds: int,
) -> dict[str, str]:
    row = WebDriverWait(driver, timeout_seconds).until(
        EC.presence_of_element_located(
            (By.XPATH, f"//em[normalize-space()='{cause_number}']/ancestor::tr[1]")
        )
    )

    def cell(label: str) -> str:
        try:
            return normalize_text(
                row.find_element(By.XPATH, f".//td[@data-label='{label}']").text
            )
        except NoSuchElementException:
            return ""

    return {
        "styled": cell("Styled"),
        "date_filed": cell("Date Filed"),
        "status": cell("Status"),
    }


def open_case_detail(
    driver: webdriver.Chrome,
    cause_number: str,
    timeout_seconds: int,
    pause_after_click: float,
) -> str:
    row = WebDriverWait(driver, timeout_seconds).until(
        EC.presence_of_element_located(
            (By.XPATH, f"//em[normalize-space()='{cause_number}']/ancestor::tr[1]")
        )
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", row)
    driver.execute_script("arguments[0].click();", row)
    WebDriverWait(driver, timeout_seconds).until(lambda d: "/case/" in d.current_url)
    time.sleep(pause_after_click)
    return driver.current_url


def find_case_events_table(driver: webdriver.Chrome) -> Any:
    tables = driver.find_elements(By.CSS_SELECTOR, "table")
    for table in tables:
        headers = [
            normalize_text(header.text)
            for header in table.find_elements(By.CSS_SELECTOR, "thead th")
            if normalize_text(header.text)
        ]
        if "Date" in headers and "Event" in headers:
            return table
    raise ScrapeError("Could not find the case events table on the case detail page.")


def extract_case_events(driver: webdriver.Chrome) -> list[dict[str, str]]:
    table = find_case_events_table(driver)
    headers = [
        normalize_text(header.text)
        for header in table.find_elements(By.CSS_SELECTOR, "thead th")
    ]

    rows: list[dict[str, str]] = []
    for tr in table.find_elements(By.CSS_SELECTOR, "tbody tr"):
        cells = tr.find_elements(By.CSS_SELECTOR, "td")
        if not cells:
            continue
        row: dict[str, str] = {}
        for idx, header in enumerate(headers):
            key = header.lower().replace(" ", "_")
            value = normalize_text(cells[idx].text) if idx < len(cells) else ""
            row[key] = value
        rows.append(row)
    return rows


def supported_county(county: str) -> bool:
    return normalize_text(county).casefold() in SUPPORTED_COUNTY_NAMES


def write_case_csv(
    path: Path,
    rows: list[dict[str, str]],
    fieldnames: list[str],
) -> None:
    normalized_fieldnames = list(fieldnames)
    for required in [
        "cause_number",
        "county",
        "attorney_in_charge",
        "scrape_flag",
        "last_scraped_on",
    ]:
        if required not in normalized_fieldnames:
            normalized_fieldnames.append(required)

    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=normalized_fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in normalized_fieldnames})


def update_case_csv_timestamp(
    rows: list[dict[str, str]],
    case_config: CaseConfig,
    timestamp: str,
) -> bool:
    for item in rows:
        if item.get("cause_number", "").strip() == case_config.cause_number:
            item["last_scraped_on"] = timestamp
            return True
    return False


def scrape_case(
    driver: webdriver.Chrome,
    case_config: CaseConfig,
    output_dir: Path,
    timeout_seconds: int,
    pause_after_search: float,
    pause_after_click: float,
) -> tuple[int, int]:
    open_search_page(driver, timeout_seconds)
    tab_counts = search_for_cause_number(
        driver,
        case_config.cause_number,
        timeout_seconds,
        pause_after_search,
    )
    logging.info("Cause %s tab counts: %s", case_config.cause_number, tab_counts)

    case_hits = tab_counts.get("Case", 0)
    if case_hits < 1:
        raise ScrapeError(
            f"No Case results were found for cause number {case_config.cause_number}."
        )

    click_tab(driver, "Case", pause_after_click, timeout_seconds)
    result_summary = extract_case_search_result(driver, case_config.cause_number, timeout_seconds)
    case_url = open_case_detail(
        driver,
        case_config.cause_number,
        timeout_seconds,
        pause_after_click,
    )
    raw_events = extract_case_events(driver)

    local_scraped_at = datetime.now().astimezone().replace(microsecond=0)
    scraped_date = local_scraped_at.date().isoformat()
    scraped_on = datetime.now(UTC).replace(microsecond=0).isoformat()
    csv_rows: list[dict[str, str]] = []
    for event in raw_events:
        csv_rows.append(
            {
                "cause_number": case_config.cause_number,
                "county": case_config.county,
                "attorney_in_charge": case_config.attorney_in_charge,
                "scraped_date": scraped_date,
                "scraped_on_utc": scraped_on,
                "case_url": case_url,
                "result_tab": "Case",
                "result_count": str(case_hits),
                "styled": result_summary.get("styled", ""),
                "date_filed": result_summary.get("date_filed", ""),
                "status": result_summary.get("status", ""),
                "event_date": event.get("date", ""),
                "event_time": event.get("time", ""),
                "event_name": event.get("event", ""),
                "cancelled_reason": event.get("cancelled_reason", ""),
                "judge": event.get("judge", ""),
                "comments": event.get("comments", ""),
            }
        )

    csv_path = output_dir / f"{sanitize_filename(case_config.cause_number)}.csv"
    return append_new_events(csv_path, csv_rows)


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    cases, case_rows, case_fieldnames = load_case_configs(args.input_csv)
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    selected_cases = [case for case in cases if case.scrape_flag]
    if not selected_cases:
        logging.warning("No cases have scrape_flag=true. Nothing to do.")
        return 0

    driver = build_driver(headful=args.headful)
    any_failures = False

    try:
        for case_config in selected_cases:
            if not supported_county(case_config.county):
                logging.warning(
                    "Skipping cause %s because county '%s' is not supported by this Collin County scraper.",
                    case_config.cause_number,
                    case_config.county,
                )
                continue

            logging.info("Scraping cause number %s", case_config.cause_number)
            try:
                new_count, total_count = scrape_case(
                    driver=driver,
                    case_config=case_config,
                    output_dir=output_dir,
                    timeout_seconds=args.timeout_seconds,
                    pause_after_search=args.pause_after_search,
                    pause_after_click=args.pause_after_click,
                )
                timestamp = datetime.now(UTC).replace(microsecond=0).isoformat()
                update_case_csv_timestamp(case_rows, case_config, timestamp)
                logging.info(
                    "Finished %s: %s new event(s), %s total event row(s) seen.",
                    case_config.cause_number,
                    new_count,
                    total_count,
                )
            except (ScrapeError, TimeoutException) as exc:
                any_failures = True
                logging.error("Failed to scrape %s: %s", case_config.cause_number, exc)
    finally:
        driver.quit()

    write_case_csv(args.input_csv, case_rows, case_fieldnames)
    logging.info("Updated %s with refreshed last_scraped_on values.", args.input_csv)
    return 1 if any_failures else 0


if __name__ == "__main__":
    sys.exit(main())
