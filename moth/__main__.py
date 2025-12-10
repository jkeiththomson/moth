from __future__ import annotations

import argparse
from pathlib import Path


# ---------------------------------------------------------------------------
# Core stub functions (no internal logic yet)
# ---------------------------------------------------------------------------


def extract(input_pdf: Path, output_csv: Path) -> None:
    """
    Stub: extract transactions from a statement PDF into a CSV.

    Expected behavior (later, when implemented):

    - Read the bank/credit-card statement PDF.
    - Parse every transaction (date, description, amount).
    - Write a flat CSV file with one transaction per row.
    - Count deposits and withdrawals and sum their amounts.

    For now, this function only prints what it *would* do.
    """
    print("[EXTRACT] stub running...")
    print(f"[EXTRACT] Would read PDF: {input_pdf}")
    print(f"[EXTRACT] Would write CSV: {output_csv}")
    print("[EXTRACT] Would also count deposits / withdrawals and sum amounts.")


def categorize(input_csv: Path, categories_file: Path) -> None:
    """
    Stub: assign categories to each transaction.

    Expected behavior (later, when implemented):

    - Load transactions from the extracted CSV.
    - Assign a category to each transaction.
    - Persist category assignments so they survive quitting/restarting,
      using the categories_file for storage.

    For now, this function only prints what it *would* do.
    """
    print("[CATEGORIZE] stub running...")
    print(f"[CATEGORIZE] Would read transactions from: {input_csv}")
    print(f"[CATEGORIZE] Would load & update categories in: {categories_file}")
    print("[CATEGORIZE] Category assignments would persist across runs.")


def export(input_csv: Path, categories_file: Path, report_file: Path) -> None:
    """
    Stub: export results and write a summary report.

    Expected behavior (later, when implemented):

    - Combine transaction data with category assignments.
    - Write out any updated, categorized data as needed.
    - Persist updated category definitions.
    - Generate a human-readable report summarizing what was done.

    For now, this function only prints what it *would* do.
    """
    print("[EXPORT] stub running...")
    print(f"[EXPORT] Would read categorized data from: {input_csv}")
    print(f"[EXPORT] Would persist categories in: {categories_file}")
    print(f"[EXPORT] Would write report to: {report_file}")


# ---------------------------------------------------------------------------
# Meta function / CLI dispatcher
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    """
    Meta function that exposes the three commands:

    - extract
    - categorize
    - export

    Each command is currently a stub with no real internal logic.
    """
    parser = argparse.ArgumentParser(
        prog="moth",
        description="moth pipeline: extract → categorize → export (stubs only)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # extract
    p_extract = subparsers.add_parser(
        "extract",
        help="Read a statement PDF and write an extracted CSV (stub).",
    )
    p_extract.add_argument("pdf", help="Path to input PDF statement.")
    p_extract.add_argument(
        "csv_out",
        help="Path to output CSV file (dates, descriptions, amounts).",
    )

    # categorize
    p_categorize = subparsers.add_parser(
        "categorize",
        help="Assign categories to transactions (stub).",
    )
    p_categorize.add_argument(
        "input_csv",
        help="Path to extracted transactions CSV.",
    )
    p_categorize.add_argument(
        "categories_file",
        help="Path to category storage file (persists across runs).",
    )

    # export
    p_export = subparsers.add_parser(
        "export",
        help="Export results and write a summary report (stub).",
    )
    p_export.add_argument(
        "input_csv",
        help="Path to categorized transactions CSV (or same as extracted).",
    )
    p_export.add_argument(
        "categories_file",
        help="Path to category storage file (same as used for categorize).",
    )
    p_export.add_argument(
        "report_file",
        help="Path to summary report output file.",
    )

    args = parser.parse_args(argv)
    command = args.command

    if command == "extract":
        extract(
            input_pdf=Path(args.pdf),
            output_csv=Path(args.csv_out),
        )
    elif command == "categorize":
        categorize(
            input_csv=Path(args.input_csv),
            categories_file=Path(args.categories_file),
        )
    elif command == "export":
        export(
            input_csv=Path(args.input_csv),
            categories_file=Path(args.categories_file),
            report_file=Path(args.report_file),
        )
    else:
        parser.error(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
