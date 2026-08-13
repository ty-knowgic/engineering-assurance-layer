#!/usr/bin/env python3
"""
Phase 3 adversarial evaluation.

    make eval          run the catalogue, regenerate eval/RESULTS.md
    make eval-check    verify the committed results still reproduce

Applies each mutation in eval/mutations.yaml to a copy of an unmodified upstream
Nav2 config, runs EAL against it, and compares the outcome to the expectation
recorded in the catalogue *before* the harness was written.

Two numbers are reported and they measure different things:

  detection rate   over mutations that introduce a real hazard, how many did
                   EAL say anything about. This is the number that describes the
                   tool. A mutation being a documented capability gap does not
                   remove it from the denominator -- the hazard is real whether
                   or not we anticipated being blind to it.

  prior accuracy   how often the expectation matched what happened. This
                   measures how well the author understands the tool, not how
                   good the tool is. A wrong prior is reported, never edited to
                   match the outcome.

The harness never rewrites mutations.yaml. If an expectation turns out wrong,
that is a result.
"""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "eval"
CATALOGUE = EVAL / "mutations.yaml"
OUTPUT = EVAL / "output"
SPEC = ROOT / "demo" / "spec" / "nav2_motion_limits.md"
PROVENANCE = ROOT / "demo" / "provenance.json"

HAZARD_ORDER = {"none": 0, "low": 1, "moderate": 2, "severe": 3}


def verify_inputs(catalogue: dict) -> None:
    manifest = {e["local_path"]: e["sha256"] for e in json.loads(PROVENANCE.read_text())["files"]}
    for key, rel in catalogue["base_files"].items():
        actual = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
        if manifest.get(rel) != actual:
            print(f"Base file {rel} does not match recorded provenance.", file=sys.stderr)
            raise SystemExit(1)
    print(f"Base file provenance OK ({len(catalogue['base_files'])} files)")


def apply_edits(text: str, mutation: dict) -> str:
    edits = mutation.get("edits") or [mutation["edit"]]
    for edit in edits:
        find, replace = edit["find"], edit["replace"]
        count = text.count(find)
        if count == 0:
            raise SystemExit(f"{mutation['id']}: anchor not found: {find!r}")
        occurrence = edit.get("occurrence")
        if occurrence is None and count > 1:
            raise SystemExit(
                f"{mutation['id']}: anchor {find!r} matches {count} times; "
                "set `occurrence` to disambiguate"
            )
        text = text.replace(find, replace, occurrence or count)
    return text


def run_eal(params_path: Path, out_dir: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "eal.cli", "review",
         "--spec", str(SPEC), "--nav2-params", str(params_path),
         "--policy-profile", "ci", "--out", str(out_dir), "--log-level", "ERROR"],
        cwd=ROOT, capture_output=True, text=True,
    )
    findings_path = out_dir / "findings.json"
    if not findings_path.exists():
        return {"exit_code": proc.returncode, "crashed": True, "stderr": proc.stderr[-2000:]}
    findings = json.loads(findings_path.read_text())
    metadata = json.loads((out_dir / "run_metadata.json").read_text())
    return {
        "exit_code": proc.returncode,
        "crashed": False,
        "analysis_status": findings["analysis_status"],
        "gate_result": metadata["gate"]["result"],
        "categories": sorted({f["category"] for f in findings["findings"]}),
        # Category alone is too coarse to diff against a baseline that already
        # fails: a mutation that worsens an existing finding (1.20x -> 7.50x)
        # changes no category and would read as "EAL said nothing".
        "signatures": sorted({f"{f['category']}|{f['title']}" for f in findings["findings"]}),
        "findings": [
            {"severity": f["severity"], "category": f["category"], "title": f["title"],
             "source_refs": f.get("source_refs", []),
             "suggested_fix": f.get("suggested_fix", ""),
             "summary": f.get("summary", "")}
            for f in findings["findings"]
        ],
        "coverage_gaps": [g["category"] for g in findings["coverage_gaps"]],
    }


def actionable(finding: dict) -> bool:
    """
    Proxy for whether a finding can be acted on without further investigation.

    This is NOT a measurement of human repair time -- that needs a human, and
    inventing a number for it would be worse than admitting the gap. What is
    measured is whether the finding names where to look and what to change:
    at least two source references and a non-empty suggested fix.
    """
    return len(finding["source_refs"]) >= 2 and bool(finding["suggested_fix"].strip())


def judge(mutation: dict, baseline: dict, actual: dict) -> dict:
    expect = mutation["expect"]
    outcome = expect["outcome"]
    new_signatures = sorted(set(actual.get("signatures", [])) - set(baseline["signatures"]))
    new_categories = sorted({s.split("|", 1)[0] for s in new_signatures})
    incomplete = actual.get("analysis_status") == "INPUTS_NOT_FULLY_READ"
    said_something = bool(new_signatures) or incomplete

    if actual.get("crashed"):
        verdict, detail = "CRASH", "EAL produced no artifacts"
    elif outcome == "DETECT":
        missing = [c for c in expect.get("categories", []) if c not in actual["categories"]]
        if missing:
            verdict = "PARTIAL" if actual["categories"] != baseline["categories"] else "MISSED"
            detail = f"expected categories absent: {', '.join(missing)}"
        else:
            verdict, detail = "DETECTED", "all expected categories present"
    elif outcome == "UNKNOWN":
        verdict = "DETECTED" if incomplete else "MISSED"
        detail = ("inputs not fully read" if incomplete else "reported inputs fully read")
    elif outcome == "MISS":
        verdict = "SILENT_AS_EXPECTED" if not said_something else "DETECTED_UNEXPECTEDLY"
        detail = "nothing fired" if not said_something else f"fired: {new_categories}"
    elif outcome == "NO_NEW_FINDINGS":
        verdict = "CLEAN" if not said_something else "FALSE_POSITIVE"
        detail = "no new findings" if not said_something else f"spurious: {new_signatures}"
    else:
        verdict, detail = "UNKNOWN_EXPECTATION", outcome

    prior_correct = verdict in ("DETECTED", "SILENT_AS_EXPECTED", "CLEAN")
    hazard = mutation["hazard"]
    # The denominator for detection rate: real hazards, regardless of whether we
    # predicted being blind to them.
    hazardous = HAZARD_ORDER[hazard] >= HAZARD_ORDER["moderate"]

    return {
        "verdict": verdict,
        "detail": detail,
        "prior_correct": prior_correct,
        "hazardous": hazardous,
        "eal_said_something": said_something,
        "new_categories": new_categories,
        "new_signatures": new_signatures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    catalogue = yaml.safe_load(CATALOGUE.read_text())
    verify_inputs(catalogue)
    bases = {k: ROOT / v for k, v in catalogue["base_files"].items()}

    baseline_dir = Path(tempfile.mkdtemp())
    baselines = {k: run_eal(p, baseline_dir / f"base_{k}") for k, p in bases.items()}
    for key, b in baselines.items():
        print(f"  baseline {key:<6} exit {b['exit_code']}  categories={b['categories']}")

    previous = None
    if args.check and OUTPUT.exists():
        previous = Path(tempfile.mkdtemp()) / "prev"
        shutil.copytree(OUTPUT, previous)

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)

    results = []
    print(f"\nRunning {len(catalogue['mutations'])} mutation(s):")
    with tempfile.TemporaryDirectory() as tmp:
        for mutation in catalogue["mutations"]:
            base_path = bases[mutation["base"]]
            mutated = Path(tmp) / f"{mutation['id']}_{base_path.name}"
            mutated.write_text(apply_edits(base_path.read_text(), mutation))

            first = run_eal(mutated, Path(tmp) / f"{mutation['id']}_out1")
            second = run_eal(mutated, Path(tmp) / f"{mutation['id']}_out2")
            reproducible = (
                first.get("signatures") == second.get("signatures")
                and first.get("analysis_status") == second.get("analysis_status")
                and first.get("exit_code") == second.get("exit_code")
            )

            verdict = judge(mutation, baselines[mutation["base"]], first)
            findings = first.get("findings", [])
            record = {
                "id": mutation["id"],
                "category": mutation["category"],
                "description": mutation["description"],
                "hazard": mutation["hazard"],
                "expected": mutation["expect"]["outcome"],
                "expected_categories": mutation["expect"].get("categories", []),
                "rationale": " ".join(mutation["rationale"].split()),
                "exit_code": first.get("exit_code"),
                "analysis_status": first.get("analysis_status"),
                "new_categories": verdict["new_categories"],
                "new_findings": verdict["new_signatures"],
                "finding_count": len(findings),
                "actionable_findings": sum(1 for f in findings if actionable(f)),
                "reproducible": reproducible,
                **{k: verdict[k] for k in ("verdict", "detail", "prior_correct",
                                           "hazardous", "eal_said_something")},
            }
            results.append(record)
            flag = "" if record["prior_correct"] else "   <-- prior was wrong"
            print(f"  {record['id']}  {record['category']:<28} {record['verdict']:<22}"
                  f" hazard={record['hazard']:<8}{flag}")

    write_report(catalogue, baselines, results)
    print(f"\nWrote {OUTPUT.relative_to(ROOT)}/ and eval/RESULTS.md")

    if args.check:
        if previous is None:
            print("No committed results to compare against.", file=sys.stderr)
            return 1
        diffs = [
            f.name for f in sorted(previous.iterdir())
            if not (OUTPUT / f.name).exists()
            or not filecmp.cmp(f, OUTPUT / f.name, shallow=False)
        ]
        if diffs:
            print(f"\nEval reproduction FAILED: {', '.join(diffs)}", file=sys.stderr)
            print("If the change is intended, run `make eval` and commit.", file=sys.stderr)
            return 1
        print("Eval reproduction OK: committed results match a fresh run.")
    return 0


def write_report(catalogue: dict, baselines: dict, results: list[dict]) -> None:
    hazardous = [r for r in results if r["hazardous"]]
    detected_hazards = [r for r in hazardous if r["eal_said_something"]]
    false_positives = [r for r in results if r["verdict"] == "FALSE_POSITIVE"]
    missed = [r for r in results if r["verdict"] == "MISSED"]
    wrong_priors = [r for r in results if not r["prior_correct"]]
    silent_gaps = [r for r in hazardous if not r["eal_said_something"]]
    with_findings = [r for r in results if r["finding_count"]]

    detection_rate = len(detected_hazards) / len(hazardous) if hazardous else 0.0
    prior_accuracy = sum(r["prior_correct"] for r in results) / len(results)
    actionability = (
        sum(r["actionable_findings"] for r in with_findings)
        / sum(r["finding_count"] for r in with_findings)
    ) if with_findings else 0.0

    summary = {
        "mutations": len(results),
        "hazardous_mutations": len(hazardous),
        "hazards_detected": len(detected_hazards),
        "detection_rate_over_hazards": round(detection_rate, 3),
        "silent_on_real_hazard": len(silent_gaps),
        "false_positives": len(false_positives),
        "expected_detections_missed": len(missed),
        "prior_accuracy": round(prior_accuracy, 3),
        "wrong_priors": [r["id"] for r in wrong_priors],
        "reproducible": all(r["reproducible"] for r in results),
        "actionability_of_emitted_findings": round(actionability, 3),
    }
    # Baselines are stored as a path-free projection. The full finding objects
    # carry source_refs containing the absolute path of the fixture and of the
    # per-run temporary directory, which differ on every machine and every run;
    # committing them would make eval-check fail for anyone but the author.
    portable_baselines = {
        key: {
            "exit_code": b["exit_code"],
            "analysis_status": b.get("analysis_status"),
            "gate_result": b.get("gate_result"),
            "categories": b.get("categories", []),
            "signatures": b.get("signatures", []),
        }
        for key, b in baselines.items()
    }
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (OUTPUT / "results.json").write_text(
        json.dumps({"baselines": portable_baselines, "results": results}, indent=2) + "\n"
    )

    up = json.loads(PROVENANCE.read_text())["upstream"]
    lines = [
        "# Phase 3 — Adversarial Evaluation",
        "",
        "Generated by `make eval`. Each mutation is applied to an unmodified upstream",
        f"Nav2 config from `{up['commit'][:10]}`; expectations were recorded in",
        "`eval/mutations.yaml` before the harness ran and are never edited to match",
        "the outcome.",
        "",
        "## Headline",
        "",
        f"**EAL said something about {len(detected_hazards)} of {len(hazardous)} mutations "
        f"that introduce a real hazard ({detection_rate:.0%}).**",
        "",
        f"- Silent on a real hazard: **{len(silent_gaps)}**",
        f"- False positives on harmless edits: **{len(false_positives)}**",
        f"- Expected detections that did not fire: **{len(missed)}**",
        f"- Re-run agreement: **{'100%' if summary['reproducible'] else 'NOT reproducible'}**",
        f"- Author's prior correct: {prior_accuracy:.0%}"
        + (f" (wrong on {', '.join(summary['wrong_priors'])})" if wrong_priors else ""),
        "",
        "Detection rate is computed over every hazardous mutation, including those",
        "the catalogue predicted would be missed. A documented blind spot is still a",
        "blind spot; excusing it would turn this report into an advertisement.",
        "",
        "## History of this catalogue",
        "",
        " ".join(catalogue["first_run"].split()),
        "",
        "## Results",
        "",
        "| ID | Category | Hazard | Expected | Verdict | EAL output |",
        "|----|----------|--------|----------|---------|------------|",
    ]
    for r in results:
        said = ", ".join(f"`{c}`" for c in r["new_categories"]) or (
            "UNKNOWN" if r["analysis_status"] == "INPUTS_NOT_FULLY_READ" else "_silent_"
        )
        lines.append(
            f"| {r['id']} | {r['category']} | {r['hazard']} | {r['expected']} | "
            f"{r['verdict']} | {said} |"
        )

    lines += ["", "## Hazards EAL is silent about", ""]
    if silent_gaps:
        lines.append(
            "These introduce moderate or severe real-world risk and produce no output "
            "at all. They define the true shape of the analysis envelope."
        )
        lines.append("")
        for r in silent_gaps:
            lines += [f"### {r['id']} — {r['description']}", "",
                      f"**Hazard:** {r['hazard']}", "", r["rationale"], ""]
    else:
        lines.append("_None._")

    if wrong_priors:
        lines += ["", "## Where the author's expectation was wrong", "",
                  "Recorded rather than corrected; a wrong prior about one's own tool is",
                  "itself a finding.", ""]
        for r in wrong_priors:
            lines += [
                f"- **{r['id']}** ({r['description']}): expected `{r['expected']}`, "
                f"got `{r['verdict']}` — {r['detail']}",
            ]

    lines += [
        "",
        "## Measurement notes",
        "",
        f"- **Actionability of emitted findings: {actionability:.0%}** — the share that name",
        "  at least two source locations and a concrete fix. This is a proxy. **Human",
        "  repair time was not measured**; that requires a human, and inventing a number",
        "  would be worse than recording the gap.",
        "- **Re-run agreement** compares two runs of every mutation in the same",
        "  environment. Cross-environment reproducibility is covered separately by",
        "  `make demo-check`, which is byte-for-byte from a clean checkout.",
        "- Mutations are applied to a temporary copy; the fixtures are never modified,",
        "  and their hashes are verified against `demo/provenance.json` before the run.",
        "",
    ]
    (EVAL / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
