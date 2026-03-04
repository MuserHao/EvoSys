# EvoSys

A self-evolving general-purpose agent that gets faster and cheaper the more it's used. The system observes its own tool usage, detects recurring patterns, and autonomously forges optimized compound skills — replacing expensive multi-step LLM tool-call loops with direct skill invocations.

## How It Works

```
User task  ──►  Agent  ──►  LLM decides tools  ──►  Execute tools
                                                         │
                                                    Trajectory logged
                                                         │
                                              ┌──────────┴──────────┐
                                              │                     │
                                     Domain patterns          Tool sequences
                                     (extract:x.com ≥3x)      (A→B→C ≥3x)
                                              │                     │
                                     Forge extraction         Forge composite
                                     skill (Tier 0-1)         skill (chained)
                                              │                     │
                                              └──────────┬──────────┘
                                                         │
                                              Next request: $0, ~0ms
```

Standard agents are stateless tool-callers. EvoSys learns from its own operation: extraction patterns become deterministic skills, recurring tool-call sequences become composite skills. Both bypass the LLM entirely on subsequent requests.

## Quick Start

### Prerequisites

- Python 3.12+
- An `ANTHROPIC_API_KEY` (or other LLM provider key supported by LiteLLM)

### Install

```bash
git clone <repo-url> && cd EvoSys
uv sync          # or: pip install -e ".[dev]"
```

### Run

**General-purpose agent** (new — handles arbitrary tasks):

```bash
evosys run "What is the top story on Hacker News right now?"
evosys run "Fetch https://example.com and summarize the content"
evosys run "Extract the title and author from https://dev.to/some-article" -f json
```

**Extract data from a URL** (original extraction pipeline):

```bash
evosys extract https://news.ycombinator.com
evosys extract https://en.wikipedia.org/wiki/Python -f pretty
evosys extract https://example.com -s '{"title": "string", "description": "string"}'
```

**Start the self-evolving server** (recommended for continuous use):

```bash
evosys serve                          # http://0.0.0.0:8000
evosys serve --port 3000              # custom port
evosys serve --evolve-interval 60     # evolve every 60s instead of 5min
```

The server exposes:
- `POST /extract` — extract structured data from a URL
- `POST /agent/run` — run the general-purpose agent on any task
- `GET /skills` — list all registered skills
- `GET /status` — system health and evolution metrics
- `POST /evolve` — manually trigger an evolution cycle

**One-shot commands:**

```bash
evosys skills list          # show registered skills
evosys skills list --active # active skills only
evosys reflect              # discover patterns in trajectory data
evosys evolve               # run one evolution cycle (reflect → forge → register)
evosys info                 # show version and configuration
```

### Configuration

All settings are configurable via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | (required) | LLM provider API key |
| `EVOSYS_DB_URL` | `sqlite+aiosqlite:///data/evosys.db` | Database connection |
| `EVOSYS_LLM_MODEL` | `anthropic/claude-sonnet-4-20250514` | LLM model |
| `EVOSYS_LLM_TEMPERATURE` | `0.0` | LLM temperature |
| `EVOSYS_HTTP_TIMEOUT_S` | `30` | HTTP fetch timeout |
| `EVOSYS_SKILL_CONFIDENCE_THRESHOLD` | `0.7` | Min confidence to route to a skill |
| `EVOSYS_AGENT_MAX_ITERATIONS` | `20` | Max agent loop iterations |
| `EVOSYS_AGENT_SYSTEM_PROMPT` | (built-in) | Custom system prompt for the agent |
| `EVOSYS_MCP_SERVERS` | `[]` | MCP server configs as JSON |

### MCP Integration

Connect external MCP servers to give the agent access to additional tools:

```bash
export EVOSYS_MCP_SERVERS='[{"name": "fs", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"]}]'
evosys serve
```

## Architecture

```
src/evosys/
├── agents/          # Agent (general-purpose), ExtractionAgent (URL extraction)
├── tools/           # Tool protocol, ToolRegistry, SkillToolAdapter, builtins, MCP
├── orchestration/   # RoutingOrchestrator (domain-based skill lookup)
├── executors/       # HttpExecutor, SkillExecutor
├── skills/          # SkillRegistry, built-in skills (HN, Wikipedia, article metadata)
├── forge/           # SkillForge (extraction), CompositeForge (tool sequences)
├── reflection/      # PatternDetector, SequenceDetector, ShadowEvaluator
├── storage/         # SQLAlchemy models, TrajectoryStore
├── trajectory/      # TrajectoryLogger, PII sanitizer
├── llm/             # LiteLLM wrapper with tool-calling support
├── loop.py          # EvolutionLoop (dual path: domains + tool sequences)
├── server.py        # FastAPI server with background evolution
├── bootstrap.py     # Runtime wiring
├── cli.py           # Typer CLI
└── config.py        # Environment-based configuration
```

**Two evolution paths:**

1. **Domain-based** (Phases 0-4): Extract request → Router checks skill registry → miss → LLM extraction → log trajectory → detect recurring domains → forge extraction skill → register
2. **Sequence-based** (Phase 9): Agent runs tasks → logs tool calls → detect recurring tool sequences (A→B→C) → forge composite skill that chains tools → register

## Built-in Skills

Ships with 7 hand-crafted Tier 0 skills (regex/html.parser, no LLM):

| Skill | Domain |
|-------|--------|
| HackerNewsSkill | `news.ycombinator.com` |
| WikipediaSummarySkill | `en.wikipedia.org` |
| ArticleMetadataSkill | `medium.com`, `dev.to`, `techcrunch.com`, `arstechnica.com`, `theverge.com` |

Built-in agent tools: `web_fetch` (HTTP fetcher), `extract_structured` (wraps ExtractionAgent). All registered skills are also available as agent tools.

## Development

```bash
uv sync --group dev          # install dev dependencies
pytest tests/ -v             # run tests (442 tests)
ruff check src/ tests/       # lint
pyright src/evosys/          # type check
```

## Current Status

Phases 0-9 implemented and tested (442 tests, ruff clean, pyright 0 errors):

- **Phase 0** — Data contracts, interface ABCs, PII sanitizer
- **Phase 1** — Extraction pipeline (URL → HTML → LLM → JSON → SQLite), skill registry, domain-based routing, CLI, built-in skills
- **Phase 2** — Reflection daemon, frequency-based pattern detection, shadow evaluator
- **Phase 3** — LLM code synthesis, AST safety validation, skill forge pipeline
- **Phase 4** — Evolution loop, FastAPI server with background evolution
- **Phase 5** — Tool abstraction layer (Tool protocol, SkillToolAdapter, ToolRegistry)
- **Phase 6** — LLM tool calling (complete_with_tools, multi-provider via LiteLLM)
- **Phase 7** — General agent loop (ReAct-style, arbitrary tasks, trajectory logging)
- **Phase 8** — MCP integration (connect external MCP servers, surface tools to agent)
- **Phase 9** — Self-evolution on tool usage (SequenceDetector, CompositeForge, dual evolution paths)

### Not yet implemented

- Embedding-based semantic routing (currently domain-exact-match)
- HDBSCAN clustering (currently frequency-based grouping)
- Docker/WASM sandboxing for forged skills
- Confidence decay and skill lifecycle management
- Federation (cross-instance skill sharing)
- Streaming responses
- Observability dashboard UI
