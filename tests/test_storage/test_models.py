"""Tests for SQLAlchemy ORM models."""

from evosys.storage.models import Base, TrajectoryRow


class TestTrajectoryRow:
    def test_tablename(self):
        assert TrajectoryRow.__tablename__ == "trajectory_records"

    def test_all_columns_exist(self):
        cols = {c.name for c in TrajectoryRow.__table__.columns}
        expected = {
            "trace_id",
            "session_id",
            "parent_task_id",
            "timestamp_utc",
            "iteration_index",
            "context_summary",
            "llm_reasoning",
            "action_name",
            "action_params_json",
            "action_result_json",
            "token_cost",
            "latency_ms",
            "skill_used",
            "success",
        }
        assert expected == cols

    def test_primary_key(self):
        pk_cols = [c.name for c in TrajectoryRow.__table__.primary_key.columns]
        assert pk_cols == ["trace_id"]

    def test_indexes_present(self):
        index_names = {idx.name for idx in TrajectoryRow.__table__.indexes}
        # Individual column indexes
        assert any("session_id" in (idx.name or "") for idx in TrajectoryRow.__table__.indexes)
        assert any("timestamp_utc" in (idx.name or "") for idx in TrajectoryRow.__table__.indexes)
        assert any("action_name" in (idx.name or "") for idx in TrajectoryRow.__table__.indexes)
        # Composite index
        assert "ix_trajectory_session_ts" in index_names

    def test_nullable_fields(self):
        table = TrajectoryRow.__table__
        assert table.c.parent_task_id.nullable is True
        assert table.c.skill_used.nullable is True
        assert table.c.trace_id.nullable is False

    def test_registered_in_base_metadata(self):
        assert "trajectory_records" in Base.metadata.tables
