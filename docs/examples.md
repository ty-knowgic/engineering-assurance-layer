# Example Corpus

This document describes the purpose of each example fixture in `examples/`.

| Example | Role | Expected Behavior | Recommended Command |
|---|---|---|---|
| `ci_smoke` | Passing CI smoke fixture | Passes `--fail-on-severity HIGH`; produces zero or low-severity noise only | `python -m eal.cli review --spec examples/ci_smoke/spec.md --model examples/ci_smoke/model.yaml --fail-on-severity HIGH --out out/ci_smoke_review` |
| `robotics_arm` | Intentionally failing multi-issue demo | Produces multiple deterministic, solver, and code-derived findings | `python -m eal.cli review --spec examples/robotics_arm/spec.md --model examples/robotics_arm/model.yaml --code examples/robotics_arm/controller.py --out out/robotics_arm_review` |
| `mode_scope_demo` | Focused mode-scoped satisfiability demo | No false global contradiction; unsat reported in a specific mode (`UNSAT_IN_MODE`/`MODE_SCOPED_CONFLICT`) | `python -m eal.cli review --spec examples/mode_scope_demo/spec.md --model examples/mode_scope_demo/model.yaml --out out/mode_scope_demo_review` |
| `code_mismatch_demo` | Focused code/spec/model mismatch demo | Emits `CODE_BOUND_MISMATCH` and `CODE_TIMING_MISMATCH` from Python `--code` | `python -m eal.cli review --spec examples/code_mismatch_demo/spec.md --model examples/code_mismatch_demo/model.yaml --code examples/code_mismatch_demo/controller.py --out out/code_mismatch_demo_review` |
| `boundary_clean` | Low-noise boundary case | Designed to avoid known noisy code findings around limit boundaries | `python -m eal.cli review --spec examples/boundary_clean/spec.md --model examples/boundary_clean/model.yaml --code examples/boundary_clean/controller.py --fail-on-severity HIGH --out out/boundary_clean_review` |

Machine-readable expectations for these examples are in `examples/manifest.json`.
