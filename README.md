# EvoSys

A self-evolving extraction agent that replaces expensive LLM calls with cheap, deterministic micro-skills over time. The system observes its own operation, detects recurring patterns, and autonomously forges optimized skills — getting faster and cheaper the longer it runs.

## How It Works

```
User request  ──►  Router  ──►  Skill exists?  ──YES──►  Local skill (~0ms, $0)
                                     │
                                     NO
                                     │
                                     ▼
                               Cloud LLM (slow, $$)
                                     │
                                     ▼
                              Trajectory logged
                                     │
                                     ▼
                           Pattern detected (≥3x)
                                     │
                                     ▼
                           Skill forged & registered
                                     │
                                     ▼
                           Next request uses skill ──► $0
```

The system runs a background evolution loop: detect recurring LLM extraction patterns → synthesize Python code via LLM → validate safety (AST check) → test against historical I/O → shadow-evaluate against LLM ground truth → register as a skill.

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

**Extract data from a URL:**

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
| `EVOSYS_LLM_MODEL` | `anthropic/claude-sonnet-4-20250514` | LLM model for extraction |
| `EVOSYS_LLM_TEMPERATURE` | `0.0` | LLM temperature |
| `EVOSYS_HTTP_TIMEOUT_S` | `30` | HTTP fetch timeout |
| `EVOSYS_SKILL_CONFIDENCE_THRESHOLD` | `0.7` | Min confidence to route to a skill |

## Architecture

```
src/evosys/
├── agents/          # ExtractionAgent (orchestrates skill vs LLM path)
├── orchestration/   # RoutingOrchestrator (domain-based skill lookup)
├── executors/       # HttpExecutor, SkillExecutor
├── skills/          # SkillRegistry, built-in skills (HN, Wikipedia, article metadata)
├── forge/           # SkillSynthesizer (LLM code gen), SkillForge (validate + register)
├── reflection/      # PatternDetector, ShadowEvaluator, ReflectionDaemon
├── storage/         # SQLAlchemy models, TrajectoryStore
├── trajectory/      # TrajectoryLogger, PII sanitizer
├── llm/             # LiteLLM wrapper
├── loop.py          # EvolutionLoop (reflect → forge → register)
├── server.py        # FastAPI server with background evolution
├── bootstrap.py     # Runtime wiring
├── cli.py           # Typer CLI
└── config.py        # Environment-based configuration
```

**Data flow:** Extract request → Router checks skill registry → skill hit: invoke directly ($0) / miss: LLM extraction → log trajectory → pattern detector finds recurring domains → forge synthesizes Python code → AST safety check → shadow evaluation → register skill → future requests routed to skill.

## Built-in Skills

Ships with 7 hand-crafted Tier 0 skills (regex/html.parser, no LLM):

| Skill | Domain |
|-------|--------|
| HackerNewsSkill | `news.ycombinator.com` |
| WikipediaSummarySkill | `en.wikipedia.org` |
| ArticleMetadataSkill | `medium.com`, `dev.to`, `techcrunch.com`, `arstechnica.com`, `theverge.com` |

Additional skills are automatically forged as the system processes more URLs.

## Development

```bash
uv sync --group dev          # install dev dependencies
pytest tests/ -v             # run tests (303 tests)
ruff check src/ tests/       # lint
pyright src/evosys/          # type check
```

## Current Status

Phases 0-4 are implemented and tested (303 tests, ruff clean, pyright 0 errors):

- **Phase 0** — Data contracts, interface ABCs, PII sanitizer
- **Phase 1** — Extraction pipeline (URL → HTML → LLM → JSON → SQLite), skill registry, domain-based routing, CLI, built-in skills, bootstrap
- **Phase 2** — Reflection daemon, frequency-based pattern detection, shadow evaluator
- **Phase 3** — LLM code synthesis, AST safety validation, skill forge pipeline
- **Phase 4** — Evolution loop, FastAPI server with background evolution, shadow evaluation integration

### Not yet implemented

- Embedding-based semantic routing (currently domain-exact-match)
- HDBSCAN clustering (currently frequency-based grouping)
- Docker/WASM sandboxing for forged skills
- Confidence decay and skill lifecycle management
- Skill composition (auto-chaining sequential skills)
- Federation (cross-instance skill sharing)
- Observability dashboard UI
