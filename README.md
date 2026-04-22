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

## What V0.0.1 Does

1. Parses a structured markdown specification (see Input Format below)
2. Merges an optional YAML model (signals, states, modes, transitions, parameters)
3. Builds an Internal Representation (IR) — signals, states, constraints, requirements
4. Runs 7 deterministic rules (missing bounds, undefined references, timing gaps, etc.)
5. Runs Z3-backed constraint satisfiability checks
6. Emits 9 review artifacts

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
```

Parameters are ingested as named numeric values and can be referenced by
timing constraint checks.

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
| `report.html` | Simple HTML report with sortable findings table |
| `run_metadata.json` | Run ID, version, status (PASS / REVIEW_REQUIRED), finding counts |

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

## Z3 Checks

| Check | Category | Severity |
|-------|----------|----------|
| Signal bounds + constraint → UNSAT | `CONSTRAINT_CONFLICT` | CRITICAL |
| All constraints jointly → UNSAT | `CONSTRAINT_CONFLICT` | CRITICAL |
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

## Limitations (V0.0.1)

- No LLM — extraction is regex/section-based and requires the structured markdown format
- Extraction quality depends on spec authoring discipline
- Z3 checks only work on numeric bounds; boolean/symbolic constraints not yet encoded
- Code file inputs are ingested but not yet statically analysed (V0.0.2 target)
- No SARIF output yet (V0.0.2 target)
- No CI gate configuration (V0.0.2 target)
- Signal-to-mode coupling (e.g., "REQ-001 applies only in CALIBRATION mode") is not
  yet encoded in Z3 — mode-scoped constraints are a V0.0.2 item

---

## Roadmap

### V0.0.2
- Static code analysis: detect constant mismatches between spec bounds and code literals
- SARIF output for IDE/CI integration
- Mode-scoped constraint encoding in Z3 (joint speed limit only in CALIBRATION mode)
- CI gate: `--fail-on-critical` exit code policy
- Threshold-based filtering: `--min-severity HIGH`

### V0.1.0
- LLM-assisted extraction pass (optional, requires API key)
- Spec linter / authoring guide enforcer
- Multi-file spec support
- Cross-reference validation across spec + code + model

---

## License

This project is licensed under the [Apache License 2.0](LICENSE).
Copyright 2026 Tetsu Yamaguchi
