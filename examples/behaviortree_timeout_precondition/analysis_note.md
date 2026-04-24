# BehaviorTree Timeout and Precondition Slice — Analysis Note

## Source Style

This fixture is inspired by a small BehaviorTree.CPP-style navigation subtree:
precondition checks gate a navigation action, a timeout decorator can trigger
fallback, and a recovery branch is expected after timeout.

The included `tree.xml` is illustrative source-style context only. EAL is not
parsing BehaviorTree.CPP XML semantics here; the review input is the EAL
markdown spec plus YAML model.

## What Was Abstracted Into EAL Inputs

- A precheck stage before `NavigateToPose`
- Two explicit execution preconditions (`battery_ok`, `localization_ready`)
- A timeout-driven handoff from `NAVIGATING` to `RECOVERING`
- A bounded retry policy in `AUTO_NAV` mode
- A recovery/fallback path represented as a state transition

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
