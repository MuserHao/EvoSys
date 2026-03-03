# Thought 002: Skill Maturation Pipeline — From Observation to Muscle Memory

**Date**: 2026-03-02
**Status**: Active exploration
**Triggered by**: Discussion on gradual learning and staleness detection

---

## The Problem with One-Shot Forging

The current Forge model is binary: a SliceCandidate goes in, either a validated
SkillRecord comes out, or the candidate is abandoned. This is like expecting a
student to go from "never seen this" to "mastered it" in one attempt.

Real learning is gradual. The system should:
1. Notice a pattern (observation)
2. Remember how to handle it (cached prompt / few-shot)
3. Practice until it can do it reliably (code synthesis with growing test suite)
4. Refine until it's automatic (optimization, tier demotion)
5. Stay sharp (drift detection, re-training)

## Proposed Maturation Stages

```
OBSERVED → PROMPTED → SYNTHESIZED → OPTIMIZED → STABLE
                                                    ↓
                                                 DEGRADED → re-enter at PROMPTED
                                                    ↓
                                                 RETIRED
```

### Stage: OBSERVED
- The reflection daemon has identified a recurring pattern
- The system has a SliceCandidate but hasn't tried to forge anything yet
- Data is accumulating: more I/O examples are being collected passively
- **No skill exists yet** — the cloud LLM still handles this pattern

### Stage: PROMPTED
- A cached prompt has been created: system prompt + few-shot examples
- Runs on a small local model (or cheap cloud model like Haiku)
- Shadow-mode: both the prompt skill and cloud LLM process the input
- Results are compared to build confidence and gather more training data
- **Cost reduction: ~70-90%** (cheap model vs frontier model)
- Exit criteria: pass rate > 0.9 over 50+ shadow comparisons

### Stage: SYNTHESIZED
- Code has been generated (Python function, regex pipeline, etc.)
- Full test suite from accumulated I/O pairs
- Running in production but still with periodic shadow-mode spot checks
- **Cost reduction: ~99%** (local compute only)
- Exit criteria: pass rate > 0.95 over 200+ invocations, no shadow divergence

### Stage: OPTIMIZED
- Code has been profiled and optimized
- Possibly demoted to a lower tier (e.g., simplified from algorithmic to regex)
- Composite skills may have been formed with adjacent skills
- **Minimal overhead**: this is the target state
- Exit criteria: none — this is steady state unless degradation detected

### Stage: STABLE
- Synonym for OPTIMIZED with high confidence over a long period
- The system has high trust in this skill
- Shadow checks are very infrequent (1% sampling)

### Stage: DEGRADED
- Drift detected: shadow comparisons show divergence
- Or: error rate has increased above threshold
- Or: user has flagged outputs as incorrect
- **Action**: re-enter the pipeline at PROMPTED with fresh examples
- The old skill version is preserved (genealogy) but deprioritized in routing

### Stage: RETIRED
- Skill hasn't been invoked in 90+ days
- Or: the pattern it handles no longer occurs
- Archived with full test suite and implementation for potential revival

## The Shadow-Mode Mechanism

Shadow mode is the system's primary learning signal. It works like this:

```
Input arrives → Orchestrator routes to skill
                      ↓
              ┌───────┴────────┐
              ↓                ↓
        Skill processes    Cloud LLM processes
        (fast, cheap)      (slow, expensive, but ground truth)
              ↓                ↓
        skill_output       llm_output
              ↓                ↓
              └───────┬────────┘
                      ↓
               Compare outputs
                      ↓
              ┌───────┴────────┐
              ↓                ↓
           Match            Diverge
              ↓                ↓
        +confidence        -confidence
        (reinforce)        (flag for review)
                           (add as training example)
```

Shadow mode frequency should be adaptive:
- New skills (PROMPTED): 100% shadow (every invocation)
- SYNTHESIZED: 20% shadow (spot checks)
- OPTIMIZED/STABLE: 1% shadow (rare verification)
- DEGRADED: 100% shadow (rebuilding confidence)

The cloud LLM cost of shadow mode is the "tuition fee" for learning. It's an
investment that pays off as skills mature and shadow frequency drops.

## Staleness Detection: Three Signals

### Signal 1: Shadow divergence
- When shadow mode is active, compare skill output to LLM output
- Use embedding similarity for free-text, exact match for structured data
- If divergence exceeds threshold over a rolling window → DEGRADED

### Signal 2: Error rate increase
- Track exceptions, timeouts, and malformed outputs per skill
- Compare to the skill's historical baseline
- Sudden spike → DEGRADED

### Signal 3: Input distribution shift
- Embed recent inputs and compare to the distribution of training inputs
- If the centroid has drifted beyond a threshold → flag for review
- This catches the case where the skill still works on old inputs but is being
  asked to handle inputs it was never trained on

### What triggers re-learning?

When a skill enters DEGRADED:
1. Shadow mode goes to 100%
2. Fresh I/O pairs from shadow comparisons are collected
3. After N new examples, the Forge re-attempts synthesis
4. The new version runs alongside the old in A/B mode
5. If the new version is better, it replaces the old (genealogy link preserved)
6. If neither version is good enough, escalate to the next tier up

## What We Can Solve Now

- Add maturation stages to the schema (extend SkillStatus or add a new field)
- Design the shadow-mode interface as part of BaseExecutor or a new ABC
- Define the comparison/scoring functions for shadow output matching
- Add `shadow_divergence_rate` and `input_distribution_hash` fields to SkillRecord

## What We Cannot Solve Now

- Optimal shadow-mode frequency scheduling (needs real usage data)
- Embedding-based input distribution drift detection (needs Phase 2 infra)
- Automatic re-forging pipeline (needs Phase 3 Forge to be built first)
- Cost-benefit analysis of shadow mode (when is the tuition too expensive?)

## Connection to Thought 001

The maturation pipeline is *per-tier*. A Tier 2 skill (cached prompt) matures
differently from a Tier 0 skill (regex). The pipeline described above is the
general framework, but the specific exit criteria and re-learning strategies
depend on the tier.

The learnability estimator from Thought 001 determines which tier to *start* at.
The maturation pipeline determines how the skill *evolves within and across tiers*.
