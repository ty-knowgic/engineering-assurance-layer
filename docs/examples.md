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
| `smacc2_atomic_mode_states_timing_drift` | Validation testbed: SMACC2 timing drift injection | Detects cross-artifact timing budget drift (`CODE_TIMING_MISMATCH`) when code constants diverge from spec/model timing limits | `python -m eal.cli review --spec examples/smacc2_atomic_mode_states_timing_drift/spec.md --model examples/smacc2_atomic_mode_states_timing_drift/model.yaml --code examples/smacc2_atomic_mode_states_timing_drift/controller.py --fail-on-severity HIGH --out out/smacc2_atomic_mode_states_timing_drift_review` |
| `smacc2_atomic_mode_states_assumption_gap` | Validation testbed: SMACC2 assumption gap injection | Detects missing safety assumption coverage (`MISSING_ASSUMPTION`) for e-stop-related declarations | `python -m eal.cli review --spec examples/smacc2_atomic_mode_states_assumption_gap/spec.md --model examples/smacc2_atomic_mode_states_assumption_gap/model.yaml --fail-on-severity HIGH --out out/smacc2_atomic_mode_states_assumption_gap_review` |
| `smacc2_atomic_mode_states_transition_gap` | Validation testbed: SMACC2 transition guard gap injection | Detects transition-intent drift (`FORBIDDEN_UNCHECKED`) when a forbidden mode switch condition is declared but not encoded in transition guards | `python -m eal.cli review --spec examples/smacc2_atomic_mode_states_transition_gap/spec.md --model examples/smacc2_atomic_mode_states_transition_gap/model.yaml --fail-on-severity HIGH --out out/smacc2_atomic_mode_states_transition_gap_review` |
| `behaviortree_timeout_precondition` | Validation testbed: BehaviorTree-oriented timeout/precondition slice | Clean BT-inspired review slice with preconditions, timeout-backed recovery, and bounded retry policy; intended for review artifact quality, not BT correctness proof | `python -m eal.cli review --spec examples/behaviortree_timeout_precondition/spec.md --model examples/behaviortree_timeout_precondition/model.yaml --fail-on-severity HIGH --out out/behaviortree_timeout_precondition_review` |
| `behaviortree_timeout_precondition_guard_gap` | Validation testbed: BehaviorTree-oriented guard drift injection | Detects guard/precondition drift (`FORBIDDEN_UNCHECKED`) when `localization_ready` is required in spec but omitted from the modeled precheck | `python -m eal.cli review --spec examples/behaviortree_timeout_precondition_guard_gap/spec.md --model examples/behaviortree_timeout_precondition_guard_gap/model.yaml --fail-on-severity HIGH --out out/behaviortree_timeout_precondition_guard_gap_review` |
| `ros2_control_joint_limits` | Validation testbed: ros2_control-oriented controller/interface slice | Clean controller review slice with activation preconditions, joint command limits, and bounded error reaction; intended for review artifact quality, not controller correctness proof | `python -m eal.cli review --spec examples/ros2_control_joint_limits/spec.md --model examples/ros2_control_joint_limits/model.yaml --fail-on-severity HIGH --out out/ros2_control_joint_limits_review` |
| `ros2_control_joint_limits_interface_gap` | Validation testbed: ros2_control-oriented interface guard drift injection | Detects interface/guard drift (`FORBIDDEN_UNCHECKED`) when `velocity` feedback readiness is required in spec but omitted from the modeled activation guard | `python -m eal.cli review --spec examples/ros2_control_joint_limits_interface_gap/spec.md --model examples/ros2_control_joint_limits_interface_gap/model.yaml --fail-on-severity HIGH --out out/ros2_control_joint_limits_interface_gap_review` |

Machine-readable expectations for these examples are in `examples/manifest.json`.

## Validation Testbeds

`complex_control_system`, `system_interlock_demo`, `subsystem_interface_review`,
`smacc2_atomic_mode_states`, the SMACC2 defect variants, and the
BehaviorTree-oriented timeout/precondition slice, and the ros2_control-oriented
joint-limits slice are
validation-oriented testbeds.

They are intentionally richer than smoke fixtures and are used to probe EAL's practical assurance envelope:
- current strengths: deterministic structure checks, mode-scoped numeric contradictions, code/spec/model threshold mismatches
- current limits: no full control-theory proof, no full distributed protocol verification, no temporal model checking

For the SMACC2 slices specifically:

- `examples/smacc2_atomic_mode_states/analysis_note.md` for the clean baseline
- `examples/smacc2_atomic_mode_states_timing_drift/analysis_note.md` for timing drift injection
- `examples/smacc2_atomic_mode_states_assumption_gap/analysis_note.md` for assumption-gap injection
- `examples/smacc2_atomic_mode_states_transition_gap/analysis_note.md` for transition-guard gap injection

For the BehaviorTree-oriented slice:

- `examples/behaviortree_timeout_precondition/analysis_note.md` for the clean baseline
- `examples/behaviortree_timeout_precondition_guard_gap/analysis_note.md` for guard-gap injection

For the ros2_control-oriented slice:

- `examples/ros2_control_joint_limits/analysis_note.md` for the clean baseline
- `examples/ros2_control_joint_limits_interface_gap/analysis_note.md` for interface-gap injection

These BT-oriented fixtures are intentionally narrow. They test whether EAL can
produce useful spec/model review artifacts around preconditions, timeout-backed
fallback intent, and guard drift. They do not claim full BehaviorTree.CPP
semantic understanding or runtime verification.

The ros2_control-oriented fixtures are similarly narrow. They test whether EAL
can produce useful review artifacts around controller activation preconditions,
state-interface expectations, joint command limits, and lifecycle/error-handling
intent. They do not claim full ros2_control semantic understanding, runtime
controller verification, or hardware-in-the-loop coverage.

Use these fixtures to benchmark practical review value and false-positive behavior as rules evolve.
