"""Tests for MemoryStore."""

from __future__ import annotations

import pytest

from evosys.storage.memory_store import MemoryStore


class TestMemoryStore:
    async def test_set_and_get(self, trajectory_store: object) -> None:
        # trajectory_store fixture gives us an async session_factory via conftest
        pass  # use the memory_store fixture instead


# Override with a proper memory_store fixture
@pytest.fixture()
async def memory_store(session_factory):
    return MemoryStore(session_factory)


class TestMemoryStoreOperations:
    async def test_set_and_get(self, memory_store: MemoryStore) -> None:
        await memory_store.set("name", "Alice")
        result = await memory_store.get("name")
        assert result == "Alice"

    async def test_get_missing_key(self, memory_store: MemoryStore) -> None:
        result = await memory_store.get("nonexistent")
        assert result is None

    async def test_overwrite(self, memory_store: MemoryStore) -> None:
        await memory_store.set("key", "v1")
        await memory_store.set("key", "v2")
        assert await memory_store.get("key") == "v2"

    async def test_delete(self, memory_store: MemoryStore) -> None:
        await memory_store.set("todelete", "value")
        await memory_store.delete("todelete")
        assert await memory_store.get("todelete") is None

    async def test_delete_noop_if_missing(self, memory_store: MemoryStore) -> None:
        await memory_store.delete("nonexistent")  # must not raise

    async def test_list_keys_empty(self, memory_store: MemoryStore) -> None:
        keys = await memory_store.list_keys()
        assert keys == []

    async def test_list_keys(self, memory_store: MemoryStore) -> None:
        await memory_store.set("b", "2")
        await memory_store.set("a", "1")
        await memory_store.set("c", "3")
        keys = await memory_store.list_keys()
        assert keys == ["a", "b", "c"]  # sorted alphabetically

    async def test_namespace_isolation(self, memory_store: MemoryStore) -> None:
        await memory_store.set("key", "ns1-value", namespace="ns1")
        await memory_store.set("key", "ns2-value", namespace="ns2")
        assert await memory_store.get("key", namespace="ns1") == "ns1-value"
        assert await memory_store.get("key", namespace="ns2") == "ns2-value"
        # Default namespace is independent
        assert await memory_store.get("key") is None

    async def test_list_keys_scoped_to_namespace(self, memory_store: MemoryStore) -> None:
        await memory_store.set("x", "1", namespace="nsx")
        await memory_store.set("y", "2", namespace="nsy")
        assert await memory_store.list_keys(namespace="nsx") == ["x"]
        assert await memory_store.list_keys(namespace="nsy") == ["y"]
