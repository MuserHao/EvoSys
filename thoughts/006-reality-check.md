# Thought 006: Reality Check — What Actually Works vs What's Aspirational

**Date**: 2026-03-03
**Status**: Active
**Triggered by**: Honest assessment of whether the vision is too broad

---

## The Concern

The EvoSys README describes a system that autonomously discovers skills, forges
code, detects concept drift, composes skills, and eventually federates across
instances. That's a research agenda for a team of 20, not a buildable system.

Before investing in Phase 1 infrastructure, we need to separate what's
practically achievable from what's speculative.

## Three tiers of realism

### Tier A: This works today, just needs engineering

- **Structured logging** of every LLM call with input/output (trajectory capture)
- **Frequency counting** of recurring action patterns
- **Prompt caching**: if similar inputs recur, serve from cache
- **Prompt template extraction**: freeze a system prompt with a cheaper model
- **Code synthesis from I/O pairs**: give Claude 20 examples, ask for a Python
  function. This works for many deterministic transformations *right now*.
- **Shadow mode**: run both paths, compare outputs. Straightforward engineering.
- **Test suite generation**: I/O pairs become pytest test cases. Trivial.

### Tier B: Hard but tractable with iteration

- **Learnability estimation**: heuristic scoring (determinism ratio, schema
  consistency) is computable. Not perfect, but useful.
- **The maturation pipeline**: OBSERVED → PROMPTED → SYNTHESIZED progression
  is a state machine. Each transition has clear criteria.
- **Concept drift via shadow divergence**: compare skill vs LLM on a sample.
  If divergence exceeds threshold, flag for re-forging. Standard ML ops.
- **Self-practice on verifiable skills**: generate test inputs, run both
  paths, compare. Requires compute budget but no novel research.

### Tier C: Speculative / may never work as described

- **Autonomous DAG granularity detection**: knowing where to draw skill
  boundaries without human guidance
- **Automatic tier demotion** (neural net → deterministic code): the gap
  between "works as a model" and "expressible as rules" is often
  unbridgeable
- **Meta-learning**: the system learns how to learn from forge history.
  Requires thousands of data points that don't exist yet.
- **Federation**: cross-instance skill sharing with privacy guarantees.
  This is a research problem, not an engineering task.
- **Skill composition**: automatically detecting and fusing skill chains.
  Useful in theory, hard to validate without extensive production data.

## The 80/20 risk

The biggest risk is that **80% of the value comes from the simplest version**:
a prompt cache with a frequency counter. If that's true, then the reflection
daemon, the Forge, the maturation pipeline — all of Phase 2-4 — are
over-engineering.

We won't know until we try. But we can de-risk by testing the hypothesis early.

## Proposed validation: manual end-to-end loop

Before building Phase 1's full infrastructure:

1. Run an agent on a set of concrete tasks (web research, data extraction, etc.)
2. Log every LLM call to a JSON file (no database, no schema — just raw logs)
3. After 50+ tasks, manually inspect the logs for recurring patterns
4. For the top 3 patterns, manually ask Claude to synthesize Python functions
5. Plug those functions back in and measure cost/latency reduction
6. If the savings are real → proceed with automation (Phase 1-3)
7. If the patterns are too varied → rethink the approach before building infra

This costs a few hours of manual work and a few dollars in LLM calls. It
validates (or invalidates) the entire premise before committing to months of
infrastructure work.

## Decision

Proceed with Phase 1, but keep the manual validation as a parallel track.
Build the trajectory logger first (it's needed regardless), accumulate real
data, and validate the pattern-detection hypothesis against actual logs
before investing heavily in the reflection daemon (Phase 2).

The system should be built bottom-up from proven value, not top-down from
the grand vision.
