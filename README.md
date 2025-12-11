# moth – Statement Pipeline (Option 1)

This is the Option 1 baseline for the **moth** project, including:

- `extract` (stub only)
- `categorize` with a persistent description→category rule system
- `export` which summarizes totals by category
- support for a `statement_date` column in the transaction CSV

## Commands

From the project root:

```bash
python -m moth categorize data/sample_transactions.csv data/category_rules.csv
python -m moth export data/sample_transactions.csv data/category_rules.csv out/report.txt
```
