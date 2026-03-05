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

**Interactive conversation mode:**

```bash
evosys chat                           # ephemeral session
evosys chat --session work            # persistent — survives restarts
```

Inside the REPL you get Rich-formatted output, message accumulation across turns, and commands like `/clear`, `/history`, `/save`, `/quit`.

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
- `WS /ws/chat` — real-time WebSocket chat (when `EVOSYS_WEB_CHAT_ENABLED=true`)

**Slack bot** (Socket Mode — no public URL needed):

```bash
uv sync --group slack
export EVOSYS_SLACK_BOT_TOKEN=xoxb-...
export EVOSYS_SLACK_APP_TOKEN=xapp-...
evosys slack
```

Or start via the server (runs alongside HTTP endpoints):

```bash
export EVOSYS_SLACK_ENABLED=true
evosys serve
```

The bot responds to direct messages and @mentions. Each Slack thread maps to an independent agent session with conversation history.

**Skill marketplace:**

```bash
evosys skills list                    # show registered skills
evosys skills list --active           # active skills only
evosys skills export extract:example.com -o ./exports/
evosys skills import ./exports/extract:example.com.evoskill.json
evosys skills search "recipe"
```

**One-shot commands:**

```bash
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
| `EVOSYS_LLM_MODEL` | `anthropic/claude-sonnet-4-20250514` | Primary LLM model |
| `EVOSYS_LLM_FALLBACK_MODELS` | (none) | Comma-separated fallback models for failover |
| `EVOSYS_LLM_COOLDOWN_S` | `60` | Seconds to cool down a failed model before retry |
| `EVOSYS_LLM_TEMPERATURE` | `0.0` | LLM temperature |
| `EVOSYS_HTTP_TIMEOUT_S` | `30` | HTTP fetch timeout |
| `EVOSYS_SKILL_CONFIDENCE_THRESHOLD` | `0.7` | Min confidence to route to a skill |
| `EVOSYS_AGENT_MAX_ITERATIONS` | `20` | Max agent loop iterations |
| `EVOSYS_AGENT_TIMEOUT_S` | (none) | Wall-clock timeout per agent run |
| `EVOSYS_ENABLE_SHELL_TOOL` | `false` | Enable shell (server mode; CLI defaults to true) |
| `EVOSYS_ENABLE_PYTHON_EVAL_TOOL` | `false` | Enable Python eval (server mode; CLI defaults to true) |
| `EVOSYS_ENABLE_BROWSER_FETCH` | `false` | Use Playwright for JS-rendered pages |
| `EVOSYS_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model for semantic memory |
| `EVOSYS_EMBEDDING_DIMENSIONS` | `1536` | Embedding vector dimensions |
| `EVOSYS_SUB_AGENT_MAX_DEPTH` | `2` | Max sub-agent nesting depth |
| `EVOSYS_SUB_AGENT_MAX_CONCURRENT` | `3` | Max concurrent sub-agent tasks |
| `EVOSYS_SLACK_BOT_TOKEN` | (none) | Slack bot token (xoxb-...) |
| `EVOSYS_SLACK_APP_TOKEN` | (none) | Slack app-level token (xapp-...) |
| `EVOSYS_SLACK_ENABLED` | `false` | Start Slack bot with server |
| `EVOSYS_WEB_CHAT_ENABLED` | `false` | Enable WebSocket chat endpoint |
| `EVOSYS_AUTH_ENABLED` | `false` | Enable Bearer token auth on API |
| `EVOSYS_AUTH_TOKEN` | (auto-generated) | Custom auth token (auto-generates if empty) |
| `EVOSYS_LOCAL_MODEL_ENABLED` | `false` | Enable local model routing via Ollama |
| `EVOSYS_SMTP_HOST` / `_USER` / `_PASSWORD` | (none) | SMTP config for email notifications |
| `EVOSYS_MCP_SERVERS` | `[]` | MCP server configs as JSON |

### LLM Failover

Configure fallback models for automatic failover when the primary model is unavailable:

```bash
export EVOSYS_LLM_MODEL=anthropic/claude-sonnet-4-20250514
export EVOSYS_LLM_FALLBACK_MODELS=openai/gpt-4o,anthropic/claude-haiku-4-5-20251001
evosys run "Your task here"
```

The router tries models in order. A model that fails repeatedly enters cooldown (configurable via `EVOSYS_LLM_COOLDOWN_S`) and is skipped until the cooldown expires.

### MCP Integration

Connect external MCP servers to give the agent access to additional tools:

```bash
export EVOSYS_MCP_SERVERS='[{"name": "fs", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"]}]'
evosys serve
```

### Authentication

Enable Bearer token authentication on the HTTP API:

```bash
export EVOSYS_AUTH_ENABLED=true
evosys serve
# Token is auto-generated on first startup and saved to data/.evosys_token
# Or set your own:
export EVOSYS_AUTH_TOKEN=my-secret-token
```

Authenticated requests:

```bash
curl -H "Authorization: Bearer $(cat data/.evosys_token)" http://localhost:8000/agent/run \
  -d '{"task": "Hello"}'
```

## Architecture

```
src/evosys/
├── agents/          # Agent (ReAct loop), ExtractionAgent, SubAgentManager
├── channels/        # Slack bot, WebSocket chat, CLI REPL, webhooks
│   ├── slack/       # Socket Mode bot, thread mapping, mrkdwn formatting
│   ├── web/         # WebSocket handler, streaming agent, chat UI
│   ├── cli_chat.py  # Rich interactive REPL
│   └── webhook.py   # Outbound event notifications
├── tools/           # 15 built-in tools, Tool protocol, ToolRegistry, MCP adapter
├── orchestration/   # RoutingOrchestrator (domain-based skill lookup)
├── executors/       # HttpExecutor (httpx + Playwright), SkillExecutor, BrowserProfiles
├── skills/          # SkillRegistry, 8 skill classes, 34 domains, Marketplace
├── forge/           # SkillForge (extraction), CompositeForge (sequences), Reforger
├── reflection/      # PatternDetector, SequenceDetector, ShadowEvaluator
├── storage/         # TrajectoryStore, MemoryStore, ScheduleStore, SkillStore, EmbeddingStore
├── trajectory/      # TrajectoryLogger, PII sanitizer
├── llm/             # LiteLLM client, ModelRouter (failover), health tracking, embeddings
├── security/        # Bearer token auth middleware, auto-generated tokens
├── loop.py          # EvolutionLoop (dual path: domains + sequences + re-forge)
├── server.py        # FastAPI server + WebSocket + Slack lifecycle + auth
├── bootstrap.py     # Runtime wiring + forged skill reload
├── cli.py           # Typer CLI (run, chat, slack, skills, evolve, serve)
└── config.py        # Environment-based configuration
```

**Two evolution paths:**

1. **Domain-based** — Extraction requests to the same domain 3+ times → forge a deterministic skill → register → route future requests at $0
2. **Sequence-based** — Recurring tool-call patterns (A→B→C) across sessions → forge composite skill → register → skip LLM planning

**Skill re-forging** — When a forged skill's shadow agreement drops below threshold, the system automatically gathers fresh trajectory data and re-synthesizes a replacement.

**Learning loop for both agent types:**

The general agent's `web_fetch` calls now log synthetic `llm_extract` records, so the evolution loop learns from *all* web interactions — not just the dedicated extraction pipeline.

## Built-in Tools

| Tool | Description | Default |
|------|-------------|---------|
| `web_fetch` | Fetch a URL (httpx or Playwright) | Always on |
| `extract_structured` | Extract structured data via skills/LLM | Always on |
| `file_read` / `file_write` / `file_list` | Local file operations | Always on |
| `remember` / `recall` | Cross-session persistent memory | Always on |
| `semantic_recall` | Natural language search over stored memory | Always on |
| `delegate_task` | Delegate sub-tasks to child agents | Always on |
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
pytest tests/ -v             # run tests (656 tests)
ruff check src/ tests/       # lint
pyright src/evosys/          # type check
```

Optional groups:
```bash
uv sync --group browser           # Playwright for JS-rendered pages
uv sync --group slack             # Slack bot (slack_bolt + slack_sdk)
uv sync --group forge-sandbox     # RestrictedPython + jsonschema for safer forge
uv sync --group skill-clustering  # sentence-transformers + HDBSCAN for semantic patterns
uv sync --group migrations        # Alembic for production schema migrations
```

## Current Status (v0.1.0)

**656 tests, ruff clean, pyright 0 errors. ~10K source lines.**

### Implemented

- **ReAct agent loop** — general-purpose task execution with 15 tools
- **Self-evolution loop** — observe → detect patterns → forge skills → persist to DB
- **Skill persistence** — forged skills survive restarts; source code stored and recompiled on bootstrap
- **Skill re-forging** — degraded skills are automatically re-synthesized from fresh trajectories
- **34 built-in extraction skills** — deterministic parsing for common domains (recipes, products, news, academic papers, GitHub, Reddit)
- **Cross-session memory** — `remember`/`recall` with namespace isolation
- **Semantic memory** — embedding-based recall via `semantic_recall` tool (hybrid vector + keyword search)
- **LLM failover** — `ModelRouter` with ordered fallback chain, per-model health tracking, and cooldown
- **Sub-agent delegation** — `delegate_task` tool spawns depth-limited child agents, supports parallel execution
- **Slack bot** — Socket Mode integration, thread → session mapping, markdown → mrkdwn conversion
- **Web chat** — WebSocket `/ws/chat` with streaming events and minimal chat UI
- **Conversation mode** — Rich interactive REPL (`evosys chat`) with session persistence
- **Skill marketplace** — export/import skills as portable manifest files
- **Browser profiles** — named persistent Playwright contexts with cookie state
- **Local model routing** — Ollama probe + tier strategy for routing simple tasks locally
- **Authentication** — Bearer token middleware with auto-generated tokens
- **Outbound webhooks** — notify external services on task_complete, skill_forged, evolution_cycle
- **Scheduled monitoring** — `watch`/`inbox` with background scheduler
- **Browser rendering** — Playwright path for JavaScript-heavy sites (opt-in)
- **External actions** — HTTP API calls and email notifications
- **Shadow evaluation** — compare forged skills against LLM ground truth; degrade on drift
- **Safety** — AST-checked forge code, opt-in dangerous tools, PII sanitizer, request timeouts
- **Learning from both agents** — general agent web fetches feed the evolution loop

### Not Yet Implemented

- HDBSCAN clustering (currently frequency-based grouping)
- Docker/WASM sandboxing for forged skills
- Federation (cross-instance skill sharing via git repos)
- Observability dashboard UI
- Telegram bot

### Stretch Goals

See [Thought 010](thoughts/010-stretch-goals.md) for the full roadmap beyond v0.1.

## License

MIT
