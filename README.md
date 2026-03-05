# EvoSys

A self-evolving general-purpose agent that gets faster and cheaper the more it's used. The system observes its own tool usage, detects recurring patterns, and autonomously forges optimized skills — replacing expensive multi-step LLM tool-call loops with direct skill invocations.

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
                                              Skill persisted to DB ✓
```

Standard agents are stateless tool-callers. EvoSys learns from its own operation: extraction patterns become deterministic skills, recurring tool-call sequences become composite skills. Both bypass the LLM entirely on subsequent requests. Forged skills persist across restarts.

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

**General-purpose agent** (shell + Python enabled by default):

```bash
evosys run "What is the top story on Hacker News right now?"
evosys run "Read ~/data/sales.csv and show me total revenue by month"
evosys run "Find all Python files in this project larger than 100 lines"
evosys run "Fetch https://arxiv.org/abs/2106.09685 and summarize the paper"
```

**With browser rendering** (for JavaScript-heavy sites):

```bash
uv sync --group browser && playwright install chromium
evosys run --browser "What is the price of the Sony WH-1000XM5 on Amazon?"
```

**With session memory** (carry context across runs):

```bash
evosys run --session work "Remember: my budget for headphones is $200"
evosys run --session work "Find noise-cancelling headphones within my budget"
```

**Restrict capabilities** (for untrusted input or CI):

```bash
evosys run --no-shell --no-python "Summarize this Wikipedia article"
```

**Extract structured data** (dedicated extraction pipeline):

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
- `GET /skills` — list all registered skills (with live invocation counts)
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
| `EVOSYS_AGENT_TIMEOUT_S` | (none) | Wall-clock timeout per agent run |
| `EVOSYS_ENABLE_SHELL_TOOL` | `false` | Enable shell (server mode; CLI defaults to true) |
| `EVOSYS_ENABLE_PYTHON_EVAL_TOOL` | `false` | Enable Python eval (server mode; CLI defaults to true) |
| `EVOSYS_ENABLE_BROWSER_FETCH` | `false` | Use Playwright for JS-rendered pages |
| `EVOSYS_SMTP_HOST` / `_USER` / `_PASSWORD` | (none) | SMTP config for email notifications |
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
├── agents/          # Agent (ReAct loop), ExtractionAgent (URL→JSON)
├── tools/           # 13 built-in tools, Tool protocol, ToolRegistry, MCP adapter
├── orchestration/   # RoutingOrchestrator (domain-based skill lookup)
├── executors/       # HttpExecutor (httpx + Playwright), SkillExecutor
├── skills/          # SkillRegistry, 8 skill classes, 34 registered domains
├── forge/           # SkillForge (extraction), CompositeForge (tool sequences)
├── reflection/      # PatternDetector, SequenceDetector, ShadowEvaluator
├── storage/         # TrajectoryStore, MemoryStore, ScheduleStore, SkillStore
├── trajectory/      # TrajectoryLogger, PII sanitizer
├── llm/             # LiteLLM wrapper with tool-calling support
├── loop.py          # EvolutionLoop (dual path: domains + tool sequences)
├── server.py        # FastAPI server with background evolution + scheduler
├── bootstrap.py     # Runtime wiring + forged skill reload
├── cli.py           # Typer CLI
└── config.py        # Environment-based configuration
```

**Two evolution paths:**

1. **Domain-based** — Extraction requests to the same domain 3+ times → forge a deterministic skill → register → route future requests at $0
2. **Sequence-based** — Recurring tool-call patterns (A→B→C) across sessions → forge composite skill → register → skip LLM planning

**Learning loop for both agent types:**

The general agent's `web_fetch` calls now log synthetic `llm_extract` records, so the evolution loop learns from *all* web interactions — not just the dedicated extraction pipeline.

## Built-in Tools

| Tool | Description | Default |
|------|-------------|---------|
| `web_fetch` | Fetch a URL (httpx or Playwright) | Always on |
| `extract_structured` | Extract structured data via skills/LLM | Always on |
| `file_read` / `file_write` / `file_list` | Local file operations | Always on |
| `remember` / `recall` | Cross-session persistent memory | Always on |
| `watch` / `inbox` | Schedule recurring tasks, check results | Always on |
| `http_api` | Call REST APIs (POST/PUT/DELETE/GET) | Always on |
| `send_email` | Send email via SMTP | When SMTP configured |
| `shell_exec` | Execute shell commands | CLI: on, Server: opt-in |
| `python_eval` | Execute Python code | CLI: on, Server: opt-in |

## Built-in Skills

34 registered domains across 8 skill classes:

| Skill | Domains | What it extracts |
|-------|---------|-----------------|
| HackerNewsSkill | `news.ycombinator.com` | title, score, author, comments |
| WikipediaSummarySkill | `en.wikipedia.org` | title, first paragraph, categories |
| GitHubRepoSkill | `github.com` | name, description, stars, forks, language, license, topics |
| ArxivPaperSkill | `arxiv.org` | title, authors, abstract, submission date, subjects |
| RedditThreadSkill | `old.reddit.com`, `www.reddit.com` | title, subreddit, score, top comments |
| RecipeSkill | 8 recipe sites | name, ingredients, times, servings, calories (schema.org) |
| ProductPageSkill | 6 shopping sites | name, price, rating, availability (schema.org) |
| ArticleMetadataSkill | 14 news/blog sites | title, description, author, date (og: + meta) |

Plus any skills the system forges at runtime from observed patterns.

## Development

```bash
uv sync --group dev          # install dev dependencies
pytest tests/ -v             # run tests (564 tests)
ruff check src/ tests/       # lint
pyright src/evosys/          # type check
```

Optional groups:
```bash
uv sync --group browser           # Playwright for JS-rendered pages
uv sync --group forge-sandbox     # RestrictedPython + jsonschema for safer forge
uv sync --group skill-clustering  # sentence-transformers + HDBSCAN for semantic patterns
uv sync --group migrations        # Alembic for production schema migrations
```

## Current Status (v0.1.0)

**564 tests, ruff clean, pyright 0 errors.**

### Implemented

- **ReAct agent loop** — general-purpose task execution with 13 tools
- **Self-evolution loop** — observe → detect patterns → forge skills → persist to DB
- **Skill persistence** — forged skills survive restarts; source code stored and recompiled on bootstrap
- **34 built-in extraction skills** — deterministic parsing for common domains (recipes, products, news, academic papers, GitHub, Reddit)
- **Cross-session memory** — `remember`/`recall` with namespace isolation
- **Scheduled monitoring** — `watch`/`inbox` with background scheduler
- **Browser rendering** — Playwright path for JavaScript-heavy sites (opt-in)
- **External actions** — HTTP API calls and email notifications
- **Shadow evaluation** — compare forged skills against LLM ground truth; degrade on drift
- **Safety** — AST-checked forge code, opt-in dangerous tools, PII sanitizer, request timeouts
- **Learning from both agents** — general agent web fetches feed the evolution loop

### Not Yet Implemented

- Embedding-based semantic routing (currently domain-exact-match)
- HDBSCAN clustering (currently frequency-based grouping)
- Docker/WASM sandboxing for forged skills
- Federation (cross-instance skill sharing)
- Streaming responses
- Multi-user authentication and isolation
- Push notifications (email tool exists, but no automated alert-on-change)
- Observability dashboard UI

### Stretch Goals

See [Thought 010](thoughts/010-stretch-goals.md) for the full roadmap beyond v0.1.

## License

MIT
