from __future__ import annotations

import argparse
from pathlib import Path
import csv
from dataclasses import dataclass
from enum import Enum


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





class TxStatus(Enum):
    MANUAL = "manual"
    AUTO_PENDING = "auto-pending"
    UNASSIGNED = "unassigned"


@dataclass
class CategoryEntry:
    id: int
    group: str
    name: str


def _build_category_entries(group_to_categories: dict[str, set[str]]) -> list[CategoryEntry]:
    """Derive sorted CategoryEntry list with IDs from master groups/categories."""
    entries: list[CategoryEntry] = []
    cat_id = 1
    for group in sorted(group_to_categories.keys()):
        cats = sorted(group_to_categories[group])
        for name in cats:
            entries.append(CategoryEntry(id=cat_id, group=group, name=name))
            cat_id += 1
    return entries


def _preview_ui_page(rows: list[dict[str, str]], statuses: list[TxStatus], group_to_categories: dict[str, set[str]], max_rows: int = 10) -> None:
    """Print a simple one-page UI preview (non-interactive).

    - Top: groups and categories laid out in up to 5 columns, 27 chars wide.
    - Bottom: first N transactions with color-coded category/group.
    """
    if not rows:
        print("[PREVIEW] No rows to display.")
        return

    # Build category entries and (group, category) -> id map
    entries = _build_category_entries(group_to_categories)
    pair_to_id: dict[tuple[str, str], int] = {
        (e.group, e.name): e.id for e in entries
    }

    # --- Top half: categories layout ---
    MAX_COLS = 5
    COL_WIDTH = 27
    MAX_LINES_PER_COL = 12  # arbitrary for preview

    # Build blocks: each group header + its category lines
    blocks: list[list[str]] = []
    for group in sorted(group_to_categories.keys()):
        cats = sorted(group_to_categories[group])
        if not cats:
            continue
        block_lines: list[str] = []
        block_lines.append(group[:COL_WIDTH].ljust(COL_WIDTH))
        for cat in cats:
            cat_id = pair_to_id.get((group, cat), 0)
            line = f"{cat_id:4d} {cat}" if cat_id else f"     {cat}"
            block_lines.append(line[:COL_WIDTH].ljust(COL_WIDTH))
        blocks.append(block_lines)

    # Distribute blocks into columns without splitting a block
    columns: list[list[str]] = [[] for _ in range(MAX_COLS)]
    col_idx = 0
    for block in blocks:
        if col_idx >= MAX_COLS:
            break
        col = columns[col_idx]
        # If block would overflow this column, move to next column
        if len(col) + len(block) > MAX_LINES_PER_COL and col:
            col_idx += 1
            if col_idx >= MAX_COLS:
                break
            col = columns[col_idx]
        col.extend(block)

    print("[CATEGORIZE PREVIEW] Categories (top half)")
    # Compute max lines actually used
    max_lines = max((len(col) for col in columns), default=0)
    for row_idx in range(max_lines):
        line_parts = []
        for col in columns:
            if row_idx < len(col):
                line_parts.append(col[row_idx])
            else:
                line_parts.append("".ljust(COL_WIDTH))
        print(" ".join(line_parts))

    # --- Bottom half: transactions preview ---
    print("\n[CATEGORIZE PREVIEW] Transactions (bottom half)")
    header = (
        "Num  Statement   Trans_Date  "
        "Description                           CatID  Category        Group"
    )
    print(header)
    print("-" * len(header))

    # ANSI colors
    GREEN = "\x1b[32m"
    YELLOW = "\x1b[33m"
    RED = "\x1b[31m"
    RESET = "\x1b[0m"

    for i, (row, status) in enumerate(zip(rows, statuses), start=1):
        if i > max_rows:
            break
        stmt_date = (row.get("statement_date") or "")[:10]
        tx_date = (row.get("date") or "")[:10]
        desc = (row.get("description") or "")[:35]
        grp = (row.get("group") or "")[:12]
        cat = (row.get("category") or "")[:12]

        cat_id = pair_to_id.get((grp, cat))
        cat_id_str = f"{cat_id:4d}" if cat_id is not None else "   -"

        if status == TxStatus.MANUAL:
            color = GREEN
        elif status == TxStatus.AUTO_PENDING:
            color = YELLOW
        else:
            color = RED

        # Only color the CatID/Category/Group portion
        prefix = f"{i:4d}  {stmt_date:10s} {tx_date:10s} {desc:35s} "
        cat_part = f"{color}{cat_id_str}  {cat:12s} {grp:12s}{RESET}"
        print(prefix + cat_part)
    print("[CATEGORIZE PREVIEW] (showing up to", max_rows, "rows)")

def categorize(input_csv: Path, categories_file: Path, master_categories_file: Path) -> None:
    """Assign (group, category) pairs and update description-based rules.

    Mental model:

    - The transactions CSV is the truth for this statement.
    - master_categories.csv defines the allowed (group, category) universe.
    - category_rules.csv is a cache of description -> (group, category) shortcuts.

    Rules:

    - We *never* create or update a rule for an invalid (group, category) pair.
    - If a row's (group, category) conflicts with an existing rule for that
      description, we WARN and leave the existing rule unchanged.
    - If a row has a valid (group, category) and no rule yet, we learn a new rule.
    - If a row has no (group, category) and we have a rule, we auto-assign it.
    """
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

    # Load master (group, category) universe (read-only).
    group_to_categories, category_to_groups = _load_group_category_master(master_categories_file)

    # Load description -> (group, category) rules.
    rules = _load_category_rules(categories_file)

    # Row-level stats
    total_rows = 0
    auto_assigned = 0
    already_categorized = 0
    uncategorized = 0

    # Rule-level stats
    new_rules = 0
    rules_skipped_invalid_pair = 0
    rules_skipped_conflict = 0

    updated_rows: list[dict[str, str]] = []
    row_statuses: list[TxStatus] = []

    for idx, row in enumerate(rows, start=1):
        total_rows += 1

        desc = (row.get("description") or "").strip()
        grp = (row.get("group") or "").strip()
        cat = (row.get("category") or "").strip()

        # Default status: assume unassigned until we know otherwise.
        status = TxStatus.UNASSIGNED

        # --- Row-level group/category consistency checks ---
        if cat and not grp:
            print(f"[CATEGORIZE] Warning: row {idx} has category={cat!r} but no group.")
        if grp and not cat:
            print(f"[CATEGORIZE] Warning: row {idx} has group={grp!r} but no category.")

        # Check validity of (group, category) if both are present
        pair_is_valid = False
        if grp and cat:
            valid_cats = group_to_categories.get(grp, set())
            if cat not in valid_cats:
                print(
                    f"[CATEGORIZE] Warning: row {idx} has (group, category)=({grp!r}, {cat!r}) "
                    "which does not exist in master categories. This pair will NOT be turned "
                    "into a rule."
                )
            else:
                pair_is_valid = True
                status = TxStatus.MANUAL  # valid pair present from the CSV

        # If no description, we can't do any rule-based work; keep row as-is.
        if not desc:
            if grp and cat and pair_is_valid:
                already_categorized += 1
            else:
                uncategorized += 1
            updated_rows.append(row)
            row_statuses.append(status)
            continue

        # --- Description-based rules logic ---
        if grp and cat:
            # Fully specified pair on this row.
            if pair_is_valid:
                already_categorized += 1
            else:
                uncategorized += 1  # invalid pair counts as not properly categorized

            if not pair_is_valid:
                # Invalid pairs never become rules.
                rules_skipped_invalid_pair += 1
            else:
                existing = rules.get(desc)
                if existing is None:
                    # New rule
                    rules[desc] = (grp, cat)
                    new_rules += 1
                elif existing == (grp, cat):
                    # Matches existing rule: nothing to change.
                    pass
                else:
                    # Conflict: keep existing rule, warn.
                    rules_skipped_conflict += 1
                    rule_grp, rule_cat = existing
                    print(
                        f"[CATEGORIZE] Warning: row {idx} has (group, category)=({grp!r}, {cat!r}) "
                        f"but the rules file already has ({rule_grp!r}, {rule_cat!r}) for "
                        f"description={desc!r}. Keeping the existing rule."
                    )

        elif not grp and not cat:
            # Nothing assigned yet: try to apply a rule from description.
            rule_pair = rules.get(desc)
            if rule_pair:
                rule_grp, rule_cat = rule_pair
                row["group"] = rule_grp
                row["category"] = rule_cat
                auto_assigned += 1
                status = TxStatus.AUTO_PENDING
            else:
                uncategorized += 1
                status = TxStatus.UNASSIGNED
        else:
            # Partial (grp xor cat): we've already warned above.
            uncategorized += 1
            status = TxStatus.UNASSIGNED

        updated_rows.append(row)
        row_statuses.append(status)

    # Write updated transactions back to the same CSV.
    with input_csv.open("w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        for row in updated_rows:
            writer.writerow(row)

    # Persist updated description -> (group, category) rules.
    _save_category_rules(categories_file, rules)

    # Summary
    print("[CATEGORIZE] Summary")
    print(f"[CATEGORIZE] Total rows processed           : {total_rows}")
    print(f"[CATEGORIZE] Already fully categorized rows : {already_categorized}")
    print(f"[CATEGORIZE] Auto-assigned via rules       : {auto_assigned}")
    print(f"[CATEGORIZE] Still blank / partial         : {uncategorized}")
    print("[CATEGORIZE] Rules")
    print(f"[CATEGORIZE] New rules created             : {new_rules}")
    print(f"[CATEGORIZE] Rules skipped (invalid pair)  : {rules_skipped_invalid_pair}")
    print(f"[CATEGORIZE] Rules skipped (conflict)      : {rules_skipped_conflict}")
    print(f"[CATEGORIZE] Rules saved to                : {categories_file}")

    # UI preview page (non-interactive)
    print("\n[CATEGORIZE] Rendering one-page console UI preview (non-interactive)...")
    _preview_ui_page(updated_rows, row_statuses, group_to_categories, max_rows=10)

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
        f_out.write(f"Report for: {input_csv}\n")
        f_out.write(f"Total rows: {total_rows}\n")
        f_out.write("Category, Count, Total Amount\n")
        for category in sorted(totals):
            f_out.write(f"{category}, {counts[category]}, {totals[category]:.2f}\n")



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
