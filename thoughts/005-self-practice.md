# Thought 005: Self-Practice — The System That Trains Itself

**Date**: 2026-03-03
**Status**: Active exploration
**Triggered by**: Observation that learning only from user requests bottlenecks improvement

---

## The Insight

A system that only learns when users make requests is fundamentally limited. It
improves discretely — one request at a time, only during active use. A human
athlete doesn't only practice during games. The practice *between* games is where
most improvement happens.

EvoSys should be able to practice on its own. When the user is idle, the system
should be strengthening its skills — generating practice inputs, testing itself,
refining its implementations, exploring edge cases it hasn't seen yet.

This is what separates a continuously evolving system from a discrete, passively
improving one.

## The Self-Practice Loop

```
                    ┌─────────────────────────┐
                    │     Practice Scheduler   │
                    │  (runs during idle time) │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   Select skill to train  │
                    │   (lowest confidence,    │
                    │    highest value,         │
                    │    or newly forged)       │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │  Generate practice inputs │
                    │  (augment real input      │
                    │   distribution, not       │
                    │   random fabrication)     │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   Run skill on inputs    │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   Evaluate outputs       │
                    │   (ground truth source   │
                    │    depends on skill tier) │
                    └────────────┬────────────┘
                                 │
                         ┌───────┴───────┐
                         │               │
                    ┌────▼────┐    ┌─────▼─────┐
                    │  Pass   │    │   Fail    │
                    │ +conf   │    │  collect  │
                    │         │    │  as new   │
                    │         │    │  training │
                    │         │    │  example  │
                    └─────────┘    └───────────┘
```

## When Self-Practice Works (and When It Doesn't)

### Works well: Verifiable outputs

Skills where the output can be mechanically checked:
- **Deterministic code (Tier 0-1)**: Generate inputs, run through both the skill
  and the cloud LLM. Any disagreement is actionable. Can also use property-based
  testing — "output should always be valid JSON," "dates should be in ISO format."
- **Schema-constrained outputs**: If the output must conform to a JSON schema,
  the system can verify structural correctness without LLM involvement.
- **Idempotent transformations**: Parse → serialize → parse should yield the same
  result. This catches bugs in parsers without needing ground truth.
- **Code skills**: Generated code that must compile and pass unit tests. The
  compiler and test harness are the evaluator.

### Works with caution: LLM-evaluated outputs

Skills where output quality requires judgment:
- **Cached prompts (Tier 2)**: The system can generate inputs and evaluate the
  local model's output against the cloud LLM. But this costs money — the cloud
  LLM call during practice is the "tuition fee."
- **Fine-tuned models (Tier 3)**: Same approach. Practice sessions should be
  budgeted — e.g., $0.50/day maximum spend on practice evaluations.
- **Key constraint**: Practice cost must be less than the projected savings from
  skill improvement. If a skill is invoked 10x/day and each invocation saves
  $0.05, spending $0.50/day on practice is break-even. Not worth it.

### Dangerous: Self-referential evaluation

Skills where the system evaluates itself without external grounding:
- **Training on self-generated outputs** → model collapse / distribution drift
- **Generating unrealistic inputs** → skill becomes good at toy problems,
  fails on real ones
- **Unbounded practice** → wasting compute on marginal improvements

## Grounded Practice: How to Generate Good Inputs

The system should NOT generate random inputs. It should:

### 1. Augment real inputs
Take actual inputs the skill has seen, and create variations:
- Swap entities: "Extract dates from {article A}" → "Extract dates from {article B}"
- Add noise: introduce typos, formatting variations, edge cases
- Combine: merge patterns from different real inputs
- Boundary cases: empty inputs, very long inputs, unusual encodings

### 2. Mine failure modes
Look at cases where the skill has failed or had low confidence. Generate more
inputs in that region of the input space. This is the highest-value practice —
working on weaknesses, not strengths.

### 3. Use the cloud LLM to generate inputs
Ask the teacher: "Given this skill's input schema and these 10 example inputs,
generate 20 more inputs that would be challenging edge cases." One LLM call
produces many practice inputs.

### 4. Respect the real distribution
Track the statistical distribution of real inputs (embedding centroids, field
value distributions, length distributions). Generated inputs that fall far
outside this distribution should be discarded — they're not relevant practice.

## The Practice Scheduler

Not all skills benefit equally from practice. The scheduler should prioritize:

### Priority signals (highest first)

1. **Newly forged skills (SYNTHESIZED stage)**: These have the most to gain.
   Practice builds confidence and may reveal bugs before they hit production.

2. **Skills with recent failures**: If a skill failed on a real request, generate
   similar inputs and practice until the failure mode is understood and fixed.

3. **Skills approaching tier demotion**: If a Tier 2 skill is being considered
   for demotion to Tier 1, intensive practice with code synthesis can validate
   whether the demotion is safe.

4. **High-value skills with declining confidence**: Skills that are invoked
   frequently and save significant cost, but whose confidence is drifting.

5. **Skills that haven't been invoked recently**: Light practice to verify they
   still work, catching silent degradation before the next real invocation.

### Anti-priorities (skip these)

- **STABLE skills with high confidence**: Already proven. Occasional spot-checks
  are sufficient; intensive practice is waste.
- **Skills where practice is more expensive than the skill itself**: If evaluating
  a practice run costs $0.10 and the skill saves $0.01 per invocation, practice
  has negative ROI.
- **OBSERVED candidates that haven't been forged yet**: Nothing to practice —
  the skill doesn't exist yet.

## Compute Budget

Self-practice must have a hard budget. Unbounded self-improvement is a resource
sink. The budget should be:

- **Per-skill cap**: No skill gets more than N practice runs per cycle.
- **Total daily cap**: Maximum compute spend on practice per day (e.g., $1/day
  for a personal deployment, $50/day for a production system).
- **ROI threshold**: Practice stops for a skill when the marginal improvement
  per practice run drops below a threshold.
- **Idle-only**: Practice runs only when the system is not handling user requests.
  Real work always preempts practice.

## Connection to the Maturation Pipeline (Thought 002)

Self-practice accelerates maturation:

```
OBSERVED  →  (practice has no effect — no skill to practice)
PROMPTED  →  Practice validates the cached prompt against cloud LLM
              Accelerates the move to SYNTHESIZED
SYNTHESIZED → Practice expands the test suite with generated examples
              Catches edge cases before production exposure
              Accelerates the move to OPTIMIZED
OPTIMIZED →  Practice maintains sharpness, detects early drift
              May discover opportunities for tier demotion
STABLE    →  Minimal practice (spot-checks only)
DEGRADED  →  Intensive practice with fresh examples to re-learn
```

## What We Can Build Now

- `BasePracticeScheduler` ABC: `select_skill() -> SkillRecord`,
  `generate_inputs(skill, n) -> list[IOPair]`, `run_practice_cycle(budget)`
- `PracticeBudget` type: daily cap, per-skill cap, ROI threshold
- Fields on `SkillRecord`: `practice_runs_total`, `last_practiced`,
  `practice_pass_rate`

## What We Cannot Build Now

- Actual input augmentation (needs real trajectory data to augment)
- The ROI calculator (needs invocation cost data from production)
- LLM-guided input generation (needs Phase 1 LLM integration)
- Distribution-aware filtering of generated inputs (needs Phase 2 embeddings)

## The Deeper Implication

If the system practices on its own, it is not just a tool that responds to
requests. It is an entity that *prepares* for requests it hasn't received yet.
It has something like anticipation — not consciousness, but a structural
incentive to improve in directions that are likely to be useful.

This is the difference between a cache (stores what it has seen) and a learner
(prepares for what it might see). Most AI systems are caches. EvoSys, with
self-practice, would be closer to a learner.

But we should be honest: the simplest version of self-practice is just
"run your test suite overnight and report failures." That's not revolutionary.
The interesting part is the *input generation* — practicing on problems the
system hasn't seen yet but expects to encounter. That requires understanding
the input distribution, which requires Phase 2 infrastructure.
