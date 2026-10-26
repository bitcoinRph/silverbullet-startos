"""Production poll lifecycle with fake wall/monotonic time and real marker files."""

import asyncio
import json
import os
import stat
from types import SimpleNamespace

import pytest

from silverbullet_memory import server
from silverbullet_memory.index import MemoryIndex
from test_rejected_pages import Space, client_for, polling

WALL = 1_800_000_000.0


def record(attempt=1, retry_at=WALL + 30):
    return {"version": 1, "attempt": attempt, "retry_at": retry_at}


def test_restart_honors_remaining_delay_without_any_reads(tmp_path, monkeypatch):
    async def run():
        space = Space()
        path = tmp_path / "memory.sqlite"
        pending = tmp_path / "rebuild-in-progress"
        pending.touch()  # Legacy empty :3 claim gets one immediate attempt.
        clock = [100.0, WALL]
        index = MemoryIndex(path)
        try:
            async with client_for(space) as client:
                await index.sync(client)
                space.inventory_failure = True
                async with polling(index, client, monkeypatch, clock=clock):
                    assert json.loads(pending.read_text()) == record()
                    assert pending.stat().st_size <= 256
                    assert stat.S_IMODE(pending.stat().st_mode) == 0o600
                index.close()
                index = MemoryIndex(path)
                clock[:] = [0.0, WALL + 10]  # New monotonic epoch after restart.
                inventories, reads = space.inventories, list(space.reads)
                space.inventory_failure = False
                async with polling(index, client, monkeypatch, clock=clock) as advance:
                    assert space.inventories == inventories
                    assert space.reads == reads
                    assert index.status()["ready"] is False
                    # Wall clock jumps after load cannot change this process's wait.
                    clock[1] = WALL - 100_000
                    await advance(19)
                    assert space.inventories == inventories and space.reads == reads
                    await advance(1)
                    assert space.inventories == inventories + 1
                    assert index.status()["ready"] is True
                    assert not pending.exists()
        finally:
            index.close()

    asyncio.run(run())


@pytest.mark.parametrize("elapsed", [30, 31, 10_000])
def test_restart_at_or_after_deadline_retries_immediately(tmp_path, monkeypatch, elapsed):
    async def run():
        space = Space()
        index = MemoryIndex(tmp_path / "memory.sqlite")
        pending = tmp_path / "rebuild-in-progress"
        try:
            async with client_for(space) as client:
                pending.touch()
                space.inventory_failure = True
                async with polling(index, client, monkeypatch):
                    assert json.loads(pending.read_text()) == record()
                inventories = space.inventories
                space.inventory_failure = False
                async with polling(index, client, monkeypatch, clock=[0.0, WALL + elapsed]):
                    assert space.inventories == inventories + 1
                    assert index.status()["ready"] is True
                    assert not pending.exists()
        finally:
            index.close()

    asyncio.run(run())


def test_repeated_restart_failure_preserves_attempt_and_caps(tmp_path, monkeypatch):
    async def run():
        space = Space()
        space.inventory_failure = True
        index = MemoryIndex(tmp_path / "memory.sqlite")
        pending = tmp_path / "rebuild-in-progress"
        pending.touch()
        wall = WALL
        try:
            async with client_for(space) as client:
                for number, delay in enumerate((30, 60, 120, 240, 480, 900, 900, 900), 1):
                    inventories = space.inventories
                    async with polling(index, client, monkeypatch, clock=[0.0, wall]):
                        assert space.inventories == inventories + 1
                        assert json.loads(pending.read_text()) == record(
                            min(number, 6), wall + delay
                        )
                    # Restart before each deadline: no inventory or page reads.
                    reads = list(space.reads)
                    async with polling(index, client, monkeypatch, clock=[999.0, wall + 1]):
                        assert space.inventories == inventories + 1
                        assert space.reads == reads
                    wall += delay
        finally:
            index.close()

    asyncio.run(run())


BAD_RECORDS = [
    "",
    "not json",
    "[]",
    "null",
    "true",
    "1",
    '"text"',
    "{}",
    "{" * 300,
    json.dumps(record() | {"version": 2}),
    json.dumps(record() | {"version": True}),
    json.dumps(record() | {"extra": "must not be accepted"}),
    '{"version":1,"version":1,"attempt":1,"retry_at":1800000900}',
    *[
        json.dumps(record(attempt=value, retry_at=WALL + 900))
        for value in (-1, 0, 7, 1.0, True, "1", None, float("nan"), float("inf"), 10**100)
    ],
    *[
        json.dumps(record(retry_at=value))
        for value in (
            -1,
            True,
            "1800000900",
            None,
            float("nan"),
            float("inf"),
            -float("inf"),
            1e300,
            253402300800,
        )
    ],
]


@pytest.mark.parametrize("raw", BAD_RECORDS)
def test_legacy_or_invalid_state_gets_one_immediate_retry(tmp_path, monkeypatch, raw):
    async def run():
        space = Space()
        space.inventory_failure = True
        index = MemoryIndex(tmp_path / "memory.sqlite")
        pending = tmp_path / "rebuild-in-progress"
        pending.write_text(raw)
        try:
            async with client_for(space) as client:
                async with polling(index, client, monkeypatch) as advance:
                    assert space.inventories == 1
                    assert json.loads(pending.read_text()) == record()
                    await advance()
                    assert space.inventories == 1
                    await advance()
                    assert space.inventories == 2
                    assert json.loads(pending.read_text()) == record(2, WALL + 90)
        finally:
            index.close()

    asyncio.run(run())


@pytest.mark.parametrize("deadline", [WALL + 900, WALL + 10_000_000, 253402300799])
def test_valid_future_state_is_capped_to_fifteen_minutes(tmp_path, monkeypatch, deadline):
    async def run():
        space = Space()
        index = MemoryIndex(tmp_path / "memory.sqlite")
        pending = tmp_path / "rebuild-in-progress"
        pending.write_text(json.dumps(record(6, deadline)))
        try:
            async with client_for(space) as client:
                async with polling(index, client, monkeypatch) as advance:
                    assert space.inventories == 0 and space.reads == []
                    await advance(899)
                    assert space.inventories == 0 and space.reads == []
                    assert index.status()["stale"] is True
                    await advance(1)
                    assert space.inventories == 1
                    assert index.status()["ready"] is True
                    assert not pending.exists()
        finally:
            index.close()

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["file_fsync", "replace", "directory_fsync"])
def test_atomic_persistence_failure_keeps_claim_and_memory_backoff(
    tmp_path, monkeypatch, caplog, failure
):
    async def run():
        space = Space()
        space.inventory_failure = True
        index = MemoryIndex(tmp_path / "memory.sqlite")
        pending = tmp_path / "rebuild-in-progress"
        pending.touch()
        events = []

        def fsync(fd):
            kind = "directory_fsync" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file_fsync"
            events.append(kind)
            if failure == kind:
                raise OSError("synthetic secret exception text must not leak")
            os.fsync(fd)

        def replace(source, target):
            assert source.parent == target.parent == tmp_path
            assert target == pending
            state = json.loads(source.read_text())
            assert set(state) == {"version", "attempt", "retry_at"}
            assert state["attempt"] == min(space.inventories, 6)
            if space.inventories == 1:
                assert state == record()
                assert pending.read_bytes() == b""
            events.append("replace")
            if failure == "replace":
                raise OSError("synthetic secret exception text must not leak")
            os.replace(source, target)

        monkeypatch.setattr(
            server, "os", SimpleNamespace(**{**vars(os), "fsync": fsync, "replace": replace})
        )
        try:
            async with client_for(space) as client:
                async with polling(index, client, monkeypatch) as advance:
                    assert (
                        events
                        == {
                            "file_fsync": ["file_fsync"],
                            "replace": ["file_fsync", "replace"],
                            "directory_fsync": ["file_fsync", "replace", "directory_fsync"],
                        }[failure]
                    )
                    assert pending.exists()
                    assert not list(tmp_path.glob("*.tmp"))
                    assert index.status()["ready"] is False
                    assert "rebuild_retry_persist_failed" in caplog.text
                    assert "secret exception" not in caplog.text
                    await advance()
                    assert space.inventories == 1
                    await advance()
                    assert space.inventories == 2
                    await advance(59)
                    assert space.inventories == 2
                    await advance(1)
                    assert space.inventories == 3
                    assert pending.exists()
                    assert "secret exception" not in caplog.text
        finally:
            index.close()

    asyncio.run(run())


def test_retry_state_is_published_only_after_file_fsync_then_directory_fsync(tmp_path, monkeypatch):
    async def run():
        space = Space()
        space.inventory_failure = True
        index = MemoryIndex(tmp_path / "memory.sqlite")
        pending = tmp_path / "rebuild-in-progress"
        pending.touch()
        events = []

        def fsync(fd):
            events.append("directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file")
            os.fsync(fd)

        def replace(source, target):
            assert events == ["file"]
            assert source.parent == target.parent == tmp_path
            assert target == pending and pending.read_bytes() == b""
            assert json.loads(source.read_text()) == record()
            events.append("replace")
            os.replace(source, target)

        monkeypatch.setattr(
            server, "os", SimpleNamespace(**{**vars(os), "fsync": fsync, "replace": replace})
        )
        try:
            async with client_for(space) as client:
                async with polling(index, client, monkeypatch):
                    assert events == ["file", "replace", "directory"]
                    assert json.loads(pending.read_text()) == record()
                    assert not list(tmp_path.glob("*.tmp"))
        finally:
            index.close()

    asyncio.run(run())


def test_incremental_inventory_retries_every_poll_without_rebuild_backoff(tmp_path, monkeypatch):
    async def run():
        space = Space()
        index = MemoryIndex(tmp_path / "memory.sqlite")
        try:
            async with client_for(space) as client:
                await index.sync(client)
                assert not (tmp_path / "rebuild-request").exists()
                space.inventory_failure = True
                async with polling(index, client, monkeypatch) as advance:
                    assert index.status()["ready"] is False
                    for _ in range(3):
                        inventories = space.inventories
                        await advance()
                        assert space.inventories == inventories + 1
                    space.inventory_failure = False
                    inventories = space.inventories
                    await advance()
                    assert space.inventories == inventories + 1
                    assert index.status()["ready"] is True
                    assert not (tmp_path / "rebuild-in-progress").exists()
        finally:
            index.close()

    asyncio.run(run())
