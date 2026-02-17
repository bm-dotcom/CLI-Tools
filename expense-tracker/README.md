# CLI Expense Tracker

Python 3 CLI expense tracker with CSV storage.

### Implementation
- argparse subcommands (`add`, `summary`)
- append-only UTF-8 CSV (stdlib `csv`, `newline=""`)
- validation: `datetime.strptime`, positive float
- aggregation: `collections.defaultdict`
- output: optional `tabulate` or ASCII tables
- charts: pure-Python fixed-width Unicode bars