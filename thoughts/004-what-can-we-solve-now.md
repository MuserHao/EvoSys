# Thought 004: What Can We Solve Now? — Phase 0 Schema Extensions

**Date**: 2026-03-02
**Status**: Resolved — implemented in Phase 0 schema extensions
**Depends on**: Thought 001, 002, 003

---

## Summary

Thoughts 001-003 raised big architectural questions. Some need real data and
infrastructure that doesn't exist yet. But several changes can be made *now*
at the schema/contract level to ensure the foundations support the full vision.

This thought catalogs what's actionable and what's deferred.

## Actionable Now (Schema & Contract Level)

### 1. Expand `ImplementationType` to cover all six tiers

Current:
```python
class ImplementationType(StrEnum):
    PYTHON_FN = "python_fn"
    PROMPT_CACHE = "prompt_cache"
    TINY_MODEL = "tiny_model"
    COMPOSITE = "composite"
```

Proposed:
```python
class ImplementationType(StrEnum):
    DETERMINISTIC = "deterministic"      # Tier 0: regex, lookup, pure math
    ALGORITHMIC = "algorithmic"          # Tier 1: Python + libraries
    CACHED_PROMPT = "cached_prompt"      # Tier 2: few-shot on local model
    FINE_TUNED_MODEL = "fine_tuned_model" # Tier 3: LoRA/QLoRA local model
    CLOUD_LLM = "cloud_llm"             # Tier 4: single API call w/ template
    AGENT_DELEGATION = "agent_delegation" # Tier 5: full agent handoff
    COMPOSITE = "composite"              # Chain of any of the above
```

### 2. Add maturation stages to SkillRecord

Either extend `SkillStatus` or add a separate `maturation_stage` field:

```python
class MaturationStage(StrEnum):
    OBSERVED = "observed"      # Pattern detected, data accumulating
    PROMPTED = "prompted"      # Cached prompt created, in shadow mode
    SYNTHESIZED = "synthesized" # Code generated, validating
    OPTIMIZED = "optimized"    # Production-ready, periodic shadow checks
    STABLE = "stable"          # Long-term proven, minimal monitoring
```

This is orthogonal to `SkillStatus` (ACTIVE/DEGRADED/etc.) — a skill can be
ACTIVE + SYNTHESIZED, or DEGRADED + STABLE (was stable, now drifting).

### 3. Add learnability metadata to SliceCandidate

```python
class SliceCandidate(EvoBaseModel):
    # ... existing fields ...

    # Learnability signals (computed by reflection daemon)
    determinism_ratio: float | None = None     # 0-1, same input → same output?
    schema_consistency: float | None = None    # 0-1, how uniform is the I/O schema?
    avg_output_tokens: int | None = None       # Helps estimate tier
    recommended_tier: ImplementationType | None = None
    learnability_score: float | None = None    # 0-1, composite score
```

### 4. Add shadow-mode tracking to SkillRecord

```python
class SkillRecord(EvoBaseModel):
    # ... existing fields ...

    maturation_stage: MaturationStage = MaturationStage.OBSERVED
    shadow_sample_rate: float = 1.0       # 0-1, fraction of calls shadow-checked
    shadow_agreement_rate: float | None = None  # rolling agreement with LLM
    total_shadow_comparisons: int = 0
    tier_demotion_attempts: int = 0       # how many times we tried cheaper tiers
    current_tier: ImplementationType | None = None  # may differ from implementation_type during transitions
```

### 5. New ABC: BaseShadowEvaluator

```python
class BaseShadowEvaluator(ABC):
    @abstractmethod
    async def compare(
        self,
        skill_output: dict,
        llm_output: dict,
        output_schema: dict,
    ) -> ShadowComparison:
        """Compare skill output against LLM ground truth."""
```

### 6. New ABC: BaseLearnabilityEstimator

```python
class BaseLearnabilityEstimator(ABC):
    @abstractmethod
    async def estimate(
        self,
        candidate: SliceCandidate,
        examples: list[IOPair],
    ) -> LearnabilityAssessment:
        """Score a candidate's learnability and recommend a tier."""
```

## Deferred (Needs Infrastructure / Data)

| Item | Blocked by | Earliest phase |
|------|-----------|----------------|
| Actual shadow-mode execution | Orchestrator + Executor (Phase 1) |
| Embedding-based drift detection | Vector DB + embedding pipeline (Phase 1-2) |
| Heuristic learnability estimator impl | Trajectory data to test against (Phase 2) |
| LLM-assisted tier assessment | LLM integration (Phase 1) |
| Meta-learning from forge outcomes | Forge + outcome data (Phase 3+) |
| Portfolio forging (multi-tier parallel) | Forge + sandbox (Phase 3) |
| Composite skill detection | Routing + invocation logs (Phase 4) |
| Automatic tier demotion | Working skills at multiple tiers (Phase 4) |

## Decision Needed

Should we implement the schema extensions (items 1-6) now as part of Phase 0,
or freeze Phase 0 and add them in Phase 1?

**Argument for now**: These are data contracts. Changing schemas later means
migrations. Getting them right now costs little and saves pain later.

**Argument for later**: We haven't validated these ideas against real data.
We might over-engineer schemas for concepts that change once we start building.

**Recommendation**: Add the enum and field extensions now (items 1-4). Defer the
new ABCs (items 5-6) to Phase 1 when we're building the executor and can test
them against real code paths.
