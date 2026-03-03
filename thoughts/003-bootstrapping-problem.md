# Thought 003: The Bootstrapping Problem — Who Teaches the Teacher?

**Date**: 2026-03-02
**Status**: Open question
**Triggered by**: "The system would have to decide or ask the powerful AI to help it decide"

---

## The Paradox

EvoSys needs intelligence to decide how to deploy intelligence. Specifically:

- The **learnability estimator** needs to judge whether a pattern is forgeable —
  but judging learnability is itself a task that requires intelligence.
- The **reflection daemon** needs to find meaningful patterns in trajectories —
  but distinguishing signal from noise requires understanding what the tasks *mean*.
- The **Forge** needs to decide which tier to target — but making this decision
  well requires experience with forging, which doesn't exist yet.

This is the bootstrapping problem. The system starts with zero skills and zero
experience about what's learnable. Everything must be routed to the cloud LLM.

## Three Strategies (Not Mutually Exclusive)

### Strategy 1: Start with heuristics, replace with learned policies

Hard-code simple rules for v1:

```python
def estimate_tier(candidate: SliceCandidate, examples: list[IOPair]) -> SkillTier:
    determinism = compute_determinism_ratio(examples)
    schema_consistency = compute_schema_consistency(examples)
    avg_output_length = mean(len(str(ex.output)) for ex in examples)

    if determinism > 0.95 and schema_consistency > 0.95:
        return SkillTier.DETERMINISTIC_CODE      # Tier 0
    if determinism > 0.8 and schema_consistency > 0.9:
        return SkillTier.ALGORITHMIC_CODE         # Tier 1
    if len(examples) >= 30 and avg_output_length < 500:
        return SkillTier.FINE_TUNED_LOCAL_MODEL   # Tier 3
    if len(examples) >= 5:
        return SkillTier.CACHED_PROMPT            # Tier 2
    return SkillTier.CLOUD_LLM_CALL              # Tier 4 (not enough data yet)
```

These rules are wrong in many cases. That's fine. The trial-and-error loop from
Thought 001 (try cheap, escalate on failure) compensates for bad initial estimates.

Over time, as the system accumulates data on which candidates succeeded at which
tiers, the heuristics can be replaced with a learned model. The learnability
estimator *itself* becomes a skill that the system can improve.

### Strategy 2: Ask the cloud LLM to help decide

For candidates where the heuristic is uncertain, ask the frontier LLM:

```
Given these I/O examples from a recurring pattern:

Input examples:  [...]
Output examples: [...]
Pattern frequency: 47 occurrences
Schema consistency: 0.82 (ambiguous)

This pattern could be implemented as:
A) A deterministic Python function (regex, string ops, etc.)
B) A Python function using NLP libraries (spaCy, etc.)
C) A few-shot prompt to a small language model
D) A fine-tuned small model
E) Not forgeable — keep using cloud LLM

Which approach would you recommend and why?
```

This costs one LLM call per candidate assessment. Since candidates are generated
infrequently (the reflection daemon runs periodically, not per-request), this is
an acceptable cost.

### Strategy 3: Portfolio approach — try multiple tiers in parallel

For high-value candidates (high frequency, high token cost), don't pick one tier.
Try multiple:

1. Attempt Tier 0/1 code synthesis
2. Simultaneously create a Tier 2 cached prompt
3. Run both in shadow mode against the cloud LLM

Whichever passes validation first gets deployed. The other is kept as a backup.
This burns more Forge compute but reduces time-to-deployment for important skills.

## The Meta-Learning Opportunity

Eventually, EvoSys's forge success/failure history becomes a dataset:

```
(candidate_features, attempted_tier, outcome) → learned_policy
```

Where candidate_features include: determinism ratio, schema consistency, example count,
output variance, action sequence length, domain signals, etc.

This dataset trains the learnability estimator, which is itself a skill (Tier 1 or 3).
The system literally learns how to learn. This is the most philosophically interesting
aspect of EvoSys, but it requires hundreds of forge attempts to have enough data.

## What We Can Build Now

- The heuristic estimator (Strategy 1) — deterministic, no dependencies
- The LLM assessment prompt template (Strategy 2) — just a prompt, no infra needed
- Data structures to record forge outcomes for future meta-learning

## What We Cannot Build Now

- The meta-learning model (needs forge outcome data that doesn't exist yet)
- The portfolio approach (needs the Forge itself, Phase 3)
- Optimal cost-benefit analysis of LLM-assisted decisions (needs usage data)

## The Uncomfortable Truth

The system will make bad decisions early on. It will try to forge things that
aren't forgeable, pick the wrong tier, waste compute on synthesis that fails.
This is *expected and acceptable*. The cost of bad decisions during bootstrapping
is bounded (a few wasted LLM calls, some failed forge attempts), and each failure
generates data that improves future decisions.

The alternative — waiting until we have a perfect policy before starting — means
never starting.
