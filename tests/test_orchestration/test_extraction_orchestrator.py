"""Tests for ExtractionOrchestrator."""

from evosys.orchestration.extraction_orchestrator import ExtractionOrchestrator


class TestExtractionOrchestrator:
    async def test_plan_has_two_actions(self):
        orch = ExtractionOrchestrator()
        plan = await orch.plan("Extract from https://example.com")
        assert len(plan.actions) == 2

    async def test_first_action_is_fetch(self):
        orch = ExtractionOrchestrator()
        plan = await orch.plan("Extract data")
        assert plan.actions[0].name == "fetch_url"

    async def test_second_action_is_llm_extract(self):
        orch = ExtractionOrchestrator()
        plan = await orch.plan("Extract data")
        assert plan.actions[1].name == "llm_extract"

    async def test_extract_depends_on_fetch(self):
        orch = ExtractionOrchestrator()
        plan = await orch.plan("Extract data")
        fetch_id = plan.actions[0].action_id
        assert fetch_id in plan.actions[1].depends_on

    async def test_task_description_preserved(self):
        orch = ExtractionOrchestrator()
        task = "Extract product data from https://shop.com"
        plan = await orch.plan(task)
        assert plan.task_description == task
