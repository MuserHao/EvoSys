# Thought 001: Skill Taxonomy — What Is a Skill, Really?

**Date**: 2026-03-02
**Status**: Active exploration
**Triggered by**: Phase 0 complete, designing maturation pipeline

---

## The Core Question

A "skill" in EvoSys is not a single thing. It spans a massive spectrum:

- A 3-line regex that extracts dates from text
- A Python function that transforms JSON schemas
- A cached prompt template with few-shot examples sent to a small local model
- A fine-tuned 0.5B model running on local hardware
- A call to Claude Sonnet with a specialized system prompt
- A call to Claude Code (a full agent) to solve a sub-problem

These are all "skills" in the sense that they accept input and produce output. But they
differ enormously in cost, latency, reliability, learning difficulty, and maintenance burden.

The system must understand these differences to make good decisions about *what kind of
skill to forge* for a given pattern.

## The Skill Tier Model

We propose **six tiers**, ordered by cost and capability:

```
Tier 0: Deterministic Code       — regex, lookup tables, pure functions
Tier 1: Algorithmic Code         — Python with libraries (spaCy, dateutil, lxml)
Tier 2: Cached Prompt            — fixed system prompt + few-shot → small local model
Tier 3: Fine-tuned Local Model   — LoRA/QLoRA on 0.5B-3B model, local inference
Tier 4: Cloud LLM Call           — single API call to Sonnet/GPT-4o-mini with template
Tier 5: Agent Delegation         — hand off to a full agent (Claude Code, etc.)
```

### Properties by tier

| Tier | Latency    | Cost/call | Learning cost | Reliability | Maintenance |
|------|-----------|-----------|---------------|-------------|-------------|
| 0    | <1ms      | $0        | Low           | Very high   | Very low    |
| 1    | 1-100ms   | $0        | Medium        | High        | Low         |
| 2    | 100-500ms | ~$0       | Low           | Medium      | Medium      |
| 3    | 50-200ms  | ~$0       | High          | Medium-High | High        |
| 4    | 500-5000ms| $0.001-0.01| None         | Medium      | Low         |
| 5    | 5-60s+    | $0.05-1+  | None          | Variable    | None        |

### Key insight: the tiers form a *distillation ladder*

The system doesn't jump from "cloud LLM does everything" to "local regex." It climbs
down the ladder:

```
Tier 5 (agent doing it)
  ↓ observe & record
Tier 4 (single LLM call with learned prompt)
  ↓ accumulate examples
Tier 3 (fine-tuned local model)
  ↓ analyze for determinism
Tier 2 (cached prompt on tiny model) or Tier 1 (algorithmic code)
  ↓ if pattern is truly deterministic
Tier 0 (pure function)
```

Not every skill descends all the way. Some tasks are inherently semantic and will
stabilize at Tier 2 or 3. That's fine. The goal is to find the *lowest viable tier*
for each skill, not to force everything into Tier 0.

## How the System Decides: Learnability Signals

Before attempting to forge a SliceCandidate, the system should estimate which tier
to target. Signals:

### Signals favoring lower tiers (0-1)
- Output is fully determined by input (same input → same output across all examples)
- Output is structured (JSON, CSV, fixed schema)
- The transformation can be described by rules ("extract all dates", "sort by field X")
- Low variance in output format across examples
- Small input/output space (enum-like)

### Signals favoring middle tiers (2-3)
- Output varies slightly for same input (paraphrasing, summarization)
- Requires world knowledge but in a narrow domain
- Pattern is consistent but rules are hard to articulate
- 30-100+ examples available
- Input/output are both text but with clear semantic structure

### Signals favoring higher tiers (4-5)
- Output requires reasoning, planning, or multi-step inference
- Requires broad world knowledge
- Very few examples available (cold-start)
- The "skill" is really a sub-task that itself decomposes into steps
- Output quality is subjective or hard to evaluate automatically

### Who decides?

This is the bootstrapping problem. The system needs intelligence to decide how to
deploy intelligence. Three approaches, not mutually exclusive:

1. **Heuristic scoring**: Compute determinism ratio, schema consistency, example count,
   output variance. Map these to a tier recommendation. No LLM needed. Fast, cheap,
   good enough for obvious cases.

2. **LLM-guided assessment**: For ambiguous cases, ask the cloud LLM:
   "Given these 10 I/O examples, can this transformation be implemented as a
   deterministic Python function? If not, what kind of model would be needed?"
   This is a one-time cost per candidate.

3. **Trial and error with promotion/demotion**: Start at the lowest plausible tier.
   If synthesis fails or the skill's pass rate is low, promote to the next tier up.
   If a Tier 2 skill has 100% pass rate over 1000 invocations, attempt to demote it
   to Tier 1 or 0.

Approach (3) is the most robust because it doesn't require perfect assessment upfront.
The system *tries* the cheapest option and escalates only when needed.

## How the System Divides Tasks into Skills

This is the reflection daemon's job (Phase 2), but the taxonomy affects how we think
about it.

### What makes something a "skill boundary"?

A sub-sequence of actions becomes a skill candidate when:

1. **It recurs** — same sequence appears across multiple unrelated tasks
2. **It has consistent I/O** — input and output schemas are stable across occurrences
3. **It's self-contained** — doesn't require mid-sequence human input or external state
   that changes between invocations
4. **It's at the right granularity** — not too fine (a single API call is not a skill)
   and not too coarse (the entire task is not a skill)

### Granularity is the hardest problem

Too fine: `add_header_to_http_request` — this is a utility, not a skill.
Too coarse: `research_company_and_write_report` — this is a task, not a skill.
Right: `extract_named_entities_from_html` — clear input, clear output, reusable.

Signals for right granularity:
- The sub-sequence takes structured input and produces structured output
- It appears in tasks that are otherwise different
- It could be described in one sentence
- Replacing it with a function call would not lose information

### The granularity problem connects to the tier model

Tier 0-1 skills tend to be fine-grained (single transformations).
Tier 2-3 skills can be medium-grained (multi-step within a domain).
Tier 4-5 "skills" are really coarse-grained (sub-tasks or task delegation).

The reflection daemon should probably discover candidates at multiple granularity
levels and let the Forge decide which ones are forgeable at which tier.

## Open Questions

1. **Should Tier 5 (agent delegation) even be called a "skill"?** It's really task
   decomposition, not skill acquisition. But modeling it uniformly simplifies the
   routing layer — the orchestrator doesn't need to know *how* a skill is implemented.

2. **How to handle stateful skills?** A skill that needs a logged-in browser session
   or a database connection is not a pure function. Do we model state as part of the
   input, or do we have a separate concept of "skill context"?

3. **Composite skills vs skill chains**: If Skill A always feeds into Skill B, do we
   forge a composite Skill AB, or do we keep them separate and optimize the routing?
   The answer might depend on whether the intermediate representation (A's output /
   B's input) is useful to other skills.

4. **When to stop distilling?** A Tier 2 skill (cached prompt on local model) that
   works perfectly is still burning compute. Is it worth the Forge's time to try
   synthesizing Tier 0 code? Maybe not if the skill is rarely invoked.

5. **How to evaluate Tier 4-5 skills?** For lower tiers, we have exact-match or
   near-exact-match testing. For LLM-based skills, the output is probabilistic.
   Do we use LLM-as-judge? Embedding similarity? Human feedback?

## What We Can Solve Now

- Extend `ImplementationType` enum to cover all six tiers (Phase 0 schema change)
- Add a `SkillTier` concept and `LearnabilityScore` to the schemas
- Design the trial-and-demotion loop as part of the Forge interface
- Add maturation stages to `SkillStatus`

## What We Cannot Solve Now

- The optimal granularity detection algorithm (needs real trajectory data, Phase 2)
- Evaluation of probabilistic/semantic skills (needs LLM-as-judge, Phase 3)
- The feedback loop from production usage back to re-forging (needs Phase 4 infra)
- When to stop distilling (needs cost modeling and usage statistics, Phase 4)
