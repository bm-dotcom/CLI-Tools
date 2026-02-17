import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.syntax import Syntax
import subprocess
import concurrent.futures
import traceback
import httpx
import os
import re

app = typer.Typer(
    name="flowrun",
    help="YAML-driven workflow runner with rich output.",
    add_completion=False,
)

console = Console()


class Step:
    def __init__(self, data: Dict[str, Any]):
        self.name: str = data.get("name", "Unnamed step")
        self.type: str = data.get("type", "").lower()
        self.command: Optional[str] = data.get("command")
        self.code: Optional[str] = data.get("code")
        self.method: Optional[str] = data.get("method", "GET").upper()
        self.url: Optional[str] = data.get("url")
        self.json: Optional[Dict] = data.get("json")
        self.headers: Optional[Dict] = data.get("headers")
        self.continue_on_error: bool = data.get("continue_on_error", False)

        if self.type not in ("shell", "python", "http"):
            raise ValueError(f"Unknown step type: {self.type}")

        if self.type == "shell" and not self.command:
            raise ValueError("Shell step requires 'command'")
        if self.type == "python" and not self.code:
            raise ValueError("Python step requires 'code'")
        if self.type == "http" and not self.url:
            raise ValueError("HTTP step requires 'url'")


def load_workflow(path: Path) -> tuple[str, List[Step], Dict[str, str]]:
    if not path.is_file():
        console.print(f"[bold red]File not found[/bold red]: {path}")
        raise typer.Exit(1)

    try:
        with open(path, encoding="utf-8") as f:
            doc = yaml.safe_load(f)
    except yaml.YAMLError as e:
        console.print(f"[bold red]Invalid YAML[/bold red]: {e}")
        raise typer.Exit(1)

    name = doc.get("name", path.stem)
    env = doc.get("env", {})
    raw_steps = doc.get("steps", [])

    if not isinstance(raw_steps, list):
        console.print("[bold red]'steps' must be a list[/bold red]")
        raise typer.Exit(1)

    steps: List[Step] = []
    for i, raw in enumerate(raw_steps, 1):
        if not isinstance(raw, dict):
            console.print(f"[bold red]Step {i} is not a mapping[/bold red]")
            raise typer.Exit(1)
        try:
            steps.append(Step(raw))
        except ValueError as e:
            console.print(f"[bold red]Step {i} invalid[/bold red]: {e}")
            raise typer.Exit(1)

    return name, steps, env


def interpolate(text: str, env: Dict[str, str], results: Dict[str, Any]) -> str:
    """Very basic {{env.KEY}} and {{steps[Name].key}} interpolation"""
    def repl(match):
        var = match.group(1)
        if var.startswith("env."):
            key = var[4:]
            return env.get(key, f"{{{{{var}}}}}")
        elif var.startswith("steps["):
            # simplistic: steps['Test B'].result
            parts = var[7:-1].split("'].")
            if len(parts) == 2:
                step_name, key = parts
                step_name = step_name.strip("'\"")
                return str(results.get(step_name, {}).get(key, f"{{{{{var}}}}}"))
        return match.group(0)

    return re.sub(r'\{\{(.*?)\}\}', repl, text)


def run_shell(cmd: str, cwd: Optional[Path] = None) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            text=True,
            capture_output=True,
            cwd=cwd,
            timeout=600,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "Command timed out"
    except Exception as e:
        return 1, "", str(e)


def run_python(code: str, results: Dict[str, Any]) -> tuple[int, str, str, Any]:
    import io
    from contextlib import redirect_stdout, redirect_stderr

    stdout = io.StringIO()
    stderr = io.StringIO()
    local_vars = {"results": results}

    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exec(code, {"__builtins__": __builtins__}, local_vars)
        return 0, stdout.getvalue(), stderr.getvalue(), local_vars.get("return")
    except Exception:
        return 1, stdout.getvalue(), traceback.format_exc(), None


def run_http(step: Step, env: Dict[str, str], results: Dict[str, Any]) -> tuple[int, str, str]:
    try:
        headers = step.headers or {}
        json_body = step.json or None

        # Interpolate
        url = interpolate(step.url, env, results)
        headers = {k: interpolate(v, env, results) for k, v in headers.items()}
        if json_body:
            json_body = {k: interpolate(str(v), env, results) for k, v in json_body.items()}

        resp = httpx.request(
            method=step.method,
            url=url,
            headers=headers,
            json=json_body,
            timeout=30,
        )
        status = resp.status_code
        out = f"Status: {status}\n{resp.text[:500]}..." if len(resp.text) > 500 else resp.text
        err = "" if 200 <= status < 300 else resp.text
        return 0 if 200 <= status < 300 else status, out, err
    except Exception as e:
        return 1, "", str(e)


def execute_step(step: Step, progress: Progress, task_id: int, env: Dict[str, str], results: Dict[str, Any]) -> bool:
    console.print(f"\n[bold cyan]→ {step.name} ({step.type.upper()})[/bold cyan]")

    if step.type == "shell":
        code = step.command
        lang = "bash"
        exec_fn = lambda: run_shell(code)
    elif step.type == "python":
        code = step.code
        lang = "python"
        exec_fn = lambda: run_python(code, results)
    else:  # http
        code = f"{step.method} {step.url}\nHeaders: {step.headers}\nBody: {step.json}"
        lang = "json"
        exec_fn = lambda: run_http(step, env, results)

    if code and code.strip():
        syntax = Syntax(code.strip(), lang, theme="monokai", line_numbers=True, word_wrap=True)
        console.print(Panel(syntax, title=f"{step.type.upper()} step", border_style="blue dim"))

    spinner = progress.add_task(f"[yellow]{step.type} running...", total=None)

    if step.type == "python":
        ret, out, err, returned = exec_fn()
        if returned is not None:
            results[step.name] = {"result": returned}
    else:
        ret, out, err = exec_fn()

    progress.remove_task(spinner)

    if out.strip():
        console.print("[green]Output:[/green]")
        console.print(out.rstrip())

    if err.strip():
        console.print("[red]Error:[/red]")
        console.print(err.rstrip())

    success = ret == 0
    if success:
        console.print("[bold green]✓ succeeded[/bold green]")
    else:
        console.print(f"[bold red]✗ failed (code {ret})[/bold red]")

    progress.update(task_id, advance=1)
    return success or step.continue_on_error


@app.command()
def run(
    filepath: Path = typer.Argument(..., exists=True, dir_okay=False),
    parallel: bool = typer.Option(False, "--parallel", "-p"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    workflow_name, steps, env = load_workflow(filepath)

    console.rule(f"[bold]Workflow: {workflow_name}[/bold]")
    console.print(f"Total steps: [cyan]{len(steps)}[/cyan]\n")

    if not steps:
        console.print("[yellow]No steps defined → nothing to do[/yellow]")
        raise typer.Exit(0)

    success = True
    step_results = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:

        main_task = progress.add_task("[bold]Executing...", total=len(steps))

        if not parallel:
            for step in steps:
                if not execute_step(step, progress, main_task, env, step_results):
                    success = False
                    if not verbose:
                        console.print("[bold red]Stopping on error (use --verbose to continue)[/bold red]")
                        break
        else:
            console.print("[yellow]Parallel mode — order not guaranteed[/yellow]")
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(steps)) as ex:
                futures = [ex.submit(execute_step, step, progress, main_task, env, step_results) for step in steps]
                for f in concurrent.futures.as_completed(futures):
                    if not f.result():
                        success = False

    if success:
        console.print("\n[bold green]Workflow completed successfully[/bold green]")
        raise typer.Exit(0)
    else:
        console.print("\n[bold red]Workflow failed[/bold red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()