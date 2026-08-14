# Decision Change Records

Every reversal of an earlier decision is recorded here with the evidence that
forced it. A decision is not changed because someone objected — it is changed
because new evidence arrived or a flaw in the earlier reasoning was identified,
and the record has to show which.

Records 001–003 were made during the work and previously lived only in commit
messages and conversation; they are collected here so the reasoning is findable
from the repository alone.

---

## DCR-001 — Stopping distance is not the demo's primary check

**Previous decision.** The public demo would be built around the stopping
distance contract `d = v·τ + v²/2a + ε`.

**Basis at the time.** It is the standard form for this class of safety
argument, and if `v` and `a` could be read from real configuration then the
check would follow.

**New evidence.** `v` and `a` *are* readable, so the premise held. But the
contract produced 84–88% margin on all three real Nav2 configurations — no
discriminating power whatsoever. Meanwhile the upstream MPPI README documents a
rule (`time_steps × model_dt × vx_max ≤ costmap radius`) that sits at a 6.7%
margin on the shipped defaults, and the real files turned out to contain a
coherence defect needing no safety model at all to detect.

**What was invalid.** Conflating "correct as a safety contract" with "produces a
signal on the data we can actually reach". The first does not imply the second.

**New decision.** Primary checks are (A) directional controller/smoother limit
coherence and (B) the upstream horizon rule. Stopping distance is retained as
secondary output, reported but not gating.

**Affected.** Phase 2 implementation order. No work discarded.

---

## DCR-002 — Reproducibility before the stopping-distance secondary output

**Previous decision.** Implement the stopping-distance secondary output, then
provenance and one-command reproduction.

**Basis at the time.** Plan order, nothing more.

**New evidence.** DCR-001 established the stopping-distance output has no
discriminating power on reachable data. Independent review — the one gate item
that cannot be closed by writing more code — requires a third party to be able
to re-run the thing.

**What was invalid.** Treating plan sequence as value sequence.

**New decision.** `make verify`, the provenance manifest and committed demo
outputs come first.

**Affected.** Order only.

---

## DCR-003 — A correct verdict is not enough; the output must not mislead

**Previous decision.** Stating the checks accurately in the README was
sufficient honesty.

**Basis at the time.** If the documentation is accurate, the tool is honest.

**New evidence.** Demonstrated on this repository's own corpus: cutting the
sensor marking range to 0.4 m — so the robot cannot see far enough to stop — and
then applying exactly the fix EAL recommended for the acceleration mismatch
produced `0 findings`, `PASS`, `exit 0`. The tool directed attention to an
unrelated issue and rewarded resolving it with a green result.

**What was invalid.** Accurate documentation does not make the *output*
non-misleading. CI reads the exit code, not the README.

**New decision.** The unchecked-hazard register is emitted on every run,
generated from measured evaluation results. Nothing reports `PASS`:
`NO_FINDINGS_IN_SCOPE`, `BELOW_THRESHOLD`/`THRESHOLD_EXCEEDED`,
`INPUTS_FULLY_READ`.

**Affected.** Minimum product claim, output vocabulary, the gate item on claim
matching capability — which this reopened and then closed.

---

## DCR-004 — Why over-declared acceleration is unsafe-leaning

**Date.** 2026-08-14

**Previous decision.** `NAV2_ACCEL_OVERDECLARED` was justified on the grounds
that MPPI rolls out and validates candidate trajectories against its own
acceleration figures, so a trajectory judged feasible or collision-free at
3.0 m/s² might not be achievable once the smoother caps the command at 2.5 m/s².

**Basis at the time.** Reading `nav2_mppi_controller/src/optimizer.cpp:318-319`,
where `ax_min`/`ax_max` bound the velocities reachable within a timestep,
combined with the presence of a trajectory validator in the same pipeline.

**New evidence.**
[ros-navigation/navigation2#6357](https://github.com/ros-navigation/navigation2/issues/6357),
answered 2026-08-14 by the Nav2 maintainer who wrote the velocity smoother:

> Yes, they are intended to be differently defined such that there can be
> different limits in different situations. There are legit reasons you may want
> a controller to not use its full dynamic capabilities at a particular time
> below what the hardware can actually do. The velocity smoother is more
> enforcing hard limitations than behavioral desires that a controller may
> compute as part of what it would like to do.

> I agree the mismatch in this case is odd and unintentional. We should revert
> MPPI to 2.5 or increase the velocity smoother to 3.0

**What was invalid.** The trajectory-validation mechanism was our inference
about MPPI internals. The maintainer neither confirmed nor mentioned it. It may
still be true, but it was being stated as the reason and it was not sourced.

Two things the answer confirmed, which are kept:

- the directional asymmetry is real. Controller *below* the smoother is
  explicitly legitimate ("legit reasons you may want a controller to not use its
  full dynamic capabilities"), which is why `NAV2_LIMIT_HEADROOM` is
  informational and `strict`-only. Controller *above* it is not.
- this specific mismatch in the shipped defaults is a genuine defect, described
  by the maintainer as "odd and unintentional".

**New decision.** The severity stays HIGH; the justification is replaced. The
smoother expresses the platform's hard limits and the controller expresses
behavioural desires that may sit below them, so declaring more than the hard
limit inverts the intended relationship — the controller plans with capability
the platform is not configured to deliver. The maintainer statement is quoted in
`MAINTAINER_SOURCE` in `src/eal/rules/nav2_coherence.py` and reproduced in the
finding text, so the claim carries its source.

The "whether this is a defect depends on intent" hedge is narrowed. Intent for
the *general* pairing is now documented, so over-declaration is a departure from
a stated relationship rather than an ambiguity. EAL still does not rule on any
particular stack.

**Affected.** `nav2_coherence.py` rationale and module docstring,
`docs/release-drift-investigation.md` finding 1, README, the demo outputs that
embed finding text, and `tests/test_nav2_coherence.py`.

**To withdraw.** The trajectory-validation argument, wherever it appears. It is
not to be reinstated without a source.

---

## What this answer did *not* settle

The maintainer proposed either lowering MPPI to 2.5 or raising the smoother to
3.0. Those are not equivalent: lowering the controller asserts nothing new,
while raising the smoother asserts that the platform really can brake at
3.0 m/s². On the maintainer's own framing — the smoother is the hard limit —
the second needs evidence about the hardware that neither this project nor the
issue thread has produced.

Recorded as open. It is also exactly the question the secondary part of #6357
asked and the kind of thing this tool exists to make visible.
