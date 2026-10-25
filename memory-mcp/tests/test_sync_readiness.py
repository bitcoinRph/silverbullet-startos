"""Serve the prior valid index during network waits, not after a known failure."""

import asyncio

import httpx
import pytest
from test_index import Corpus

from silverbullet_memory.client import PermanentPageError, UpstreamError
from silverbullet_memory.index import MemoryIndex
from silverbullet_memory.server import create_app
from silverbullet_memory.tools import MemoryTools


@pytest.mark.parametrize("rebuild", [False, True], ids=["poll", "rebuild"])
@pytest.mark.parametrize(
    "phase,outcome",
    [
        (phase, outcome)
        for phase in ("inventory", "get")
        for outcome in ("success", "transient", "unknown", "cancelled")
    ]
    + [("get", "permanent")],
)
def test_ready_search_remain_available_until_sync_failure_known(
    tmp_path, monkeypatch, rebuild, phase, outcome
):
    async def run():
        index = MemoryIndex(tmp_path / "memory.sqlite")
        corpus = Corpus()
        await index.sync(corpus)
        tools = MemoryTools(corpus, index)
        before = tools.memory_search("bitcoin")
        assert before and all(not row["index_stale"] for row in before)
        if phase == "get" and not rebuild:
            corpus.pages["Business/A.md"] += "\nChanged"
        entered, release = asyncio.Event(), asyncio.Event()
        original = getattr(corpus, phase)

        async def blocked(*args):
            entered.set()
            await release.wait()
            if outcome == "transient":
                raise UpstreamError("synthetic upstream failure")
            if outcome == "unknown":
                raise RuntimeError("synthetic unknown failure")
            if outcome == "permanent":
                raise PermanentPageError("invalid_markdown_encoding")
            return await original(*args)

        monkeypatch.setattr(corpus, phase, blocked)
        app = create_app(tools, "r" * 48, "w" * 48, ["localhost:3001"], [])
        task = asyncio.create_task(index.sync(corpus, rebuild=rebuild))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://localhost:3001"
            ) as http:
                response = await http.get("/health/ready")
                assert response.status_code == 200
                assert response.json()["stale"] is False
                assert tools.memory_status()["ready"] is True
                assert tools.memory_search("bitcoin") == before
                if outcome == "cancelled":
                    task.cancel()
                else:
                    release.set()
                if outcome == "unknown":
                    with pytest.raises(RuntimeError, match="synthetic unknown failure"):
                        await asyncio.wait_for(task, 2)
                elif outcome == "cancelled":
                    with pytest.raises(asyncio.CancelledError):
                        await task
                else:
                    await asyncio.wait_for(task, 2)
                failed = outcome in ("transient", "unknown", "cancelled")
                response = await http.get("/health/ready")
                assert response.status_code == (503 if failed else 200)
                assert response.json()["stale"] is failed
                assert tools.memory_status()["ready"] is not failed
                rows = tools.memory_search("bitcoin")
                assert all(row["index_stale"] is failed for row in rows)
                if outcome == "permanent":
                    assert tools.memory_status()["skipped"] > 0
                else:
                    assert rows
                    assert tools.memory_status()["skipped"] == 0
        finally:
            release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            index.close()

    asyncio.run(run())


def test_transient_read_marks_stale_before_later_network_wait(tmp_path, monkeypatch):
    async def run():
        index = MemoryIndex(tmp_path / "memory.sqlite")
        corpus = Corpus()
        await index.sync(corpus)
        corpus.pages["Business/A.md"] += "\nChanged"
        corpus.pages["Inbox/B.md"] += "\nChanged"
        original = corpus.get
        entered, release = asyncio.Event(), asyncio.Event()

        async def get(path):
            if path == "Business/A.md":
                raise UpstreamError("synthetic first page failure")
            entered.set()
            await release.wait()
            return await original(path)

        monkeypatch.setattr(corpus, "get", get)
        task = asyncio.create_task(index.sync(corpus))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            assert index.status()["stale"] is True
            assert index.status()["ready"] is False
            assert all(row["index_stale"] for row in index.search("bitcoin"))
            release.set()
            await asyncio.wait_for(task, 2)
            assert index.status()["stale"] is True
        finally:
            release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            index.close()

    asyncio.run(run())
