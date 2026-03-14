from __future__ import annotations

import argparse
import csv
import re
import subprocess
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import fitz  # type: ignore
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from pypdf import PdfReader
except ImportError as exc:
    raise SystemExit(
        'Missing dependency: ' + str(exc) + '. Install with: '
        'python -m pip install pypdf openpyxl pymupdf pillow'
    )

DEFAULT_BATES_REGEX = r'JF0+\d{4}'
OCR_SCRIPT = Path(__file__).with_name('ocr_image.ps1')


@dataclass
class ParsedFields:
    issuer: str = ''
    account_number: str = ''
    account_holders: str = ''
    beginning_date: str = ''
    ending_date: str = ''


@dataclass
class Row:
    file_path: str
    filename_examined: str
    issuer: str
    account_number: str
    account_holders: str
    beginning_date: str
    ending_date: str
    bates_number: str
    extraction_method: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Extract first-page metadata from credit card statement PDFs.')
    parser.add_argument('source_dir', help='Folder containing credit card statement PDFs.')
    parser.add_argument('output_dir', help='Folder to receive the CSV/XLSX outputs.')
    parser.add_argument('--csv-name', default='credit_card_statement_index.csv')
    parser.add_argument('--xlsx-name', default='credit_card_statement_index.xlsx')
    parser.add_argument('--bates-regex', default=DEFAULT_BATES_REGEX, help='Matter-specific regex used to identify Bates numbers.')
    return parser.parse_args()


def normalize_lines(text: str) -> list[str]:
    return [re.sub(r'\s+', ' ', line).strip() for line in text.splitlines() if re.sub(r'\s+', ' ', line).strip()]


def parse_mmddyy(text: str) -> date | None:
    for fmt in ('%m/%d/%y', '%m/%d/%Y'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def file_date(pdf_path: Path) -> date | None:
    match = re.search(r'(\d{4})\.(\d{2})\.(\d{2})', pdf_path.name)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def fmt_date(value: date | None) -> str:
    return value.isoformat() if value else ''


def dedupe_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.upper()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def flat_text(lines: list[str]) -> str:
    return ' '.join(lines)


def clean_holder_lines(lines: list[str]) -> list[str]:
    blocked_prefixes = (
        'P.O. BOX', 'PO BOX', 'PAYMENT COUPON', 'ACCOUNT SUMMARY', 'CUSTOMER SERVICE', 'ACCOUNT NUMBER',
        'PAYMENT DUE DATE', 'NEW BALANCE', 'MINIMUM PAYMENT', 'AMERICAN EXPRESS', 'CITIBUSINESS CARD',
        'CARDMEMBER SERVICE', 'CHASE CARD SERVICES', 'MANAGE YOUR ACCOUNT', 'MAKE YOUR PAYMENT',
        'PREVIOUS BALANCE', 'OPENING/CLOSING DATE', 'BUSINESS PLATINUM CARD', 'CREDIT CARD STATEMENT',
        'YOUR MONTHLY STATEMENT', 'JANUARY STATEMENT', 'FEBRUARY STATEMENT', 'MARCH STATEMENT',
        'APRIL STATEMENT', 'MAY STATEMENT', 'JUNE STATEMENT', 'JULY STATEMENT', 'AUGUST STATEMENT',
        'SEPTEMBER STATEMENT', 'OCTOBER STATEMENT', 'NOVEMBER STATEMENT', 'DECEMBER STATEMENT',
        'PRODUCTS AND SERVICES ARE OFFERED', 'WITH THESE DIGITAL TOOLS', 'WHY NOT TRY PAPERLESS',
        'USE THIS COUPON', 'PAYMENT DUE DATE', 'MINIMUM PAYMENT DUE', 'NEW BALANCE', 'AMOUNT ENCLOSED', 'FIS',
    )
    cleaned: list[str] = []
    for line in lines:
        upper = line.upper()
        if any(upper.startswith(prefix) for prefix in blocked_prefixes):
            continue
        if upper in {'JF', 'PAGE 1 OF 3', 'PAGE 1 OF 4'}:
            continue
        if re.search(r'\d', upper) and not re.search(r'LLC|LP|LTD|INC|TRUST|DBA', upper):
            continue
        cleaned.append(line.strip(' ,'))
    return dedupe_preserve(cleaned)


def holders_from_lines(lines: list[str]) -> str:
    for idx in range(len(lines) - 1):
        if re.match(r'^\d{1,6}\s+[A-Z0-9 ]+$', lines[idx]) and re.match(r'^[A-Z .]+\s+[A-Z]{2}\s+\d{5}(?:-\d{4})?$', lines[idx + 1]):
            holders: list[str] = []
            probe = idx - 1
            while probe >= 0 and len(holders) < 3:
                line = lines[probe].strip()
                if re.search(r'\d', line):
                    break
                if len(line) > 35 or line.upper() != line:
                    break
                holders.insert(0, line)
                probe -= 1
            cleaned = clean_holder_lines(holders)
            if cleaned:
                return '; '.join(cleaned)
    return ''


def holders_from_amex(flat: str) -> str:
    address_match = re.search(r'(\d{1,6}\s+[A-Z0-9 ]+?\s+[A-Z]{2}\s+\d{5}(?:-\d{4})?)', flat)
    if not address_match:
        return ''
    pre = re.sub(r'\s+', ' ', flat[max(0, address_match.start() - 120):address_match.start()])
    candidates: list[tuple[int, str]] = []
    for match in re.finditer(r'\b[A-Z]{2,}\s+[A-Z]\s+[A-Z]{2,}\b', pre):
        candidates.append((match.start(), match.group(0)))
    remainder = re.sub(r'\b[A-Z]{2,}\s+[A-Z]\s+[A-Z]{2,}\b', ' ', pre)
    remainder = re.sub(r'\b(?:PAYMENT|DUE|DATE|MINIMUM|NEW|BALANCE|ACCOUNT|SUMMARY|AMOUNT|ENCLOSED)\b', ' ', remainder)
    remainder = re.sub(r'\s+', ' ', remainder).strip()
    words = [word for word in remainder.split() if word.isalpha() and len(word) <= 15]
    if len(words) >= 2:
        if len(words) % 2 == 0 and words[: len(words) // 2] == words[len(words) // 2:] and 1 < len(words) // 2 <= 3:
            candidates.append((999, ' '.join(words[: len(words) // 2])))
        elif 1 < len(words) <= 3:
            candidates.append((999, ' '.join(words)))
    ordered = [item for _, item in sorted(candidates, key=lambda x: x[0])]
    cleaned = clean_holder_lines(ordered)
    if 'VINSON' in address_match.group(1) and 'FERETT PATH' in pre:
        person = next((item for item in cleaned if 'FIELD' in item), '')
        names = ['FERETT PATH']
        if person:
            names.append(person)
        return '; '.join(dedupe_preserve(names))
    if 'MONTICELLO' in address_match.group(1):
        person = next((item for item in cleaned if 'FIELD' in item), '')
        if person:
            return person
    return '; '.join(dedupe_preserve(cleaned)) if cleaned else ''


def holders_from_flat(flat: str) -> str:
    address_match = re.search(r'(\d{1,6}\s+[A-Z0-9 ]+?\s+[A-Z]{2}\s+\d{5}(?:-\d{4})?)', flat)
    if not address_match:
        return ''
    pre = flat[max(0, address_match.start() - 120):address_match.start()]
    pre = re.sub(r'\b(?:PAYMENT DUE DATE|MINIMUM PAYMENT DUE|NEW BALANCE|ACCOUNT SUMMARY|AMOUNT ENCLOSED|USE THIS COUPON|MEMBER SINCE|BILLING PERIOD|PAYMENT COUPON)\b', ' ', pre)
    pre = re.sub(r'\d[\d/$.,:-]*', ' ', pre)
    pre = re.sub(r'\s+', ' ', pre).strip()
    candidates: list[str] = []
    for match in re.finditer(r'\b[A-Z][A-Z&.]+(?:\s+[A-Z][A-Z&.]+){0,4}', pre):
        candidates.append(match.group(0))
    cleaned = clean_holder_lines(candidates)
    return '; '.join(dedupe_preserve(cleaned)) if cleaned else ''


def find_bates(text: str, pdf_path: Path, bates_re: re.Pattern[str]) -> str:
    match = bates_re.search(text)
    if match:
        return match.group(0)
    name_match = re.match(r'(\d{6})-', pdf_path.name)
    if name_match:
        return f'JF{name_match.group(1)}'
    return ''


def render_page(pdf_path: Path, page_index: int, image_path: Path) -> None:
    doc = fitz.open(pdf_path)
    try:
        pix = doc[page_index].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        pix.save(image_path)
    finally:
        doc.close()


def ocr_lines(image_path: Path) -> list[str]:
    proc = subprocess.run(
        ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(OCR_SCRIPT), str(image_path)],
        check=True,
        capture_output=True,
        text=True,
        encoding='utf-8',
    )
    return normalize_lines(proc.stdout)


def read_page(reader: PdfReader, pdf_path: Path, page_index: int, tmp_dir: Path) -> tuple[list[str], str]:
    text = reader.pages[page_index].extract_text() or ''
    lines = normalize_lines(text)
    joined = '\n'.join(lines)
    if len(joined) >= 200 and not (joined.strip().startswith('JF0') and len(lines) <= 2):
        return lines, 'pdf-text'

    tmp_dir.mkdir(parents=True, exist_ok=True)
    image_path = tmp_dir / f'{pdf_path.stem}_page{page_index + 1}.png'
    render_page(pdf_path, page_index, image_path)
    return ocr_lines(image_path), 'ocr'


def parse_amex(lines: list[str], pdf_path: Path) -> ParsedFields:
    flat = flat_text(lines)
    parsed = ParsedFields(issuer='American Express')
    parsed.account_holders = holders_from_amex(flat) or holders_from_flat(flat)

    match = re.search(r'Account Ending\s+([0-9-]+)', flat, re.IGNORECASE)
    if match:
        parsed.account_number = match.group(1)
    else:
        tail_match = re.search(r'x(\d{4,5})', pdf_path.name, re.IGNORECASE)
        if tail_match:
            parsed.account_number = tail_match.group(1)

    close_match = re.search(r'Closing Date\s+(\d{2}/\d{2}/\d{2})', flat, re.IGNORECASE)
    days_match = re.search(r'Days in Billing Period:?\s*(\d+)', flat, re.IGNORECASE)
    close_date = parse_mmddyy(close_match.group(1)) if close_match else file_date(pdf_path)
    if close_date:
        parsed.ending_date = close_date.isoformat()
        if days_match:
            parsed.beginning_date = (close_date - timedelta(days=int(days_match.group(1)) - 1)).isoformat()
    return parsed


def parse_chase(lines: list[str], pdf_path: Path) -> ParsedFields:
    flat = flat_text(lines)
    parsed = ParsedFields(issuer='Chase')
    parsed.account_holders = holders_from_lines(lines) or holders_from_flat(flat)

    match = re.search(r'Account Number:\s*([0-9 ]{12,25})', flat, re.IGNORECASE)
    if match:
        parsed.account_number = re.sub(r'\s+', ' ', match.group(1)).strip()
    date_match = re.search(r'Opening/Closing Date\s+(\d{2}/\d{2}/\d{2})\s*-\s*(\d{2}/\d{2}/\d{2})', flat, re.IGNORECASE)
    if date_match:
        parsed.beginning_date = fmt_date(parse_mmddyy(date_match.group(1)))
        parsed.ending_date = fmt_date(parse_mmddyy(date_match.group(2)))
    elif file_date(pdf_path):
        parsed.ending_date = file_date(pdf_path).isoformat()
    return parsed


def parse_citi(lines: list[str], pdf_path: Path) -> ParsedFields:
    flat = flat_text(lines)
    parsed = ParsedFields(issuer='Citi')
    parsed.account_holders = holders_from_lines(lines) or holders_from_flat(flat)

    match = re.search(r'Account number ending in(?::)?\s*(\d{4})', flat, re.IGNORECASE)
    if match:
        parsed.account_number = match.group(1)
    date_match = re.search(r'Billing Period:.*?(\d{2}/\d{2}/\d{2})\s*-\s*(\d{2}/\d{2}/\d{2})', flat, re.IGNORECASE)
    if date_match:
        parsed.beginning_date = fmt_date(parse_mmddyy(date_match.group(1)))
        parsed.ending_date = fmt_date(parse_mmddyy(date_match.group(2)))
    elif file_date(pdf_path):
        parsed.ending_date = file_date(pdf_path).isoformat()
    return parsed


def parse_generic(lines: list[str], pdf_path: Path) -> ParsedFields:
    folder = pdf_path.parent.name.lower()
    if 'amex' in folder:
        return parse_amex(lines, pdf_path)
    if 'chase' in folder:
        return parse_chase(lines, pdf_path)
    return parse_citi(lines, pdf_path)


def merge_missing(base: ParsedFields, extra: ParsedFields) -> ParsedFields:
    return ParsedFields(
        issuer=base.issuer or extra.issuer,
        account_number=base.account_number or extra.account_number,
        account_holders=base.account_holders or extra.account_holders,
        beginning_date=base.beginning_date or extra.beginning_date,
        ending_date=base.ending_date or extra.ending_date,
    )


def needs_second_page(parsed: ParsedFields) -> bool:
    return not all([parsed.issuer, parsed.account_number, parsed.account_holders, parsed.beginning_date, parsed.ending_date])


def normalize_rows(rows: list[Row]) -> None:
    blocked_holder_bits = ('DUE PAYMENT DUE DATE', 'PAYMENT DUE DATE', 'BALANCE PAYMENT', 'FIS')

    def holder_invalid(value: str) -> bool:
        upper = value.upper()
        return (not value) or any(bit in upper for bit in blocked_holder_bits)

    grouped: dict[tuple[str, str], list[Row]] = {}
    for row in rows:
        grouped.setdefault((row.issuer, row.account_number), []).append(row)

    for group in grouped.values():
        valid_holders = [row.account_holders for row in group if not holder_invalid(row.account_holders)]
        fallback_holder = valid_holders[0] if valid_holders else ''
        for row in group:
            if holder_invalid(row.account_holders) and fallback_holder:
                row.account_holders = fallback_holder

        sortable = []
        for row in group:
            if row.ending_date:
                try:
                    sortable.append((datetime.strptime(row.ending_date, '%Y-%m-%d').date(), row))
                except ValueError:
                    pass
        sortable.sort(key=lambda item: item[0])
        prev_end = None
        for end_date, row in sortable:
            if not row.beginning_date and prev_end is not None and end_date >= prev_end:
                row.beginning_date = (prev_end + timedelta(days=1)).isoformat()
            prev_end = end_date


def write_outputs(rows: list[Row], csv_path: Path, xlsx_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Credit Card Statements'
    headers = [
        'File Path', 'Filename Examined', 'Credit Card Issuer', 'Account Number', 'Account Holder(s) Name(s)',
        'Beginning Date of the Statement', 'Ending Date of the Statement', 'Bates Number', 'Extraction Method',
    ]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append([
            row.file_path, row.filename_examined, row.issuer, row.account_number, row.account_holders,
            row.beginning_date, row.ending_date, row.bates_number, row.extraction_method,
        ])
    widths = [78, 46, 24, 24, 34, 24, 24, 18, 18]
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + idx)].width = width
    wb.save(xlsx_path)

    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([
                row.file_path, row.filename_examined, row.issuer, row.account_number, row.account_holders,
                row.beginning_date, row.ending_date, row.bates_number, row.extraction_method,
            ])


def main() -> int:
    args = parse_args()
    source_dir = Path(args.source_dir)
    output_dir = Path(args.output_dir)
    bates_re = re.compile(args.bates_regex)
    tmp_dir = output_dir / 'tmp_cc_ocr'
    csv_path = output_dir / args.csv_name
    xlsx_path = output_dir / args.xlsx_name

    rows: list[Row] = []
    for pdf_path in sorted(source_dir.rglob('*.pdf')):
        reader = PdfReader(str(pdf_path))
        page1_lines, method1 = read_page(reader, pdf_path, 0, tmp_dir)
        parsed = parse_generic(page1_lines, pdf_path)
        methods = {method1}
        combined_text = '\n'.join(page1_lines)

        if needs_second_page(parsed) and len(reader.pages) > 1:
            page2_lines, method2 = read_page(reader, pdf_path, 1, tmp_dir)
            parsed = merge_missing(parsed, parse_generic(page2_lines, pdf_path))
            methods.add(method2)
            combined_text += '\n' + '\n'.join(page2_lines)

        if not parsed.account_number:
            tail_match = re.search(r'x(\d{4,5})', pdf_path.name, re.IGNORECASE)
            if tail_match:
                parsed.account_number = tail_match.group(1)

        rows.append(
            Row(
                file_path=str(pdf_path),
                filename_examined=pdf_path.name,
                issuer=parsed.issuer,
                account_number=parsed.account_number,
                account_holders=parsed.account_holders,
                beginning_date=parsed.beginning_date,
                ending_date=parsed.ending_date,
                bates_number=find_bates(combined_text, pdf_path, bates_re),
                extraction_method='+'.join(sorted(methods)),
            )
        )

    normalize_rows(rows)
    write_outputs(rows, csv_path, xlsx_path)
    print(f'Processed {len(rows)} PDFs')
    print(f'CSV: {csv_path}')
    print(f'XLSX: {xlsx_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
