from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime
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
    bank_name: str = ''
    account_number: str = ''
    account_holders: str = ''
    beginning_date: str = ''
    ending_date: str = ''


@dataclass
class Row:
    file_path: str
    filename_examined: str
    bank_name: str
    account_number: str
    account_holders: str
    beginning_date: str
    ending_date: str
    bates_number: str
    extraction_method: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Extract first-page metadata from bank statement PDFs.')
    parser.add_argument('source_dir', help='Folder containing bank statement PDFs.')
    parser.add_argument('output_dir', help='Folder to receive the CSV/XLSX outputs.')
    parser.add_argument('--csv-name', default='bank_statement_index.csv')
    parser.add_argument('--xlsx-name', default='bank_statement_index.xlsx')
    parser.add_argument('--bates-regex', default=DEFAULT_BATES_REGEX, help='Matter-specific regex used to identify Bates numbers.')
    return parser.parse_args()


def normalize_lines(text: str) -> list[str]:
    return [re.sub(r'\s+', ' ', line).strip() for line in text.splitlines() if re.sub(r'\s+', ' ', line).strip()]


def parse_month_date(text: str) -> date | None:
    for fmt in ('%B %d, %Y', '%b %d, %Y'):
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


def parse_mmdd(text: str, end_date: date | None) -> date | None:
    if not end_date:
        return None
    match = re.fullmatch(r'(\d{1,2})/(\d{1,2})', text)
    if not match:
        return None
    month, day = int(match.group(1)), int(match.group(2))
    year = end_date.year - 1 if month > end_date.month else end_date.year
    try:
        return date(year, month, day)
    except ValueError:
        return None


def fmt_date(value: date | None) -> str:
    return value.isoformat() if value else ''


def looks_like_street(line: str) -> bool:
    return bool(re.match(r'^\d{1,6}\s+[A-Z0-9]', line))


def clean_holder_lines(lines: list[str]) -> list[str]:
    blocked_prefixes = (
        'WRITE:', 'PHONE:', 'ONLINE:', 'QUESTIONS?', 'PLEASE CONTACT', 'AVAILABLE BY PHONE',
        'P.O. BOX', 'CONCORD,', 'PORTLAND,', 'YOU AND WELLS FARGO', 'YOUR BUSINESS AND WELLS FARGO',
        'ACCOUNT SUMMARY', 'ACCOUNT DETAIL', 'PREVIOUS BALANCE', 'CAPITALONE-BANK', 'CAPITALUNE BANK',
        'MANAGE YOUR CASH', 'NAVIGATE BUSINESS CHECKING', 'PRIVATE BANK INTEREST CHECKING',
        'WELLS FARGO PREFERRED CHECKING', 'SPARK BASIC', 'PP',
    )
    cleaned: list[str] = []
    for line in lines:
        upper = line.upper()
        if any(upper.startswith(prefix) for prefix in blocked_prefixes):
            continue
        if re.search(r'\d', upper) and not re.search(r'LLC|LP|LTD|INC|TRUST|DBA', upper):
            continue
        cleaned.append(line.strip(' ,'))
    return cleaned


def holders_before_street(lines: list[str]) -> str:
    for idx, line in enumerate(lines):
        if looks_like_street(line):
            holders: list[str] = []
            probe = idx - 1
            while probe >= 0:
                candidate = lines[probe]
                upper = candidate.upper()
                if (
                    looks_like_street(candidate)
                    or upper.startswith(('WRITE:', 'ONLINE:', 'PHONE:', 'QUESTIONS?', 'PLEASE CONTACT', 'P.O. BOX'))
                    or upper.endswith('(808)')
                    or upper in {'CONCORD, CA 94524-4056', 'PORTLAND, OR 97228-6995'}
                    or upper.startswith(('WELLS FARGO', 'CAPITAL ONE', 'CAPITALONE'))
                ):
                    break
                holders.insert(0, candidate)
                probe -= 1
            holders = clean_holder_lines(holders)
            if holders:
                return '; '.join(holders)
    return ''


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


def parse_wells_fargo(lines: list[str], pdf_path: Path) -> ParsedFields:
    text = '\n'.join(lines)
    parsed = ParsedFields(bank_name='Wells Fargo')
    parsed.account_holders = holders_before_street(lines)

    end_date = None
    for line in lines[:8]:
        match = re.search(r'([A-Z][a-z]+ \d{1,2}, \d{4})', line)
        if match:
            end_date = parse_month_date(match.group(1))
            break
    if not end_date:
        end_date = file_date(pdf_path)
    parsed.ending_date = fmt_date(end_date)

    acct_match = re.search(r'Account number:\s*([0-9]+)', text, re.IGNORECASE)
    if acct_match:
        parsed.account_number = acct_match.group(1)
    else:
        linked_match = re.search(r'\(\s*([0-9]{4,})\)\s+[\$0-9,.-]+', text)
        if linked_match:
            parsed.account_number = linked_match.group(1)

    begin_match = re.search(r'Beginning balance on\s+(\d{1,2}/\d{1,2})', text, re.IGNORECASE)
    if begin_match:
        parsed.beginning_date = fmt_date(parse_mmdd(begin_match.group(1), end_date))

    end_balance_match = re.search(r'Ending balance on\s+(\d{1,2}/\d{1,2})', text, re.IGNORECASE)
    if end_balance_match:
        parsed_end = parse_mmdd(end_balance_match.group(1), end_date)
        if parsed_end:
            parsed.ending_date = fmt_date(parsed_end)

    return parsed


def parse_capital_one(lines: list[str], pdf_path: Path) -> ParsedFields:
    text = '\n'.join(lines)
    parsed = ParsedFields(bank_name='Capital One Bank')
    parsed.account_holders = holders_before_street(lines)

    for pattern in (
        r'(?:Spark\s+Basic\s+[^\n]{0,40}?)([0-9]{6,})',
        r'Account\s+number\s*[:#]?\s*([0-9]{6,})',
        r'(?:Checking|Savings|Money Market)\s+([0-9]{6,})',
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            parsed.account_number = match.group(1)
            break

    end_match = re.search(r'Ending Balance\s+(\d{2}/\d{2}/\d{2})', text, re.IGNORECASE)
    file_end = file_date(pdf_path)
    if end_match:
        parsed.ending_date = datetime.strptime(end_match.group(1), '%m/%d/%y').date().isoformat()
    elif file_end:
        parsed.ending_date = file_end.isoformat()

    for idx, line in enumerate(lines):
        if 'ACCOUNT SUMMARY' in line.upper() or 'ACCOUNT DETAIL' in line.upper():
            summary_block = ' '.join(lines[idx: idx + 10]).upper()
            date_match = re.search(r'([A-Z]+ \d{2}, \d{4})\s*-\s*([A-Z]+ \d{2}, \d{4})', summary_block)
            if date_match:
                parsed.beginning_date = fmt_date(parse_month_date(date_match.group(1).title()))
                parsed.ending_date = fmt_date(parse_month_date(date_match.group(2).title())) or parsed.ending_date
                break

    if not parsed.beginning_date and parsed.ending_date:
        end_date_obj = datetime.strptime(parsed.ending_date, '%Y-%m-%d').date()
        parsed.beginning_date = date(end_date_obj.year, end_date_obj.month, 1).isoformat()

    return parsed


def parse_generic(lines: list[str], pdf_path: Path) -> ParsedFields:
    text = '\n'.join(lines).lower()
    folder = pdf_path.parent.name.lower()
    if 'capital one' in text or 'capital one' in folder or 'capitalone' in text:
        return parse_capital_one(lines, pdf_path)
    return parse_wells_fargo(lines, pdf_path)


def merge_missing(base: ParsedFields, extra: ParsedFields) -> ParsedFields:
    return ParsedFields(
        bank_name=base.bank_name or extra.bank_name,
        account_number=base.account_number or extra.account_number,
        account_holders=base.account_holders or extra.account_holders,
        beginning_date=base.beginning_date or extra.beginning_date,
        ending_date=base.ending_date or extra.ending_date,
    )


def needs_second_page(parsed: ParsedFields) -> bool:
    return not all([parsed.account_number, parsed.account_holders, parsed.beginning_date, parsed.ending_date])


def write_outputs(rows: list[Row], csv_path: Path, xlsx_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = 'Bank Statements'
    headers = [
        'File Path', 'Filename Examined', 'Bank Name', 'Account Number', 'Account Holder(s) Name(s)',
        'Beginning Date of the Statement', 'Ending Date of the Statement', 'Bates Number', 'Extraction Method',
    ]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append([
            row.file_path, row.filename_examined, row.bank_name, row.account_number, row.account_holders,
            row.beginning_date, row.ending_date, row.bates_number, row.extraction_method,
        ])
    widths = [78, 42, 20, 22, 34, 24, 24, 18, 18]
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + idx)].width = width
    wb.save(xlsx_path)

    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([
                row.file_path, row.filename_examined, row.bank_name, row.account_number, row.account_holders,
                row.beginning_date, row.ending_date, row.bates_number, row.extraction_method,
            ])


def main() -> int:
    args = parse_args()
    source_dir = Path(args.source_dir)
    output_dir = Path(args.output_dir)
    bates_re = re.compile(args.bates_regex)
    tmp_dir = output_dir / 'tmp_bank_ocr'
    csv_path = output_dir / args.csv_name
    xlsx_path = output_dir / args.xlsx_name

    pdfs = sorted(source_dir.rglob('*.pdf'))
    rows: list[Row] = []
    for pdf_path in pdfs:
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

        rows.append(
            Row(
                file_path=str(pdf_path),
                filename_examined=pdf_path.name,
                bank_name=parsed.bank_name,
                account_number=parsed.account_number,
                account_holders=parsed.account_holders,
                beginning_date=parsed.beginning_date,
                ending_date=parsed.ending_date,
                bates_number=find_bates(combined_text, pdf_path, bates_re),
                extraction_method='+'.join(sorted(methods)),
            )
        )

    write_outputs(rows, csv_path, xlsx_path)
    print(f'Processed {len(rows)} PDFs')
    print(f'CSV: {csv_path}')
    print(f'XLSX: {xlsx_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
