import typer
from rich.console import Console
from rich.table import Table
import csv
from pathlib import Path
from collections import Counter
import statistics
from typing import Optional
import json

app = typer.Typer(rich_markup_mode="rich")
console = Console()

@app.command("summary")          
def summarize(                   
    filepath: Path = typer.Argument(..., exists=True, help="CSV/TSV file"),
    column: Optional[str] = typer.Option(None, "--column", "-c", help="Focus on one column"),
    json_out: bool = typer.Option(False, "--json", help="Output machine-readable JSON"),
):

    """Generate rich summary for tabular data."""
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = list(reader)

    if not rows:
        console.print("[yellow]Empty file[/yellow]")
        raise typer.Exit()

    preview = Table(title=f"Preview — {len(rows)} rows")
    for h in headers[:8]:
        preview.add_column(h[:12], overflow="fold")
    for row in rows[:5]:
        preview.add_row(*[str(row.get(h, ""))[:15] for h in headers[:8]])
    console.print(preview)

    if column and column in headers:
        values = [row[column].strip() for row in rows if row[column].strip()]
        try:
            nums = [float(v) for v in values]
            data = {
                "count": len(nums),
                "mean": round(statistics.mean(nums), 4),
                "median": round(statistics.median(nums), 4),
                "std": round(statistics.stdev(nums), 4) if len(nums) > 1 else None,
                "min": min(nums),
                "max": max(nums),
            }
            if json_out:
                console.print(json.dumps(data, indent=2))
            else:
                t = Table(title=f"Stats for column '{column}'")
                t.add_column("Metric"); t.add_column("Value")
                for k, v in data.items():
                    t.add_row(k, str(v))
                console.print(t)
        except ValueError:
            cnt = Counter(values)
            if json_out:
                console.print(json.dumps(dict(cnt.most_common(10)), indent=2))
            else:
                t = Table(title=f"Top values for '{column}'")
                t.add_column("Value"); t.add_column("Count")
                for v, c in cnt.most_common(10):
                    t.add_row(str(v), str(c))
                console.print(t)

if __name__ == "__main__":
    app()