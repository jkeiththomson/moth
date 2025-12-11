from __future__ import annotations

import argparse
from pathlib import Path
import csv

from .extractors import extract_chase_activity


def _derived_extracted_csv_path(input_pdf: Path) -> Path:
    """Return <pdf_dir>/<pdf_stem>-extracted.csv for a given PDF."""
    input_pdf = input_pdf.resolve()
    return input_pdf.with_name(f"{input_pdf.stem}-extracted.csv")


def extract(input_pdf: Path) -> Path:
    """
    Extract transactions from a statement PDF into a CSV.

    Output file is always:
        <same directory>/<pdf_stem>-extracted.csv
    """
    input_pdf = input_pdf.resolve()
    out_csv = _derived_extracted_csv_path(input_pdf)

    print("[EXTRACT] Using Chase-style extractor (Monarch-derived).")
    print("[EXTRACT] Input PDF : ", input_pdf)
    print("[EXTRACT] Output CSV: ", out_csv)

    extract_chase_activity(input_pdf, out_csv)
    return out_csv


def _load_group_category_master(master_path: Path) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Load and validate the master group/category mapping."""
    group_to_categories: dict[str, set[str]] = {}
    category_to_groups: dict[str, set[str]] = {}

    if not master_path.exists():
        print("[GROUPS] Warning: master categories file not found:", master_path)
        return group_to_categories, category_to_groups

    seen_pairs: set[tuple[str, str]] = set()

    with master_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        group_field = None
        category_field = None
        for name in fieldnames:
            lname = name.lower()
            if lname == "group":
                group_field = name
            elif lname == "category":
                category_field = name

        if not group_field or not category_field:
            print("[GROUPS] ERROR: master categories file must have 'group' and 'category' columns.")
            return group_to_categories, category_to_groups

        for row in reader:
            raw_group = (row.get(group_field) or "").strip()
            raw_cat = (row.get(category_field) or "").strip()
            if not raw_group and not raw_cat:
                continue
            if not raw_group or not raw_cat:
                print(f"[GROUPS] Warning: skipping row with missing data: group={raw_group!r}, category={raw_cat!r}")
                continue

            pair = (raw_group, raw_cat)
            if pair in seen_pairs:
                print(f"[GROUPS] Warning: duplicate (group, category) pair found; ignoring: group={raw_group!r}, category={raw_cat!r}")
                continue
            seen_pairs.add(pair)

            group_to_categories.setdefault(raw_group, set()).add(raw_cat)
            category_to_groups.setdefault(raw_cat, set()).add(raw_group)

    empty_groups = [g for g, cats in group_to_categories.items() if not cats]
    for g in empty_groups:
        print(f"[GROUPS] Warning: dropping empty group: {g!r}")
        group_to_categories.pop(g, None)

    print("[GROUPS] Loaded master categories from:", master_path)
    print(f"[GROUPS] Groups: {len(group_to_categories)}")
    print(f"[GROUPS] Categories (unique names): {len(category_to_groups)}")

    return group_to_categories, category_to_groups


def _load_category_rules(categories_file: Path) -> dict[str, tuple[str, str]]:
    """Load description -> (group, category) rules from CSV."""
    rules: dict[str, tuple[str, str]] = {}
    if not categories_file.exists():
        return rules

    with categories_file.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        desc_field = None
        group_field = None
        category_field = None
        for name in fieldnames:
            lname = name.lower()
            if lname == "description":
                desc_field = name
            elif lname == "group":
                group_field = name
            elif lname == "category":
                category_field = name

        if not desc_field or not group_field or not category_field:
            print(f"[CATEGORIZE] Warning: {categories_file} is missing required columns; ignoring existing rules.")
            return rules

        for row in reader:
            desc = (row.get(desc_field) or "").strip()
            grp = (row.get(group_field) or "").strip()
            cat = (row.get(category_field) or "").strip()
            if desc and grp and cat:
                rules[desc] = (grp, cat)

    return rules


def _save_category_rules(categories_file: Path, rules: dict[str, tuple[str, str]]) -> None:
    """Persist description -> (group, category) rules."""
    categories_file.parent.mkdir(parents=True, exist_ok=True)
    with categories_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["description", "group", "category"])
        for desc in sorted(rules):
            grp, cat = rules[desc]
            writer.writerow([desc, grp, cat])


def categorize(input_csv: Path, categories_file: Path, master_categories_file: Path) -> None:
    """Assign (group, category) pairs and update rules."""
    if not input_csv.exists():
        print(f"[CATEGORIZE] ERROR: transactions CSV not found: {input_csv}")
        return

    with input_csv.open(newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    required_cols = ["statement_date", "date", "description", "amount", "group", "category"]
    missing = [c for c in required_cols if c not in fieldnames]
    if missing:
        print("[CATEGORIZE] ERROR: input CSV must have columns:", ", ".join(required_cols))
        print("[CATEGORIZE] Missing:", ", ".join(missing))
        return

    group_to_categories, category_to_groups = _load_group_category_master(master_categories_file)
    rules = _load_category_rules(categories_file)

    auto_assigned = 0
    already_categorized = 0
    uncategorized = 0

    updated_rows: list[dict[str, str]] = []

    for idx, row in enumerate(rows, start=1):
        desc = (row.get("description") or "").strip()
        grp = (row.get("group") or "").strip()
        cat = (row.get("category") or "").strip()

        if cat and not grp:
            print(f"[CATEGORIZE] Warning: row {idx} has category={cat!r} but no group.")
        if grp and not cat:
            print(f"[CATEGORIZE] Warning: row {idx} has group={grp!r} but no category.")
        if grp and cat:
            valid_cats = group_to_categories.get(grp, set())
            if cat not in valid_cats:
                print(
                    f"[CATEGORIZE] Warning: row {idx} has (group, category)=({grp!r}, {cat!r}) "
                    "which does not exist in master categories."
                )

        if not desc:
            updated_rows.append(row)
            continue

        if grp and cat:
            rule_pair = (grp, cat)
            if rules.get(desc) != rule_pair:
                rules[desc] = rule_pair
            already_categorized += 1
        elif not grp and not cat:
            rule_pair = rules.get(desc)
            if rule_pair:
                rule_grp, rule_cat = rule_pair
                row["group"] = rule_grp
                row["category"] = rule_cat
                auto_assigned += 1
            else:
                uncategorized += 1
        else:
            uncategorized += 1

        updated_rows.append(row)

    with input_csv.open("w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        for row in updated_rows:
            writer.writerow(row)

    _save_category_rules(categories_file, rules)

    print("[CATEGORIZE] Done.")
    print(f"[CATEGORIZE] Already fully categorized rows : {already_categorized}")
    print(f"[CATEGORIZE] Auto-assigned via rules       : {auto_assigned}")
    print(f"[CATEGORIZE] Still uncategorized/partial   : {uncategorized}")
    print(f"[CATEGORIZE] Rules saved to                : {categories_file}")


def check(input_csv: Path, categories_file: Path, master_categories_file: Path) -> None:
    """Validate transactions, master categories, and rules without modifying anything."""
    if not input_csv.exists():
        print(f"[CHECK] ERROR: transactions CSV not found: {input_csv}")
        return

    with input_csv.open(newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    required_cols = ["statement_date", "date", "description", "amount", "group", "category"]
    missing = [c for c in required_cols if c not in fieldnames]
    if missing:
        print("[CHECK] ERROR: input CSV must have columns:", ", ".join(required_cols))
        print("[CHECK] Missing:", ", ".join(missing))
        return

    group_to_categories, category_to_groups = _load_group_category_master(master_categories_file)
    rules = _load_category_rules(categories_file)

    total_rows = 0
    warn_no_group = 0
    warn_no_category = 0
    warn_invalid_pair = 0
    warn_rule_conflict = 0
    warn_rule_missing_for_used = 0
    info_rule_could_apply = 0

    for idx, row in enumerate(rows, start=1):
        total_rows += 1
        desc = (row.get("description") or "").strip()
        grp = (row.get("group") or "").strip()
        cat = (row.get("category") or "").strip()

        if cat and not grp:
            warn_no_group += 1
            print(f"[CHECK] Warning: row {idx} has category={cat!r} but no group.")
        if grp and not cat:
            warn_no_category += 1
            print(f"[CHECK] Warning: row {idx} has group={grp!r} but no category.")
        if grp and cat:
            valid_cats = group_to_categories.get(grp, set())
            if cat not in valid_cats:
                warn_invalid_pair += 1
                print(
                    f"[CHECK] Warning: row {idx} has (group, category)=({grp!r}, {cat!r}) "
                    "which does not exist in master categories."
                )

        rule_pair = rules.get(desc)
        if grp and cat:
            if rule_pair is None:
                warn_rule_missing_for_used += 1
                print(
                    f"[CHECK] Note: row {idx} has (group, category)=({grp!r}, {cat!r}) "
                    f"for description={desc!r}, but there is no rule yet for this description."
                )
            else:
                rule_grp, rule_cat = rule_pair
                if (grp, cat) != rule_pair:
                    warn_rule_conflict += 1
                    print(
                        f"[CHECK] Warning: row {idx} has (group, category)=({grp!r}, {cat!r}) "
                        f"but the rules file has ({rule_grp!r}, {rule_cat!r}) "
                        f"for description={desc!r}."
                    )
        else:
            if rule_pair is not None:
                info_rule_could_apply += 1
                rule_grp, rule_cat = rule_pair
                print(
                    f"[CHECK] Info: row {idx} has description={desc!r} but no full "
                    "(group, category); rules file would assign "
                    f"({rule_grp!r}, {rule_cat!r})."
                )

    print("\n[CHECK] Summary")
    print(f"[CHECK] Total rows examined           : {total_rows}")
    print(f"[CHECK] category without group       : {warn_no_group}")
    print(f"[CHECK] group without category       : {warn_no_category}")
    print(f"[CHECK] invalid (group, category)    : {warn_invalid_pair}")
    print(f"[CHECK] rule mismatches (conflicts)  : {warn_rule_conflict}")
    print(f"[CHECK] rows with pair but no rule   : {warn_rule_missing_for_used}")
    print(f"[CHECK] rows where a rule could apply: {info_rule_could_apply}")
    print(f"[CHECK] Done. No files were modified.")


def export(input_csv: Path, categories_file: Path, report_file: Path) -> None:
    """Export a simple text summary grouped by category."""
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
        f_out.write(f"Report for: {input_csv}")
        f_out.write(f"Categories file: {categories_file}")
        f_out.write(f"Total rows: {total_rows}")
        f_out.write("Category, Count, Total Amount")
        for category in sorted(totals):
            f_out.write(f"{category}, {counts[category]}, {totals[category]:.2f}")

    print("[EXPORT] Report written to:", report_file)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="moth",
        description="moth pipeline: extract -> categorize -> export -> check",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_extract = subparsers.add_parser("extract", help="Read a PDF and write an extracted CSV next to it.")
    p_extract.add_argument("pdf", help="Path to input PDF statement.")

    p_cat = subparsers.add_parser("categorize", help="Assign (group, category) and update rules.")
    p_cat.add_argument("input_csv", help="Path to extracted transactions CSV.")
    p_cat.add_argument("categories_file", help="Path to category rules CSV.")
    p_cat.add_argument("master_categories_file", help="Path to master (group, category) CSV.")

    p_export = subparsers.add_parser("export", help="Export a simple summary report.")
    p_export.add_argument("input_csv", help="Path to categorized transactions CSV.")
    p_export.add_argument("categories_file", help="Path to category rules CSV.")
    p_export.add_argument("report_file", help="Path to output report file.")

    p_check = subparsers.add_parser("check", help="Validate without modifying files.")
    p_check.add_argument("input_csv", help="Path to transactions CSV to check.")
    p_check.add_argument("categories_file", help="Path to category rules CSV.")
    p_check.add_argument("master_categories_file", help="Path to master (group, category) CSV.")

    args = parser.parse_args(argv)
    if args.command == "extract":
        extract(Path(args.pdf))
    elif args.command == "categorize":
        categorize(Path(args.input_csv), Path(args.categories_file), Path(args.master_categories_file))
    elif args.command == "export":
        export(Path(args.input_csv), Path(args.categories_file), Path(args.report_file))
    elif args.command == "check":
        check(Path(args.input_csv), Path(args.categories_file), Path(args.master_categories_file))
    else:
        parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
