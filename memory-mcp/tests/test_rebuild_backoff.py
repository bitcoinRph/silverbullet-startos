"""Claimed rebuilds retry on a fake monotonic clock, never wall-clock sleeps."""

import asyncio
from types import SimpleNamespace

import pytest

from silverbullet_memory.index import MemoryIndex
from silverbullet_memory.tools import MemoryTools
from test_rejected_pages import Space, client_for, polling


@pytest.mark.parametrize("failure", [404, 403, 500, "network", "unknown", "inventory"])
def test_claimed_rebuild_backoff_grows_caps_and_skips_all_reads(tmp_path, monkeypatch, failure):
    async def run():
        space = Space()
        index = MemoryIndex(tmp_path / "memory.sqlite")
        marker = tmp_path / "rebuild-request"
        pending = tmp_path / "rebuild-in-progress"
        try:
            async with client_for(space) as client:
                await index.sync(client)
                if isinstance(failure, int):
                    space.status = failure
                elif failure == "network":
                    space.fail.add("Business/b.md")
                elif failure == "inventory":
                    space.inventory_failure = True
                else:

                    def fail():
                        raise RuntimeError("unknown transient failure")

                    space.on_get = fail
                marker.write_text("first")
                async with polling(index, client, monkeypatch) as advance:
                    assert pending.read_text() == "first"
                    assert not marker.exists()
                    # Each deadline is measured from the previous failed attempt.
                    for delay in (30, 60, 120, 240, 480, 900, 900):
                        reads, inventories = list(space.reads), space.inventories
                        for _ in range(delay // 15 - 1):
                            await advance()
                            assert space.reads == reads
                            assert space.inventories == inventories
                            assert index.status()["stale"] is True
                            assert index.status()["ready"] is False
                            assert index.status()["skipped"] == 0
                            assert pending.read_text() == "first"
                        await advance()
                        assert space.inventories == inventories + 1
                        expected = 0 if failure == "inventory" else 1 if failure == "unknown" else 2
                        assert len(space.reads) == len(reads) + expected
        finally:
            index.close()

    asyncio.run(run())


def test_rebuild_retry_success_consumes_only_claim_resets_and_recovers_on_restart(
    tmp_path, monkeypatch
):
    async def run():
        space = Space()
        index = MemoryIndex(tmp_path / "memory.sqlite")
        marker = tmp_path / "rebuild-request"
        pending = tmp_path / "rebuild-in-progress"
        try:
            async with client_for(space) as client:
                await index.sync(client)
                space.fail.add("Business/b.md")
                marker.write_text("first")
                async with polling(index, client, monkeypatch) as advance:
                    # Concurrent request arrives while the first claim is backing off.
                    marker.write_text("second")
                    space.fail.clear()
                    reads = list(space.reads)
                    await advance()
                    assert space.reads == reads
                    assert index.status()["ready"] is False
                    await advance()
                    assert index.status()["ready"] is True
                    assert not pending.exists()
                    assert marker.read_text() == "second"
                    reads = len(space.reads)
                    # The second request is processed on the next poll, not delayed.
                    space.fail.add("Business/b.md")
                    await advance()
                    assert len(space.reads) == reads + 2
                    assert pending.read_text() == "second"
                    reads = list(space.reads)
                    await advance()
                    assert space.reads == reads
                    space.fail.clear()
                    await advance()  # Reset means 30 seconds, not the previous 60.
                    assert index.status()["ready"] is True
                    assert not pending.exists() and not marker.exists()
                    reads = list(space.reads)
                    await advance()
                    assert space.reads == reads
                    marker.write_text("third")
                    space.fail.add("Business/b.md")
                    await advance()
                    assert pending.read_text() == "third"
                # A restarted poller retries the recoverable claim immediately.
                reads = len(space.reads)
                space.fail.clear()
                async with polling(index, client, monkeypatch) as advance:
                    assert len(space.reads) == reads + 2
                    assert index.status()["ready"] is True
                    assert not pending.exists()
                    reads = list(space.reads)
                    await advance()
                    assert space.reads == reads
        finally:
            index.close()

    asyncio.run(run())


def test_rebuild_poll_does_not_swallow_page_cancellation(tmp_path, monkeypatch):
    from silverbullet_memory import server

    async def run():
        space = Space()
        index = MemoryIndex(tmp_path / "memory.sqlite")
        tasks = []
        cancelled = asyncio.Event()

        def create_task(coro):
            task = asyncio.create_task(coro)
            task.add_done_callback(lambda _: cancelled.set())
            tasks.append(task)
            return task

        def cancel():
            raise asyncio.CancelledError()

        async def unexpected_sleep(_):
            pytest.fail("page cancellation must propagate, not enter retry sleep")

        monkeypatch.setattr(
            server,
            "asyncio",
            SimpleNamespace(
                **{**vars(asyncio), "create_task": create_task, "sleep": unexpected_sleep}
            ),
        )
        (tmp_path / "rebuild-request").write_text("cancelled claim")
        space.on_get = cancel
        try:
            async with client_for(space) as client:
                app = server.create_app(
                    MemoryTools(client, index),
                    "r" * 48,
                    "w" * 48,
                    ["localhost:3001"],
                    [],
                    poll=True,
                )
                async with app.app.router.lifespan_context(app.app):
                    await asyncio.wait_for(cancelled.wait(), 2)
                    assert tasks and all(task.cancelled() for task in tasks)
                    assert index.status()["stale"] is True
                    assert (tmp_path / "rebuild-in-progress").exists()
        finally:
            index.close()

    asyncio.run(run())
