# Changelog

All notable changes to EvoSys are documented here.

## [0.1.0] — 2026-03-05

First public release.

### Core
- ReAct agent loop with 15 built-in tools (web fetch, file I/O, shell, Python eval, HTTP API, email, memory, scheduling, semantic recall, sub-agent delegation)
- Self-evolution loop: trajectory mining → pattern detection → skill forging → shadow evaluation → registration
- Dual evolution paths: domain-based extraction patterns + recurring tool-call sequences
- Skill persistence — forged skills survive process restarts (source stored in SQLite, recompiled on bootstrap)
- Skill re-forging — degraded skills automatically re-synthesized from fresh trajectory data
- 34 built-in extraction skills across 8 skill classes (HackerNews, Wikipedia, GitHub, arXiv, Reddit, recipes, products, articles)

### LLM
- LiteLLM backend supporting Anthropic, OpenAI, Google, Ollama, and any litellm-compatible provider
- ModelRouter with ordered failover, per-model health tracking, and configurable cooldown
- Embedding provider (litellm.aembedding) for semantic memory
- Local model probe (Ollama) + tier routing strategy

### Channels
- Slack bot via Socket Mode (thread → session mapping, markdown → mrkdwn formatting)
- WebSocket `/ws/chat` with streaming events and minimal chat UI
- Interactive CLI conversation mode (`evosys chat --session NAME`)
- Outbound webhook notifications (task_complete, skill_forged, evolution_cycle)

### Storage
- Trajectory store, memory store, schedule store, skill store (all async SQLAlchemy + aiosqlite)
- Embedding memory store (chunk → embed → vector search with hybrid keyword+cosine retrieval)

### Infrastructure
- Sub-agent system with depth-limited asyncio task delegation and parallel execution
- Browser profile manager with persistent Playwright contexts and cookie state
- Skill marketplace (export/import as portable JSON manifest files)
- Bearer token authentication middleware with auto-generated tokens
- FastAPI server with background evolution worker and scheduled task runner
- Typer CLI: `run`, `chat`, `slack`, `extract`, `serve`, `evolve`, `reflect`, `info`, `skills list/export/import/search`

### Quality
- 656 tests, ruff clean, pyright 0 errors
- PII sanitizer on all trajectory data (API keys, emails, SSNs, credit cards)
- AST safety check on forged skill code (blocks os, sys, subprocess, eval, exec, open)
