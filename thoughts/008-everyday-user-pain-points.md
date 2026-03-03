# Thought 008: Everyday User Pain Points — What Should EvoSys Actually Do?

**Date**: 2026-03-03
**Status**: Active
**Triggered by**: Need to ground the system in tasks real people actually need

---

## What Do Regular People Do on Computers?

Roughly ordered by frequency:

1. **Browse the web** — search for information, read articles, compare products
2. **Email** — read, write, organize, respond
3. **Messaging** — chat, coordinate, share links
4. **Documents** — write reports, notes, summaries, presentations
5. **Files** — organize, find, rename, convert, backup
6. **Shopping** — research products, compare prices, track orders
7. **Finance** — check accounts, pay bills, track expenses
8. **Scheduling** — manage calendar, set reminders, coordinate meetings
9. **Media** — photos, music, videos — organize and consume
10. **Learning** — read tutorials, take notes, practice

## Where Is the Friction?

Not all computer tasks are painful. Opening YouTube is frictionless. The pain
points are tasks that are:
- **Repetitive but slightly different each time** (can't just record a macro)
- **Require gathering information from multiple sources**
- **Involve tedious formatting or transformation**
- **Require judgment that feels like it shouldn't need a human**

### High-friction everyday tasks (ranked by EvoSys suitability)

#### 1. "Find me the best X" — Research & Comparison
**What users do**: Search Google, open 10 tabs, read reviews, compare specs,
make a spreadsheet, eventually pick one.
**Pain**: Takes 30-60 minutes. Most of the work is mechanical (extracting specs,
normalizing formats, comparing).
**EvoSys fit**: EXCELLENT
- Recurring pattern: search → visit pages → extract structured data → compare
- Output is verifiable (structured comparison table)
- Sub-skills: product spec extraction, price normalization, review summarization
- Distillation: site-specific extractors can be forged (Amazon, Best Buy, etc.)

**Example**: "Compare the top 5 wireless earbuds under $100"
→ Agent searches, extracts specs from 5 product pages, builds comparison table

#### 2. "Summarize this for me" — Content Digestion
**What users do**: Read long articles, papers, email threads, documents.
Mentally extract the key points.
**Pain**: Time-consuming. Hard to know what matters until you've read everything.
**EvoSys fit**: GOOD (but evaluation is harder)
- Recurring pattern: fetch content → identify structure → extract key points
- Sub-skills: HTML cleaning, section detection, key point extraction
- Distillation: format-specific summarizers (arxiv papers, news articles, emails)
- Challenge: output quality is subjective — harder to verify automatically

**Example**: "Summarize this 20-page PDF report into 5 bullet points"

#### 3. "Turn this into that" — Format Conversion & Transformation
**What users do**: Copy data from a webpage into a spreadsheet. Reformat a
document. Convert CSV to JSON. Clean up messy data.
**Pain**: Extremely tedious. Perfectly suited for automation.
**EvoSys fit**: EXCELLENT
- Recurring pattern: parse input format → transform → produce output format
- Output is mechanically verifiable (schema validation, round-trip tests)
- Sub-skills: CSV parsing, JSON transformation, date normalization, unit conversion
- Distillation: most transformations are Tier 0-1 (deterministic code)

**Example**: "Convert this bank statement PDF into a categorized expense CSV"

#### 4. "What did I do / what do I need to do?" — Personal Organization
**What users do**: Search through emails, files, browser history, notes to
reconstruct context. Track tasks across multiple tools.
**Pain**: Information is scattered. Context switching is expensive.
**EvoSys fit**: MEDIUM
- Recurring pattern: search across sources → aggregate → present timeline
- Challenge: requires access to many personal data sources (privacy-sensitive)
- Sub-skills: email search, file search, calendar parsing
- Distillation: query patterns can be cached, but integration is the hard part

#### 5. "Help me write this" — Drafting & Editing
**What users do**: Write emails, reports, social media posts, cover letters.
Often stare at a blank page.
**Pain**: Starting is hard. Formatting is tedious. Tone is tricky.
**EvoSys fit**: GOOD (for templated writing)
- Recurring pattern: understand context → apply template → customize
- Sub-skills: tone detection, format templating, grammar checking
- Distillation: personal writing templates can be forged from history
- Challenge: highly personal — needs user's style, which varies

**Example**: "Write a polite decline email for this meeting request"

#### 6. "Keep me updated on X" — Monitoring & Alerts
**What users do**: Manually check websites, stock prices, product availability,
news about specific topics.
**Pain**: Repetitive checking. Easy to forget. Often time-sensitive.
**EvoSys fit**: EXCELLENT
- Recurring pattern: fetch source → extract value → compare to threshold → alert
- Output is binary (alert or no alert) — perfectly verifiable
- Sub-skills: site-specific value extraction, threshold comparison
- Distillation: monitoring checks are almost always Tier 0-1 after first setup

**Example**: "Tell me when this product drops below $50"
**Example**: "Alert me when there's news about EvoSys competitors"

#### 7. "Fill this out for me" — Form Filling & Data Entry
**What users do**: Fill in the same information (name, address, payment) across
different websites. Enter data from one system into another.
**Pain**: Repetitive. Error-prone. Mind-numbing.
**EvoSys fit**: GOOD
- Recurring pattern: identify form fields → map to known data → fill
- Sub-skills: form field detection, personal data mapping
- Challenge: requires browser automation (Playwright/Selenium territory)
- Distillation: per-site form filling becomes Tier 0 quickly

## Suitability Matrix

| Task | Recurring? | Verifiable? | Distillable? | Value? | Start here? |
|------|-----------|-------------|--------------|--------|-------------|
| Research & compare | Yes | Yes (structured) | Yes (per-site) | High | YES |
| Content summarization | Yes | Partial | Medium | High | Later |
| Format conversion | Yes | Yes (schema) | Yes (Tier 0-1) | Medium | YES |
| Personal organization | Medium | Partial | Medium | High | Later |
| Drafting & editing | Yes | No (subjective) | Low | Medium | No |
| Monitoring & alerts | Yes | Yes (binary) | Yes (Tier 0) | High | YES |
| Form filling | Yes | Yes (filled/not) | Yes (per-site) | Medium | Later |

## Recommended Starting Set

### Primary task: Structured Data Extraction (from Thought 007)
This is the foundation. Research/comparison, monitoring, and format conversion
all depend on the ability to extract structured data from unstructured sources.

### Second task: Price/Availability Monitoring
"Watch this product page and tell me when the price drops below $X."
- Simple, high-frequency, perfectly verifiable
- The extraction skill forged from the primary task directly applies here
- Adds a scheduling component (periodic checks) that exercises new muscles
- Users immediately understand the value

### Third task: Format Conversion
"Convert this CSV/PDF/HTML into this other format with these transformations."
- Exercises the Tier 0-1 distillation path heavily (most conversions are
  deterministic code)
- Easy to build a test suite (input file → expected output file)
- Users have this need constantly and it's pure tedium

## Strategy: Bottom-Up Skill Accumulation

These three tasks share sub-skills:

```
                    ┌─────────────────────┐
                    │  HTTP Fetch (Tier 0) │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
     ┌────────▼──────┐ ┌──────▼────────┐ ┌─────▼──────────┐
     │ HTML → Text   │ │ CSS Selector  │ │ JSON Schema    │
     │ (Tier 1)      │ │ Extract       │ │ Validation     │
     │               │ │ (Tier 0)      │ │ (Tier 0)       │
     └────────┬──────┘ └──────┬────────┘ └─────┬──────────┘
              │                │                │
    ┌─────────┼────────────────┼────────────────┤
    │         │                │                │
┌───▼───┐ ┌──▼────┐    ┌──────▼──────┐  ┌──────▼──────┐
│ Data  │ │ Price │    │ Product     │  │ CSV/JSON    │
│ Extrac│ │ Monit │    │ Comparison  │  │ Converter   │
│ -tion │ │ -oring│    │             │  │             │
└───────┘ └───────┘    └─────────────┘  └─────────────┘
```

Low-level skills (HTTP fetch, HTML cleaning, selector extraction) are forged
first through the extraction task. Then monitoring and comparison tasks reuse
those skills and add their own layer. This is the **bottom-up accumulation**
that makes the system get cheaper over time.

## What This Means for Phase 1

Phase 1 should build the extraction agent first (Thought 007's plan), but
with the awareness that monitoring and conversion will follow. This means:

- The trajectory logger should be generic (not extraction-specific)
- The skill registry should support arbitrary input/output schemas
- The orchestrator should be pluggable (new task types = new planning strategies)
- The HTTP executor should be reusable across all three task types

We already designed the schemas this way in Phase 0. Good.
