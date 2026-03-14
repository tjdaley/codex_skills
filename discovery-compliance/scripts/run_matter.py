from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BANK_SCRIPT = SCRIPT_DIR / 'extract_bank_statements.py'
CREDIT_SCRIPT = SCRIPT_DIR / 'extract_credit_card_statements.py'
MATRIX_SCRIPT = SCRIPT_DIR / 'generate_compliance_matrices.py'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Run the discovery compliance workflow in extraction or matrix mode.'
    )
    parser.add_argument('--phase', choices=['extract', 'matrices', 'all'], default='extract')
    parser.add_argument('--bank-folder', help='Folder containing bank statement PDFs.')
    parser.add_argument('--credit-folder', help='Folder containing credit card statement PDFs.')
    parser.add_argument('--output-dir', required=True, help='Folder for extracted indexes and matrices.')
    parser.add_argument('--bates-regex', help='Matter-specific Bates regex. Required for extract/all.')
    parser.add_argument('--year-start', type=int, default=2020)
    parser.add_argument('--year-end', type=int, default=2026)
    parser.add_argument('--bank-csv-name', default='bank_statement_index.csv')
    parser.add_argument('--credit-csv-name', default='credit_card_statement_index.csv')
    parser.add_argument('--bank-xlsx-name', default='bank_statement_index.xlsx')
    parser.add_argument('--credit-xlsx-name', default='credit_card_statement_index.xlsx')
    return parser.parse_args()


def run_step(args: list[str]) -> None:
    subprocess.run([sys.executable, *args], check=True)


def do_extract(args: argparse.Namespace, output_dir: Path) -> None:
    if not args.bates_regex:
        raise SystemExit('--bates-regex is required for extract/all phase.')
    if not args.bank_folder and not args.credit_folder:
        raise SystemExit('Provide --bank-folder, --credit-folder, or both for extract/all phase.')

    if args.bank_folder:
        bank_out = output_dir / 'bank'
        bank_out.mkdir(parents=True, exist_ok=True)
        run_step([
            str(BANK_SCRIPT),
            args.bank_folder,
            str(bank_out),
            '--csv-name',
            args.bank_csv_name,
            '--xlsx-name',
            args.bank_xlsx_name,
            '--bates-regex',
            args.bates_regex,
        ])
    if args.credit_folder:
        credit_out = output_dir / 'credit'
        credit_out.mkdir(parents=True, exist_ok=True)
        run_step([
            str(CREDIT_SCRIPT),
            args.credit_folder,
            str(credit_out),
            '--csv-name',
            args.credit_csv_name,
            '--xlsx-name',
            args.credit_xlsx_name,
            '--bates-regex',
            args.bates_regex,
        ])


def do_matrices(args: argparse.Namespace, output_dir: Path) -> None:
    bank_csv = output_dir / 'bank' / args.bank_csv_name
    credit_csv = output_dir / 'credit' / args.credit_csv_name
    if not bank_csv.exists() and not credit_csv.exists():
        raise SystemExit('No extracted CSVs found under output folder. Run extract first.')
    if not bank_csv.exists():
        raise SystemExit(f'Missing bank CSV: {bank_csv}')
    if not credit_csv.exists():
        raise SystemExit(f'Missing credit CSV: {credit_csv}')

    run_step([
        str(MATRIX_SCRIPT),
        str(bank_csv),
        str(credit_csv),
        str(output_dir),
        '--year-start',
        str(args.year_start),
        '--year-end',
        str(args.year_end),
    ])


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.phase == 'extract':
        do_extract(args, output_dir)
        print('Extraction complete. Review and clean the CSVs, then rerun with --phase matrices.')
        return 0

    if args.phase == 'matrices':
        do_matrices(args, output_dir)
        print('Compliance matrices complete.')
        return 0

    do_extract(args, output_dir)
    print('Extraction complete. Review and clean the CSVs before continuing to matrices.')
    print('Rerun this command with --phase matrices after cleanup.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
