# EAL Positioning and Strategic Boundaries

## What EAL Is

EAL is a deterministic engineering assurance layer that converts existing
engineering artifacts into reviewable and gateable evidence.

Today, that includes:

- spec/model extraction into a typed IR
- deterministic rule findings
- mode-aware Z3 satisfiability checks
- Python code-aware mismatch checks
- CI-gate behavior (`--fail-on-severity`)
- strictness controls for heuristic findings
- SARIF and artifact-first outputs for workflow integration

## What EAL Is Not

EAL is not:

- a system modeling language
- a SysML/MBSE replacement
- a theorem prover for full design correctness
- a runtime verification framework
- a simulation environment
- a replacement for compiler/framework validation (for example SMACC2 compile-time checks)
- a generic AI reviewer

## Why EAL Exists

Engineering teams already have specs, models, code, and configuration spread
across tools. Those artifacts often drift and become hard to review as a single
assurance story.

EAL exists to surface cross-artifact contradictions and review gaps with low
adoption friction, then emit evidence that can be consumed in PR/CI workflows.

## Where EAL Fits in the Engineering Toolchain

EAL fits between authoring and release gates:

- after spec/model/code/config edits
- before merge/release decisions

Its output is review and governance evidence, not a replacement for authoring,
simulation, testing, or runtime monitoring.

## How EAL Differs from SysML / MBSE

SysML/MBSE tools are primarily about building and maintaining system models as
the central source of design structure and behavior.

EAL is different:

- it does not try to be a better modeling language
- it consumes already-existing artifacts
- it focuses on consistency checks and review artifacts
- it optimizes for low-friction insertion into existing engineering workflows

The strategic value is review integration, not modeling breadth.

## How EAL Differs from Formal Verification Tools

Formal verification tools aim to prove properties over mathematically precise
models/programs with stronger completeness guarantees in scoped domains.

EAL currently provides bounded, deterministic assurance checks and contradiction
detection, including mode-scoped numeric constraints. It does not claim full
proof of behavior correctness.

## How EAL Differs from Runtime Verification / Testing

Runtime verification and testing validate behavior under execution, including
timing jitter, integration effects, and environment interactions.

EAL operates pre-runtime on declared artifacts. It complements runtime
validation by catching consistency and assumption issues earlier in review.

## What EAL Should Optimize For

- deterministic, explainable findings
- actionable evidence with source traceability
- review acceleration in PR/CI workflows
- assumption visibility
- mode/transition/constraint drift detection across artifacts
- operationally useful artifacts over theoretical coverage claims

## What EAL Should Avoid

- drifting into a general system design environment
- building a new broad modeling language
- expanding into unconstrained theorem-proving claims
- adding high-friction workflows that require teams to re-author designs
- hiding signal quality behind opaque heuristics

## Current Strategic Wedge

EAL's wedge is:

- cross-artifact assurance evidence generation
- deterministic gate integration
- low-friction adoption on top of existing engineering documentation and code

It should remain focused on making review decisions better and faster, not on
owning all engineering semantics.

## Near-Term Direction

Near-term direction should preserve focus on:

- higher-fidelity extraction where current linkage is coarse
- stronger evidence quality and lower-noise findings
- workflow reliability in CI/code-scanning/review artifacts
- clearer domain-specific review value without overstating correctness guarantees

## Non-Goals

Non-goals for current project direction:

- replacing SysML/MBSE toolchains
- replacing simulation, hardware tests, or runtime monitors
- replacing compile-time framework validation
- proving full-system behavioral correctness
- becoming a generic AI design assistant platform

The long-term risk to manage is strategic drift into broad MBSE/formal-tool
categories that dilute EAL's core review-assurance role.
