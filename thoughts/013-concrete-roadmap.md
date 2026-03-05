# Thought 013: Concrete Roadmap — From Prototype to Personal System

**Date**: 2026-03-05
**Status**: Active
**Triggered by**: Completing the OpenClaw-inspired upgrade (Thought 012) and needing a prioritized action plan
**Depends on**: 010 (stretch goals), 012 (gap analysis)

---

## Current State

EvoSys v0.1.0: ~10K source lines, 656 tests, 15 tools, 34 built-in skills, Slack bot, web chat, conversation mode, LLM failover, sub-agents, embedding memory, skill marketplace, auth, webhooks.

The system is feature-rich but **empirically unvalidated**. The evolution loop has never forged a skill from real-world trajectories outside of mocked tests.

---

## Guiding Principle

> Build more intelligence, not more channels.

OpenClaw wins on breadth (23 channels, 250K lines, native apps). EvoSys wins on depth (self-evolution). Every decision below prioritizes deepening the intelligence advantage.

---

## Phase A: Validate (Week 1-2) — Zero new code

**Goal**: Prove the evolution loop works on real data. Identify what breaks.

### A.1 Daily driver usage
- Use `evosys chat --session daily` as the primary assistant for 1 week
- Tasks: research, data analysis, web extraction, file operations
- Let trajectories accumulate naturally in SQLite

### A.2 Forge validation
- Extract from the same 5 domains 5+ times each (HN, GitHub, Wikipedia, a recipe site, a product page)
- Run `evosys evolve` and observe:
  - Did it detect patterns?
  - Did it forge skills?
  - Do the forged skills actually work on new pages?
  - What's the shadow agreement rate?
- **Success criterion**: at least 1 forged skill that correctly extracts data from a previously unseen page

### A.3 Slack validation
- Set up personal Slack workspace
- Run `evosys slack` for 3+ days
- Use it for real tasks via DM
- Identify: thread mapping bugs, formatting issues, timeout problems

### A.4 Scheduler validation
- Set up 3 real watch tasks:
  - Price monitoring on a specific product
  - Hacker News top story check (every 6h)
  - Weather or news summary (daily)
- Let the scheduler run for 5+ days
- Check `inbox` tool results for quality and change detection

### A.5 Document findings
- Write Thought 014: "What Broke — First Week of Real Usage"
- Capture: forge quality, failure modes, latency, cost, UX friction

---

## Phase B: Operational Foundation (Week 3-4) — Make it always-on

**Goal**: EvoSys runs continuously without manual intervention.

### B.1 Daemon mode (`evosys install-daemon`)
- Create `src/evosys/daemon.py`
- macOS: generate launchd plist, install to `~/Library/LaunchAgents/`
- Linux: generate systemd unit, install to `~/.config/systemd/user/`
- Commands: `evosys daemon install`, `evosys daemon status`, `evosys daemon logs`, `evosys daemon uninstall`
- **Why first**: The evolution loop only works if the system accumulates trajectories continuously. Manual `evosys serve` means it's off most of the time.
- ~150 lines

### B.2 Basic observability
- Create `src/evosys/metrics.py` — in-memory counters + periodic SQLite persistence
- Track: tasks_run, tools_called, skills_hit, skills_forged, forge_failures, shadow_agreements, total_tokens, total_cost_estimate
- Add `GET /metrics` endpoint (JSON, not OpenTelemetry — keep it simple)
- Add `evosys metrics` CLI command (pretty table of last 24h / 7d / 30d)
- ~200 lines

### B.3 Docker sandbox for forged skills
- Create `src/evosys/forge/sandbox.py`
- Run forged skill code in a subprocess with restricted imports (no os, sys, subprocess, socket, ctypes)
- Use `RestrictedPython` (already in optional group) as the primary gate
- Fall back to current `exec()` when RestrictedPython is not installed
- ~120 lines

---

## Phase C: Deepen Intelligence (Week 5-8) — The distillation ladder

**Goal**: Fill in the missing tiers so the system degrades gracefully.

### C.1 Tier 2: Cached prompt skills
- When code synthesis fails but a pattern has 5+ occurrences:
  - Freeze the best 3-shot prompt (system + examples)
  - Store as a SkillRecord with `implementation_type=CACHED_PROMPT`
  - On invocation: send the cached prompt to local model (Ollama) or cloud with low temperature
- This catches patterns where HTML structure is too variable for regex but consistent enough for few-shot
- Create `src/evosys/skills/cached_prompt.py` — ~120 lines
- Modify forge pipeline to attempt code synthesis first, fall back to cached prompt

### C.2 Learnability estimator (Thought 003)
- Before spending LLM tokens on forging, estimate whether the pattern is learnable
- Signals: determinism ratio (do same inputs produce same outputs?), schema consistency, output token variance
- Use forge history as training data — if similar patterns failed before, skip
- Create `src/evosys/reflection/learnability.py` — ~150 lines
- Wire into EvolutionLoop before forge attempts

### C.3 Self-practice during idle (Thought 005)
- When the scheduler has no due tasks and the system is idle:
  - Pick a forged skill with < 10 shadow comparisons
  - Generate synthetic inputs (augment from stored trajectory params)
  - Run the skill, compare against LLM output
  - Update shadow agreement rate
- This catches degradation *before* a user hits it
- Create `src/evosys/reflection/self_practice.py` — ~150 lines
- Add to scheduler worker as a low-priority idle task

### C.4 Semantic skill routing
- Current: exact domain match (`extract:{domain}`)
- New: embed task descriptions, match against skill descriptions by cosine similarity
- Use the existing EmbeddingMemoryStore infrastructure
- On skill registration, embed the skill description
- On routing, embed the task, find closest skill above threshold
- Modify `RoutingOrchestrator` to fall back to semantic when domain match fails
- ~100 lines of changes

---

## Phase D: Mature the Ecosystem (Month 3+)

These are stretch goals that depend on Phase A-C being validated.

### D.1 Skill composition DAGs
- Allow multi-skill pipelines: `fetch → detect_type → route_to_skill → format`
- Represent as networkx DAG
- Forge composite skills from recurring multi-tool sequences (Phase 9 extension)
- ~200 lines

### D.2 Federation
- Skill manifest files (Phase 4.1) are the foundation
- Add: git-based skill registry protocol
- `evosys skills publish` pushes manifest to a git repo
- `evosys skills pull` imports from a remote registry
- Trust model: signature verification, source attribution
- ~300 lines

### D.3 Confidence lifecycle
- Decay scores on consecutive failures or missed shadow comparisons
- Promote on sustained agreement (>0.9 for 50+ comparisons → bump confidence)
- Auto-retire skills unused for 90+ days
- ~100 lines

### D.4 Observability dashboard
- Minimal HTML dashboard served from `/dashboard`
- Charts: skills forged over time, cost per task, shadow agreement distribution
- Built with vanilla JS + the `/metrics` endpoint
- ~300 lines HTML/JS

---

## Summary Timeline

| Phase | When | Focus | New Code |
|---|---|---|---|
| **A** | Week 1-2 | Validate (use it daily, no new code) | 0 lines |
| **B** | Week 3-4 | Operational foundation (daemon, metrics, sandbox) | ~470 lines |
| **C** | Week 5-8 | Deepen intelligence (Tier 2, learnability, self-practice, semantic routing) | ~520 lines |
| **D** | Month 3+ | Ecosystem maturity (DAGs, federation, dashboard) | ~900 lines |

Total new code across B-D: ~1,900 lines. EvoSys grows from 10K to ~12K lines.

---

## Anti-Goals

Things EvoSys should **not** build:

1. **More messaging channels.** Slack + web + CLI is enough. Don't build WhatsApp, Telegram, Discord, Signal adapters. That's OpenClaw's game.
2. **Native apps.** No macOS menu bar, no iOS/Android. Stay in the terminal and browser.
3. **Multi-user SaaS features.** EvoSys is a personal system. Don't build user management, billing, or team workspaces.
4. **Visual UI builder.** No Canvas/A2UI. The agent works through text, tools, and code.
5. **Voice interface.** No wake words, TTS, or STT. Text in, text out.

---

## Decision Framework

When considering a new feature, ask:

1. **Does it deepen the intelligence advantage?** (evolution quality, forge success rate, cost reduction) → Build it.
2. **Does it enable sustained usage?** (daemon mode, reliability, observability) → Build it.
3. **Does it add breadth without depth?** (new channels, new platforms, new UI surfaces) → Don't build it.
4. **Can I validate it with real usage data?** → If no data exists, run the system first.

---

## The One Metric That Matters

**Forge success rate on real-world data.**

Everything else — channels, marketplace, auth, sub-agents — is infrastructure in service of this. If the evolution loop forges skills that work on real pages, EvoSys has a unique value proposition. If it doesn't, no amount of infrastructure matters.

Phase A answers this question. Everything after Phase A depends on the answer.
