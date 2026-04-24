# 1. Validation Families Reviewed

This review covers the three current real-world-ish validation families in the
repository:

- SMACC2-oriented slice:
  `examples/smacc2_atomic_mode_states/`,
  `examples/smacc2_atomic_mode_states_timing_drift/`,
  `examples/smacc2_atomic_mode_states_assumption_gap/`,
  `examples/smacc2_atomic_mode_states_transition_gap/`
- BehaviorTree-oriented slice:
  `examples/behaviortree_timeout_precondition/`,
  `examples/behaviortree_timeout_precondition_guard_gap/`
- ros2_control-oriented slice:
  `examples/ros2_control_joint_limits/`,
  `examples/ros2_control_joint_limits_interface_gap/`

For each family, the review also inspected:

- example `spec.md` and `model.yaml`
- optional illustrative source-style files:
  `controller.py`, `tree.xml`, `controller.yaml`
- `analysis_note.md`
- `docs/examples.md`
- `examples/manifest.json`
- `tests/test_examples_corpus.py`

# 2. Inputs, Commands, and Artifacts Examined

## Inputs Examined

- SMACC2:
  baseline `spec.md` / `model.yaml`, timing-drift `controller.py`,
  and all three `analysis_note.md` files
- BehaviorTree:
  baseline `spec.md` / native `tree.xml`, guard-gap `spec.md` / `model.yaml`,
  and both `analysis_note.md` files
- ros2_control:
  baseline and interface-gap `spec.md` / `model.yaml`,
  illustrative `controller.yaml`, and both `analysis_note.md` files

## Commands Run

```bash
PYTHONPATH=src .venv/bin/python -m eal.cli review --spec examples/smacc2_atomic_mode_states/spec.md --model examples/smacc2_atomic_mode_states/model.yaml --fail-on-severity HIGH --out /tmp/eal_valr1_smacc2_clean
PYTHONPATH=src .venv/bin/python -m eal.cli review --spec examples/smacc2_atomic_mode_states_timing_drift/spec.md --model examples/smacc2_atomic_mode_states_timing_drift/model.yaml --code examples/smacc2_atomic_mode_states_timing_drift/controller.py --fail-on-severity HIGH --out /tmp/eal_valr1_smacc2_timing
PYTHONPATH=src .venv/bin/python -m eal.cli review --spec examples/smacc2_atomic_mode_states_assumption_gap/spec.md --model examples/smacc2_atomic_mode_states_assumption_gap/model.yaml --fail-on-severity HIGH --out /tmp/eal_valr1_smacc2_assumption
PYTHONPATH=src .venv/bin/python -m eal.cli review --spec examples/smacc2_atomic_mode_states_transition_gap/spec.md --model examples/smacc2_atomic_mode_states_transition_gap/model.yaml --fail-on-severity HIGH --out /tmp/eal_valr1_smacc2_transition
PYTHONPATH=src .venv/bin/python -m eal.cli review --spec examples/behaviortree_timeout_precondition/spec.md --bt-xml examples/behaviortree_timeout_precondition/tree.xml --fail-on-severity HIGH --out /tmp/eal_valr1_bt_clean
PYTHONPATH=src .venv/bin/python -m eal.cli review --spec examples/behaviortree_timeout_precondition_guard_gap/spec.md --model examples/behaviortree_timeout_precondition_guard_gap/model.yaml --fail-on-severity HIGH --out /tmp/eal_valr1_bt_guard
PYTHONPATH=src .venv/bin/python -m eal.cli review --spec examples/ros2_control_joint_limits/spec.md --model examples/ros2_control_joint_limits/model.yaml --fail-on-severity HIGH --out /tmp/eal_valr1_ros2_clean
PYTHONPATH=src .venv/bin/python -m eal.cli review --spec examples/ros2_control_joint_limits_interface_gap/spec.md --model examples/ros2_control_joint_limits_interface_gap/model.yaml --fail-on-severity HIGH --out /tmp/eal_valr1_ros2_gap
PYTHONPATH=src .venv/bin/pytest -q
```

## Artifacts Examined

For each run, the following artifacts were inspected:

- `findings.json`
- `review_summary.md`
- `counterexamples.json`
- `review_evidence.json`
- `ir_snapshot.json`
- `run_metadata.json`
- `results.sarif`

Observed facts from the run outputs:

- all eight runs produced the full artifact set above
- all clean baselines passed the `HIGH` gate with zero findings
- all defect variants failed the `HIGH` gate with the expected category
- all `counterexamples.json` files were empty
- SARIF was generated for all runs, including clean baselines

# 3. Family-by-Family Assessment

## SMACC2

What EAL extracted well:

- The baseline extracted a coherent small state/mode slice:
  3 signals, 2 states, 2 modes, 2 transitions, 3 requirements, 11 constraints.
- Requirement linkage in the IR is strongest here.
  `REQ-001` and `REQ-002` link narrowly to matching mode-scoped constraints.
  `REQ-003` links narrowly to `TC-001` and `PARAM-MODE_SWITCH_RESPONSE_MS`.
- The timing-drift variant also carried code evidence through to findings and SARIF.

What findings were useful:

- `CODE_TIMING_MISMATCH` on the timing-drift variant is the strongest single
  finding across the three families. It points to a specific code constant,
  a specific comparison, the declared 100 ms limit, and the matching model
  parameter/timing constraint.
- `MISSING_ASSUMPTION` on the assumption-gap variant is useful because it
  surfaces assurance debt that compile-time and ordinary tests do not usually
  express explicitly.
- `FORBIDDEN_UNCHECKED` on the transition-gap variant is a direct review-level
  signal that a forbidden transition intent is not actually encoded.

What was weak, noisy, or absent:

- The slice is still manually abstracted from SMACC2 concepts rather than
  ingested from SMACC2 source artifacts.
- No solver-backed counterexample was produced; in this family the value came
  from deterministic rules and code matching, not from counterexample search.
- The assumption finding is useful, but still generic. It does not establish
  how strong the missing guarantee must be or whether the real system has some
  other mitigation.

Whether the slice demonstrated real added assurance value:

- Yes. This family shows value beyond compile-time validation because it checks
  cross-artifact consistency that SMACC2 compile-time checks do not cover:
  timing-budget drift, missing safety assumptions, and review-visible forbidden
  condition coverage.

Beyond compile/build/test/runtime:

- Beyond compile-time validation: yes, especially timing drift and assumption visibility.
- Beyond ordinary build/test: yes, because these findings rely on spec/model/code comparison.
- Beyond simulation/runtime testing: partially. It does not replace runtime
  testing, but it can surface drift and missing declarations earlier and more
  structurally than simulation usually does.

## BehaviorTree

What EAL extracted well:

- The baseline extracted a usable state-style abstraction and now also ingests
  `tree.xml` directly for narrow BT evidence:
  5 signals, 7 states, 4 transitions, 3 requirements, 6 constraints, and
  6 assumptions after XML merge.
- The timing requirement `REQ-002` linked cleanly to `TC-001` and to the
  XML-derived `PARAM-BT_TIMEOUT_NAVIGATE_TO_POSE_MS`.
- The retry bound `REQ-003` linked cleanly to `CON-001` and a derived
  requirement constraint.
- The guard-gap variant produced a clean `FORBIDDEN_UNCHECKED` finding for
  `FC-001`, with no extra noise.

What findings were useful:

- `FORBIDDEN_UNCHECKED` is useful here because it exposes a real review issue:
  the spec still requires `localization_ready`, but the modeled precheck no
  longer enforces it.

What was weak, noisy, or absent:

- `REQ-001` did not become a first-class linked requirement in the IR.
  It has no `requirement_classes`; it only links indirectly to `FC-001` and
  `FC-002` through shared signals.
- Native XML ingestion is intentionally narrow. It extracts condition leaves,
  explicit `Timeout msec`, and fallback/precondition visibility, but the state
  transition slice and retry policy are still specified manually in `spec.md`.
- The slice demonstrates timeout-backed recovery intent only at the abstraction
  level. It does not validate decorator ordering, fallback semantics, or BT
  execution behavior.

Whether the slice demonstrated real added assurance value:

- Yes, but narrower than SMACC2.
  It shows that EAL can catch missing precondition enforcement and produce clean
  review artifacts around timeout and fallback intent.

Beyond compile/build/test/runtime:

- Beyond compile-time validation: yes, because BT XML/runtime frameworks do not
  usually give this kind of cross-artifact precondition review.
- Beyond ordinary build/test: yes, if the defect is subtle enough not to break tests.
- Beyond simulation/runtime testing: partially. It can flag a missing guard
  before running scenarios, but it does not reason about BT runtime semantics.

## ros2_control

What EAL extracted well:

- The baseline extracted a plausible controller/interface abstraction:
  8 signals, 4 states, 5 transitions, 4 requirements, 11 constraints.
- The limit requirement `REQ-002` linked cleanly to `CON-001`,
  `REQC-REQ-002-01`, and `MCON-001`.
- The hardware-error timing requirement `REQ-003` linked cleanly to `TC-001`
  and `PARAM-HARDWARE_ERROR_REACTION_MS`.
- The interface-gap variant produced a single `FORBIDDEN_UNCHECKED` finding for
  `FC-002`, which is a useful signal for missing state-feedback enforcement.

What findings were useful:

- `FORBIDDEN_UNCHECKED` usefully catches interface readiness drift:
  the spec still requires velocity feedback readiness, but the activation guard
  no longer enforces it.

What was weak, noisy, or absent:

- `REQ-001` did not become a first-class linked requirement in the IR.
  Like the BT precondition requirement, it only links indirectly through
  forbidden conditions.
- `REQ-004` is classified as `timing` in the IR but has no linked constraints,
  despite a matching `ACTIVE -> INACTIVE` transition and a `command_timeout_ms`
  model parameter. That is a concrete extraction/linkage weakness.
- The illustrative `controller.yaml` is not ingested directly.
- The slice does not validate real ros2_control interface negotiation,
  lifecycle semantics, controller-manager behavior, or hardware plugin behavior.

Whether the slice demonstrated real added assurance value:

- Yes. It shows that EAL can produce actionable review output around
  interface-guard drift, limit declarations, and bounded error handling.
  But the value is still constrained by the manual abstraction.

Beyond compile/build/test/runtime:

- Beyond compile-time validation: yes, because the issue is review-level drift
  between declared interface expectations and the modeled activation logic.
- Beyond ordinary build/test: yes, especially for config/spec mismatches that
  might not be exercised by current tests.
- Beyond simulation/runtime testing: partially. It can catch drift earlier, but
  it does not replace hardware-in-the-loop or lifecycle testing.

# 4. Cross-Family Comparison

- Extraction viability:
  all three families are viable once expressed in EAL's markdown+YAML format.
  SMACC2 currently has the cleanest requirement linkage.
  BehaviorTree and ros2_control still show gaps on precondition/lifecycle-style requirements.
- Assurance yield:
  SMACC2 is highest. It covers a clean baseline plus three distinct defect
  classes, including a code-backed timing drift check.
  BehaviorTree and ros2_control currently each demonstrate one main defect
  pattern well: guard omission.
- False-positive risk:
  low in these curated fixtures. The emitted findings were specific and the
  clean baselines stayed clean.
  The caution is that the fixtures are manually abstracted and therefore already
  partially normalized for EAL.
- Actionability of findings:
  high for the findings that do fire.
  Each emitted finding points to a specific missing guard, missing assumption,
  or mismatched timing declaration with concrete source references.
- Fit into PR / design-review / CI workflow:
  strong.
  The combination of `review_summary.md`, `findings.json`, `run_metadata.json`,
  `review_evidence.json`, and `results.sarif` is well-suited to gated review workflows.
- Realism of the slice:
  credible but bounded.
  The domains are realistic; the ingestion path is still hand-authored EAL IR input.
- Dependence on manual abstraction:
  high across all three families.
  This is the largest factor limiting external credibility.
- Support for EAL's intended positioning:
  good for a narrow claim:
  deterministic cross-artifact review for small robotics assurance slices.
  not yet good for a broad claim about direct assurance of large robotics stacks.

# 5. Strongest Assurance Slice EAL Delivers Today

The two strongest slices today are:

- Cross-artifact drift detection when there is an explicit numeric limit or
  timing budget to match across spec, model, and optional code.
  Best evidence: the SMACC2 timing-drift slice.
- Forbidden/guard omission detection in small state-oriented or activation-style
  slices.
  Best evidence: SMACC2 transition gap, BehaviorTree guard gap, and ros2_control
  interface gap.

These are the areas where EAL currently produces the clearest review value with
the least ambiguity.

# 6. Weakest Current Areas

- Manual abstraction burden remains high.
  All three families rely on hand-authored markdown+YAML slices.
  The illustrative BT XML and ros2_control YAML are not actually ingested.
- Requirement-to-constraint linkage is still uneven outside SMACC2.
  BehaviorTree `REQ-001` and ros2_control `REQ-001` are only indirectly linked.
  ros2_control `REQ-004` is effectively unlinked.
- Timing semantics are still shallow.
  EAL can match explicit numeric timing declarations, but not richer timeout or
  execution semantics.
- Counterexample output is not carrying weight in these slices.
  All eight runs produced empty `counterexamples.json`.
  In practice, the current value is coming from deterministic rule checks and
  code matching, not from solver-driven explanation.
- Category granularity is still limited for some review problems.
  Both the BT guard gap and ros2_control interface gap collapse into the same
  `FORBIDDEN_UNCHECKED` category, which is correct but not especially specific.

# 7. What EAL Can Honestly Claim Now

Based on these three validation families, EAL can credibly claim that it can:

- deterministically review small manually abstracted robotics assurance slices
  expressed as spec/model artifacts
- emit structured CI-friendly review outputs, including SARIF and stable JSON artifacts
- catch specific cross-artifact timing/limit drift when those declarations are explicit
- catch missing guard coverage for forbidden conditions in state/activation-style slices
- surface missing safety assumptions as explicit review findings
- maintain low-noise clean baselines on curated validation fixtures

That is a real and useful assurance-adjacent review capability.
It is not a claim of broad correctness or comprehensive robotics verification.

# 8. What EAL Still Cannot Claim

EAL still cannot credibly claim that it:

- proves correctness of SMACC2, BehaviorTree.CPP, ros2_control, or any larger robotics stack
- replaces compile-time validation, ordinary unit/integration testing,
  simulation, hardware-in-the-loop, or runtime validation
- understands full SMACC2, BehaviorTree.CPP, or ros2_control semantics directly from their native artifacts
- ingests arbitrary real repositories directly with broad fidelity
- produces meaningful solver-backed counterexample evidence on these current slices
- covers lifecycle, timing, fallback, and interface semantics with deep behavioral precision

# 9. Overall Verdict

EAL now has a credible but narrow assurance envelope.

Fact:

- Across all three families, EAL produced stable artifacts, kept curated clean
  baselines clean, and caught the injected defects with specific categories.
- The best evidence is strongest where the slice can be reduced to explicit
  bounds, timing budgets, missing guards, and missing assumptions.

Inference:

- EAL is currently best understood as a deterministic cross-artifact review and
  gating tool for small, manually abstracted robotics assurance slices.
- That is enough to support disciplined PR/design-review/CI positioning.
- It is not yet enough to justify broad claims about direct assurance of
  real robotics frameworks at repository scale.

# 10. Recommended Next Move

Improve extraction fidelity before expanding to a larger target.

Why this is the best next move:

- The current three-family review already exposes the main limitation:
  the abstraction is useful once written, but intent is still lost in linkage,
  especially for BehaviorTree and ros2_control precondition/lifecycle requirements.
- Expanding immediately to a larger target such as Nav2 or OpenRMF would scale
  the current weaknesses faster than it would scale assurance value.
- A tighter next round should focus on:
  preserving requirement intent more reliably,
  improving linkage for precondition and lifecycle-style requirements,
  and reducing dependence on manual normalization of source-style artifacts.

If that step succeeds, the next larger validation target will say more about
EAL itself and less about hand-curated fixture quality.
