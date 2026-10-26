"""Write-ahead recovery through fresh processes and the production poll lifespan."""

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from silverbullet_memory import server
from silverbullet_memory.index import MemoryIndex
from silverbullet_memory.tools import MemoryTools
from test_rebuild_restart import WALL, record
from test_rejected_pages import Space, client_for, polling


def waiting(attempt=1, deadline=WALL + 30):
    return {"version": 2, "phase": "waiting", "attempt": attempt, "retry_at": deadline}


def interrupted(attempt=1):
    return {"version": 2, "phase": "in_progress", "attempt": attempt}


def crash_process(path, wall, *, after_commit=False):
    """Exit a child without cleanup during sync or just after commit, before unlink."""
    result = subprocess.run(
        [sys.executable, __file__, str(path), str(wall), str(int(after_commit))],
        capture_output=True,
        text=True,
        timeout=10,
        env=os.environ | {"PYTHONPATH": os.pathsep.join(sys.path)},
    )
    assert result.returncode == 73, result.stdout + result.stderr
    expected = "committed before unlink" if after_commit else "blocked full rebuild"
    assert result.stdout.strip() == expected


def test_blocked_sync_abrupt_death_waits_from_recovery_before_any_reads(tmp_path, monkeypatch):
    async def run():
        pending = tmp_path / "rebuild-in-progress"
        pending.touch()
        crash_process(tmp_path, WALL)
        # Even a long-running attempt must not have used up its retry wait before death.
        clock = [99.0, WALL + 10_000]
        space = Space()
        index = MemoryIndex(tmp_path / "memory.sqlite")
        try:
            async with client_for(space) as client:
                async with polling(index, client, monkeypatch, clock=clock) as advance:
                    assert space.inventories == 0 and space.reads == []
                    assert json.loads(pending.read_text()) == waiting(1, clock[1] + 30)
                    assert index.status()["ready"] is False
                    await advance(29)
                    assert space.inventories == 0 and space.reads == []
                    await advance(1)
                    assert space.inventories == 1 and len(space.reads) == 2
                    assert index.status()["ready"] is True
                    assert not pending.exists()
        finally:
            index.close()

    asyncio.run(run())


def test_repeated_interrupted_fresh_processes_escalate_and_persist_wait(tmp_path, monkeypatch):
    async def run():
        pending = tmp_path / "rebuild-in-progress"
        pending.touch()
        wall = WALL
        for number, delay in enumerate((30, 60, 120, 240, 480, 900, 900), 1):
            crash_process(tmp_path, wall)
            assert pending.read_bytes(), "interrupted rebuild must have published write-ahead"
            assert json.loads(pending.read_text()) == interrupted(min(number, 6))
            space = Space()
            index = MemoryIndex(tmp_path / "memory.sqlite")
            wall += 10_000  # Detection, not the attempt's start, begins an interruption wait.
            try:
                async with client_for(space) as client:
                    async with polling(index, client, monkeypatch, clock=[0.0, wall]) as advance:
                        assert json.loads(pending.read_text()) == waiting(
                            min(number, 6), wall + delay
                        )
                        assert space.inventories == 0 and space.reads == []
                        await advance(delay - 1)
                        assert space.inventories == 0 and space.reads == []
                    # A second fresh poller honors the same deadline, not a renewed delay.
                    async with polling(index, client, monkeypatch, clock=[0.0, wall + delay - 1]):
                        assert space.inventories == 0 and space.reads == []
                        assert index.status()["ready"] is False
            finally:
                index.close()
            wall += delay

    asyncio.run(run())


def test_commit_before_unlink_replays_idempotently_after_bounded_wait(tmp_path, monkeypatch):
    async def run():
        pending = tmp_path / "rebuild-in-progress"
        pending.touch()
        (tmp_path / "rebuild-request").write_text("concurrent request")
        crash_process(tmp_path, WALL, after_commit=True)
        index = MemoryIndex(tmp_path / "memory.sqlite")
        space = Space()
        try:
            before = index.get("Business/a.md")
            assert before is not None
            async with client_for(space) as client:
                async with polling(index, client, monkeypatch) as advance:
                    assert space.inventories == 0 and space.reads == []
                    await advance(29)
                    assert space.inventories == 0 and space.reads == []
                    await advance(1)
                    assert space.inventories == 1 and len(space.reads) == 2
                    assert index.get("Business/a.md") == before
                    assert not pending.exists()
                    assert (tmp_path / "rebuild-request").read_text() == "concurrent request"
        finally:
            index.close()

    asyncio.run(run())


@pytest.mark.parametrize("version", [1, 2])
def test_existing_wait_is_honored_then_failure_deadline_is_after_failure(
    tmp_path, monkeypatch, version
):
    async def run():
        pending = tmp_path / "rebuild-in-progress"
        state = record(2, WALL + 60, version=1) if version == 1 else waiting(2, WALL + 60)
        pending.write_text(json.dumps(state))
        clock = [0.0, WALL]
        space = Space()
        space.inventory_failure = True
        index = MemoryIndex(tmp_path / "memory.sqlite")
        try:
            async with client_for(space) as client:
                inventory = client.inventory

                async def slow_failure():
                    assert json.loads(pending.read_text()) == interrupted(3 + space.inventories)
                    clock[0] += 100
                    clock[1] += 100
                    return await inventory()

                monkeypatch.setattr(client, "inventory", slow_failure)
                async with polling(index, client, monkeypatch, clock=clock) as advance:
                    assert space.inventories == 0 and space.reads == []
                    await advance(59)
                    assert space.inventories == 0 and space.reads == []
                    await advance(1)
                    assert space.inventories == 1
                    assert json.loads(pending.read_text()) == waiting(3, WALL + 280)
                    await advance(119)
                    assert space.inventories == 1
                    await advance(1)
                    assert space.inventories == 2
        finally:
            index.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "prior",
    [
        b"",
        b' { "retry_at":1800000000, "attempt":2, "version":1 }\n',
        b'{"phase":"waiting","version":2,"retry_at":1800000000,"attempt":2}\n',
    ],
)
@pytest.mark.parametrize("restore_failure", [False, True])
def test_cancellation_restores_exact_prior_bytes_or_keeps_bounded_claim(
    tmp_path, monkeypatch, caplog, prior, restore_failure
):
    async def run():
        pending = tmp_path / "rebuild-in-progress"
        pending.write_bytes(prior)
        space = Space()
        index = MemoryIndex(tmp_path / "memory.sqlite")
        tasks = []
        finished = asyncio.Event()
        entered = asyncio.Event()
        observed = []
        replacements = []

        def create_task(coro):
            task = asyncio.create_task(coro)
            tasks.append(task)
            task.add_done_callback(lambda _: finished.set())
            return task

        def replace(source, target):
            replacements.append(source.read_bytes())
            if restore_failure and len(replacements) == 2:
                raise OSError("secret restore failure")
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
                inventory = client.inventory

                async def cancel_inventory():
                    observed.append(pending.read_bytes())
                    entered.set()
                    await asyncio.Event().wait()

                monkeypatch.setattr(client, "inventory", cancel_inventory)
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
                    await asyncio.wait_for(finished.wait(), 2)
                    assert tasks and all(task.cancelled() for task in tasks)
                    attempt = 1 if not prior else 3
                    assert observed and observed[0], "write-ahead must precede blocked sync"
                    assert [json.loads(raw) for raw in observed] == [interrupted(attempt)]
                    assert index.status()["ready"] is False
                    assert len(replacements) == 2
                    assert replacements[1] == prior
                    assert not list(tmp_path.glob("*.tmp"))
                    if restore_failure:
                        assert json.loads(pending.read_bytes()) == interrupted(attempt)
                        assert "rebuild_retry_restore_failed" in caplog.text
                    else:
                        assert pending.read_bytes() == prior
                if restore_failure:
                    # Restore failure leaves ownership and the interrupted wait, not an immediate loop.
                    monkeypatch.setattr(client, "inventory", inventory)
                    async with polling(index, client, monkeypatch) as advance:
                        assert space.inventories == 0 and space.reads == []
                        delay = 30 if not prior else 120
                        await advance(delay - 1)
                        assert space.inventories == 0 and space.reads == []
                        await advance(1)
                        assert space.inventories == 1 and not pending.exists()
                    assert "secret restore failure" not in caplog.text
        finally:
            index.close()

    asyncio.run(run())


@pytest.mark.parametrize("fail_final", [False, True])
def test_write_ahead_failure_keeps_claim_and_attempts_final_wait_without_busy_loop(
    tmp_path, monkeypatch, caplog, fail_final
):
    async def run():
        pending = tmp_path / "rebuild-in-progress"
        pending.touch()
        space = Space()
        space.inventory_failure = True
        index = MemoryIndex(tmp_path / "memory.sqlite")
        writes = []

        def replace(source, target):
            state = json.loads(source.read_text())
            writes.append(state)
            if state.get("phase") == "in_progress" or fail_final:
                raise OSError("secret persistence failure")
            os.replace(source, target)

        monkeypatch.setattr(server, "os", SimpleNamespace(**{**vars(os), "replace": replace}))
        try:
            async with client_for(space) as client:
                async with polling(index, client, monkeypatch) as advance:
                    assert writes == [interrupted(), waiting()]
                    assert pending.exists()
                    assert "rebuild_retry_persist_failed" in caplog.text
                    assert "secret persistence failure" not in caplog.text
                    await advance(29)
                    assert space.inventories == 1
                    await advance(1)
                    assert space.inventories == 2
                    assert writes[-2:] == [interrupted(2), waiting(2, WALL + 90)]
                    assert not list(tmp_path.glob("*.tmp"))
        finally:
            index.close()

    asyncio.run(run())


BAD_V2 = [
    json.dumps(interrupted() | {"version": True}),
    json.dumps(interrupted() | {"version": 2.0}),
    json.dumps(interrupted() | {"phase": True}),
    json.dumps(interrupted() | {"phase": "unknown"}),
    json.dumps(interrupted() | {"retry_at": WALL + 900}),
    json.dumps(waiting() | {"extra": 1}),
    *[json.dumps(interrupted(value)) for value in [True, 0, -1, 7, 1.0, None, 10**100]],
    *[
        json.dumps(waiting(deadline=value))
        for value in [True, -1, float("nan"), float("inf"), 1e300, None]
    ],
    '{"version":2,"phase":"in_progress","attempt":1,"attempt":1}',
    '{"version":2,"phase":"waiting","attempt":1,"retry_at":1e400}',
    json.dumps(waiting(6, WALL + 900)) + " " * 257,
    "[" * 17 + "0" + "]" * 17,
]


@pytest.mark.parametrize("raw", BAD_V2)
def test_hostile_v2_cannot_defer_or_poison_next_attempt(tmp_path, monkeypatch, raw):
    async def run():
        pending = tmp_path / "rebuild-in-progress"
        pending.write_text(raw)
        space = Space()
        space.inventory_failure = True
        index = MemoryIndex(tmp_path / "memory.sqlite")
        try:
            async with client_for(space) as client:
                async with polling(index, client, monkeypatch) as advance:
                    assert space.inventories == 1
                    assert json.loads(pending.read_text()) == waiting()
                    await advance(29)
                    assert space.inventories == 1
                    await advance(1)
                    assert space.inventories == 2
        finally:
            index.close()

    asyncio.run(run())


if __name__ == "__main__":

    async def abrupt_worker():
        path, wall = Path(sys.argv[1]), float(sys.argv[2])
        server.time = SimpleNamespace(time=lambda: wall, monotonic=lambda: 0)
        index = MemoryIndex(path / "memory.sqlite")
        async with client_for(Space()) as client:
            entered = asyncio.Event()

            async def blocked_inventory():
                entered.set()
                await asyncio.Event().wait()

            after_commit = sys.argv[3] == "1"
            if after_commit:
                unlink = Path.unlink

                def crash_before_unlink(self, *args, **kwargs):
                    if self.name == "rebuild-in-progress":
                        print("committed before unlink", flush=True)
                        os._exit(73)
                    return unlink(self, *args, **kwargs)

                Path.unlink = crash_before_unlink
            else:
                client.inventory = blocked_inventory
            sync = index.sync

            async def full_sync(client, *, rebuild=False):
                assert rebuild is True
                await sync(client, rebuild=rebuild)

            index.sync = full_sync
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
                print("blocked full rebuild", flush=True)
                os._exit(73)

    asyncio.run(abrupt_worker())
