# Example Corpus

This document describes the purpose of each example fixture in `examples/`.

| Example | Role | Expected Behavior | Recommended Command |
|---|---|---|---|
| `ci_smoke` | Passing CI smoke fixture | Passes `--fail-on-severity HIGH`; produces zero or low-severity noise only | `python -m eal.cli review --spec examples/ci_smoke/spec.md --model examples/ci_smoke/model.yaml --fail-on-severity HIGH --out out/ci_smoke_review` |
| `robotics_arm` | Intentionally failing multi-issue demo | Produces multiple deterministic, solver, and code-derived findings | `python -m eal.cli review --spec examples/robotics_arm/spec.md --model examples/robotics_arm/model.yaml --code examples/robotics_arm/controller.py --out out/robotics_arm_review` |
| `mode_scope_demo` | Focused mode-scoped satisfiability demo | No false global contradiction; unsat reported in a specific mode (`UNSAT_IN_MODE`/`MODE_SCOPED_CONFLICT`) | `python -m eal.cli review --spec examples/mode_scope_demo/spec.md --model examples/mode_scope_demo/model.yaml --out out/mode_scope_demo_review` |
| `code_mismatch_demo` | Focused code/spec/model mismatch demo | Emits `CODE_BOUND_MISMATCH` and `CODE_TIMING_MISMATCH` from Python `--code` | `python -m eal.cli review --spec examples/code_mismatch_demo/spec.md --model examples/code_mismatch_demo/model.yaml --code examples/code_mismatch_demo/controller.py --out out/code_mismatch_demo_review` |
| `boundary_clean` | Low-noise boundary case | Designed to avoid known noisy code findings around limit boundaries | `python -m eal.cli review --spec examples/boundary_clean/spec.md --model examples/boundary_clean/model.yaml --code examples/boundary_clean/controller.py --fail-on-severity HIGH --out out/boundary_clean_review` |
| `complex_control_system` | Validation testbed: multi-mode process control | Mode-scoped contradiction + code bound/timing mismatches on a richer control scenario | `python -m eal.cli review --spec examples/complex_control_system/spec.md --model examples/complex_control_system/model.yaml --code examples/complex_control_system/controller.py --out out/complex_control_system_review` |
| `system_interlock_demo` | Validation testbed: interlock + structure quality | Interlock coverage gaps, undefined references/transition targets, and code threshold mismatches | `python -m eal.cli review --spec examples/system_interlock_demo/spec.md --model examples/system_interlock_demo/model.yaml --code examples/system_interlock_demo/controller.py --out out/system_interlock_demo_review` |
| `subsystem_interface_review` | Validation testbed: subsystem boundary review | Interface-boundary declaration issues plus code threshold mismatches across modes | `python -m eal.cli review --spec examples/subsystem_interface_review/spec.md --model examples/subsystem_interface_review/model.yaml --code examples/subsystem_interface_review/controller.py --out out/subsystem_interface_review` |
| `smacc2_atomic_mode_states` | Validation testbed: real-world SMACC2 assurance slice | Meaningful clean baseline on a minimal SMACC2-style state machine abstraction; validates structural/mode/timing consistency | `python -m eal.cli review --spec examples/smacc2_atomic_mode_states/spec.md --model examples/smacc2_atomic_mode_states/model.yaml --fail-on-severity HIGH --out out/smacc2_atomic_mode_states_review` |

Machine-readable expectations for these examples are in `examples/manifest.json`.

## Validation Testbeds

`complex_control_system`, `system_interlock_demo`, `subsystem_interface_review`, and `smacc2_atomic_mode_states` are validation-oriented testbeds.

They are intentionally richer than smoke fixtures and are used to probe EAL's practical assurance envelope:
- current strengths: deterministic structure checks, mode-scoped numeric contradictions, code/spec/model threshold mismatches
- current limits: no full control-theory proof, no full distributed protocol verification, no temporal model checking

For the SMACC2 slice specifically, see `examples/smacc2_atomic_mode_states/analysis_note.md` for source-traceability and limits framing.

Use these fixtures to benchmark practical review value and false-positive behavior as rules evolve.
