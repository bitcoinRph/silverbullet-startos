"""Unreadable prior bytes must not prevent production poller write-ahead."""

import asyncio
import json
import os
import runpy
import subprocess
import sys
from types import SimpleNamespace

import pytest

from silverbullet_memory import server
from silverbullet_memory.index import MemoryIndex
from silverbullet_memory.tools import MemoryTools
from test_rebuild_crash_loop import crash_process, interrupted, waiting
from test_rebuild_restart import WALL
from test_rejected_pages import Space, client_for, polling


def unreadable_prior(_pending):
    raise OSError("private prior read failure must not leak")


def crash_with_read_error(path, wall):
    result = subprocess.run(
        [sys.executable, __file__, str(path), str(wall)],
        capture_output=True,
        text=True,
        timeout=10,
        env=os.environ | {"PYTHONPATH": os.pathsep.join(sys.path)},
    )
    assert result.returncode == 73, result.stdout + result.stderr
    assert result.stdout.strip() == "blocked full rebuild"
    assert "private prior read failure" not in result.stderr


@pytest.mark.parametrize("read_error", [False, True], ids=["oversized", "oserror"])
def test_unreadable_prior_crash_publishes_before_sync_then_waits_exactly_30_seconds(
    tmp_path, monkeypatch, read_error
):
    async def run():
        pending = tmp_path / "rebuild-in-progress"
        pending.write_bytes(b"x" * 300)
        worker = crash_with_read_error if read_error else crash_process
        worker(tmp_path, WALL)
        # The child ran production sync into a blocked inventory and exited without cleanup.
        assert json.loads(pending.read_bytes()) == interrupted()
        assert pending.stat().st_size <= 256
        index = MemoryIndex(tmp_path / "memory.sqlite")
        space = Space()
        clock = [99.0, WALL + 10_000]
        try:
            async with client_for(space) as client:
                async with polling(index, client, monkeypatch, clock=clock) as advance:
                    assert json.loads(pending.read_bytes()) == waiting(1, clock[1] + 30)
                    assert space.inventories == 0 and space.reads == []
                    assert index.status()["ready"] is False
                    assert index.status()["stale"] is True
                    await advance(29)
                    assert space.inventories == 0 and space.reads == []
                    assert index.status()["ready"] is False
                    await advance(1)
                    assert space.inventories == 1 and len(space.reads) == 2
                    assert index.status()["ready"] is True
                    assert not pending.exists()
        finally:
            index.close()

    asyncio.run(run())


def test_initially_oversized_prior_repeated_child_deaths_escalate_through_cap(
    tmp_path, monkeypatch
):
    async def run():
        pending = tmp_path / "rebuild-in-progress"
        pending.write_bytes(b"x" * 300)
        wall = WALL
        for number, delay in enumerate((30, 60, 120, 240, 480, 900, 900), 1):
            crash_process(tmp_path, wall)
            attempt = min(number, 6)
            assert json.loads(pending.read_bytes()) == interrupted(attempt)
            space = Space()
            index = MemoryIndex(tmp_path / "memory.sqlite")
            wall += 10_000
            try:
                async with client_for(space) as client:
                    async with polling(index, client, monkeypatch, clock=[0.0, wall]) as advance:
                        assert json.loads(pending.read_bytes()) == waiting(attempt, wall + delay)
                        assert space.inventories == 0 and space.reads == []
                        assert index.status()["ready"] is False
                        await advance(delay - 1)
                        assert space.inventories == 0 and space.reads == []
                        assert index.status()["stale"] is True
                    # Another fresh poller cannot renew or skip the published deadline.
                    async with polling(index, client, monkeypatch, clock=[0.0, wall + delay - 1]):
                        assert json.loads(pending.read_bytes()) == waiting(attempt, wall + delay)
                        assert space.inventories == 0 and space.reads == []
            finally:
                index.close()
            # The next abrupt child begins exactly at the previous persisted deadline.
            wall += delay

    asyncio.run(run())


@pytest.mark.parametrize("read_error", [False, True], ids=["oversized", "oserror"])
def test_cancellation_without_captured_prior_propagates_and_retains_valid_write_ahead(
    tmp_path, monkeypatch, caplog, read_error
):
    async def run():
        pending = tmp_path / "rebuild-in-progress"
        pending.write_bytes(b"x" * 300)
        if read_error:
            monkeypatch.setattr(server, "_read_rebuild_marker", unreadable_prior)
        space = Space()
        index = MemoryIndex(tmp_path / "memory.sqlite")
        tasks = []
        entered = asyncio.Event()
        replacements = []
        observed = []

        def create_task(coro):
            task = asyncio.create_task(coro)
            tasks.append(task)
            return task

        def replace(source, target):
            replacements.append(source.read_bytes())
            os.replace(source, target)

        async def no_sleep(_):
            pytest.fail("cancellation must propagate without retry sleep")

        monkeypatch.setattr(server, "time", SimpleNamespace(time=lambda: WALL, monotonic=lambda: 0))
        monkeypatch.setattr(
            server,
            "asyncio",
            SimpleNamespace(**{**vars(asyncio), "create_task": create_task, "sleep": no_sleep}),
        )
        monkeypatch.setattr(server, "os", SimpleNamespace(**{**vars(os), "replace": replace}))
        try:
            async with client_for(space) as client:

                async def blocked_inventory():
                    observed.append(pending.read_bytes())
                    entered.set()
                    await asyncio.Event().wait()

                monkeypatch.setattr(client, "inventory", blocked_inventory)
                app = server.create_app(
                    MemoryTools(client, index),
                    "r" * 48,
                    "w" * 48,
                    ["localhost:3001"],
                    [],
                    poll=True,
                )
                async with app.app.router.lifespan_context(app.app):
                    await asyncio.wait_for(entered.wait(), 2)
                    tasks[0].cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await tasks[0]
                    assert tasks and all(task.cancelled() for task in tasks)
                    assert observed == replacements
                    assert len(replacements) == 1, "no fabricated prior bytes may be restored"
                    assert json.loads(observed[0]) == interrupted()
                    assert json.loads(pending.read_bytes()) == interrupted()
                    assert index.status()["ready"] is False
                    assert index.status()["stale"] is True
                    assert not list(tmp_path.glob("*.tmp"))
                    messages = [r.getMessage() for r in caplog.records if r.name == "memory.audit"]
                    assert all(message == "rebuild_retry_persist_failed" for message in messages)
                    assert "private prior read failure" not in caplog.text
        finally:
            index.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "fail_final", [False, True], ids=["final-wait-succeeds", "final-wait-fails"]
)
def test_prior_read_and_write_ahead_failure_keep_claim_and_backoff_without_fake_persistence(
    tmp_path, monkeypatch, caplog, fail_final
):
    async def run():
        pending = tmp_path / "rebuild-in-progress"
        prior = b"private original claim"
        pending.write_bytes(prior)
        monkeypatch.setattr(server, "_read_rebuild_marker", unreadable_prior)
        writes = []
        space = Space()
        space.inventory_failure = True
        index = MemoryIndex(tmp_path / "memory.sqlite")

        def replace(source, target):
            state = json.loads(source.read_bytes())
            writes.append(state)
            assert target == pending
            if state["phase"] == "in_progress" or fail_final:
                raise OSError("private write failure must not leak")
            os.replace(source, target)

        monkeypatch.setattr(server, "os", SimpleNamespace(**{**vars(os), "replace": replace}))
        try:
            async with client_for(space) as client:
                inventory = client.inventory

                async def failed_inventory():
                    assert pending.exists()
                    assert writes[-1] == interrupted(min(space.inventories + 1, 6))
                    if fail_final or space.inventories == 0:
                        assert pending.read_bytes() == prior
                    return await inventory()

                monkeypatch.setattr(client, "inventory", failed_inventory)
                async with polling(index, client, monkeypatch) as advance:
                    assert writes == [interrupted(), waiting()]
                    if fail_final:
                        assert pending.read_bytes() == prior
                    else:
                        assert json.loads(pending.read_bytes()) == waiting()
                    assert space.inventories == 1 and space.reads == []
                    assert index.status()["ready"] is False
                    assert index.status()["stale"] is True
                    await advance(29)
                    assert space.inventories == 1 and space.reads == []
                    await advance(1)
                    assert space.inventories == 2
                    assert writes[-2:] == [interrupted(2), waiting(2, WALL + 90)]
                    await advance(59)
                    assert space.inventories == 2 and space.reads == []
                    await advance(1)
                    assert space.inventories == 3
                    assert writes[-2:] == [interrupted(3), waiting(3, WALL + 210)]
                    assert pending.exists()
                    if fail_final:
                        assert pending.read_bytes() == prior
                    assert index.status()["ready"] is False
                    assert not list(tmp_path.glob("*.tmp"))
                    messages = [r.getMessage() for r in caplog.records if r.name == "memory.audit"]
                    assert messages == ["rebuild_retry_persist_failed"] * (9 if fail_final else 6)
                    assert "private" not in caplog.text
        finally:
            index.close()

    asyncio.run(run())


if __name__ == "__main__":
    # Reuse the existing real-lifespan abrupt worker, injecting only the prior-byte reader.
    import test_rebuild_crash_loop

    server._read_rebuild_marker = unreadable_prior
    sys.argv = [test_rebuild_crash_loop.__file__, sys.argv[1], sys.argv[2], "0"]
    runpy.run_path(test_rebuild_crash_loop.__file__, run_name="__main__")
