from __future__ import annotations

from pathlib import Path
import csv

from .chase_legacy import extract_activity as legacy_extract_activity


def extract_chase_activity(pdf_path: Path, out_csv: Path) -> Path:
    """Adapter between legacy Chase extractor and moth pipeline."""
    pdf_path = pdf_path.resolve()
    out_csv = out_csv.resolve()

    out_dir = out_csv.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    legacy_csv_path_str = legacy_extract_activity(str(pdf_path), str(out_dir))
    legacy_csv_path = Path(legacy_csv_path_str).resolve()

    print(f"[EXTRACT] Legacy Chase extractor wrote: {legacy_csv_path}")
    if not legacy_csv_path.exists():
        raise FileNotFoundError(f"Legacy extractor reported output at {legacy_csv_path}, but it does not exist.")

    with legacy_csv_path.open(newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        fieldnames = reader.fieldnames or []

        def find_col(candidates):
            for name in fieldnames:
                lname = name.lower()
                for cand in candidates:
                    if cand in lname:
                        return name
            return None

        date_col = find_col(["date"])
        desc_col = find_col(["description", "desc", "merchant"])
        amt_col = find_col(["amount", "amt"])

        if not (date_col and desc_col and amt_col):
            raise RuntimeError(
                f"Legacy CSV {legacy_csv_path} is missing required columns; found: {fieldnames!r}"
            )

        rows = list(reader)

    statement_date_value = ""

    with out_csv.open("w", newline="", encoding="utf-8") as f_out:
        writer = csv.writer(f_out)
        writer.writerow(["statement_date", "date", "description", "amount", "group", "category"])
        for row in rows:
            writer.writerow([
                statement_date_value,
                (row.get(date_col) or "").strip(),
                (row.get(desc_col) or "").strip(),
                (row.get(amt_col) or "").strip(),
                "",
                "",
            ])

    print(f"[EXTRACT] Adapted legacy output into moth CSV: {out_csv}")
    return out_csv
