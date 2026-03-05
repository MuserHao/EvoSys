# Thought 010: Stretch Goals — Where EvoSys Goes From Here

**Date**: 2026-03-04
**Status**: Active
**Triggered by**: v0.1 functionally complete; need a roadmap beyond the current implementation

---

## Where We Are

v0.1 is a functionally complete personal agent. The ReAct loop works, the self-evolution loop is correctly wired, skills persist across restarts, and the system can handle file operations, data analysis, web extraction, scheduling, memory, and external API calls. 564 tests, clean types.

The system has never been run against sustained real usage. That empirical validation is the immediate next step, not more code.

## Near-term (validate what exists)

### 1. Real-world forge validation

Run 50+ extraction requests across 5-10 domains through the evolution loop. Measure:
- What percentage of forged skills pass the I/O tests?
- Do they actually work on new pages from the same domain?
- How stable are they over time (shadow agreement rate)?

This is not a code task. It's a usage task. The code is ready; the data doesn't exist yet.

### 2. Playwright validation against real consumer sites

Enable `--browser`, hit Amazon, Best Buy, Reddit (new), Airbnb, and measure:
- Does the ProductPageSkill parse the rendered HTML correctly?
- Does the RecipeSkill work on AllRecipes via browser?
- What's the latency penalty in practice?

### 3. Scheduler end-to-end validation

Set up 3-5 real watch tasks (price monitoring, news checking) and let them run for a week. Measure:
- Do the results make sense?
- Does the agent detect changes across runs (with prior context)?
- What's the token cost per scheduled run?

---

## Medium-term stretch goals

### 4. Semantic skill routing

**Current**: exact domain match (`extract:{domain}`).
**Goal**: embed task descriptions and match against skill descriptions using cosine similarity.

This unlocks routing like "extract the price from this page" matching `ProductPageSkill` even for an unregistered domain, because the task description is semantically close to the skill's description. Requires `sentence-transformers` (already in optional group).

### 5. Skill re-forging on degradation

**Current**: skills are marked DEGRADED when shadow agreement drops, but nothing happens after that.
**Goal**: when a skill degrades, automatically re-queue it for forging with fresh trajectory data. If the site changed its HTML structure, the new forge attempt uses recent HTML and produces an updated extractor.

This closes the skill lifecycle loop: forge → deploy → monitor → degrade → re-forge.

### 6. Multi-user isolation

**Current**: single namespace for memory, schedules, and skills.
**Goal**: namespace all state by user ID. Each user gets their own memory, their own scheduled tasks, and their own forged skills. Shared built-in skills are global.

Requires: authentication on the server (API key header), user_id propagation through the runtime.

### 7. Push notifications

**Current**: results from watch tasks are stored in the DB; user must ask `inbox()`.
**Goal**: when a watch task detects a meaningful change, proactively send a notification via email (tool exists), webhook (`http_api` tool), or desktop notification.

Change detection logic: compare current answer to `previous_answer` in context; if they differ meaningfully, trigger notification. "Meaningfully" can start as string inequality and evolve to semantic comparison.

### 8. Conversation mode

**Current**: each `evosys run` is a single-turn interaction.
**Goal**: `evosys chat` opens a multi-turn REPL where the agent maintains conversation history, can ask clarifying questions, and builds on previous answers within the session.

This is the natural UI for data analysis workflows where the user iterates: "show me the data" → "filter to Q4" → "plot revenue vs expenses" → "save this chart."

---

## Long-term stretch goals

### 9. Distillation ladder (Tier 2-3)

**Current**: skills are either Tier 0-1 (deterministic code) or Tier 4-5 (LLM calls).
**Goal**: implement the middle tiers from Thought 001:

- **Tier 2 (Cached Prompt)**: freeze a system prompt + few-shot examples → run against a small local model. Cheaper than Sonnet, more flexible than regex.
- **Tier 3 (Fine-tuned Local Model)**: accumulate enough I/O pairs → LoRA fine-tune a 0.5B-3B model → deploy locally. Near-zero cost, high reliability for narrow tasks.

This requires the fine-tuning optional group (already declared in pyproject.toml) and a local model inference server.

### 10. Skill composition graph

**Current**: composite skills are linear chains (A → B → C).
**Goal**: allow DAG-structured compositions where skills can branch, merge, and conditionally route. Example: fetch page → if recipe schema present → RecipeSkill, else → ProductPageSkill, else → LLM fallback.

Requires `networkx` or similar (already in optional group) for graph representation and traversal.

### 11. Self-practice

**Current**: the system only learns from user-initiated tasks.
**Goal**: during idle time, the agent generates its own test inputs for existing skills, runs them, and identifies degradation proactively. If a skill starts failing on generated inputs, it flags for re-forging before any user is affected.

This is Thought 005's core idea, now implementable because we have the skill persistence and shadow evaluation infrastructure.

### 12. Autonomous skill discovery

**Current**: the system only forges skills for patterns it has already observed in trajectories.
**Goal**: the agent identifies common tasks in its domain (e.g., "users often ask about product prices") and preemptively builds skills for related domains it hasn't seen yet. If it has a good `ProductPageSkill`, it could attempt to forge one for a new shopping site proactively.

This is the most speculative goal — it requires the system to generalize from known patterns to unknown domains. It's the boundary between engineering and research.

### 13. Federation

**Current**: single-instance, single-user.
**Goal**: multiple EvoSys instances share forged skills through a registry protocol. If instance A forges a skill for `arxiv.org`, instance B can import it without re-forging.

Requires: skill serialization protocol, trust/verification model, discovery mechanism. This is a research-grade problem.

---

## What to do next, concretely

1. **Use the system.** Run real tasks for a week. The forge quality question can only be answered empirically.
2. **Validate browser fetch** against 5 real JS-heavy sites.
3. **Validate scheduling** with 3 real watch tasks over a few days.
4. **If forge quality is good**: implement skill re-forging on degradation (stretch goal 5).
5. **If forge quality is poor**: tune the synthesizer prompt and I/O pair selection before adding more infrastructure.

The system is at the point where building more features without usage data risks building the wrong things. Use it first.
