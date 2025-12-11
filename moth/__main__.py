
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
    print(
        "[EXTRACT] CSV schema would include: "
        "statement_date, date, description, amount, group, category"
    )


# ---------------------------------------------------------------------------
# Group / category master (read-only)
# ---------------------------------------------------------------------------


def _load_group_category_master(
    master_path: Path,
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Load and validate the master group/category mapping.

    Rules enforced:

    - Each (group, category) pair must be unique.
    - A category name is allowed to appear in multiple groups.
    - Groups with no valid categories are ignored.
    - Rows with missing group or category are skipped.

    The file is treated as read-only for now.

    Returns:
        group_to_categories: {group -> set of categories}
        category_to_groups: {category -> set of groups}
    """

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
            print(
                "[GROUPS] ERROR: master categories file must have 'group' and 'category' columns."
            )
            return group_to_categories, category_to_groups

        for row in reader:
            raw_group = (row.get(group_field) or "").strip()
            raw_cat = (row.get(category_field) or "").strip()

            if not raw_group and not raw_cat:
                continue  # completely empty row
            if not raw_group or not raw_cat:
                print(
                    f"[GROUPS] Warning: skipping row with missing data: "
                    f"group={raw_group!r}, category={raw_cat!r}"
                )
                continue

            pair = (raw_group, raw_cat)
            if pair in seen_pairs:
                print(
                    "[GROUPS] Warning: duplicate (group, category) pair found; "
                    f"ignoring: group={raw_group!r}, category={raw_cat!r}"
                )
                continue
            seen_pairs.add(pair)

            group_to_categories.setdefault(raw_group, set()).add(raw_cat)
            category_to_groups.setdefault(raw_cat, set()).add(raw_group)

    # Remove any groups that ended up with no categories (just in case)
    empty_groups = [g for g, cats in group_to_categories.items() if not cats]
    for g in empty_groups:
        print(f"[GROUPS] Warning: dropping empty group: {g!r}")
        group_to_categories.pop(g, None)

    print("[GROUPS] Loaded master categories from:", master_path)
    print(f"[GROUPS] Groups: {len(group_to_categories)}")
    print(f"[GROUPS] Categories (unique names): {len(category_to_groups)}")

    return group_to_categories, category_to_groups


# ---------------------------------------------------------------------------
# Category rule persistence: description → (group, category)
# ---------------------------------------------------------------------------


def _load_category_rules(
    categories_file: Path,
) -> dict[str, tuple[str, str]]:
    """Load a description→(group, category) mapping from a CSV rules file.

    Expected format:

        description,group,category
        "SAFEWAY",Household,Groceries
        "CHEVRON",Transport,Fuel

    If the file is missing or malformed, an empty mapping is returned.
    """
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
            print(
                f"[CATEGORIZE] Warning: {categories_file} does not have "
                "'description', 'group', and 'category' columns; ignoring existing rules."
            )
            return rules

        for row in reader:
            desc = (row.get(desc_field) or "").strip()
            grp = (row.get(group_field) or "").strip()
            cat = (row.get(category_field) or "").strip()
            if desc and grp and cat:
                rules[desc] = (grp, cat)

    return rules


def _save_category_rules(
    categories_file: Path,
    rules: dict[str, tuple[str, str]],
) -> None:
    """Persist the description→(group, category) mapping to a CSV file."""
    categories_file.parent.mkdir(parents=True, exist_ok=True)
    with categories_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["description", "group", "category"])
        for desc in sorted(rules):
            grp, cat = rules[desc]
            writer.writerow([desc, grp, cat])


# ---------------------------------------------------------------------------
# Categorize: persistent (group, category) system with statement_date support
# ---------------------------------------------------------------------------


def categorize(
    input_csv: Path,
    categories_file: Path,
    master_categories_file: Path,
) -> None:
    """Assign (group, category) to each transaction and persist description-based rules.

    Behavior:

    - Transactions are read from ``input_csv`` (a CSV file).
    - Rules are stored in ``categories_file`` as description→(group, category).
    - For each row:
      * If both ``group`` and ``category`` are set:
          - We validate (group, category) against the master categories.
          - We learn/update the rule for this description.
      * If both ``group`` and ``category`` are empty:
          - We look up the description in the rules and, if found,
            assign both group and category to the row.
      * If one is set and the other is empty:
          - We warn, but do not auto-fix yet.

    Required columns in ``input_csv``:

        statement_date, date, description, amount, group, category
    """

    if not input_csv.exists():
        print(f"[CATEGORIZE] ERROR: transactions CSV not found: {input_csv}")
        return

    with input_csv.open(newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    required_cols = [
        "statement_date",
        "date",
        "description",
        "amount",
        "group",
        "category",
    ]
    missing = [c for c in required_cols if c not in fieldnames]

    if missing:
        print(
            "[CATEGORIZE] ERROR: input CSV must have columns: "
            + ", ".join(required_cols)
        )
        print("[CATEGORIZE] Missing:", ", ".join(missing))
        return

    # Load master (group, category) universe (read-only).
    group_to_categories, category_to_groups = _load_group_category_master(
        master_categories_file
    )

    # Load description → (group, category) rules.
    rules = _load_category_rules(categories_file)

    auto_assigned = 0
    already_categorized = 0
    uncategorized = 0

    updated_rows: list[dict[str, str]] = []

    row_index = 0
    for row in rows:
        row_index += 1
        desc = (row.get("description") or "").strip()
        grp = (row.get("group") or "").strip()
        cat = (row.get("category") or "").strip()

        # --- Row-level group/category consistency checks ---

        if cat and not grp:
            print(
                f"[CATEGORIZE] Warning: row {row_index} has category={cat!r} "
                "but no group; this is probably unintended."
            )

        if grp and not cat:
            print(
                f"[CATEGORIZE] Warning: row {row_index} has group={grp!r} "
                "but no category; this is probably unintended."
            )

        if grp and cat:
            # Validate against master (group, category) universe.
            valid_cats = group_to_categories.get(grp, set())
            if cat not in valid_cats:
                print(
                    f"[CATEGORIZE] Warning: row {row_index} has (group, category)="
                    f"({grp!r}, {cat!r}) which does not exist in master categories."
                )

        # --- Description-based rules logic ---

        if not desc:
            updated_rows.append(row)
            continue

        if grp and cat:
            # Fully specified pair; learn/update rule.
            rule_pair = (grp, cat)
            if rules.get(desc) != rule_pair:
                rules[desc] = rule_pair
            already_categorized += 1
        elif not grp and not cat:
            # Nothing assigned yet: try to apply a rule from description.
            rule_pair = rules.get(desc)
            if rule_pair:
                rule_grp, rule_cat = rule_pair
                row["group"] = rule_grp
                row["category"] = rule_cat
                grp, cat = rule_grp, rule_cat
                auto_assigned += 1
            else:
                uncategorized += 1
        else:
            # Partial (grp xor cat): we've already warned above.
            uncategorized += 1

        updated_rows.append(row)

    # Write updated transactions back to the same CSV.
    with input_csv.open("w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        for row in updated_rows:
            writer.writerow(row)

    # Persist updated description→(group, category) rules.
    _save_category_rules(categories_file, rules)

    print("[CATEGORIZE] Done.")
    print(f"[CATEGORIZE] Already fully categorized rows : {already_categorized}")
    print(f"[CATEGORIZE] Auto-assigned via rules       : {auto_assigned}")
    print(f"[CATEGORIZE] Still uncategorized/partial   : {uncategorized}")
    print(f"[CATEGORIZE] Rules saved to                : {categories_file}")


# ---------------------------------------------------------------------------
# Check: validate without modifying
# ---------------------------------------------------------------------------


def check(
    input_csv: Path,
    categories_file: Path,
    master_categories_file: Path,
) -> None:
    """Validate transactions, master categories, and rules WITHOUT modifying anything.

    This performs:

    - Schema check on the transactions CSV.
    - Row-level (group, category) checks:
        * group with no category
        * category with no group
        * (group, category) not found in master categories
    - Consistency between transactions and description→(group, category) rules:
        * If a rule exists and row has a conflicting (group, category), warn.
        * If a row has a full (group, category) but no rule yet, note it.
        * If a row is blank but a rule exists, note that it *could* be auto-assigned.

    It does NOT write or update any files.
    """
    if not input_csv.exists():
        print(f"[CHECK] ERROR: transactions CSV not found: {input_csv}")
        return

    with input_csv.open(newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    required_cols = [
        "statement_date",
        "date",
        "description",
        "amount",
        "group",
        "category",
    ]
    missing = [c for c in required_cols if c not in fieldnames]

    if missing:
        print(
            "[CHECK] ERROR: input CSV must have columns: "
            + ", ".join(required_cols)
        )
        print("[CHECK] Missing:", ", ".join(missing))
        return

    group_to_categories, category_to_groups = _load_group_category_master(
        master_categories_file
    )
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
            print(
                f"[CHECK] Warning: row {idx} has category={cat!r} "
                "but no group."
            )

        if grp and not cat:
            warn_no_category += 1
            print(
                f"[CHECK] Warning: row {idx} has group={grp!r} "
                "but no category."
            )

        if grp and cat:
            valid_cats = group_to_categories.get(grp, set())
            if cat not in valid_cats:
                warn_invalid_pair += 1
                print(
                    f"[CHECK] Warning: row {idx} has (group, category)="
                    f"({grp!r}, {cat!r}) which does not exist in master categories."
                )

        # Cross-check with rules
        rule_pair = rules.get(desc)

        if grp and cat:
            if rule_pair is None:
                # We have a fully specified pair but no rule yet
                warn_rule_missing_for_used += 1
                print(
                    f"[CHECK] Note: row {idx} has (group, category)=({grp!r}, {cat!r}) "
                    f"for description={desc!r}, but there is no rule yet for this "
                    "description. categorize() would learn this rule."
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
            # No full pair on the row
            if rule_pair is not None:
                info_rule_could_apply += 1
                rule_grp, rule_cat = rule_pair
                print(
                    f"[CHECK] Info: row {idx} has description={desc!r} but no full "
                    "(group, category); rules file would assign "
                    f"({rule_grp!r}, {rule_cat!r})."
                )

    print("\\n[CHECK] Summary")
    print(f"[CHECK] Total rows examined           : {total_rows}")
    print(f"[CHECK] category without group       : {warn_no_group}")
    print(f"[CHECK] group without category       : {warn_no_category}")
    print(f"[CHECK] invalid (group, category)    : {warn_invalid_pair}")
    print(f"[CHECK] rule mismatches (conflicts)  : {warn_rule_conflict}")
    print(f"[CHECK] rows with pair but no rule   : {warn_rule_missing_for_used}")
    print(f"[CHECK] rows where a rule could apply: {info_rule_could_apply}")
    print(f"[CHECK] Done. No files were modified.")


# ---------------------------------------------------------------------------
# Export: simple summary report (still category-based for now)
# ---------------------------------------------------------------------------


def export(input_csv: Path, categories_file: Path, report_file: Path) -> None:
    """
    Export a simple text report based on the categorized CSV.

    Current behavior:

    - Reads ``input_csv`` (must have at least 'category' and 'amount' columns).
    - Computes, per category:
        * number of transactions
        * total amount (sum of 'amount')
    - Writes a plain-text report to ``report_file`` summarizing these totals.

    Note: for now, this groups only by category, not by (group, category).
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
        f_out.write("\\n")
        f_out.write("Category, Count, Total Amount\\n")
        for category in sorted(totals):
            f_out.write(
                f"{category}, {counts[category]}, {totals[category]:.2f}\\n"
            )

    print("[EXPORT] Report written to:", report_file)


# ---------------------------------------------------------------------------
# Meta function / CLI dispatcher
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    """
    Meta function that exposes the commands:

    - extract
    - categorize
    - export
    - check
    """
    parser = argparse.ArgumentParser(
        prog="moth",
        description="moth pipeline: extract → categorize → export → check",
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
        help="Assign (group, category) to transactions and persist rules.",
    )
    p_categorize.add_argument(
        "input_csv",
        help="Path to extracted transactions CSV.",
    )
    p_categorize.add_argument(
        "categories_file",
        help="Path to category rules file (persists across runs).",
    )
    p_categorize.add_argument(
        "master_categories_file",
        help="Path to master (group, category) CSV.",
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
        help="Path to category rules file (same as used for categorize).",
    )
    p_export.add_argument(
        "report_file",
        help="Path to summary report output file.",
    )

    # check
    p_check = subparsers.add_parser(
        "check",
        help="Validate transactions, master categories, and rules without modifying anything.",
    )
    p_check.add_argument(
        "input_csv",
        help="Path to transactions CSV to check.",
    )
    p_check.add_argument(
        "categories_file",
        help="Path to category rules file.",
    )
    p_check.add_argument(
        "master_categories_file",
        help="Path to master (group, category) CSV.",
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
            master_categories_file=Path(args.master_categories_file),
        )
    elif command == "export":
        export(
            input_csv=Path(args.input_csv),
            categories_file=Path(args.categories_file),
            report_file=Path(args.report_file),
        )
    elif command == "check":
        check(
            input_csv=Path(args.input_csv),
            categories_file=Path(args.categories_file),
            master_categories_file=Path(args.master_categories_file),
        )
    else:
        parser.error(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
