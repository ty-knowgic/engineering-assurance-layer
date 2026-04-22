"""
Engineering Assurance Layer — CLI entry point.

Commands:
  review   Run a full assurance review of a spec + optional model/code
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="eal",
    help="Engineering Assurance Layer — spec-to-constraint review tool",
    add_completion=False,
    no_args_is_help=True,
)


@app.callback()
def _root() -> None:
    """Engineering Assurance Layer — spec-to-constraint review tool."""
console = Console()


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )


@app.command("review")
def review(
    spec: Path = typer.Option(
        ...,
        "--spec", "-s",
        help="Path to the markdown spec file",
        exists=True, file_okay=True, dir_okay=False,
    ),
    model: Optional[Path] = typer.Option(
        None,
        "--model", "-m",
        help="Path to the YAML model file (optional)",
        exists=True, file_okay=True, dir_okay=False,
    ),
    code: Optional[list[Path]] = typer.Option(
        None,
        "--code", "-c",
        help="Path to code file(s) (may be specified multiple times)",
    ),
    out: Path = typer.Option(
        Path("out/review"),
        "--out", "-o",
        help="Output directory for review artifacts",
    ),
    log_level: str = typer.Option("INFO", "--log-level", help="Logging level"),
) -> None:
    """Run a full engineering assurance review and emit artifacts."""
    _setup_logging(log_level)

    code_paths: list[Path] = list(code) if code else []

    console.rule("[bold blue]Engineering Assurance Layer[/bold blue]")
    console.print(f"  Spec:  [cyan]{spec}[/cyan]")
    console.print(f"  Model: [cyan]{model or '(none)'}[/cyan]")
    if code_paths:
        for cp in code_paths:
            console.print(f"  Code:  [cyan]{cp}[/cyan]")
    console.print(f"  Out:   [cyan]{out}[/cyan]")
    console.print()

    from eal.pipeline import run_review

    exit_code = run_review(
        spec_path=spec,
        model_path=model,
        code_paths=code_paths,
        out_dir=out,
    )

    if exit_code != 0:
        console.print("[bold red]Pipeline error — see logs above.[/bold red]")
        raise typer.Exit(exit_code)

    # ── Terminal summary ───────────────────────────────────────────────────────
    import json
    findings_path = out / "findings.json"
    findings_data = json.loads(findings_path.read_text()) if findings_path.exists() else {}
    findings = findings_data.get("findings", [])

    by_sev: dict[str, int] = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in findings:
        sev = f.get("severity", "LOW")
        by_sev[sev] = by_sev.get(sev, 0) + 1

    table = Table(title="Review Findings", show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("Severity")
    table.add_column("Category")
    table.add_column("Title", max_width=60)
    for f in findings:
        sev = f.get("severity", "")
        color = {"CRITICAL": "red", "HIGH": "yellow", "MEDIUM": "blue", "LOW": "dim"}.get(sev, "")
        table.add_row(
            f.get("id", ""),
            f"[{color}]{sev}[/{color}]" if color else sev,
            f.get("category", ""),
            f.get("title", ""),
        )
    console.print(table)

    overall_ok = by_sev["CRITICAL"] == 0 and by_sev["HIGH"] == 0
    if overall_ok:
        console.print("\n[bold green]✅  Review PASS — no CRITICAL or HIGH findings.[/bold green]")
    else:
        console.print(
            f"\n[bold red]❌  Review REQUIRED — "
            f"{by_sev['CRITICAL']} CRITICAL, {by_sev['HIGH']} HIGH finding(s).[/bold red]"
        )

    console.print(f"\nArtifacts written to: [cyan]{out.resolve()}[/cyan]")
    console.print(f"  → [link={out.resolve() / 'report.html'}]report.html[/link]")
    console.print(f"  → findings.json ({len(findings)} findings)")
    console.print(f"  → counterexamples.json")
    console.print(f"  → ir_snapshot.json")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
