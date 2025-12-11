from __future__ import annotations

from pathlib import Path
from datetime import datetime
import csv
import re

import pdfplumber

from .chase_legacy import extract_activity as legacy_extract_activity



def _find_statement_date_from_pdf(pdf_path: Path) -> str:
    """Return statement date as YYYY-MM-DD string, or empty string if not found."""
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            if not pdf.pages:
                print("[EXTRACT] Warning: PDF has no pages when searching for statement date.")
                return ""
            first_page = pdf.pages[0]
            text = first_page.extract_text() or ""
    except Exception as e:
        print(f"[EXTRACT] Warning: could not read PDF for statement date: {e}")
        return ""

    # Look for something like 'Statement Date 01/12/2018' or 'Closing Date 01/12/18'
    date_pattern = re.compile(
        r"(Statement Date|Closing Date)\s*:?\s*([0-1]?\d/[0-3]?\d/(?:\d{2}|\d{4}))",
        re.IGNORECASE,
    )

    m = date_pattern.search(text)
    if not m:
        # Best-effort only; if we can't find it, we leave statement_date blank.
        print("[EXTRACT] Warning: no statement/closing date found on first page.")
        return ""

    mmddyy = m.group(2)
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            dt = datetime.strptime(mmddyy, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    print(f"[EXTRACT] Warning: could not parse statement date {mmddyy!r}")
    return ""

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

    statement_date_value = _find_statement_date_from_pdf(pdf_path)
    if not statement_date_value:
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
