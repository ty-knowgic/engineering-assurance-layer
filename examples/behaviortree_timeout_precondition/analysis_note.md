# BehaviorTree Timeout and Precondition Slice — Analysis Note

## Source Style

This fixture is inspired by a small BehaviorTree.CPP-style navigation subtree:
precondition checks gate a navigation action, a timeout decorator can trigger
fallback, and a recovery branch is expected after timeout.

The included `tree.xml` is illustrative source-style context only. EAL is not
performing full BehaviorTree.CPP semantic analysis, but this fixture now uses
native narrow XML ingestion for review-relevant evidence. The clean validation
command is:

```bash
python -m eal.cli review \
  --spec examples/behaviortree_timeout_precondition/spec.md \
  --bt-xml examples/behaviortree_timeout_precondition/tree.xml \
  --fail-on-severity HIGH \
  --out out/behaviortree_timeout_precondition_review
```

## What Was Abstracted Into EAL Inputs

- A precheck stage before `NavigateToPose`
- Two explicit execution preconditions (`battery_ok`, `localization_ready`)
- The explicit `Timeout msec="100"` value from `tree.xml`
- Fallback/recovery branch visibility from `tree.xml`
- A timeout-driven handoff from `NAVIGATING` to `RECOVERING` remains specified manually
- A bounded retry policy in `AUTO_NAV` mode
- State names, transition names, and retry policy remain manually modeled in `spec.md`

## Supported Native XML Subset

- `Sequence` and `Fallback` structure
- `Timeout` only when `msec` is explicitly present and integer-valued
- `Precondition` only when an explicit expression attribute is present
- `Action` and `Condition` leaves with `ID` or `name`
- Simple custom leaf tags are recorded as leaf evidence only

Unsupported/manual: full BehaviorTree.CPP execution semantics, blackboard
resolution, port typing, arbitrary decorators, tick timing, and full conversion
from BT branches into EAL state transitions.

## What EAL Should Detect Here

This baseline is intended to review cleanly under `--fail-on-severity HIGH`:

- the action preconditions are represented in transition guards
- the timeout requirement is backed by a timing parameter
- the fallback/recovery intent is visible in the state/transition slice
- the retry bound is represented as both a requirement and a model constraint

## What EAL Is Not Proving

- Full BehaviorTree.CPP execution semantics
- Runtime correctness of decorator ordering, tick frequency, or blackboard usage
- Correctness of all recovery-node implementations or BT engine internals
