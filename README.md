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
8. Emits 10 review artifacts, including SARIF v2.1.0 output
9. Includes a minimal GitHub Actions workflow for test + review + artifact upload

---

## Current Status

### Implemented

- Deterministic extraction/rules pipeline with artifact-first outputs
- Python code-aware checks for constants/comparisons via `ast`
- Mode-scoped constraint representation and conditional Z3 encoding
- Severity-threshold gate exit behavior (`0` pass, `2` threshold fail, `1` pipeline error)
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

- `--fail-on-severity <LEVEL>`
  - Values: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `NONE`
  - Default: `NONE` (preserves historical behavior: completed reviews do not fail process)
  - Semantics: fail when highest finding severity is at or above the threshold
- `--min-severity <LEVEL>`
  - Values: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`
  - Default: `LOW`
  - Affects terminal table and `review_summary.md` top-findings presentation
  - Does not remove findings from canonical machine-readable artifacts (`findings.json`)

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
   `--fail-on-severity HIGH`

The workflow uploads `out/ci_smoke_review` as a build artifact, which includes
`findings.json`, `review_summary.md`, `run_metadata.json`, `results.sarif`,
`report.html`, and the other emitted review artifacts.

`examples/robotics_arm` and `examples/mobile_robot` intentionally contain issues
for demonstration/testing, so CI uses the dedicated passing smoke fixture to
avoid permanent workflow failure from intentionally failing examples.

---

## Deterministic Rules

| Rule | Category | Severity |
|------|----------|----------|
| Actuator/sensor signal without upper bound | `MISSING_BOUND` | MEDIUM |
| Requirement mentions snake_case token not in Signals | `UNDEFINED_REFERENCE` | HIGH |
| Transition references state not in States | `TRANSITION_GAP` | HIGH |
| Forbidden condition with no guard or assumption | `FORBIDDEN_UNCHECKED` | HIGH |
| Timing requirement with no timing parameter | `TIMING_GAP` | MEDIUM |
| Safety-critical signal with no reliability assumption | `MISSING_ASSUMPTION` | HIGH |
| Signal min bound violates a `<=` constraint | `CONTRADICTORY_CONSTRAINT` | CRITICAL |
| Code constant/comparison exceeds declared bound | `CODE_BOUND_MISMATCH` | HIGH |
| Code timing constant/threshold exceeds declared timing | `CODE_TIMING_MISMATCH` | HIGH |
| Code parameter appears related but unmodeled | `CODE_UNMODELED_PARAMETER` | MEDIUM |

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
tests/test_rules.py        — each rule individually + full run on examples
tests/test_solver.py       — Z3 checks including UNSAT case
tests/test_cli.py          — end-to-end CLI smoke tests on both examples
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

---

## Roadmap

### V0.0.3
- Broaden mode-scoped extraction beyond the current deterministic phrase patterns
- Broaden Python checks to include additional guard patterns and more robust constant propagation
- Further reduce false positives with tighter context-aware matching heuristics
- Add optional per-rule strictness controls for code-analysis findings
- Add configurable severity policies per branch/environment profile

### V0.1.0
- LLM-assisted extraction pass (optional, requires API key)
- Spec linter / authoring guide enforcer
- Multi-file spec support
- Cross-reference validation across spec + code + model

---

## License

This project is licensed under the [Apache License 2.0](LICENSE).
Copyright 2026 Tetsu Yamaguchi
