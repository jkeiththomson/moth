from __future__ import annotations

import argparse
from pathlib import Path
import csv


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def extract(input_pdf: Path, output_csv: Path) -> None:
    """
    Stub: extract transactions from a statement PDF into a CSV.

    Expected behavior (later, when implemented):

    - Read the bank/credit-card statement PDF.
    - Parse every transaction (statement_date, date, description, amount).
    - Write a flat CSV file with one transaction per row.
    - Count deposits and withdrawals and sum their amounts.

    For now, this function only prints what it *would* do.
    """
    print("[EXTRACT] stub running...")
    print(f"[EXTRACT] Would read PDF: {input_pdf}")
    print(f"[EXTRACT] Would write CSV: {output_csv}")
    print("[EXTRACT] Would also compute deposits/withdrawals and totals.")
    print("[EXTRACT] CSV schema would include: "
          "statement_date, date, description, amount, category")


# ---------------------------------------------------------------------------
# Category persistence helpers
# ---------------------------------------------------------------------------


def _load_category_map(categories_file: Path) -> dict[str, str]:
    """Load a description→category mapping from a CSV file, if it exists.

    The expected format is:

        description,category
        "SAFEWAY",Groceries
        "CHEVRON",Fuel
    """
    mapping: dict[str, str] = {}
    if not categories_file.exists():
        return mapping

    with categories_file.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        if "description" not in fieldnames or "category" not in fieldnames:
            print(
                f"[CATEGORIZE] Warning: {categories_file} does not have "
                "'description' and 'category' columns; ignoring existing data."
            )
            return mapping

        for row in reader:
            desc = (row.get("description") or "").strip()
            cat = (row.get("category") or "").strip()
            if desc and cat:
                mapping[desc] = cat

    return mapping


def _save_category_map(categories_file: Path, mapping: dict[str, str]) -> None:
    """Persist the description→category mapping to a CSV file."""
    categories_file.parent.mkdir(parents=True, exist_ok=True)
    with categories_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["description", "category"])
        for desc in sorted(mapping):
            writer.writerow([desc, mapping[desc]])


# ---------------------------------------------------------------------------
# Categorize: persistent category system with statement_date support
# ---------------------------------------------------------------------------


def categorize(input_csv: Path, categories_file: Path) -> None:
    """Assign categories to each transaction and persist the rules.

    Simple rule-based persistent category system:

    - Transactions are read from ``input_csv`` (a CSV file).
    - Categories are stored in ``categories_file`` as description→category rules.
    - For each row:
      * If ``category`` is already set, that value is kept and the rule
        is stored/updated in ``categories_file``.
      * If ``category`` is empty but we have a rule for this description,
        the category is filled in from the rule.
      * If there is no rule and no category, the category is left blank.

    Required columns in ``input_csv``:

        statement_date, date, description, amount

    Effect:
    - Category assignments survive quitting and restarting the app.
    - Editing categories directly in the CSV and re-running ``categorize``
      will update the persistent rule set.
    """

    if not input_csv.exists():
        print(f"[CATEGORIZE] ERROR: transactions CSV not found: {input_csv}")
        return

    with input_csv.open(newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    required_cols = ["statement_date", "date", "description", "amount"]
    missing = [c for c in required_cols if c not in fieldnames]

    if missing:
        print(
            "[CATEGORIZE] ERROR: input CSV must have columns: "
            + ", ".join(required_cols)
        )
        print("[CATEGORIZE] Missing:", ", ".join(missing))
        return

    if "category" not in fieldnames:
        fieldnames.append("category")

    category_map = _load_category_map(categories_file)

    auto_assigned = 0
    already_categorized = 0
    uncategorized = 0

    updated_rows: list[dict[str, str]] = []

    for row in rows:
        desc = (row.get("description") or "").strip()
        cat = (row.get("category") or "").strip()

        if not desc:
            updated_rows.append(row)
            continue

        if cat:
            # Row already has a category; learn or update the rule.
            if category_map.get(desc) != cat:
                category_map[desc] = cat
            already_categorized += 1
        else:
            # No category yet; try to apply a rule.
            rule_cat = category_map.get(desc)
            if rule_cat:
                row["category"] = rule_cat
                auto_assigned += 1
            else:
                uncategorized += 1

        updated_rows.append(row)

    # Write updated transactions back to the same CSV.
    with input_csv.open("w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        for row in updated_rows:
            writer.writerow(row)

    # Persist updated category rules.
    _save_category_map(categories_file, category_map)

    print("[CATEGORIZE] Done.")
    print(f"[CATEGORIZE] Already categorized rows : {already_categorized}")
    print(f"[CATEGORIZE] Auto-assigned via rules : {auto_assigned}")
    print(f"[CATEGORIZE] Still uncategorized     : {uncategorized}")
    print(f"[CATEGORIZE] Rules saved to          : {categories_file}")


# ---------------------------------------------------------------------------
# Export: simple summary report
# ---------------------------------------------------------------------------


def export(input_csv: Path, categories_file: Path, report_file: Path) -> None:
    """Export a simple text report based on the categorized CSV.

    Current behavior:

    - Reads ``input_csv`` (must have at least 'category' and 'amount' columns).
    - Computes, per category:
        * number of transactions
        * total amount (sum of 'amount')
    - Writes a plain-text report to ``report_file`` summarizing these totals.

    ``statement_date`` is preserved in the CSV but not yet used for grouping.
    """

    if not input_csv.exists():
        print(f"[EXPORT] ERROR: input CSV not found: {input_csv}")
        return

    with input_csv.open(newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        fieldnames = reader.fieldnames or []

        if "amount" not in fieldnames:
            print("[EXPORT] ERROR: input CSV must have an 'amount' column.")
            return

        has_category = "category" in fieldnames

        totals: dict[str, float] = {}
        counts: dict[str, int] = {}
        total_rows = 0

        for row in reader:
            total_rows += 1
            raw_cat = (row.get("category") or "").strip() if has_category else ""
            category = raw_cat or "Uncategorized"

            raw_amount = (row.get("amount") or "").replace(",", "").strip()
            try:
                amount = float(raw_amount)
            except (TypeError, ValueError):
                amount = 0.0

            totals[category] = totals.get(category, 0.0) + amount
            counts[category] = counts.get(category, 0) + 1

    report_file.parent.mkdir(parents=True, exist_ok=True)
    with report_file.open("w", encoding="utf-8") as f_out:
        f_out.write(f"Report for: {input_csv}\n")
        f_out.write(f"Categories file: {categories_file}\n")
        f_out.write(f"Total rows: {total_rows}\n")
        f_out.write("\n")
        f_out.write("Category, Count, Total Amount\n")
        for category in sorted(totals):
            f_out.write(
                f"{category}, {counts[category]}, {totals[category]:.2f}\n"
            )

    print("[EXPORT] Report written to:", report_file)


# ---------------------------------------------------------------------------
# Meta function / CLI dispatcher
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    """Meta function that exposes the three commands:

    - extract
    - categorize
    - export
    """
    parser = argparse.ArgumentParser(
        prog="moth",
        description="moth pipeline: extract → categorize → export",
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
        help="Assign categories to transactions and persist rules.",
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
        help="Export a simple summary report.",
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
