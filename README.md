# Engineering Assurance Layer (EAL)

**Spec-to-constraint review tool for engineering assurance workflows.**

EAL takes an engineering specification (markdown), an optional model (YAML),
and optional code files, then produces structured review artifacts including
deterministic rule findings, Z3-verified constraint checks, and counterexamples.

It is not a theorem prover. It is not an AI assistant. It is a deterministic
review pipeline that helps engineering teams decide whether a specification is
internally consistent, has declared its assumptions, and is ready for review.

Project positioning and strategic boundaries: [docs/positioning.md](docs/positioning.md).

---

## What Problem It Solves

Engineering specifications accumulate problems that are invisible to casual review:

- Signal bounds are declared in requirements but never formalized
- Forbidden conditions have no guard in the state machine
- Timing requirements have no corresponding timing parameter
- Constraints are satisfied on paper but contradict the model's declared bounds
- Assumptions are implicit ("the sensor will detect this") but never stated

EAL surfaces these issues deterministically — no LLM, no randomness — and
produces machine-readable artifacts that can feed CI gates or human review workflows.

---

## Current Capability (v0.0.2)

1. Parses a structured markdown specification (see Input Format below)
2. Merges an optional YAML model (signals, states, modes, transitions, parameters)
3. Builds an Internal Representation (IR) — signals, states, constraints, requirements
4. Statically analyzes Python `--code` files (AST) for constants and comparisons
5. Runs deterministic rules, including spec/model/code mismatch checks
6. Runs mode-aware Z3-backed constraint satisfiability checks
7. Applies severity-threshold CI gate behavior (`--fail-on-severity`)
8. Supports deterministic rule strictness profiles (`--strictness relaxed|balanced|strict`)
9. Supports built-in policy profiles for operational contexts (`--policy-profile`)
10. Ingests a narrow BehaviorTree XML slice via `--bt-xml`
11. Ingests real upstream Nav2 parameter YAML via `--nav2-params` (MPPI and DWB)
12. Reports `PASS / FAIL / UNKNOWN`, where UNKNOWN means analysis coverage was incomplete
13. Emits 10 review artifacts, including SARIF v2.1.0 output
14. Includes a minimal GitHub Actions workflow for test + review + artifact upload

---

## Current Status

### Implemented

- Deterministic extraction/rules pipeline with artifact-first outputs
- Python code-aware checks for constants/comparisons via `ast`
- Mode-scoped constraint representation and conditional Z3 encoding
- Severity-threshold gate exit behavior (`0` pass, `2` threshold fail, `1` pipeline error)
- Rule strictness control for suppressing low-confidence heuristic findings
- Built-in policy profiles with explicit-flag override precedence
- SARIF emission (`results.sarif`) derived from canonical findings
- Minimal GitHub Actions CI workflow (`.github/workflows/eal-ci.yml`)

### Experimental / Narrow by Design

- Markdown extraction remains regex/section-pattern based
- Python static analysis covers simple constants/comparisons only
- Mode-scope extraction supports only explicit deterministic phrase patterns
- BehaviorTree XML ingestion is a narrow review-evidence wedge, not full BT semantics

### Not Yet Implemented

- Multi-file/cross-document spec linkage
- Symbolic/boolean theorem-proving-style checks beyond current numeric Z3 encoding

---

## Reproduce the Demo

One command, from a fresh clone:

```bash
make verify
```

That creates a virtualenv, installs the package, runs the test suite, then
regenerates the demo from four **unmodified upstream Nav2 files** and checks the
result against the committed output byte-for-byte. No network access and no ROS
installation are required.

The demo runs four scenarios and shows all three outcomes on real input:

| Scenario | Input | Exit | Outcome |
|----------|-------|------|---------|
| `nav2_dwb_coherent` | `nav2_system_params.yaml` (DWB) | 0 | PASS, 0 findings |
| `nav2_mppi_bringup` | `nav2_params.yaml` (MPPI) | 2 | FAIL, 3 findings |
| `nav2_mppi_no_map` | `nav2_no_map_params.yaml` (MPPI) | 2 | FAIL, 6 findings |
| `nav2_bt_unanalyzable` | `navigate_to_pose_w_replanning_and_recovery.xml` | 3 | UNKNOWN |

Results and the full artifact set for each are committed under
[`demo/`](demo/) — see [`demo/RESULTS.md`](demo/RESULTS.md). You can read what
the tool produces without installing anything.

**Input provenance.** [`demo/provenance.json`](demo/provenance.json) pins the
upstream repository, commit, and the SHA-256 of every third-party file. The
runner verifies those hashes before executing and refuses to run if any fixture
has been modified — a demo on altered input proves nothing. The manifest
includes a `verify_command` so you can re-check the hashes against upstream
yourself.

**Why the committed outputs are normalized.** Artifacts embed a run id,
timestamps, and the git checkout the tool ran from. Those change every run, and
the git block is absent entirely from an exported copy — so committing them raw
would make the outputs fail to reproduce for exactly the people the demo is for.
The demo harness replaces those fields with fixed tokens *after* the run.
Normalization lives in `scripts/run_demo.py`, never in the product: real runs
keep their real run ids, timestamps, and git info. Input provenance is not
normalized away — each artifact still carries the SHA-256 of its inputs in
`review_evidence.json`.

Other targets: `make test`, `make lint`, `make demo`, `make demo-check`,
`make eval`, `make eval-check`.

---

## What EAL Does Not Catch

`make eval` runs an adversarial mutation evaluation: 23 edits to unmodified
upstream Nav2 configs, each with the hazard it introduces and the expected EAL
outcome recorded in [`eval/mutations.yaml`](eval/mutations.yaml) **before** the
harness ran. Expectations are never edited to match results. Full report:
[`eval/RESULTS.md`](eval/RESULTS.md).

**EAL says something about 8 of the 19 mutations that introduce a real hazard
(42%). It is silent on the other 11.** Zero false positives on harmless edits.

The detection rate is computed over every hazardous mutation, including ones the
catalogue predicted would be missed. A documented blind spot is still a blind
spot.

The silent cases share a shape worth stating plainly: **the limit-coherence
check compares two declarations against each other, so any edit that keeps them
agreeing is invisible, no matter how dangerous the agreed value is.** Examples
that produce no output at all:

- speed raised 8x coherently on both controller and smoother (DWB, no horizon rule to catch it)
- braking weakened 6x coherently on both sides
- sensor marking range cut from 2.5 m to 0.4 m, so the robot cannot see far enough to stop
- control loop slowed from 20 Hz to 2 Hz
- a smoother claiming 100 m/s² of braking, roughly 10 g
- a unit error applied consistently to both sides

EAL has no model of stopping distance, latency, or physical plausibility, and no
notion of what magnitude is reasonable for a quantity. It checks that
declarations agree with each other and that one upstream-documented horizon rule
holds. That is the entire envelope.

---

## Quick Start

```bash
# Install
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run on the robotics arm example (has intentional issues)
python -m eal.cli review \
  --spec examples/robotics_arm/spec.md \
  --model examples/robotics_arm/model.yaml \
  --code examples/robotics_arm/controller.py \
  --out out/robotics_arm_review

# Run on the mobile robot example
python -m eal.cli review \
  --spec examples/mobile_robot/spec.md \
  --model examples/mobile_robot/model.yaml \
  --out out/mobile_robot_review

# Run on CI smoke example (expected to pass HIGH gate threshold)
python -m eal.cli review \
  --spec examples/ci_smoke/spec.md \
  --model examples/ci_smoke/model.yaml \
  --fail-on-severity HIGH \
  --out out/ci_smoke_review

# Run the BehaviorTree-oriented slice using native tree.xml ingestion
python -m eal.cli review \
  --spec examples/behaviortree_timeout_precondition/spec.md \
  --bt-xml examples/behaviortree_timeout_precondition/tree.xml \
  --fail-on-severity HIGH \
  --out out/behaviortree_timeout_precondition_review

# CI gate examples
# Fail only on CRITICAL findings
python -m eal.cli review \
  --spec examples/robotics_arm/spec.md \
  --model examples/robotics_arm/model.yaml \
  --fail-on-severity CRITICAL \
  --out out/robotics_arm_gate_critical

# Fail on HIGH and above
python -m eal.cli review \
  --spec examples/robotics_arm/spec.md \
  --model examples/robotics_arm/model.yaml \
  --fail-on-severity HIGH \
  --out out/robotics_arm_gate_high
```

---

## Example Corpus

Examples are organized by role so they can be used for demos, regression checks,
and rule-tuning without mixing passing and intentionally failing behavior.

- `examples/ci_smoke/`
  - Passing CI smoke fixture used by GitHub Actions.
- `examples/robotics_arm/`
  - Intentionally failing multi-issue demo (rules + solver + code mismatch signals).
- `examples/mode_scope_demo/`
  - Focused mode-scoped contradiction demo (mode-local UNSAT without false global conflict).
- `examples/code_mismatch_demo/`
  - Focused Python code/spec/model mismatch demo.
- `examples/boundary_clean/`
  - Low-noise boundary case for false-positive regression checks.
- `examples/complex_control_system/`
  - Validation testbed for multi-mode control envelopes, timing, and code threshold mismatches.
- `examples/system_interlock_demo/`
  - Validation testbed for interlock structure quality, forbidden-condition coverage, and code threshold mismatches.
- `examples/subsystem_interface_review/`
  - Validation testbed for subsystem boundary/interface consistency across modes and timing expectations.
- `examples/smacc2_atomic_mode_states/`
  - Real-world validation slice based on SMACC2 `sm_atomic_mode_states` concepts; intentionally modeled as a clean assurance baseline.
- `examples/smacc2_atomic_mode_states_timing_drift/`
  - SMACC2-oriented defect injection: code timing constant drifts above declared mode-switch timing budget.
- `examples/smacc2_atomic_mode_states_assumption_gap/`
  - SMACC2-oriented defect injection: safety-relevant e-stop declarations without supporting reliability assumption.
- `examples/smacc2_atomic_mode_states_transition_gap/`
  - SMACC2-oriented defect injection: forbidden transition intent declared in spec but not encoded in transition guards.
- `examples/behaviortree_timeout_precondition/`
  - BehaviorTree-oriented validation slice for precondition gating, timeout-backed recovery intent, and bounded retry policy; the clean baseline uses native `tree.xml` ingestion.
- `examples/behaviortree_timeout_precondition_guard_gap/`
  - BehaviorTree-oriented defect injection: spec requires `localization_ready`, but the modeled precheck omits that guard.
- `examples/ros2_control_joint_limits/`
  - ros2_control-oriented validation slice for activation interface expectations, joint command limits, and bounded error handling.
- `examples/ros2_control_joint_limits_interface_gap/`
  - ros2_control-oriented defect injection: spec requires velocity feedback readiness, but the modeled activation guard omits it.
- `examples/mobile_robot/`
  - Broader mixed scenario with timing/forbidden-condition coverage.

See [docs/examples.md](docs/examples.md) for a command table, and
`examples/manifest.json` for machine-readable expectations.
See [docs/validation-review-round1.md](docs/validation-review-round1.md) for an
integrated technical assessment of the current SMACC2, BehaviorTree, and
ros2_control validation families.

---

## Input Format

### Markdown Spec

The spec must use `##` section headings. All sections are optional but the
more you include, the more checks EAL can perform.

```markdown
## Entities
- robot_arm: 6-DOF manipulator arm

## Signals
- joint_speed: sensor, rad/s, bounds=[0, 2.5]
- motor_torque: actuator, Nm, bounds=[0, 100]
- human_detected: sensor, bool, bounds=[0, 1]

## Modes
- NORMAL: standard operation
- CALIBRATION: calibration routine

## States
- IDLE: waiting for task
- OPERATING: executing motion plan
- SAFE_STOP: emergency halt

## Transitions
- OPERATING -> SAFE_STOP: guard=e_stop=true
- SAFE_STOP -> IDLE: guard=fault_cleared

## Requirements
- REQ-001: Joint speed must remain <= 1.2 rad/s in calibration mode.
- REQ-002: The gripper must not close when human_detected = true.

## Assumptions
- ASM-001: The proximity sensor latency is < 10 ms.

## Safety Constraints
- CON-001: motor_torque <= 10 Nm when mode = MAINTENANCE

## Forbidden Conditions
- FC-001: gripper_force > 0 when human_detected = true

## Timing Constraints
- TC-001: OPERATING -> SAFE_STOP within 100 ms of e_stop activation
```

**Signal format:** `- name: kind, unit, bounds=[min, max]`
- `kind`: `sensor | actuator | internal | mode | timing | derived`
- `bounds` is optional but required for Z3 checks

**Requirement format:** `- REQ-NNN: requirement text`

Requirement linkage in `ir_snapshot.json` is selective and inspectable:
each requirement records `requirement_classes`, linked `parsed_constraints`,
and `linkage_reasons` explaining why a constraint was attached.

**Constraint formats:**
- Safety Constraints: `- CON-NNN: expression`
- Forbidden Conditions: `- FC-NNN: expression`
- Timing Constraints: `- TC-NNN: expression`

**Assumption format:** `- ASM-NNN: assumption text`

**Transition format:** `- FROM_STATE -> TO_STATE: guard=condition`

**Mode-scoped constraint syntax (deterministic patterns):**
- `... in CALIBRATION mode`
- `... only in NORMAL mode`
- `... when mode = MAINTENANCE`

### BehaviorTree XML

`--bt-xml PATH` ingests a narrow, deterministic subset of BehaviorTree-style
XML as additional review evidence. It currently supports:

- `Sequence` and `Fallback` structure for simple branch visibility
- `Timeout msec="N"` decorators as timing parameters
- `Precondition` decorators with an explicit `if`, `condition`, `expression`, or `cond` attribute
- `Action` and `Condition` leaves with `ID` or `name`
- simple custom leaf tags with no children, recorded only as leaf evidence

The importer maps condition leaves to boolean internal signals, action leaves
to traceability states, timeout decorators to `bt_timeout_<action>_ms`
parameters, and explicit precondition/fallback evidence to assumptions. It
does not implement full BehaviorTree.CPP execution semantics, blackboard
resolution, port typing, decorator ordering, or arbitrary XML node behavior.

### Nav2 Parameter YAML (`--nav2-params`)

`--nav2-params PATH` reads a **real, unmodified upstream Nav2 parameter file** —
not an EAL-shaped abstraction of one. It is currently the only importer that
does so.

It extracts the motion limits a Nav2 stack declares in two independent places,
plus the supporting values those limits must be consistent with:

| Source | Extracted |
|--------|-----------|
| `controller_server.<plugin_key>` | max/min linear velocity, max angular velocity, linear accel/decel, angular accel |
| `velocity_smoother` | the same six roles, from the `[x, y, theta]` limit vectors |
| `controller_server` | `controller_frequency`, `costmap_update_timeout` |
| MPPI plugin block | `time_steps`, `model_dt` |
| `local_costmap` | `update_frequency`, `width`, `height`, `resolution`, `robot_radius` |
| inflation layer | `inflation_radius`, `cost_scaling_factor` |
| observation sources | `obstacle_max_range`, `obstacle_min_range`, `raytrace_max_range` |

Values are normalized to **plugin-independent roles** (`v_max_linear`,
`a_decel_linear`, …) so the same downstream logic works across controllers. Only
the parameter-name mapping is per-plugin:

| Role | MPPI | DWB |
|------|------|-----|
| `v_max_linear` | `vx_max` | `max_vel_x` |
| `v_min_linear` | `vx_min` | `min_vel_x` |
| `v_max_angular` | `wz_max` | `max_vel_theta` |
| `a_accel_linear` | `ax_max` | `acc_lim_x` |
| `a_decel_linear` | `ax_min` | `decel_lim_x` |
| `a_accel_angular` | `az_max` | `acc_lim_theta` |

Every extracted value keeps the exact dotted YAML path it came from, e.g.
`controller_server.ros__parameters.FollowPath.ax_min`, so a finding can name the
line a human has to go edit. The plugin config key is read from
`controller_plugins` rather than assumed to be `FollowPath`.

The importer only extracts and records provenance. Comparing the values is done
separately (see Nav2 Coherence Checks below), so that an extraction bug and a
check bug cannot hide inside each other.

**Unrecognised controller plugins are reported as UNKNOWN, never guessed at.**
Only MPPI and DWB have mappings, because those are the only ones validated
against a real upstream file. Inventing a mapping for an unvalidated plugin
would produce confident nonsense.

Fixtures and expected values live in `tests/fixtures/nav2_upstream_params/` and
`tests/test_nav2_params.py`. The expected values were transcribed by reading the
YAML by hand, not by running the parser — an extractor validated against its own
output validates nothing.

Not extracted, and therefore not available to any check: sensor and actuator
latency (absent from every Nav2 config file), and actual obstacle clearance
(runtime state, not configuration).

### YAML Model

```yaml
entities:
  - name: robot_arm
    description: 6-DOF manipulator

signals:
  - name: joint_speed
    kind: sensor
    unit: rad/s
    bounds:
      min: 0
      max: 2.5

states:
  - name: IDLE
  - name: OPERATING

modes:
  - name: NORMAL
  - name: CALIBRATION

transitions:
  - from: IDLE
    to: OPERATING
    guard: "task_ready == true"
  - from: OPERATING
    to: SAFE_STOP
    guard: "e_stop == true"
    forbidden: false

parameters:
  max_speed_calibration: 1.2
  estop_response_ms: 100

invariants:
  - "motor_torque <= 120 at all times"

mode_constraints:
  - id: MCON-001
    mode: CALIBRATION
    signal: joint_speed
    operator: <=
    value: 1.2
```

Parameters are ingested as named numeric values and can be referenced by
timing constraint checks.

### Python Code Inputs (`--code`)

EAL V0.0.2 performs a first static-analysis pass on Python files:

- module-level numeric assignments (`MAX_JOINT_SPEED = 1.5`)
- simple class attributes (`class Limits: ESTOP_RESPONSE_MS = 150`)
- simple comparisons with numeric thresholds in `if`/`assert`/`while`
  (for example `joint_speed > 1.5`, `assert estop_response_ms <= 100`)

Extracted code evidence is added to the IR as:
- `code_constants`
- `code_comparisons`
- `code_evidence`

Each extracted symbol is conservatively classified as:
- `signal_bound_candidate`
- `timing_parameter_candidate`
- `generic_numeric_constant`

Name matching is deterministic and conservative:
- lowercase normalization
- strip max/min prefixes and common limit suffixes
- unit normalization for time suffixes (`milliseconds` → `ms`)
- alias normalization for common emergency-stop spellings (`e_stop` → `estop`)
- ontology-aware gating: timing candidates are matched to timing declarations first,
  and bound candidates are matched to signal/bound declarations

This pass is intentionally narrow: no symbolic execution, no interprocedural flow,
and no dynamic/runtime analysis.

---

## Output Artifacts

All artifacts are written to `--out` directory. All are always written,
even if empty (explicit status markers prevent silent omissions).

| File | Contents |
|------|----------|
| `review_summary.md` | Human-readable summary: finding counts, IR summary, top findings |
| `constraint_violations.md` | All CRITICAL and HIGH findings with full detail |
| `missing_assumptions.md` | MISSING_ASSUMPTION findings with suggested fixes |
| `counterexamples.json` | Solver evidence, separated by kind: minimal unsat cores, witnesses, structural conflicts |
| `review_evidence.json` | Run provenance: inputs, SHA-256 of every input file, IR summary, git info, timestamp |
| `ir_snapshot.json` | Full IR dump, including selective requirement linkage metadata (`requirement_classes`, `parsed_constraints`, `linkage_reasons`) |
| `findings.json` | All findings in stable schema (id, severity, category, title, summary, fix) |
| `results.sarif` | SARIF v2.1.0 transform of canonical findings for IDE/CI ingestion |
| `report.html` | Simple HTML report with sortable findings table |
| `run_metadata.json` | Run ID, version, review status, gate config/result, finding counts |

`run_metadata.json` also records strictness profile and strictness-suppressed finding counts.

### SARIF Output

EAL always emits `results.sarif` as a deterministic transform of `findings.json`.
No rules are re-run for SARIF generation.

Severity mapping:
- `CRITICAL` → `error`
- `HIGH` → `error`
- `MEDIUM` → `warning`
- `LOW` → `note`

Location mapping:
- `source_refs` entries like `path:line` map to SARIF physical locations
- first source ref is the primary location
- additional source refs are emitted as related locations

Current limitation:
- only path + line (+ optional column when present) are parsed from source refs

---

## CLI Gate Options

`eal review` supports deterministic severity-threshold gating:

- `--policy-profile <NAME>`
  - Values: `local`, `ci`, `main`, `prod`, `strict`
  - Default: `local`
  - Built-in defaults:
    - `local` → `fail_on_severity=NONE`, `strictness=balanced`, `min_severity=LOW`, `fail_on_unknown=false`
    - `ci` → `fail_on_severity=HIGH`, `strictness=balanced`, `min_severity=LOW`, `fail_on_unknown=true`
    - `main` → `fail_on_severity=HIGH`, `strictness=relaxed`, `min_severity=LOW`, `fail_on_unknown=true`
    - `strict` → `fail_on_severity=MEDIUM`, `strictness=strict`, `min_severity=LOW`, `fail_on_unknown=true`
- `--fail-on-unknown` / `--no-fail-on-unknown`
  - Exit `3` when analysis coverage is incomplete (overrides the profile default)
  - Does not affect reporting: UNKNOWN appears in all artifacts either way
- `--fail-on-severity <LEVEL>`
  - Values: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `NONE`
  - Default via policy profile (`local` resolves to `NONE`)
  - Semantics: fail when highest finding severity is at or above the threshold
- `--min-severity <LEVEL>`
  - Values: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`
  - Default via policy profile (all built-ins currently resolve to `LOW`)
  - Affects terminal table and `review_summary.md` top-findings presentation
  - Does not remove findings from canonical machine-readable artifacts (`findings.json`)
- `--strictness <PROFILE>`
  - Values: `relaxed`, `balanced`, `strict`
  - Default via policy profile (`local` resolves to `balanced`)
  - `relaxed`: suppresses low-confidence heuristic rule findings
  - `balanced`: standard default profile
  - `strict`: includes all currently implemented heuristic findings
  - Solver findings and high-confidence deterministic contradictions are unaffected

Precedence:
- Explicit CLI flags override profile defaults (`--fail-on-severity`, `--min-severity`, `--strictness`).
- `run_metadata.json` records selected profile, effective values, and whether each value came from profile defaults or explicit flags.

### Exit Codes

- `0`: review completed and gate passed
- `2`: review completed and gate threshold exceeded
- `3`: analysis coverage incomplete (UNKNOWN) and the profile blocks on UNKNOWN
- `1`: pipeline/infrastructure error

This allows CI scripts to distinguish analysis execution failures from policy
failures, and both of those from *an analysis that did not actually cover the
input*. Exit `3` takes precedence over `2`.

---

## Analysis Coverage and the UNKNOWN Result

A finding says "I analyzed this and found a problem". A **coverage gap** says
"I could not analyze this, so my silence about it means nothing".

EAL's importers are narrow by design. Given input they do not model, the honest
answer is UNKNOWN, not PASS. When any coverage gap is detected:

- `findings.json` → `status: "analysis_incomplete"`, plus `analysis_status`,
  `coverage_gap_count`, and a `coverage_gaps[]` array
- `run_metadata.json` → `results.status: "UNKNOWN"`, `gate.result: "UNKNOWN"`,
  `gate.exit_reason: "ANALYSIS_COVERAGE_INCOMPLETE"`, and a `coverage` block
- `results.sarif` → one result per gap under rule id `EAL_COVERAGE_<CATEGORY>`
  at level `warning`, plus `invocations[0].properties.analysisStatus`
- `review_summary.md` / `report.html` → a coverage section above the findings
- exit code → `3` when the profile blocks on UNKNOWN

Coverage is a **separate plane from severity**, not a fifth severity level.
Severity is an ordered scale driving gate thresholds; coverage is orthogonal to
it. Folding UNKNOWN into `FindingSeverity` would corrupt every threshold
comparison and let unanalyzable input masquerade as a graded result.

### Coverage gap categories

| Category | Fires when |
|----------|-----------|
| `UNSUPPORTED_INPUT_CONSTRUCT` | An importer named constructs it does not model (BehaviorTree nodes outside the supported subset; a Nav2 controller plugin with no validated mapping) |
| `AMBIGUOUS_INPUT` | The same key is declared twice with different values. YAML keeps the last, so the file may read differently to a human than to the parser |
| `INCOMPLETE_COMPARISON` | A cross-artifact check ran but one side of some quantity is absent, so those quantities were not compared |
| `INPUT_YIELDED_NO_CONTENT` | An input file was explicitly supplied but contributed nothing to the IR |
| `NO_ANALYZABLE_CONTENT` | The merged IR has no signals, constraints, or transitions, so no check could have fired |

Detection is deliberately conservative — a false UNKNOWN destroys trust in the
gate as surely as a false PASS does. Each rule fires only on an unambiguous
signal, and contribution is measured as a before/after IR delta rather than
trusted from the loader. All 17 curated examples report `COMPLETE`.

### Reporting vs blocking

Reporting is always honest; blocking is a policy decision. The `local` profile
reports UNKNOWN in every artifact but still exits `0`, so exploratory runs stay
non-blocking. All other profiles exit `3`. Override with
`--fail-on-unknown` / `--no-fail-on-unknown`.

### Known-limitation regression fixtures

`tests/fixtures/nav2_upstream_bt/` holds five unmodified behavior trees from
`ros-navigation/navigation2` @ `075b29611a7d21ff4f1c74077a17c672e708001c`
(retrieved 2026-08-13). EAL cannot analyze them — they are built from
`RecoveryNode`, `PipelineSequence`, `ReactiveSequence`, `RateController`,
`Inverter`, `ReactiveFallback`, and `RoundRobin`, none of which the importer
models. `tests/test_coverage.py` asserts that every one of them yields UNKNOWN
rather than a zero-finding PASS in every machine-readable plane.

---

## GitHub Actions CI

This repo includes a minimal GitHub Actions workflow at
`.github/workflows/eal-ci.yml`.

It runs on `push` and `pull_request` and executes:
1. `pip install -e ".[dev]"`
2. `pytest`
3. `python -m eal.cli review` against `examples/ci_smoke` with
   `--policy-profile ci`
4. attempts to publish `out/ci_smoke_review/results.sarif` to GitHub code scanning

The workflow uploads `out/ci_smoke_review` as a build artifact, which includes
`findings.json`, `review_summary.md`, `run_metadata.json`, `results.sarif`,
`report.html`, and the other emitted review artifacts.

The same canonical `results.sarif` file is used for both artifact preservation
and GitHub code scanning upload (no parallel SARIF generation in CI).

`examples/robotics_arm` and `examples/mobile_robot` intentionally contain issues
for demonstration/testing, so CI uses the dedicated passing smoke fixture to
avoid permanent workflow failure from intentionally failing examples.

GitHub code scanning visibility depends on repository settings and token
permissions. Upload is skipped for fork-based pull requests where
`security-events: write` is not available. SARIF publication is best-effort and
does not determine CI pass/fail; the EAL smoke review gate result remains the
authoritative signal.

---

## Deterministic Rules

| Rule | Category | Severity | Confidence | Strictness sensitivity |
|------|----------|----------|------------|-----------------------|
| Actuator/sensor signal without upper bound | `MISSING_BOUND` | MEDIUM | high | always-on |
| Requirement mentions snake_case token not in Signals | `UNDEFINED_REFERENCE` | HIGH | medium | always-on |
| Transition references state not in States | `TRANSITION_GAP` | HIGH | high | always-on |
| Forbidden condition with no guard or assumption | `FORBIDDEN_UNCHECKED` | HIGH | high | always-on |
| Timing requirement with no timing parameter | `TIMING_GAP` | MEDIUM | medium | always-on |
| Safety-critical signal with no reliability assumption | `MISSING_ASSUMPTION` | HIGH | medium | always-on |
| Signal min bound violates a `<=` constraint | `CONTRADICTORY_CONSTRAINT` | CRITICAL | high | always-on |
| Code constant/comparison exceeds declared bound | `CODE_BOUND_MISMATCH` | HIGH | high | always-on |
| Code timing constant/threshold exceeds declared timing | `CODE_TIMING_MISMATCH` | HIGH | high | always-on |
| Code parameter appears related but unmodeled | `CODE_UNMODELED_PARAMETER` | MEDIUM | low | heuristic (suppressed in `relaxed`) |

## Nav2 Coherence Checks

Run automatically when `--nav2-params` is supplied.

### (A) Controller / velocity_smoother limit coherence

A Nav2 stack declares its motion limits twice. The verified command chain
(`nav2_bringup/launch/navigation_launch.py` remappings) is:

```
controller_server -> cmd_vel_nav -> velocity_smoother
    -> cmd_vel_smoothed -> collision_monitor -> cmd_vel -> base
```

so the smoother's limits are what the base actually receives and the
controller's are a request. A text diff of `vx_max: 0.5 -> 2.0` cannot tell you
whether the two still agree. This check compares them by magnitude, per role.

**Direction determines the finding, and the three cases are not equivalent:**

| Case | Category | Severity |
|------|----------|----------|
| Controller > smoother, on **acceleration** | `NAV2_ACCEL_OVERDECLARED` | HIGH |
| Controller > smoother, on **velocity** | `NAV2_VELOCITY_OVERDECLARED` | MEDIUM |
| Controller < smoother, either quantity | `NAV2_LIMIT_HEADROOM` | LOW, `strict` only |

Acceleration is separated out because the controller rolls out and validates
candidate trajectories against its own figure. If the chain delivers less
braking than assumed, a trajectory accepted as collision-free may not be
achievable — that leans unsafe. Over-declared *velocity* only means the robot
executes more slowly than planned: a model-fidelity problem, not an unsafe one.

The informational third case is `strict`-only because it was measured to be
noise: on the real corpus it fired twice, once for 5% of unused angular envelope
and once for DWB's `min_vel_x: 0.0`, which just means the robot does not
reverse. Both are dismissed by any reviewer. The direction *distinction* is
enforced at every strictness level — the conservative case is never reported as
a mismatch.

**The check does not decide whether a mismatch is a defect.** That depends on
intent, which is not in the file: a generically-tuned controller paired with a
platform-tuned smoother produces this legitimately. Findings report both values,
both YAML paths, and the direction, and say so explicitly.

If a stack has no `velocity_smoother`, the comparison is inapplicable and stays
silent. That is not the same as UNKNOWN and does not raise a coverage gap.

### (B) MPPI prediction horizon vs local costmap

Not EAL's model — the rule is stated in the upstream
`nav2_mppi_controller/README.md`:

```
time_steps * model_dt * vx_max  <=  min(costmap width, height) / 2
```

When the prediction horizon at maximum speed overruns the costmap radius, the
planner is reasoning about space it has no map data for and the robot is
artificially limited by the costmap. Category
`NAV2_HORIZON_EXCEEDS_COSTMAP`, MEDIUM. Silently inapplicable to controllers
that declare no `time_steps`/`model_dt`.

### Results on the real corpus

All three fixtures are unmodified upstream files at the same commit. No defects
were injected.

| Fixture | Controller | Result |
|---------|-----------|--------|
| `nav2_system_params.yaml` | DWB | **PASS** — all six roles agree |
| `nav2_params.yaml` | MPPI | **FAIL** — 3x `NAV2_ACCEL_OVERDECLARED` (1.20x, 1.20x, 1.09x) |
| `nav2_no_map_params.yaml` | MPPI | **FAIL** — the same 3, plus 3x `NAV2_VELOCITY_OVERDECLARED` (1.92x, 1.90x, 1.35x) |

The horizon rule passes on both MPPI configs, but only just:
`56 x 0.05 x 0.5 = 1.400 m` against a `1.500 m` radius, a 6.7% margin. Raising
`vx_max` to `0.54` alone breaks it — which is the point of the check, since that
edit looks harmless in a diff.

---

## Z3 Checks

| Check | Category | Severity |
|-------|----------|----------|
| Global (mode-independent) numeric system → UNSAT | `GLOBAL_CONSTRAINT_CONFLICT` | CRITICAL |
| Signal bounds + constraints in one mode → UNSAT | `UNSAT_IN_MODE` | CRITICAL |
| Full numeric system in a specific mode → UNSAT | `MODE_SCOPED_CONFLICT` | CRITICAL |
| Transition is both required and forbidden | `UNREACHABLE_STATE` | CRITICAL |

### Unsat cores, not counterexamples

An unsatisfiable system has no satisfying assignment, so there is no model to
report and nothing that can honestly be called a counterexample. What EAL
reports instead is a **minimal unsat core**: the smallest set of declared facts
that is still jointly contradictory. That is the more useful artifact anyway —
it names the handful of declarations a human has to reconcile rather than
everything that happened to be asserted.

Facts are added to the solver as `selector => fact` and satisfiability is
queried with the selectors as assumptions, so a fact can genuinely be withdrawn.
Z3's `unsat_core()` returns an unsat but not necessarily irreducible subset, so
each core is then minimized by deletion — drop one fact, re-check, keep the drop
if the remainder is still unsat. The result is irreducible, and
`tests/test_unsat_core.py` verifies that by brute force over proper subsets
rather than trusting the minimizer that produced it.

Cores name **signal bounds and the one-mode-active rule**, not only constraint
IDs, because a bound is frequently half of the contradiction. On
`examples/robotics_arm` the core is:

```
declared bound joint_speed >= 1.5
joint_speed <= 1.2 rad/s when mode = CALIBRATION
```

Two facts, one of them a bound that earlier output never mentioned, and with the
redundant `REQC-REQ-001-01` correctly excluded.

`counterexamples.json` separates the kinds and counts them apart, so nothing is
filed as a counterexample that is not one:

| Key | Contents |
|-----|----------|
| `counterexamples` / `counterexample_count` | Witness models. Currently always empty — nothing produces them yet |
| `unsat_cores` / `unsat_core_count` | Minimal cores, each with `core`, `core_size`, `core_constraint_ids`, `minimal` |
| `other_evidence` | Non-solver findings, e.g. `structural_conflict` |

---

## Tests

```bash
pip install -e ".[dev]"
pytest
```

Tests are 100% offline — no external APIs, no network calls required.

```
tests/test_extraction.py   — markdown parsing
tests/test_ir.py           — IR schema and helpers
tests/test_code_analysis.py — Python AST extraction
tests/test_matching.py     — deterministic code/spec name matching
tests/test_policy.py       — built-in policy profile resolution + override precedence
tests/test_rules.py        — each rule individually + full run on examples
tests/test_solver.py       — Z3 checks including UNSAT case
tests/test_cli.py          — end-to-end CLI smoke tests on both examples
tests/test_examples_corpus.py — role-based example corpus expectations
tests/test_coverage.py     — UNKNOWN plane; real upstream Nav2 trees must never report PASS
tests/test_nav2_params.py  — Nav2 param extraction vs hand-read values on real upstream files
tests/test_nav2_coherence.py — Nav2 limit-coherence and horizon checks, incl. direction regression
tests/test_demo.py         — demo fixture provenance and committed-output integrity
tests/test_unsat_core.py   — core minimality verified by brute force over proper subsets
tests/test_eval.py         — adversarial catalogue integrity; asserts the tool still fails cases
```

---

## What Is Reused from Synthetic Danger

See `docs/synthetic_danger_reuse_report.md` for the full breakdown.

Short version:
- **Kept**: CLI skeleton, artifact-first output pattern, run_id/git provenance, rule-per-function design, offline test pattern
- **Refactored**: Finding schema (removed ECO fields, added counterexample), HTML report writer
- **Not reused**: Hazard taxonomy, ECO schema, LLM integration, manufacturing-specific rules

---

## Limitations (v0.0.2)

- No LLM — extraction is regex/section-based and requires the structured markdown format
- Extraction quality depends on spec authoring discipline
- Z3 checks only work on numeric bounds; boolean/symbolic constraints not yet encoded
- Mode scoping supports only explicit deterministic patterns listed above
- Python static analysis currently covers only simple constants/comparisons
- Strictness control currently suppresses only explicitly marked heuristic rules
- Real ROS 2 artifact ingestion is limited to Nav2 parameter YAML for the MPPI
  and DWB controllers. Real BehaviorTree files from upstream Nav2 produce
  UNKNOWN, not analysis — see the regression fixtures above
- Nav2 coherence covers declared limits and the documented horizon rule only.
  It does not model stopping distance, sensor or actuator latency (absent from
  every Nav2 config file), or actual obstacle clearance (runtime state)
- The `TIMING_GAP` rule's trigger regex matches the word "within" without
  distinguishing temporal from spatial use, so a requirement like "must fit
  within the costmap" is misread as a timing requirement. Known false positive,
  not yet fixed
- No genuine counterexamples are produced. Every solver finding is an UNSAT
  result, which has no model to report; the tool emits minimal unsat cores
  instead (see below). Producing a witness would mean searching for a model
  that violates a desired property, which is not implemented
- The `UNREACHABLE_STATE` check (transition both required and forbidden) cannot
  be reached through any supported input. The spec extractor never marks a
  transition forbidden, and the model merger dedups transitions by
  `(from, to)`, so a model entry cannot flip a pair the spec already declared.
  The rule fires only on hand-constructed IR

---

## Roadmap

### V0.0.3
- Broaden mode-scoped extraction beyond the current deterministic phrase patterns
- Broaden Python checks to include additional guard patterns and more robust constant propagation
- Further reduce false positives with tighter context-aware matching heuristics
- Add optional user-defined profile files on top of built-in policy profiles

### V0.1.0
- LLM-assisted extraction pass (optional, requires API key)
- Spec linter / authoring guide enforcer
- Multi-file spec support
- Cross-reference validation across spec + code + model

---

## License

This project is licensed under the [Apache License 2.0](LICENSE).
Copyright 2026 Tetsu Yamaguchi
