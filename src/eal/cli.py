"""
Engineering Assurance Layer — CLI entry point.

Commands:
  review   Run a full assurance review of a spec + optional model/code
"""

from __future__ import annotations

import logging
from enum import Enum
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


class FailOnSeverityOption(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


class MinSeverityOption(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class StrictnessOption(str, Enum):
    RELAXED = "relaxed"
    BALANCED = "balanced"
    STRICT = "strict"


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
    fail_on_severity: FailOnSeverityOption = typer.Option(
        FailOnSeverityOption.NONE,
        "--fail-on-severity",
        help="Fail the process when finding severity is at or above this threshold",
    ),
    min_severity: MinSeverityOption = typer.Option(
        MinSeverityOption.LOW,
        "--min-severity",
        help="Minimum severity shown in terminal and review_summary.md top findings",
    ),
    strictness: StrictnessOption = typer.Option(
        StrictnessOption.BALANCED,
        "--strictness",
        help="Rule strictness profile (relaxed suppresses heuristic findings)",
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
    console.print(f"  Gate:  fail on [cyan]{fail_on_severity.value}[/cyan] and above")
    console.print(f"  View:  min severity [cyan]{min_severity.value}[/cyan]")
    console.print(f"  Rules: strictness [cyan]{strictness.value}[/cyan]")
    console.print()

    from eal.pipeline import run_review

    exit_code = run_review(
        spec_path=spec,
        model_path=model,
        code_paths=code_paths,
        out_dir=out,
        fail_on_severity=fail_on_severity.value,
        min_severity=min_severity.value,
        strictness=strictness.value,
    )

    if exit_code == 1:
        console.print("[bold red]Pipeline error — see logs above.[/bold red]")
        raise typer.Exit(exit_code)

    # ── Terminal summary ───────────────────────────────────────────────────────
    import json
    from eal.findings.schema import meets_or_exceeds_threshold, severity_rank

    findings_path = out / "findings.json"
    metadata_path = out / "run_metadata.json"
    findings_data = json.loads(findings_path.read_text()) if findings_path.exists() else {}
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    findings = findings_data.get("findings", [])
    strictness_info = metadata.get("strictness", {})
    suppressed_count = int(strictness_info.get("suppressed_finding_count", 0))
    active_strictness = strictness_info.get("level", strictness.value)

    by_sev: dict[str, int] = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in findings:
        sev = f.get("severity", "LOW")
        by_sev[sev] = by_sev.get(sev, 0) + 1

    highest_found = (
        max((f.get("severity", "LOW") for f in findings), key=severity_rank)
        if findings
        else "NONE"
    )

    displayed_findings = [
        f for f in findings
        if meets_or_exceeds_threshold(f.get("severity", "LOW"), min_severity.value)
    ]

    table = Table(
        title=f"Review Findings (>= {min_severity.value})",
        show_header=True,
        header_style="bold",
    )
    table.add_column("ID")
    table.add_column("Severity")
    table.add_column("Category")
    table.add_column("Title", max_width=60)
    for f in displayed_findings:
        sev = f.get("severity", "")
        color = {"CRITICAL": "red", "HIGH": "yellow", "MEDIUM": "blue", "LOW": "dim"}.get(sev, "")
        table.add_row(
            f.get("id", ""),
            f"[{color}]{sev}[/{color}]" if color else sev,
            f.get("category", ""),
            f.get("title", ""),
        )
    if displayed_findings:
        console.print(table)
    else:
        console.print(
            f"[dim]No findings at or above {min_severity.value} "
            f"({len(findings)} total findings exist).[/dim]"
        )

    overall_ok = by_sev["CRITICAL"] == 0 and by_sev["HIGH"] == 0
    review_status = "PASS" if overall_ok else "REVIEW REQUIRED"
    gate_failed = exit_code == 2

    console.print(f"\nHighest severity found: [bold]{highest_found}[/bold]")
    console.print(f"Gate threshold: [bold]{fail_on_severity.value}[/bold]")
    console.print(f"Rule strictness: [bold]{active_strictness}[/bold]")
    if suppressed_count:
        console.print(f"Strictness-suppressed findings: [bold]{suppressed_count}[/bold]")
    console.print(f"Displayed findings: {len(displayed_findings)} of {len(findings)}")
    console.print(f"Review status: [bold]{review_status}[/bold]")

    if gate_failed:
        console.print("[bold red]Gate result: FAIL (severity threshold exceeded).[/bold red]")
    else:
        console.print("[bold green]Gate result: PASS.[/bold green]")

    console.print(f"\nArtifacts written to: [cyan]{out.resolve()}[/cyan]")
    console.print(f"  → [link={out.resolve() / 'report.html'}]report.html[/link]")
    console.print(f"  → findings.json ({len(findings)} findings)")
    console.print(f"  → results.sarif")
    console.print(f"  → counterexamples.json")
    console.print(f"  → ir_snapshot.json")

    if gate_failed:
        raise typer.Exit(2)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
