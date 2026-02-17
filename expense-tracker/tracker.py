import argparse
import csv
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import sys

try:
    from tabulate import tabulate
except ImportError:
    tabulate = None

DATA_FILE = Path("expenses.csv")


def ensure_file():
    if not DATA_FILE.exists():
        with open(DATA_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["date", "amount", "category", "description"])


def load_data():
    if not DATA_FILE.exists():
        return []
    expenses = []
    with open(DATA_FILE, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                row["amount"] = float(row["amount"])
                expenses.append(row)
            except (ValueError, KeyError):
                continue  # skip malformed rows
    return expenses


def add_expense(date_str, amount, category, desc=""):
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        date_iso = date_obj.date().isoformat()
    except ValueError:
        print(f"Error: Invalid date format. Use YYYY-MM-DD (got: {date_str})", file=sys.stderr)
        sys.exit(1)

    if amount <= 0:
        print("Error: Amount must be positive.", file=sys.stderr)
        sys.exit(1)

    with open(DATA_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([date_iso, amount, category.strip(), desc.strip()])

    print(f"Added: ${amount:.2f} in {category} on {date_iso}" + (f" ({desc})" if desc else ""))


def print_table(rows, headers):
    if tabulate:
        print(tabulate(rows, headers=headers, tablefmt="simple"))
    else:
        # Fallback: very basic aligned output
        print(" | ".join(headers))
        print("-" * (len(" | ".join(headers))))
        for row in rows:
            print(" | ".join(str(x) for x in row))


def show_summary():
    expenses = load_data()
    if not expenses:
        print("No expenses recorded yet.")
        return

    monthly_total = defaultdict(float)
    category_by_month = defaultdict(lambda: defaultdict(float))

    for exp in expenses:
        month = exp["date"][:7]  # YYYY-MM
        monthly_total[month] += exp["amount"]
        category_by_month[month][exp["category"]] += exp["amount"]

    # Show monthly totals
    print("\nMonthly Totals:")
    rows = []
    for month in sorted(monthly_total):
        rows.append([month, f"${monthly_total[month]:.2f}"])
    print_table(rows, ["Month", "Total"])

    # Show latest month's category breakdown + tiny bar chart
    if rows:
        latest_month = rows[-1][0]
        print(f"\nCategory breakdown for {latest_month}:")
        cat_totals = category_by_month[latest_month]
        if cat_totals:
            max_amount = max(cat_totals.values())
            bar_width = 30
            rows = []
            for cat, amt in sorted(cat_totals.items(), key=lambda x: x[1], reverse=True):
                bar_len = int(bar_width * amt / max_amount) if max_amount > 0 else 0
                bar = "█" * bar_len + " " * (bar_width - bar_len)
                rows.append([cat, f"${amt:.2f}", bar])
            print_table(rows, ["Category", "Amount", "Bar"])
        else:
            print("  (no categories this month)")


def main():
    parser = argparse.ArgumentParser(description="Simple Expense Tracker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ADD command
    add_parser = subparsers.add_parser("add", help="Add a new expense")
    add_parser.add_argument("date", help="Date in YYYY-MM-DD format")
    add_parser.add_argument("amount", type=float, help="Amount spent (positive number)")
    add_parser.add_argument("category", help="Category (e.g. Coffee, Groceries)")
    add_parser.add_argument("--desc", default="", help="Optional description")

    # SUMMARY command
    subparsers.add_parser("summary", help="Show monthly summary and category breakdown")

    args = parser.parse_args()
    ensure_file()

    if args.command == "add":
        add_expense(args.date, args.amount, args.category, args.desc)
    elif args.command == "summary":
        show_summary()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()