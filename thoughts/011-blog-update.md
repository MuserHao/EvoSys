# Thought 011: Blog Update — From Vision to Working System

**Date**: 2026-03-04
**Status**: Active
**Triggered by**: v0.1 complete; aligning the original blog post with reality

---

## How the Original Blog Post Aligns with What We Built

The original blog post (Thoughts 001-003, published as "Teaching Machines to Build Their Own Muscles") made several specific claims about how EvoSys would work. Here is an honest accounting of each.

### The Skill Tier Model (Thought 001)

**Claimed**: Six tiers from deterministic code (Tier 0) to agent delegation (Tier 5), with a "distillation ladder" that progressively moves skills down to cheaper implementations.

**What we built**: Tiers 0, 1, and 5 are fully implemented and working.

- **Tier 0 (Deterministic Code)**: 34 registered hand-crafted skills across 8 skill classes. HackerNews, Wikipedia, GitHub, arXiv, Reddit, recipes, products, news — all deterministic HTML parsing, zero LLM cost.
- **Tier 1 (Algorithmic Code)**: The forge synthesizes Python functions from LLM-observed patterns. These use `re`, `json`, `html.parser` — stdlib only, validated by AST safety check. The full pipeline works: observe → detect → synthesize → compile → test → register → persist to DB.
- **Tier 5 (Agent Delegation)**: The general-purpose ReAct agent handles arbitrary tasks using 13 tools. Any task the system can't do with a skill falls through to the agent, which uses the LLM to reason and plan.

**What we didn't build**: Tiers 2-4.

- **Tier 2 (Cached Prompt)**: not implemented. Would require a local model inference server.
- **Tier 3 (Fine-tuned Local Model)**: not implemented. Declared as optional dependency group `fine-tuning` in pyproject.toml, but no training pipeline exists.
- **Tier 4 (Cloud LLM with template)**: partially exists — the extraction agent's LLM path is essentially Tier 4 (single API call with a system prompt), but it's not formalized as a "skill" in the registry. It's the fallback, not a registered entity.

**Honest assessment**: The system currently jumps from Tier 0-1 directly to Tier 5. The middle tiers — the distillation ladder's intermediate rungs — don't exist. This means the system either has a deterministic extractor or it falls back to the full LLM. There's no graceful degradation through cached prompts or fine-tuned models. This is a real gap for tasks that are semi-structured: too variable for regex, too predictable to justify a full LLM call every time.

### The Maturation Pipeline (Thought 002)

**Claimed**: `OBSERVED → PROMPTED → SYNTHESIZED → OPTIMIZED → STABLE → DEGRADED → re-enter`

**What we built**: `OBSERVED → SYNTHESIZED → DEGRADED`. Three of the five stages.

- **OBSERVED**: PatternDetector identifies recurring domains in trajectory data. Works.
- **SYNTHESIZED**: SkillForge generates Python code, compiles it, tests it, registers it. Works. Skills persist across restarts via SkillStore.
- **DEGRADED**: ShadowEvaluator compares forged skills against LLM ground truth. If agreement drops below threshold, skill is marked DEGRADED and routing stops using it. Works. Persisted to DB.

**What we didn't build**:

- **PROMPTED**: No cached-prompt stage. Skills go directly from "pattern detected" to "code synthesized." There's no intermediate step where a cheap prompt template handles the task before full code synthesis is attempted.
- **OPTIMIZED / STABLE**: No optimization pass. Once a skill is synthesized and passing, it stays as-is. There's no mechanism to refine a Tier 1 skill down to Tier 0, or to build a richer test suite over time. The `MaturationStage` enum exists in the schema, but only `OBSERVED` and `SYNTHESIZED` are used.
- **Re-entry from DEGRADED**: Skills get marked DEGRADED but don't re-enter the forge pipeline. They stay degraded until the process restarts (which wipes in-memory state) or a manual evolution cycle happens to re-detect the pattern.

### The Bootstrapping Problem (Thought 003)

**Claimed**: The system needs intelligence to decide how to deploy intelligence. Three approaches: heuristic scoring, LLM-guided assessment, trial-and-error with promotion/demotion.

**What we built**: Heuristic scoring only.

- `boundary_confidence = min(1.0, frequency / 10.0)` — simple linear scaling
- `confidence_score = boundary_confidence * pass_rate` — multiplicative gate
- `min_pass_rate = 0.8` — hard threshold for forge success
- `shadow_degradation_threshold = 0.5` — hard threshold for degradation

No LLM-guided assessment of learnability. No trial-and-demotion across tiers. The system tries Tier 1 (code synthesis) and either succeeds or gives up. It doesn't try Tier 2 as a fallback.

**Honest assessment**: The bootstrapping approach works for the cases it handles (deterministic extraction from structured HTML), but it has no fallback path for semi-structured tasks.

### Everyday User Pain Points (Thought 008)

**Claimed**: Research/comparison, monitoring, and format conversion as the three highest-value starting points.

**What we built**:

- **Research/comparison**: Partially. The agent can fetch and extract from static HTML sites. 34 domains have deterministic skills. Browser rendering is implemented but opt-in. The agent can write Python to compare data. But it can't yet handle multi-site comparison as a single coherent task — it would need multiple `web_fetch` calls and reasoning across them, which works but is slow and token-expensive.
- **Monitoring**: Implemented. `watch`/`inbox` tools, `ScheduleStore`, background scheduler worker. The scheduler passes prior results as context so the agent can detect changes. Email notification tool exists (when SMTP configured).
- **Format conversion**: Implemented. `file_read` + `python_eval` + `file_write`. The agent's system prompt explicitly tells it to write Python for data tasks. Shell and Python are on by default in CLI mode.

---

## What the Blog Post Should Say Now

The original blog post's vision is correct in direction. The tier model is the right mental framework. The maturation pipeline is the right lifecycle. The bootstrapping problem is real.

What's different from the original vision:

1. **The system is broader than extraction.** The blog focused on structured data extraction as the primary use case. EvoSys v0.1 is a general-purpose agent that also does extraction — plus file management, data analysis, shell operations, API calls, scheduling, and memory. Extraction is one capability, not the sole purpose.

2. **The distillation ladder has two rungs, not six.** Tiers 0-1 and Tier 5 work. The middle is empty. This is the honest state. The architecture supports adding the middle tiers (the enum, the schema fields, the optional dependency groups all exist), but the implementations don't.

3. **The self-evolution loop works but is unvalidated empirically.** The mechanism is correct, tested, and persisted. But no one has run it against real production traffic to measure forge quality. The original blog post implied this would be proven by now. It isn't, because the infrastructure to support it was built in the right order (correctness before scale) but usage hasn't happened yet.

4. **The system does more practical things than the blog imagined.** The blog didn't mention scheduling, memory, email, API calls, browser rendering, or data analysis. These came from asking "what does a real user need?" rather than "what does the evolution architecture require?"

---

## Revised Blog Post Outline

If updating the published post, the honest structure would be:

### Part 1: The Vision (unchanged)
The skill tier model. The distillation ladder. The maturation pipeline. These are still the right mental framework.

### Part 2: What We Actually Built (new)
- A general-purpose agent with 13 tools and 34 domain skills
- Self-evolution from Tier 5 to Tier 0-1 (skipping the middle)
- Skill persistence, shadow evaluation, degradation
- Practical capabilities: scheduling, memory, file operations, data analysis, API calls, email

### Part 3: What's Missing and Why (new)
- The middle tiers (2-4) don't exist yet
- The maturation pipeline has 3 of 5 stages
- Forge quality is structurally sound but empirically unvalidated
- Multi-user, authentication, push notifications

### Part 4: What Comes Next (new)
- Use the system. Validate forge quality against real data.
- Semantic routing (embeddings instead of exact domain match)
- Skill re-forging on degradation (close the lifecycle loop)
- Conversation mode for interactive data analysis
- Distillation ladder middle rungs (Tier 2-3) when there's data to train on

---

## Status of Thought 006's Tier Classification

Thought 006 classified capabilities into three tiers of realism:

**Tier A (works today, just needs engineering)** — All implemented:
- Structured logging ✓
- Frequency counting ✓
- Code synthesis from I/O pairs ✓
- Shadow mode ✓
- Test suite generation (via I/O pairs) ✓

**Tier B (hard but tractable)** — Partially implemented:
- Learnability estimation ✓ (heuristic only)
- Maturation pipeline ✓ (3 of 5 stages)
- Concept drift via shadow divergence ✓
- Self-practice on verifiable skills ✗ (infrastructure exists, not triggered)

**Tier C (speculative)** — Not implemented:
- Autonomous DAG granularity detection ✗
- Automatic tier demotion ✗
- Meta-learning ✗
- Federation ✗
- Skill composition ✓ (linear chains only via CompositeForge)

Thought 006 was right. Tier A is done. Tier B is half done. Tier C is mostly untouched. The system was built bottom-up from proven value, exactly as the thought recommended.
