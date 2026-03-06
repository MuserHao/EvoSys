"""Skill forge — synthesize, validate, and promote skills."""

from __future__ import annotations

import ast
import types
from typing import TYPE_CHECKING, Any

import structlog

from evosys.core.interfaces import BaseForge, BaseSkill
from evosys.core.types import IOPair
from evosys.forge.synthesizer import SkillSynthesizer
from evosys.schemas._types import ImplementationType, MaturationStage, new_ulid
from evosys.schemas.skill import SkillRecord
from evosys.schemas.slice import SliceCandidate
from evosys.skills.registry import SkillRegistry

if TYPE_CHECKING:
    from evosys.storage.skill_store import SkillStore

log = structlog.get_logger()


class _SynthesizedSkill(BaseSkill):
    """A skill whose implementation is a synthesized async function."""

    def __init__(self, extract_fn: Any) -> None:
        self._extract_fn = extract_fn

    async def invoke(self, input_data: dict[str, object]) -> dict[str, object]:
        return await self._extract_fn(input_data)

    def validate(self) -> bool:
        return callable(self._extract_fn)


class SkillForge(BaseForge):
    """Synthesise, evaluate, and promote a SliceCandidate into a SkillRecord.

    Pipeline:
    1. Synthesize Python code from I/O examples via LLM.
    2. Validate the code is safe (AST check, no imports of dangerous modules).
    3. Execute against sample I/O pairs to verify correctness.
    4. If pass rate is sufficient, create a SkillRecord and register it.
    5. Persist the record and source code to the DB so it survives restarts.
    """

    def __init__(
        self,
        synthesizer: SkillSynthesizer,
        registry: SkillRegistry,
        *,
        min_pass_rate: float = 0.8,
        skill_store: SkillStore | None = None,
    ) -> None:
        self._synthesizer = synthesizer
        self._registry = registry
        self._min_pass_rate = min_pass_rate
        self._skill_store = skill_store
        self.last_forge_error: str = ""

    async def forge(
        self,
        candidate: SliceCandidate,
        *,
        domain: str = "",
        sample_io: list[IOPair] | None = None,
    ) -> SkillRecord | None:
        """Attempt to forge *candidate* into a registered skill.

        Returns the new SkillRecord on success, or None on failure.
        """
        if not domain:
            log.warning("forge.no_domain", candidate_id=str(candidate.candidate_id))
            self.last_forge_error = "no domain provided"
            return None

        skill_name = f"extract:{domain}"
        if skill_name in self._registry:
            log.info("forge.already_registered", skill_name=skill_name)
            return None

        io_pairs = sample_io or []
        sample_inputs = [p.input_data for p in io_pairs]
        sample_outputs = [p.output_data for p in io_pairs]

        # 1. Synthesize code
        try:
            code = await self._synthesizer.synthesize(
                domain=domain,
                sample_inputs=sample_inputs,
                sample_outputs=sample_outputs,
            )
        except Exception as exc:
            log.error("forge.synthesis_failed", error=str(exc))
            self.last_forge_error = f"synthesis failed: {exc}"
            return None

        # 2. Validate code safety
        if not _is_safe_code(code):
            log.warning("forge.unsafe_code", domain=domain)
            self.last_forge_error = "unsafe code detected"
            return None

        # 3. Compile and load
        extract_fn = _compile_extract(code)
        if extract_fn is None:
            log.warning("forge.compile_failed", domain=domain)
            self.last_forge_error = "compile failed"
            return None

        # 4. Test against I/O pairs
        pass_count = 0
        for pair in io_pairs:
            try:
                result = await extract_fn(dict(pair.input_data))
                if _outputs_match(result, dict(pair.output_data)):
                    pass_count += 1
            except Exception:
                continue

        total = len(io_pairs)
        pass_rate = pass_count / total if total > 0 else 0.0

        if total > 0 and pass_rate < self._min_pass_rate:
            log.info(
                "forge.insufficient_pass_rate",
                domain=domain,
                pass_rate=pass_rate,
            )
            self.last_forge_error = f"low pass rate: {pass_rate:.2f}"
            return None

        # 5. Create and register
        skill = _SynthesizedSkill(extract_fn)

        # Infer schemas from I/O pairs
        input_schema = _infer_schema(sample_inputs) if sample_inputs else {}
        output_schema = _infer_schema(sample_outputs) if sample_outputs else {}

        record = SkillRecord(
            skill_id=new_ulid(),
            name=skill_name,
            description=f"Auto-forged extraction skill for {domain}",
            implementation_type=ImplementationType.ALGORITHMIC,
            implementation_path=f"forge:synthesized:{domain}",
            test_suite_path="auto-generated",
            pass_rate=pass_rate if total > 0 else 1.0,
            confidence_score=min(
                1.0, candidate.boundary_confidence * (pass_rate if total > 0 else 0.5)
            ),
            input_schema=input_schema,
            output_schema=output_schema,
            created_from_traces=list(candidate.occurrence_trace_ids),
            maturation_stage=MaturationStage.SYNTHESIZED,
        )

        try:
            self._registry.register(record, skill)
        except ValueError as exc:
            log.warning("forge.register_failed", error=str(exc))
            return None

        # 6. Persist to DB so the skill survives restarts
        if self._skill_store is not None:
            try:
                await self._skill_store.save(record, code)
                log.info("forge.persisted", skill_name=skill_name)
            except Exception as exc:
                # Persistence failure is non-fatal: skill is live in memory
                # and will be re-forged on the next evolution cycle if lost.
                log.warning("forge.persist_failed", skill_name=skill_name, error=str(exc))

        log.info(
            "forge.success",
            skill_name=skill_name,
            pass_rate=pass_rate,
            confidence=record.confidence_score,
        )
        return record


def _is_safe_code(code: str) -> bool:
    """Check if synthesized code is safe to execute.

    Rejects code that:
    - Imports os, sys, subprocess, shutil, pathlib, socket, or importlib
    - Uses exec(), eval(), compile(), __import__(), open()
    - Accesses dangerous modules via attribute access (e.g. os.system)
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False

    dangerous_modules = {
        "os", "sys", "subprocess", "shutil", "pathlib", "socket", "importlib",
    }
    dangerous_calls = {"exec", "eval", "compile", "__import__", "open"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in dangerous_modules:
                    return False
        elif isinstance(node, ast.ImportFrom):
            # node.module is None for relative imports like `from . import foo`
            if node.module and node.module.split(".")[0] in dangerous_modules:
                return False
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in dangerous_calls
        ) or (
            # Block attribute access on dangerous module names, e.g. os.system(...)
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Load)
            and isinstance(node.value, ast.Name)
            and node.value.id in dangerous_modules
        ):
            return False

    return True


def _compile_extract(code: str) -> Any | None:
    """Compile code and extract the `extract` function."""
    try:
        module = types.ModuleType("_synthesized")
        exec(code, module.__dict__)
        fn = getattr(module, "extract", None)
        if callable(fn):
            return fn
    except Exception:
        pass
    return None


def _outputs_match(actual: dict[str, object], expected: dict[str, object]) -> bool:
    """Check if actual output matches expected, with tolerance."""
    for key in expected:
        if key not in actual:
            return False
        if str(actual[key]).strip().lower() != str(expected[key]).strip().lower():
            return False
    return True


def _infer_schema(samples: list[dict[str, object]]) -> dict[str, object]:
    """Infer a minimal schema from sample dicts.

    Returns a dict mapping field names to their inferred Python type names.
    """
    if not samples:
        return {}

    schema: dict[str, object] = {}
    for sample in samples:
        for key, value in sample.items():
            if key not in schema:
                schema[key] = type(value).__name__
    return schema
