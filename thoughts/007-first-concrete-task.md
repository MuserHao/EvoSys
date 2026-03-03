# Thought 007: The First Concrete Task — Structured Data Extraction

**Date**: 2026-03-03
**Status**: Active — designing Phase 1 around this
**Triggered by**: Need to validate the system against a real, practical task

---

## Task Selection Criteria

The first task for EvoSys must satisfy all of these:

1. **Recurring sub-patterns**: The task naturally decomposes into steps that
   repeat across different inputs.
2. **Verifiable outputs**: We can mechanically check if the output is correct
   (not subjective, not "creative").
3. **Clear distillation path**: Some sub-steps are obviously automatable with
   code; others genuinely need LLM reasoning. The spectrum exists.
4. **Practically useful**: We'd actually run this enough to generate trajectory
   data.
5. **Demonstrable cost reduction**: The savings from distillation are measurable
   in tokens and dollars.

## The Task: Structured Data Extraction from Web Pages

**Given**: A URL and a target schema (what fields to extract)
**Produce**: A JSON object conforming to the schema

### Example tasks

```
Input:  { url: "https://arxiv.org/abs/2106.09685",
          schema: { title: str, authors: list[str], abstract: str,
                    year: int, venue: str } }
Output: { title: "LoRA: Low-Rank Adaptation of Large Language Models",
          authors: ["Edward J. Hu", "Yelong Shen", ...],
          abstract: "We propose Low-Rank Adaptation...",
          year: 2021, venue: "ICLR 2022" }
```

```
Input:  { url: "https://github.com/anthropics/claude-code",
          schema: { name: str, description: str, language: str,
                    stars: int, license: str } }
Output: { name: "claude-code", description: "...",
          language: "TypeScript", stars: 28400, license: "MIT" }
```

```
Input:  { url: "https://news.ycombinator.com/item?id=12345",
          schema: { title: str, author: str, points: int,
                    comment_count: int, url: str } }
Output: { title: "...", author: "...", points: 142,
          comment_count: 67, url: "..." }
```

### Why this task is ideal for EvoSys

**Recurring sub-patterns that will emerge:**

| Sub-pattern | Frequency | Forgeable? | Target tier |
|-------------|-----------|------------|-------------|
| Fetch HTML from URL | Every task | Tier 0 (httpx call) | Already deterministic |
| Clean HTML to text | Every task | Tier 1 (BeautifulSoup) | Algorithmic |
| Extract field by CSS selector | High | Tier 0 (deterministic) | CSS selector string |
| Extract field by regex | High | Tier 0 (compiled regex) | Pure function |
| Parse date string to ISO | High | Tier 1 (dateutil) | Algorithmic |
| Infer field from surrounding text | Medium | Tier 2-3 (needs NLU) | Cached prompt |
| Parse structured page (arxiv, GitHub) | Per-domain | Tier 1 (site-specific parser) | Python function |
| Handle dynamic/JS-rendered pages | Low | Tier 4-5 (hard) | Stays as LLM call |

The key observation: **the same extraction task on the same domain will
converge rapidly**. The 3rd time you extract from an arxiv page, the system
should already have a domain-specific parser. The LLM's job shrinks from
"read this whole page and figure it out" to "I've never seen this domain,
let me figure out the selectors."

**Verifiable outputs:**
- Output must conform to the target JSON schema (mechanically checkable)
- For known pages, we can cache the expected output and regression-test
- Field types are enforceable (int must be int, dates must parse)

**Clear distillation ladder:**
- First extraction from arxiv.org: Tier 5 (LLM reads full page, reasons about structure)
- Second extraction: Tier 4 (LLM with a prompt template that includes the page structure hints)
- After 5-10 extractions: Tier 1 (Python function with BeautifulSoup + known CSS selectors)
- Stable state: Tier 0 for known domains, Tier 4 fallback for unknown domains

**Measurable savings:**
- First arxiv extraction: ~5000 tokens input (full page HTML) + ~500 tokens output = ~$0.02
- Forged skill: 0 tokens, ~50ms, $0
- At 10 extractions/day: saves ~$6/month per domain. Small but demonstrable.

## Agent Architecture (Phase 1 target)

```
User request: "Extract paper info from https://arxiv.org/abs/2106.09685"
        │
        ▼
┌───────────────────┐
│   Orchestrator    │  Checks skill registry for domain-specific extractor
│                   │  If found + confident → route to skill
│                   │  If not → route to cloud LLM
└───────┬───────────┘
        │
   ┌────┴────────────────────────────┐
   │                                 │
   ▼                                 ▼
┌──────────────┐            ┌────────────────┐
│ Skill: arxiv │            │   Cloud LLM    │
│ extractor    │            │   (fallback)   │
│ (Tier 1)     │            │                │
│ ~50ms, $0    │            │  Fetch HTML    │
└──────┬───────┘            │  Read + reason │
       │                    │  Extract fields│
       │                    │  ~5s, $0.02    │
       │                    └───────┬────────┘
       │                            │
       └────────────┬───────────────┘
                    │
                    ▼
           ┌────────────────┐
           │ Trajectory Log │  Records: input, output, method used,
           │                │  latency, token cost, skill/LLM flag
           └────────────────┘
```

## What This Validates

If we build this and run it for a few weeks:

1. **Pattern detection**: Do recurring sub-patterns actually emerge in the logs?
   If every extraction is unique, the whole premise fails.

2. **Code synthesis**: Can Claude reliably synthesize a Python extraction function
   from 5-10 I/O pairs? If the synthesized functions are brittle or wrong, the
   Forge concept needs rethinking.

3. **Cost reduction**: Is the savings meaningful? If the LLM cost per extraction
   is already negligible, there's no point in forging skills.

4. **Self-practice**: Can the system generate arxiv URLs it hasn't seen, run
   extractions, and verify outputs against the forged skill? This tests the
   self-practice loop on a real task.

## Implementation Plan

### Phase 1a: The skeleton (build first)
- Trajectory logger (writes to SQLite via the schemas we already have)
- Basic orchestrator (always routes to cloud LLM for now)
- HTTP executor (fetches URLs, returns HTML)
- A single end-to-end flow: URL → fetch → LLM extract → JSON output → log

### Phase 1b: The skill registry (build second)
- In-memory skill registry (dict of SkillRecord objects)
- Manual skill registration (we forge the first skills by hand)
- Routing: orchestrator checks registry before falling back to LLM

### Phase 1c: The first forge (build third)
- Take 10 trajectory records for arxiv extractions
- Feed them to Claude: "Write a Python function that extracts these fields"
- Run the function against the 10 test cases
- If all pass: register as a skill, route future arxiv requests to it

Phase 1c is the manual validation from Thought 006, implemented as code
instead of done by hand.

## What We Defer

- Automatic pattern detection (Phase 2)
- Automatic code synthesis (Phase 3)
- Shadow mode and maturation tracking (Phase 1b+ or Phase 2)
- Self-practice (needs skills to practice with, comes after first forge)
- Multiple task types (start with extraction only, expand later)
