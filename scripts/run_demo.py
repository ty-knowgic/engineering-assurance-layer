#!/usr/bin/env python3
"""
One-command reproducible demo.

    make demo          regenerate demo/output/
    make demo-check    verify demo/output/ still reproduces byte-for-byte

Runs EAL against three unmodified upstream Nav2 configuration files and one
unmodified upstream Nav2 behavior tree, and writes the full artifact set for
each to demo/output/. Those outputs are committed, so anyone can read what the
tool actually produces without installing it, and can prove the committed
outputs are what the current code produces by running `make demo-check`.

## Why the outputs are normalized

Review artifacts embed a run id, wall-clock timestamps, and absolute input
paths. Committing them raw would mean every run produces a diff, which makes
the committed outputs useless as a reproducibility check. This script replaces
exactly those volatile fields with fixed tokens after the run, so a re-run is a
byte-for-byte comparison.

Normalization happens here, in the demo harness — never in the product code.
Real runs keep their real run ids and timestamps. Input provenance is not
normalized away: the SHA-256 of every input is recorded in demo/provenance.json
and verified before any scenario runs.
"""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"
OUTPUT = DEMO / "output"
MANIFEST = DEMO / "provenance.json"

RUN_ID_TOKEN = "eal-DEMO-NORMALIZED"
TIMESTAMP_TOKEN = "1970-01-01T00:00:00+00:00"

PARAMS = "tests/fixtures/nav2_upstream_params"
TREES = "tests/fixtures/nav2_upstream_bt"

# (name, description, CLI args). Expected outcomes are asserted by the test
# suite, not here — this script reports what happened, it does not grade it.
SCENARIOS: list[tuple[str, str, list[str]]] = [
    (
        "nav2_dwb_coherent",
        "Upstream DWB config: controller and smoother limits agree",
        ["--spec", "demo/spec/nav2_motion_limits.md",
         "--nav2-params", f"{PARAMS}/nav2_system_params.yaml",
         "--policy-profile", "ci"],
    ),
    (
        "nav2_mppi_bringup",
        "Upstream MPPI bringup config: acceleration limits disagree with smoother",
        ["--spec", "demo/spec/nav2_motion_limits.md",
         "--nav2-params", f"{PARAMS}/nav2_params.yaml",
         "--policy-profile", "ci"],
    ),
    (
        "nav2_mppi_no_map",
        "Upstream MPPI GPS config: acceleration and velocity limits disagree",
        ["--spec", "demo/spec/nav2_motion_limits.md",
         "--nav2-params", f"{PARAMS}/nav2_no_map_params.yaml",
         "--policy-profile", "ci"],
    ),
    (
        "nav2_bt_unanalyzable",
        "Upstream Nav2 behavior tree: outside EAL's analysis envelope (UNKNOWN)",
        ["--spec", "demo/spec/nav2_motion_limits.md",
         "--bt-xml", f"{TREES}/navigate_to_pose_w_replanning_and_recovery.xml",
         "--policy-profile", "ci"],
    ),
]

EXIT_MEANING = {
    0: "PASS",
    2: "FAIL (severity gate)",
    3: "UNKNOWN (analysis coverage incomplete)",
    1: "PIPELINE ERROR",
}


# ── Input integrity ───────────────────────────────────────────────────────────

def verify_inputs() -> None:
    """Refuse to run on tampered fixtures — a demo on altered input proves nothing."""
    manifest = json.loads(MANIFEST.read_text())
    bad: list[str] = []
    for entry in manifest["files"]:
        path = ROOT / entry["local_path"]
        if not path.exists():
            bad.append(f"missing: {entry['local_path']}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != entry["sha256"]:
            bad.append(
                f"modified: {entry['local_path']}\n"
                f"    expected {entry['sha256']}\n"
                f"    actual   {actual}"
            )
    if bad:
        print("Input provenance check FAILED:\n  " + "\n  ".join(bad), file=sys.stderr)
        print(
            f"\nThese files must match {MANIFEST.relative_to(ROOT)} exactly. "
            "See its verify_command to re-check against upstream.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    up = manifest["upstream"]
    print(f"Input provenance OK: {len(manifest['files'])} files")
    print(f"  upstream {up['repository']}")
    print(f"  commit   {up['commit']} ({up['commit_date']})")


# ── Normalization ─────────────────────────────────────────────────────────────

_RUN_ID_RE = re.compile(r"eal-\d{8}T\d{6}-[0-9a-f]{10}")
_ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?\+00:00")
# The git block records the checkout the tool ran from. It changes on every
# commit, and is absent entirely from a tarball or exported copy, so leaving it
# in would make the committed outputs fail to reproduce for exactly the people
# this demo is for. Input provenance is unaffected: it lives in
# demo/provenance.json and in each artifact's input_digests.
_GIT_BLOCK_RE = re.compile(r'"git":\s*\{[^{}]*\}')


def normalize(text: str, tmp_out: Path) -> str:
    """Replace run-varying content with fixed tokens. See module docstring."""
    text = _RUN_ID_RE.sub(RUN_ID_TOKEN, text)
    text = _ISO_RE.sub(TIMESTAMP_TOKEN, text)
    text = _GIT_BLOCK_RE.sub('"git": {"normalized_by_demo_harness": true}', text)
    # Absolute paths differ per machine; make every reference repo-relative.
    text = text.replace(str(tmp_out), "demo/output/<scenario>")
    text = text.replace(str(ROOT) + "/", "")
    text = text.replace(str(ROOT), ".")
    return text


def run_scenario(name: str, description: str, args: list[str], dest: Path) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_out = Path(tmp) / "out"
        proc = subprocess.run(
            [sys.executable, "-m", "eal.cli", "review", *args,
             "--out", str(tmp_out), "--log-level", "ERROR"],
            cwd=ROOT, capture_output=True, text=True,
        )
        if not tmp_out.exists():
            print(f"  {name}: no artifacts produced\n{proc.stderr}", file=sys.stderr)
            raise SystemExit(1)

        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        for artifact in sorted(tmp_out.iterdir()):
            if artifact.is_file():
                (dest / artifact.name).write_text(
                    normalize(artifact.read_text(encoding="utf-8"), tmp_out),
                    encoding="utf-8",
                )

    findings = json.loads((dest / "findings.json").read_text())
    metadata = json.loads((dest / "run_metadata.json").read_text())
    return {
        "scenario": name,
        "description": description,
        "command": "eal review " + " ".join(args),
        "exit_code": proc.returncode,
        "outcome": EXIT_MEANING.get(proc.returncode, "unexpected"),
        "analysis_status": findings["analysis_status"],
        "gate_result": metadata["gate"]["result"],
        "finding_count": findings["finding_count"],
        "coverage_gap_count": findings["coverage_gap_count"],
        "findings": [
            {"severity": f["severity"], "category": f["category"], "title": f["title"]}
            for f in findings["findings"]
        ],
    }


# ── Summary ───────────────────────────────────────────────────────────────────

def write_summary(results: list[dict]) -> None:
    manifest = json.loads(MANIFEST.read_text())
    up = manifest["upstream"]
    lines = [
        "# EAL Demo Results",
        "",
        "Generated by `make demo`. Every input is an unmodified upstream file; no",
        "defects were injected. Run-varying fields (run id, timestamps, absolute",
        "paths) are normalized so these outputs can be diffed — see",
        "`scripts/run_demo.py`.",
        "",
        f"**Upstream:** [{up['repository']}]({up['repository']}) @ `{up['commit']}` "
        f"({up['commit_date']}), retrieved {up['retrieved']}",
        "",
        "| Scenario | Exit | Outcome | Analysis | Findings |",
        "|----------|------|---------|----------|----------|",
    ]
    for r in results:
        lines.append(
            f"| `{r['scenario']}` | {r['exit_code']} | {r['outcome']} | "
            f"{r['analysis_status']} | {r['finding_count']} |"
        )
    lines.append("")

    for r in results:
        lines += [
            f"## {r['scenario']}",
            "",
            r["description"],
            "",
            "```bash",
            r["command"],
            "```",
            "",
            f"Exit `{r['exit_code']}` — {r['outcome']}. "
            f"Analysis status `{r['analysis_status']}`, "
            f"gate `{r['gate_result']}`, "
            f"{r['coverage_gap_count']} coverage gap(s).",
            "",
        ]
        if r["findings"]:
            lines += ["| Severity | Category | Finding |", "|---|---|---|"]
            lines += [
                f"| {f['severity']} | `{f['category']}` | {f['title']} |"
                for f in r["findings"]
            ]
        else:
            lines.append("_No findings._")
        lines += ["", f"Artifacts: [`demo/output/{r['scenario']}/`](output/{r['scenario']}/)", ""]

    (DEMO / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
    (DEMO / "results.json").write_text(
        json.dumps({"upstream": up, "scenarios": results}, indent=2) + "\n",
        encoding="utf-8",
    )


# ── Check mode ────────────────────────────────────────────────────────────────

def check(previous: Path) -> int:
    """Compare freshly generated output against what was committed."""
    differences: list[str] = []
    for expected_dir in sorted(p for p in previous.iterdir() if p.is_dir()):
        actual_dir = OUTPUT / expected_dir.name
        if not actual_dir.exists():
            differences.append(f"{expected_dir.name}: not regenerated")
            continue
        names = {p.name for p in expected_dir.iterdir()} | {p.name for p in actual_dir.iterdir()}
        for name in sorted(names):
            a, b = expected_dir / name, actual_dir / name
            if not a.exists():
                differences.append(f"{expected_dir.name}/{name}: newly produced")
            elif not b.exists():
                differences.append(f"{expected_dir.name}/{name}: no longer produced")
            elif not filecmp.cmp(a, b, shallow=False):
                differences.append(f"{expected_dir.name}/{name}: content differs")

    if differences:
        print("\nDemo reproduction FAILED:", file=sys.stderr)
        for d in differences:
            print(f"  {d}", file=sys.stderr)
        print(
            "\nThe committed demo output no longer matches what the code produces.\n"
            "If the change is intended, run `make demo` and commit the result.",
            file=sys.stderr,
        )
        return 1
    print("\nDemo reproduction OK: committed output matches a fresh run byte-for-byte.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true",
        help="verify the committed demo output still reproduces exactly",
    )
    args = parser.parse_args()

    verify_inputs()

    baseline = None
    if args.check and OUTPUT.exists():
        baseline = Path(tempfile.mkdtemp()) / "baseline"
        shutil.copytree(OUTPUT, baseline)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    print(f"\nRunning {len(SCENARIOS)} scenario(s):")
    results = []
    for name, description, argv in SCENARIOS:
        result = run_scenario(name, description, argv, OUTPUT / name)
        results.append(result)
        print(
            f"  {name:<24} exit {result['exit_code']}  "
            f"{result['outcome']:<38} {result['finding_count']} finding(s)"
        )
    write_summary(results)
    print(f"\nWrote {OUTPUT.relative_to(ROOT)}/ and demo/RESULTS.md")

    if args.check:
        if baseline is None:
            print("No committed demo output to compare against.", file=sys.stderr)
            return 1
        return check(baseline)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
