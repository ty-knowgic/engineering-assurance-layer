# BehaviorTree Timeout and Precondition Slice — Guard Gap Analysis Note

## Intended Defect

This variant keeps the same timeout and fallback intent as the clean baseline,
but the modeled precheck transition no longer references `localization_ready`.

That drift represents a common BT review problem: the specification and
illustrative tree still imply a condition node or precondition gate, while the
reviewed configuration/model slice allows action execution without it.

## What EAL Should Detect

EAL should emit `FORBIDDEN_UNCHECKED` for the forbidden execution condition:

- `FC-001: NAVIGATING when localization_ready = 0`

The timeout requirement remains model-backed, so this fixture is not trying to
demonstrate timing drift. It is a focused guard/precondition regression.

## Limits

As with the clean baseline, EAL is not proving full BehaviorTree.CPP semantics
or runtime tick behavior. This is a consistency and review artifact exercise.
