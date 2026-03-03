# EvoSys

> *A self-evolving autonomous agent ecosystem that transforms expensive general intelligence into a network of specialized, near-zero-cost micro-skills — through observation, reflection, and autonomous differentiation.*

---

## Table of Contents

1. [Grand Vision & Philosophy](#1-grand-vision--philosophy)
2. [Core Innovations](#2-core-innovations)
3. [System Architecture Overview](#3-system-architecture-overview)
4. [Evolutionary Workflow — End-to-End Example](#4-evolutionary-workflow--end-to-end-example)
5. [Detailed Development Roadmap](#5-detailed-development-roadmap)
   - [Phase 0: Foundations & Design Contracts](#phase-0-foundations--design-contracts)
   - [Phase 1: Infrastructure & The All-Seeing Eye](#phase-1-infrastructure--the-all-seeing-eye)
   - [Phase 2: Cognition — Reflection, Clustering & Boundary Detection](#phase-2-cognition--reflection-clustering--boundary-detection)
   - [Phase 3: The Forge — Code Synthesis & Sandboxed Auto-Eval](#phase-3-the-forge--code-synthesis--sandboxed-auto-eval)
   - [Phase 4: Dynamic Routing, Concept Drift & Skill Lifecycle](#phase-4-dynamic-routing-concept-drift--skill-lifecycle)
   - [Phase 5: Federation, Composition & Ecosystem](#phase-5-federation-composition--ecosystem)
6. [Open Research Questions](#6-open-research-questions)
7. [Design Principles](#7-design-principles)
8. [Tech Stack Reference](#8-tech-stack-reference)

---

## 1. Grand Vision & Philosophy

### 1.1 From Tool-User to Tool-Creator

Current agent frameworks (LangGraph, AutoGPT, OpenClaw) are fundamentally **puppets**: a general LLM brain issues commands to system APIs, and every execution of the same task consumes identical compute, tokens, and time regardless of how many times the system has done it before.

This violates the most basic law of biological learning: **repetition should reduce cost.**

EvoSys is built around a different principle. It does not merely use intelligence — it **accumulates and solidifies** it. High-dimensional LLM reasoning is progressively distilled downward into lightweight, deterministic, millisecond-level local micro-skills. The system gets cheaper, faster, and more reliable the longer it runs.

### 1.2 The Cell Differentiation Model

EvoSys treats its own computational ecosystem as a living organism governed by the same pressures as biological evolution: resource scarcity, selective pressure, and specialization.

**Initial state — the Stem Cell:**
A maximally capable but maximally expensive universal agent: a frontier LLM (Claude Opus / GPT-4o) backed by a general-purpose executor. It can do anything. It is slow and costly.

**Evolved state — a Differentiated Ecosystem:**

```
                    [ Orchestrator (Minimal LLM) ]
                   /         |         |          \
          [Skill_A]    [Skill_B]   [Skill_C]   [Skill_D ...]
         Python fn    0.5B model   Regex+NLP    Cached prompt
          ~0ms, $0    ~10ms, $0    ~1ms, $0     ~50ms, $0
```

Each leaf node is a **micro-skill**: a frozen, validated, domain-specific function that costs nothing to call and responds in milliseconds. The orchestrator at the top is progressively simplified as more skills are forged — it no longer needs to reason about *how*, only *which skill* to route to.

### 1.3 Why "EvoSys" — Not Just "EvoSkill"

The name reflects a broader ambition. It is not only the **skills** that evolve.

- The **orchestrator's routing logic** evolves as the skill registry grows
- The **topology** of the agent graph evolves (flat → hierarchical → federated)
- The **reflection daemon** itself can be upgraded by the system when better clustering algorithms become available
- Eventually, the system's **own meta-strategy** for when and how to forge new skills is learned, not hardcoded

EvoSys is the evolution of the entire system, not just its components.

---

## 2. Core Innovations

### 2.1 Autonomous Task Slicing via Trajectory DAG Analysis

The defining capability of EvoSys. The system finds its own cut points without human-defined task boundaries.

**How it works:**

1. **Trajectory Graphing**: Every LLM reasoning step and tool invocation is recorded as a node in a Directed Acyclic Graph (DAG). Nodes represent states or actions; edges represent data flow.

2. **Isomorphic Subgraph Discovery**: A background reflection process compares thousands of historical DAGs. When a subgraph (e.g., `fetch_html → locate_table_DOM → extract_text → serialize_JSON`) appears frequently across unrelated macro-tasks, it is flagged.

3. **I/O Signature Extraction**: The boundary is confirmed when the subgraph's input and output have semantically consistent structure across all occurrences. A consistent I/O signature means the subgraph is a deterministic function in disguise.

4. **Slicing & Forging**: The subgraph is extracted, its I/O examples are compiled into a test suite, and a code synthesis engine attempts to forge it into a local Python function or a tiny fine-tuned model.

### 2.2 Closed-Loop Auto-Evaluation

EvoSys never deploys a skill it has not validated. The sandboxed auto-eval pipeline:
- Uses historical I/O pairs as ground truth tests
- Runs generated code in an isolated Docker/WASM container
- Applies LLM-guided self-correction on failure (up to N retries)
- Only promotes a skill to the registry after full test passage

### 2.3 Concept Drift Detection

Static skills in a dynamic world will degrade silently. EvoSys monitors live skill performance against a rolling baseline. When output distribution shifts beyond a threshold, the skill is flagged for re-forging — not just discarded, but automatically re-trained on fresh data.

### 2.4 Skill Composition & Auto-Chaining

When the orchestrator's routing layer detects that two registered skills are frequently invoked in sequence (Skill_A output → Skill_B input), EvoSys can automatically forge a **composite skill** — a single unit that chains A and B with zero orchestrator overhead between them.

---

## 3. System Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        EvoSys Runtime                            │
│                                                                  │
│  User Input                                                      │
│      │                                                           │
│      ▼                                                           │
│  ┌─────────────────────────────────────────┐                    │
│  │         Smart Router / Orchestrator      │                    │
│  │  - Semantic search over Skill Registry   │                    │
│  │  - Confidence threshold gating           │                    │
│  │  - Fallback to Cloud LLM if no match     │                    │
│  └────────────┬──────────────┬─────────────┘                    │
│               │              │                                   │
│       [Local Skills]   [Cloud LLM + Executor]                    │
│       Fast / $0        Expensive / Capable                       │
│               │              │                                   │
│               └──────────────┘                                   │
│                      │                                           │
│               Trajectory Logger ◄─────────────────────┐         │
│               (Every action, state, reasoning, I/O)    │         │
│                      │                                 │         │
│                      ▼                                 │         │
│            ┌──────────────────┐                        │         │
│            │  Persistent Store │                        │         │
│            │  - SQLite (trace) │                        │         │
│            │  - VectorDB (emb) │                        │         │
│            └────────┬─────────┘                        │         │
│                     │                                  │         │
│                     ▼                          ┌───────┴──────┐  │
│           ┌──────────────────┐                 │  Skill       │  │
│           │ Reflection Daemon │                 │  Registry    │  │
│           │ (offline, async)  │                 │  (JSON +     │  │
│           │ - Clustering      │                 │   VectorDB)  │  │
│           │ - DAG subgraph    │                 └──────────────┘  │
│           │   discovery       │                                   │
│           │ - Boundary detect │                                   │
│           └────────┬──────────┘                                   │
│                    │                                              │
│                    ▼                                              │
│           ┌──────────────────┐                                   │
│           │   The Forge       │                                   │
│           │ - Code synthesis  │                                   │
│           │ - Sandbox eval    │                                   │
│           │ - Self-correction │                                   │
│           │ - Skill promotion │──────────────────────────────────┘
│           └──────────────────┘                                   │
└──────────────────────────────────────────────────────────────────┘
```

**Data flows clockwise**: execution produces trajectories → trajectories feed the reflection daemon → the daemon identifies slice candidates → the forge produces and validates skills → validated skills enter the registry → the router uses skills on the next execution.

---

## 4. Evolutionary Workflow — End-to-End Example

**Initial state (expensive cloud LLM doing all the work):**

User: *"Research Company A and B's latest core products and extract the name of their technical leads into data.csv."*

The LLM invokes search APIs, opens web pages, reads large HTML blobs (tens of thousands of tokens), performs entity extraction, formats output, and writes to disk.

**Evolution process:**

| Step | What happens |
|------|-------------|
| Trajectory capture | Every action logged: fetch URL → parse HTML → extract entities → serialize JSON → write CSV |
| Pattern accumulation | Over weeks, same sub-sequence appears for companies C, D, E and for unrelated blog post extraction tasks |
| Reflection fires | HDBSCAN clusters `[fetch_html → extract_named_entities → to_JSON]` as a high-frequency subgraph with consistent I/O signature |
| LLM confirms boundary | Teacher LLM analyzes 50 historical I/O pairs: input = raw HTML string, output = `{name: str, title: str}[]`. Signature confirmed. |
| Forge synthesizes | Python function written using `spaCy` + custom regex, no LLM API calls |
| Sandbox validates | All 50 historical outputs matched. Promoted as `Skill_EntityExtraction_HTML_v1` |
| Next run | Orchestrator routes HTML → local skill. Token cost for this step: 0. Latency: ~3ms vs ~8s |

**Post-evolution execution of the same task type:**

```
[Orchestrator LLM]  →  plan: "1. search. 2. fetch HTML. 3. pipe to Skill_EntityExtraction_HTML_v1. 4. write CSV"
        ↓
[Search API]  →  URLs
        ↓
[Fetch HTML]  →  raw HTML
        ↓
[Skill_EntityExtraction_HTML_v1]  →  structured JSON  (local, 0 tokens)
        ↓
[Write CSV]  →  done
```

Token reduction on the extraction step: ~95%. Total task cost reduction: ~60-70%.

---

## 5. Detailed Development Roadmap

---

### Phase 0: Foundations & Design Contracts

**Goal**: Before writing a single line of runtime code, establish the schemas, interfaces, and design contracts that every subsequent module depends on. Dirty foundations corrupt all downstream evolution data.

**Module 0.1: Core Data Schemas**

Define and freeze (with versioning) the following schemas:

- **TrajectoryRecord** — the atomic log unit:
  ```json
  {
    "trace_id": "uuid",
    "session_id": "uuid",
    "parent_task_id": "uuid | null",
    "timestamp_utc": "ISO8601",
    "iteration_index": 0,
    "context_summary": "string",
    "llm_reasoning": "string (CoT scratchpad)",
    "action_name": "string",
    "action_params": {},
    "action_result": {},
    "token_cost": 0,
    "latency_ms": 0,
    "skill_used": "string | null"
  }
  ```

- **SkillRecord** — the micro-skill registry entry:
  ```json
  {
    "skill_id": "uuid",
    "name": "string",
    "version": "semver",
    "parent_skill_id": "uuid | null",
    "description": "string",
    "input_schema": {},
    "output_schema": {},
    "implementation_type": "python_fn | prompt_cache | tiny_model | composite",
    "implementation_path": "string",
    "created_from_traces": ["trace_id"],
    "test_suite_path": "string",
    "pass_rate": 1.0,
    "invocation_count": 0,
    "last_invoked": "ISO8601",
    "confidence_score": 1.0,
    "status": "active | degraded | deprecated | archived"
  }
  ```

- **SliceCandidate** — output of the reflection daemon:
  ```json
  {
    "candidate_id": "uuid",
    "action_sequence": ["action_name"],
    "frequency": 0,
    "occurrence_trace_ids": ["uuid"],
    "input_schema_inferred": {},
    "output_schema_inferred": {},
    "boundary_confidence": 0.0,
    "forge_status": "pending | forging | passed | failed | abandoned"
  }
  ```

**Module 0.2: Interface Contracts**

Define Python abstract base classes (ABCs) for:
- `BaseOrchestrator` — `plan(task) → ActionPlan`
- `BaseSkill` — `invoke(input: dict) → dict`, `validate() → bool`
- `BaseExecutor` — `execute(action: Action) → Observation`
- `BaseReflectionDaemon` — `run_cycle() → list[SliceCandidate]`
- `BaseForge` — `forge(candidate: SliceCandidate) → SkillRecord | None`

Establishing these contracts early means modules can be built and tested independently and swapped without breaking the system.

**Module 0.3: Sanitization Layer**

All trajectory data passes through a sanitization filter before being written to storage:
- Strip API keys, tokens, passwords matching common patterns
- Redact PII (emails, phone numbers, credit card numbers) using regex + optional NER
- This runs synchronously in the trajectory logger hot path — must be fast

---

### Phase 1: Infrastructure & The All-Seeing Eye

**Goal**: A working agent loop that perfectly captures every action, state, and reasoning step. No evolution is possible without clean, rich data.

**Module 1.1: Core Orchestrator (Baseline)**

- Framework: Python + LangGraph (preferred for explicit state graph modeling) or LlamaIndex Workflows
- Initial state: all decisions routed to cloud LLM (Claude Opus / GPT-4o). No local skills exist yet.
- Executor: implement a minimal general-purpose executor supporting: web search, HTTP fetch, file I/O, code execution, shell commands
- The orchestrator must be **instrumented from day one** — no retrofitting logging later

**Module 1.2: Trajectory Logger (Critical Path)**

- Implemented as a **middleware interceptor** wrapping every LLM call and executor action
- Writes to persistent store synchronously (critical data — no async drops)
- Enforces the TrajectoryRecord schema from Phase 0
- Exposes a streaming interface for the reflection daemon to tail new records

**Module 1.3: Persistent Storage**

| Layer | Technology | Stores |
|-------|-----------|--------|
| Relational | SQLite (dev) / PostgreSQL (prod) | TrajectoryRecords, SkillRecords, SliceCandidates |
| Vector | ChromaDB (dev) / Qdrant (prod) | Semantic embeddings of states, actions, I/O pairs |
| File | Local filesystem | Generated Python skills, test suites, tiny model weights |

**Module 1.4: Observability Dashboard**

A lightweight web UI (FastAPI + simple HTML or Streamlit) showing:
- Live trajectory feed
- Skill registry with invocation counts and confidence scores
- Evolution timeline: when each skill was forged
- Cost savings metrics: tokens/$ saved by local skills over time

This is not optional — invisible evolution is undebuggable evolution.

---

### Phase 2: Cognition — Reflection, Clustering & Boundary Detection

**Goal**: The system's "sleeping brain" — an offline process that mines accumulated trajectories for patterns that the system can learn to automate.

**Module 2.1: Offline Reflection Daemon**

- Runs as a background process triggered by: (a) CRON schedule (nightly), (b) trajectory count threshold (every N new traces)
- Input: all TrajectoryRecords since last reflection cycle
- Converts action sequences to fixed-length embedding vectors using a lightweight sentence transformer

**Module 2.2: Two-Stage Clustering (Improved from original plan)**

The original plan's pure HDBSCAN approach is improved with a two-stage process:

*Stage 1 — Statistical clustering:*
- Apply HDBSCAN on action sequence embeddings to find rough clusters
- Filter clusters by minimum frequency threshold (e.g., appears in at least 20 distinct sessions)
- Output: list of high-frequency action sequence candidates

*Stage 2 — LLM-guided annotation (new):*
- For each cluster, sample 5-10 representative trajectory segments
- Feed to a lightweight LLM (can be a smaller model than the main orchestrator) with prompt:
  *"Examine these action sequences. Are they performing the same logical operation? If yes, describe the operation, its input, and its output in one sentence each."*
- LLM confirms or rejects the cluster as a coherent unit
- This dramatically reduces false positives from pure embedding similarity

This hybrid approach combines the scalability of unsupervised clustering with the semantic precision of LLM judgment.

**Module 2.3: I/O Signature Extraction & Boundary Scoring**

For each LLM-confirmed candidate:
1. Collect all input/output pairs across all occurrences
2. Run JSON Schema inference on the input set and output set separately
3. Compute **schema consistency score**: what fraction of occurrences conform to the inferred schema
4. A candidate becomes a `SliceCandidate` if:
   - Frequency ≥ threshold (e.g., 20 occurrences)
   - Schema consistency ≥ 0.9 for both input and output
   - LLM annotation confidence ≥ 0.8

**Module 2.4: Temporal Pattern Detection (new)**

Beyond pure frequency, track *when* tasks occur:
- Detect time-of-day or day-of-week patterns in task invocation
- Skills that are needed at predictable times can be pre-warmed or pre-computed
- Future: enables proactive execution before the user even asks

---

### Phase 3: The Forge — Code Synthesis & Sandboxed Auto-Eval

**Goal**: Transform slice candidates into validated, registered micro-skills. This phase is the system's metabolic core — it converts observed intelligence into stored capability.

**Module 3.1: Code Synthesis Engine**

Input: a `SliceCandidate` with N historical I/O pairs (target: 30-100 pairs for reliable synthesis)

Synthesis strategy (in priority order):
1. **Pure Python function**: preferred. Uses standard library + approved packages (spaCy, regex, json, lxml, etc.). No LLM API calls.
2. **Cached prompt**: for linguistic/semantic tasks that resist deterministic code. A fixed system prompt + few-shot examples + a tiny local model (Ollama, llama.cpp).
3. **Tiny fine-tuned model**: for complex pattern recognition. Fine-tune a 0.5B-1B model on the I/O pairs. Higher upfront cost, but zero inference cost thereafter.

Synthesis prompt template (for strategy 1):
```
You are a code synthesis engine. Below are {N} input/output pairs demonstrating a transformation.

INPUT SCHEMA: {input_schema}
OUTPUT SCHEMA: {output_schema}
TASK DESCRIPTION: {llm_annotation}

EXAMPLES:
{io_pairs}

Write a robust Python function with signature:
  def skill(input: dict) -> dict

Requirements:
- Pure function, no side effects, no LLM API calls
- Handle edge cases and malformed input gracefully
- Use only: standard library, spaCy, regex, lxml, json, dateutil
- Include inline comments for non-obvious logic
```

**Module 3.2: Sandboxed Auto-Evaluation (Critical)**

Every generated skill is evaluated in isolation before touching the registry.

```
SliceCandidate
    │
    ▼
Generate code (Teacher LLM)
    │
    ▼
Inject into Docker/WASM sandbox
    │
    ▼
Run all N historical I/O pairs as unit tests
    │
   / \
PASS  FAIL
 │      │
 │   Feed error traceback to LLM + retry (max 5x)
 │      │
 │   Still failing? → Mark candidate as "abandoned"
 │      │               Archive for manual review
 ▼      ▼
Promote to registry
```

Test harness details:
- Exact match for structured outputs (JSON, lists)
- Fuzzy match (≥ 0.95 cosine similarity of embeddings) for free-text outputs
- Timeout enforced per test case (e.g., 2 seconds max)
- Resource limits: 128MB RAM, no network access, no filesystem access outside sandbox

**Module 3.3: Skill Genealogy & Versioning (new)**

When a skill is forged from an existing skill (e.g., a refined v2 that handles more edge cases):
- `parent_skill_id` links the new version to the old
- The old version is not deleted — it is archived with a deprecation timestamp
- This creates a **species tree** of skill evolution over time, visualizable in the dashboard

---

### Phase 4: Dynamic Routing, Concept Drift & Skill Lifecycle

**Goal**: Close the loop. The orchestrator learns to prefer local skills, and the system actively monitors for degradation and environmental change.

**Module 4.1: Smart Router**

Routing decision logic (in order of precedence):
1. Compute semantic embedding of the current sub-task
2. Search Skill Registry for skills with similarity > 0.85
3. If match found AND confidence_score > threshold: route to local skill
4. If match found BUT confidence_score degraded (0.5-0.85): route to local skill with shadow-mode logging (compare output against cloud LLM in background)
5. If no match OR confidence_score < 0.5: route to cloud LLM, log full trajectory

**Module 4.2: Confidence Decay & Skill Lifecycle**

A skill's `confidence_score` is a live metric, not a one-time grade:

| Event | Effect on confidence_score |
|-------|---------------------------|
| Successful invocation, output validated by user/downstream | +0.01 (capped at 1.0) |
| Output flagged as incorrect by user | -0.2 |
| Exception raised during invocation | -0.1 |
| Concept drift detected (see 4.3) | -0.3, flag for re-forging |
| N days without any invocation | -0.001/day (forgetting curve) |

Lifecycle states: `active → degraded → deprecated → archived`

Skills in `archived` state are not deleted — their test suites and I/O pairs are preserved as training data for future re-forging.

**Module 4.3: Concept Drift Detection (new)**

Static evaluation on historical data is not enough. The real world changes.

Mechanism:
- In **shadow mode**, when a degraded skill is invoked, the cloud LLM also processes the same input independently
- Compare outputs. If divergence exceeds threshold over a rolling window of 50 invocations: **drift confirmed**
- Trigger: collect new I/O pairs from shadow-mode runs, re-run the forge pipeline, promote the new skill version

This handles cases like: a target website restructures its HTML, an API changes its response format, or user query patterns shift semantically.

**Module 4.4: Skill Composition Engine (new)**

Monitor the orchestrator's execution logs for patterns like:
- `Skill_A` output is consistently piped directly to `Skill_B` input
- The pair appears together in ≥ 80% of `Skill_A` invocations

When detected:
- Automatically forge `Skill_AB_Composite` — a single Python function wrapping both
- Removes orchestrator round-trip overhead between A and B
- Composite skills follow the same versioning and evaluation pipeline

**Module 4.5: Forgetting & Pruning**

Skills that have not been invoked in 90+ days and have low confidence scores are candidates for archival. The system:
1. Notifies via dashboard (never silently deletes)
2. Archives the skill record and implementation
3. Frees the registry slot from active semantic search (reduces routing noise)

Analogy: synaptic pruning in the developing brain. Unused connections are eliminated to sharpen the pathways that matter.

---

### Phase 5: Federation, Composition & Ecosystem

**Goal**: EvoSys instances are not isolated. Skills forged in one context should be portable, shareable, and collectively improvable.

**Module 5.1: Skill Export & Portable Packaging**

Each registered skill can be exported as a self-contained package:
- Python file + `requirements.txt`
- Full test suite (I/O pairs as JSON)
- Metadata JSON (`SkillRecord`)
- Signed with a content hash for integrity verification

**Module 5.2: Cross-Instance Skill Import**

A receiving EvoSys instance can import a packaged skill:
- Runs the full sandbox evaluation against the importer's own historical data
- Only adopts the skill if it passes locally (no blind trust)
- Logs provenance: which instance originally forged it

**Module 5.3: Federated Skill Registry (future)**

A distributed registry where EvoSys instances can publish and discover skills:
- Privacy-preserving: only skill metadata and test suites are shared, never raw trajectory data
- Reputation system: skills gain trust as more instances independently validate them
- Category taxonomy: skills organized by domain (web extraction, data transformation, API interaction, etc.)

---

## 6. Open Research Questions

These are the hard, unsolved problems at the core of EvoSys:

| Question | Why it matters |
|----------|---------------|
| **How to determine optimal DAG granularity?** | Too fine-grained → skills are useless single API calls. Too coarse → skills are too specific to generalize. |
| **When is an I/O signature "stable enough" to forge?** | More examples = higher confidence, but more delay before forging. What's the right sample size threshold? |
| **How to handle skills with stateful dependencies?** | A skill that requires a logged-in browser session cannot be a pure function. How to model and enforce this? |
| **Evaluation beyond exact match** | For creative or summarization tasks, historical output is not ground truth. How to auto-evaluate open-ended skill outputs? |
| **How to evolve the orchestrator itself?** | The routing logic is currently hand-coded. Can it be learned from routing history? |
| **Privacy of shared skills** | A skill trained on user data may encode private information in its weights. How to ensure federation is safe? |
| **The bootstrapping problem** | EvoSys needs a large volume of trajectory data before reflection becomes useful. How to accelerate the initial cold-start period? |

---

## 7. Design Principles

1. **Data before code**: No module is built before its schema is defined and frozen. Bad data = bad evolution.
2. **Never deploy unvalidated skills**: Every skill must pass its full sandbox test suite before it can be routed to. No exceptions.
3. **Reversibility at every step**: Skills are archived, not deleted. Orchestrator changes are versioned. The system can always roll back.
4. **Transparency over performance**: The evolution happening inside EvoSys must be observable. The dashboard is as critical as any functional module.
5. **Least-privilege execution**: Forged skills run in sandboxes with no network, no filesystem, strict resource limits. A malformed generated script cannot damage the host system.
6. **Privacy first**: Trajectory data is sanitized before storage. Skills are never federated with raw user data attached.
7. **Fail loudly, degrade gracefully**: A failing local skill should immediately surface to the orchestrator, which falls back to the cloud LLM. Silent failures are forbidden.

---

## 8. Tech Stack Reference

| Layer | Technology | Notes |
|-------|-----------|-------|
| Language | Python 3.12 | Pinned via `uv` |
| Package manager | **uv** | Rust-based, 10-100x faster than pip, native lockfile |
| Orchestration | **Hand-rolled** (no LangGraph) | Enum-based state machine + custom executor |
| Primary LLM | Claude Opus 4 / GPT-4o via **LiteLLM** | Unified `completion()` across 100+ providers |
| Skill LLM (synthesis) | Claude Sonnet via LiteLLM | Same |
| Local model serving | **llama-cpp-python** | GGUF models on Metal GPU natively (no CUDA needed) |
| Training | **PyTorch + PEFT/LoRA** | MPS backend for Apple Silicon |
| Relational DB | SQLite (dev) / PostgreSQL (prod) | Via **SQLAlchemy 2.0** + **Alembic** |
| Vector DB | **LanceDB** | Embedded (like SQLite), Pydantic-native, hybrid search |
| Sandbox | Docker SDK for Python | Docker / WASM |
| Embeddings | **sentence-transformers** | Local embedding models |
| Clustering | scikit-learn (**HDBSCAN**, K-Means) | Phase 2 optional group |
| NLP (in skills) | **spaCy** | Phase 3 optional group |
| Dashboard | **FastAPI + Jinja2 + HTMX** | No full SPA — server-rendered with live updates |
| CLI | **typer** + **rich** | Type-hint based, auto-generated help |
| JSON serialization | **orjson** | 3-10x faster than stdlib json |
| Logging | **structlog** | Structured logging for trajectory hot path |

---

*EvoSys is not a chatbot wrapper. It is an attempt to build a system that genuinely learns from its own operation — one that gets better, faster, and cheaper with every task it completes.*
