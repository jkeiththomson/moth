# moth – Option B (master categories as an explicit parameter)

This project is a skeleton for a statement-processing pipeline with four commands:

- `extract`  – stub: pretend to read a PDF and write a CSV
- `categorize` – assign (group, category) via description→(group, category) rules
- `export`  – simple category-level summary report
- `check`   – dry-run validation; no files are modified

## Data files

- `data/sample_transactions.csv`
- `data/category_rules.csv`      (description → (group, category) rules)
- `data/master_categories.csv`   (universe of allowed (group, category) pairs)

### Transaction CSV schema

`data/sample_transactions.csv` uses:

- `statement_date`
- `date`
- `description`
- `amount`
- `group`
- `category`

### Master categories

`data/master_categories.csv` must have:

- `group`
- `category`

Each `(group, category)` pair must be unique. A category name may appear
in multiple groups, but the combination of group + category must not be
duplicated.

### Category rules

`data/category_rules.csv` is a description-based rule file:

- `description`
- `group`
- `category`

The `categorize` command will *learn* rules from any row that already
has both group and category set, and will *apply* rules to rows whose
group/category are blank.

## How to run

From the project root:

```bash
python -m moth extract statement.pdf data/extracted.csv

python -m moth categorize \
    data/sample_transactions.csv \
    data/category_rules.csv \
    data/master_categories.csv

python -m moth check \
    data/sample_transactions.csv \
    data/category_rules.csv \
    data/master_categories.csv

python -m moth export \
    data/sample_transactions.csv \
    data/category_rules.csv \
    out/report.txt
```
