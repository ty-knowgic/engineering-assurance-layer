# Release Drift — Kill Test

Read-only investigation, 2026-08-13. No implementation. The question was whether
comparing a configuration across releases can say anything a single-release
analysis and a plain `git diff` cannot.

## Why the question

The adversarial evaluation (`eval/RESULTS.md`) established that EAL's
limit-coherence check is blind to any change that keeps two declarations in
agreement, however dangerous the agreed value is. Eleven of nineteen hazardous
mutations produce no output for exactly that reason.

A change of that shape is invisible *within* one release. The hypothesis was
that it becomes visible *between* releases: a value that doubled since the last
release is conspicuous even when the current file is internally consistent.

## Method

`nav2_bringup/params/nav2_params.yaml` fetched from every Nav2 distro branch and
parsed with EAL's own importer. No mutation; these are the real shipped defaults
of six consecutive releases.

| branch | commit |
|--------|--------|
| humble | `3c3db59d69` |
| iron | `022e7e1857` |
| jazzy | `3f71f94b10` |
| kilted | `71a1d84f49` |
| lyrical | `cc843b58e1` |
| main | `6dbf4549ae` |

## What changed

| quantity | humble | iron | jazzy | kilted | lyrical | main |
|----------|--------|------|-------|--------|---------|------|
| controller plugin | DWB | DWB | **MPPI** | MPPI | MPPI | MPPI |
| controller `v_max_linear` | 0.26 | 0.26 | **0.5** | 0.5 | 0.5 | 0.5 |
| controller `v_max_angular` | 1.0 | 1.0 | **1.9** | 1.9 | 1.9 | 1.9 |
| controller `a_decel_linear` | -2.5 | -2.5 | **-3.0** | -3.0 | -3.0 | -3.0 |
| controller `a_accel_angular` | 3.2 | 3.2 | **3.5** | 3.5 | 3.5 | 3.5 |
| smoother `v_max_linear` | 0.26 | 0.26 | **0.5** | 0.5 | 0.5 | 0.5 |
| smoother `v_max_angular` | 1.0 | 1.0 | **2.0** | 2.0 | 2.0 | 2.0 |
| smoother `a_decel_linear` | -2.5 | -2.5 | -2.5 | -2.5 | -2.5 | -2.5 |
| smoother `a_accel_angular` | 3.2 | 3.2 | 3.2 | 3.2 | 3.2 | 3.2 |
| `inflation_radius` | 0.55 | 0.55 | **0.70** | 0.70 | 0.70 | 0.70 |
| `controller_frequency` | 20.0 | 20.0 | 20.0 | 20.0 | 20.0 | 20.0 |
| costmap width | 3.0 | 3.0 | 3.0 | 3.0 | 3.0 | 3.0 |
| `obstacle_max_range` | 2.5 | 2.5 | 2.5 | 2.5 | 2.5 | 2.5 |

Eleven of seventeen tracked quantities changed. Everything moved at one
boundary, iron → jazzy, when the default controller became MPPI.

## Finding 1 — the mismatch EAL reports has a birthday

Running EAL on each release:

| release | exit | findings |
|---------|------|----------|
| humble | 0 | 0 |
| iron | 0 | 0 |
| jazzy | 2 | 3 × `NAV2_ACCEL_OVERDECLARED` |
| kilted | 2 | 3 |
| main | 2 | 3 |

Under DWB the configuration was fully coherent: all six limit roles agreed. At
the jazzy transition the controller's **velocity** limits were raised and the
smoother's velocity limits were raised to match — but the controller's
**acceleration** limits were raised and the smoother's were not.

That is the textbook shape of assumption drift: a subsystem is replaced, the
coupled configuration is partly updated, and one half of a pair is missed. The
mismatch has now been carried through three further releases.

It also weakens the "the mismatch is intentional" reading. It was not a
deliberate pairing of a generic controller with a tuned smoother from the start;
it appeared at a specific change, alongside a velocity update that *was* applied
to both sides. Still not proof of a defect — only upstream can say — but the
question is now better posed.

## Finding 2 — the drift-only signal is real but weak here

The velocity change is precisely the blind spot: 0.26 → 0.5 on **both** sides,
internally consistent, and EAL says nothing about it in any single release.

As a release delta it is visible, and a consequence can be derived:

```
tau_lower_bound = 1/20 Hz + 1/5 Hz = 0.25 s     (artifact-derived floor, not true latency)
iron    d_required = 0.26·0.25 + 0.26²/(2·2.5) = 0.0785 m
jazzy   d_required = 0.50·0.25 + 0.50²/(2·2.5) = 0.1750 m
```

Required stopping distance grew **2.23x** while braking authority
(`max_decel -2.5`) and sensing range (`obstacle_max_range 2.5 m`) did not change
at all. `inflation_radius` rose 0.55 → 0.70, which partly compensates.

But the absolute margin stayed enormous — 96.9% → 93.0% of the sensing range. On
this instance a drift alert would have been technically correct and practically
uninteresting.

## Verdict

**The hypothesis is not killed, but it is narrowed, and it is bottlenecked.**

What survives: limits genuinely do move between releases; a real coherence
defect really was introduced at a release boundary and persists; and the change
class EAL is blind to within a release really is visible across releases.

What does not survive: the idea that detecting the *change* is the value. `git
diff` detects the change. The only thing worth paying for is relating the change
to a **consequence** — and Phase 3 already measured that our one consequence
model, stopping distance, has no discriminating power at Nav2's speeds. It did
not discriminate here either.

So drift detection depends on a consequence model that is itself weak. Building
it now would produce alerts of the form "this number doubled", which is a diff
with extra steps.

## What this argues for instead

Let the human supply the consequence, and make the tool responsible for
remembering it.

Record the assumption set at release *N* — "the stopping analysis assumes
`v_max ≤ 0.3 m/s`", "we assume sensor latency ≤ 50 ms" — with provenance. At
release *N+1*, re-check each recorded assumption against the current
configuration and report the ones that are now void. `v_max` moving 0.26 → 0.5
invalidates a recorded 0.3 m/s assumption immediately and unambiguously, with no
general consequence model required.

This also reaches the one gap nothing else here touches: assumptions that exist
only in someone's head. It cannot invent them, but it gives them somewhere to
live where a later release will trip over them.

Sensor latency is the standing example. It appears in no Nav2 configuration
file, is not modelled, and is currently listed only as an unchecked hazard. As a
declared assumption it would become a durable, auditable, re-validated fact.

## Reproducing

```bash
for b in humble iron jazzy kilted lyrical main; do
  sha=$(curl -sS "https://api.github.com/repos/ros-navigation/navigation2/commits/$b" \
        | python3 -c "import json,sys;print(json.load(sys.stdin)['sha'])")
  curl -sS -o "$b.yaml" \
    "https://raw.githubusercontent.com/ros-navigation/navigation2/$sha/nav2_bringup/params/nav2_params.yaml"
done
```

Then parse each with `eal.ingestion.nav2_params.parse_nav2_params`.
