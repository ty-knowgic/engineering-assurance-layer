# Engineering Assurance Layer (EAL)

**Spec-to-constraint review tool for engineering assurance workflows.**

EAL takes an engineering specification (markdown), an optional model (YAML),
and optional code files, then produces structured review artifacts including
deterministic rule findings, Z3-verified constraint checks, and counterexamples.

It is not a theorem prover. It is not an AI assistant. It is a deterministic
review pipeline that helps engineering teams decide whether a specification is
internally consistent, has declared its assumptions, and is ready for review.

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
10. Emits 10 review artifacts, including SARIF v2.1.0 output
11. Includes a minimal GitHub Actions workflow for test + review + artifact upload

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

### Not Yet Implemented

- Multi-file/cross-document spec linkage
- Symbolic/boolean theorem-proving-style checks beyond current numeric Z3 encoding

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
- `examples/mobile_robot/`
  - Broader mixed scenario with timing/forbidden-condition coverage.

See [docs/examples.md](docs/examples.md) for a command table, and
`examples/manifest.json` for machine-readable expectations.

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
| `counterexamples.json` | Machine-readable counterexample structures from Z3 and rule checks |
| `review_evidence.json` | Run provenance: inputs, IR summary, git info, timestamp |
| `ir_snapshot.json` | Full IR dump (all extracted signals, states, requirements, constraints) |
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
  - Values: `local`, `ci`, `main`, `strict`
  - Default: `local`
  - Built-in defaults:
    - `local` → `fail_on_severity=NONE`, `strictness=balanced`, `min_severity=LOW`
    - `ci` → `fail_on_severity=HIGH`, `strictness=balanced`, `min_severity=LOW`
    - `main` → `fail_on_severity=HIGH`, `strictness=relaxed`, `min_severity=LOW`
    - `strict` → `fail_on_severity=MEDIUM`, `strictness=strict`, `min_severity=LOW`
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
- `1`: pipeline/infrastructure error

This allows CI scripts to distinguish analysis execution failures from policy failures.

---

## GitHub Actions CI

This repo includes a minimal GitHub Actions workflow at
`.github/workflows/eal-ci.yml`.

It runs on `push` and `pull_request` and executes:
1. `pip install -e ".[dev]"`
2. `pytest`
3. `python -m eal.cli review` against `examples/ci_smoke` with
   `--policy-profile ci`
4. publishes `out/ci_smoke_review/results.sarif` to GitHub code scanning

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
`security-events: write` is not available.

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

## Z3 Checks

| Check | Category | Severity |
|-------|----------|----------|
| Global (mode-independent) numeric system → UNSAT | `GLOBAL_CONSTRAINT_CONFLICT` | CRITICAL |
| Signal bounds + constraints in one mode → UNSAT | `UNSAT_IN_MODE` | CRITICAL |
| Full numeric system in a specific mode → UNSAT | `MODE_SCOPED_CONFLICT` | CRITICAL |
| Transition is both required and forbidden | `UNREACHABLE_STATE` | CRITICAL |

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
