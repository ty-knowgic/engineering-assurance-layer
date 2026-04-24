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

from eal.policy import resolve_policy

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


class PolicyProfileOption(str, Enum):
    LOCAL = "local"
    CI = "ci"
    MAIN = "main"
    PROD = "prod"
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
    bt_xml: Optional[Path] = typer.Option(
        None,
        "--bt-xml",
        help="Path to a narrow BehaviorTree XML artifact (optional)",
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
    policy_profile: PolicyProfileOption = typer.Option(
        PolicyProfileOption.LOCAL,
        "--policy-profile",
        help="Built-in policy profile for gate + strictness defaults",
    ),
    fail_on_severity: Optional[FailOnSeverityOption] = typer.Option(
        None,
        "--fail-on-severity",
        help="Fail process when severity is at/above threshold (overrides policy profile)",
    ),
    min_severity: Optional[MinSeverityOption] = typer.Option(
        None,
        "--min-severity",
        help="Minimum severity shown in terminal/summary (overrides policy profile)",
    ),
    strictness: Optional[StrictnessOption] = typer.Option(
        None,
        "--strictness",
        help="Rule strictness profile (overrides policy profile)",
    ),
    log_level: str = typer.Option("INFO", "--log-level", help="Logging level"),
) -> None:
    """Run a full engineering assurance review and emit artifacts."""
    _setup_logging(log_level)

    code_paths: list[Path] = list(code) if code else []
    resolved_policy = resolve_policy(
        profile=policy_profile.value,
        fail_on_severity=fail_on_severity.value if fail_on_severity else None,
        min_severity=min_severity.value if min_severity else None,
        strictness=strictness.value if strictness else None,
    )

    console.rule("[bold blue]Engineering Assurance Layer[/bold blue]")
    console.print(f"  Spec:  [cyan]{spec}[/cyan]")
    console.print(f"  Model: [cyan]{model or '(none)'}[/cyan]")
    console.print(f"  BT XML: [cyan]{bt_xml or '(none)'}[/cyan]")
    if code_paths:
        for cp in code_paths:
            console.print(f"  Code:  [cyan]{cp}[/cyan]")
    console.print(f"  Out:   [cyan]{out}[/cyan]")
    console.print(f"  Policy: [cyan]{resolved_policy.profile.value}[/cyan]")
    console.print(f"  Gate:  fail on [cyan]{resolved_policy.fail_on_severity}[/cyan] and above")
    console.print(f"  View:  min severity [cyan]{resolved_policy.min_severity}[/cyan]")
    console.print(f"  Rules: strictness [cyan]{resolved_policy.strictness}[/cyan]")
    console.print()

    from eal.pipeline import run_review

    exit_code = run_review(
        spec_path=spec,
        model_path=model,
        code_paths=code_paths,
        out_dir=out,
        bt_xml_path=bt_xml,
        fail_on_severity=resolved_policy.fail_on_severity,
        min_severity=resolved_policy.min_severity,
        strictness=resolved_policy.strictness,
        policy_profile=resolved_policy.profile.value,
        policy_sources=resolved_policy.source_map(),
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
    policy_info = metadata.get("policy", {})
    suppressed_count = int(strictness_info.get("suppressed_finding_count", 0))
    active_strictness = strictness_info.get("level", resolved_policy.strictness)
    active_min_severity = metadata.get("gate", {}).get("min_severity", resolved_policy.min_severity)
    active_fail_threshold = metadata.get("gate", {}).get("fail_on_severity", resolved_policy.fail_on_severity)
    active_policy_profile = policy_info.get("profile", resolved_policy.profile.value)

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
        if meets_or_exceeds_threshold(f.get("severity", "LOW"), active_min_severity)
    ]

    table = Table(
        title=f"Review Findings (>= {active_min_severity})",
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
            f"[dim]No findings at or above {active_min_severity} "
            f"({len(findings)} total findings exist).[/dim]"
        )

    overall_ok = by_sev["CRITICAL"] == 0 and by_sev["HIGH"] == 0
    review_status = "PASS" if overall_ok else "REVIEW REQUIRED"
    gate_failed = exit_code == 2

    console.print(f"\nHighest severity found: [bold]{highest_found}[/bold]")
    console.print(f"Policy profile: [bold]{active_policy_profile}[/bold]")
    console.print(f"Gate threshold: [bold]{active_fail_threshold}[/bold]")
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
