# moth – statement pipeline (parallel extract output)

Commands:

- `extract`   – takes ONE argument (the PDF path) and writes an extracted CSV
                next to it, named `<pdf_stem>-extracted.csv`.
- `categorize` – applies/learns (group, category) rules and rewrites the CSV.
- `check`     – validates without modifying any files.
- `export`    – writes a simple category-level summary report.

## Example

```bash
python -m moth extract statements/chase/9391/2018/20180112-statements-9391.pdf
```

This will create:

```text
statements/chase/9391/2018/20180112-statements-9391-extracted.csv
```

You can then run:

```bash
python -m moth check statements/chase/9391/2018/20180112-statements-9391-extracted.csv data/category_rules.csv data/master_categories.csv
python -m moth categorize statements/chase/9391/2018/20180112-statements-9391-extracted.csv data/category_rules.csv data/master_categories.csv
```
