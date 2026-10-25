"""Regression through the real bounded HTTP reader, index and daemon poll lifecycle."""

import asyncio
import hashlib
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest

from silverbullet_memory.client import SilverBulletClient, UpstreamError
from silverbullet_memory.index import MemoryIndex
from silverbullet_memory.tools import MemoryTools


class Space:
    def __init__(self):
        self.pages = {"Business/a.md": b"bitcoin decision", "Business/b.md": b"bitcoin plan"}
        self.reads = []
        self.fail = set()
        self.bad_etag = set()
        self.inventory_failure = False
        self.status = None
        self.inventories = 0
        self.on_get = lambda: None

    def handle(self, request):
        if request.url.path == "/.fs":
            self.inventories += 1
            if self.inventory_failure:
                return httpx.Response(503)
            return httpx.Response(
                200,
                json=[
                    {
                        "name": path,
                        "size": len(raw),
                        "lastModified": int(hashlib.sha256(raw).hexdigest()[:8], 16),
                    }
                    for path, raw in self.pages.items()
                ],
            )
        path = request.url.path.removeprefix("/.fs/")
        self.reads.append(path)
        self.on_get()
        if path in self.fail:
            raise httpx.ReadTimeout("synthetic timeout")
        if self.status is not None:
            return httpx.Response(self.status)
        raw = self.pages[path]
        digest = "0" * 64 if path in self.bad_etag else hashlib.sha256(raw).hexdigest()
        return httpx.Response(200, content=raw, headers={"etag": '"sha256:' + digest + '"'})


@asynccontextmanager
async def client_for(space):
    async with httpx.AsyncClient(transport=httpx.MockTransport(space.handle)) as http:
        yield SilverBulletClient("http://silverbullet.test", "synthetic", http)


@asynccontextmanager
async def polling(index, client, monkeypatch):
    from silverbullet_memory import server

    checkpoints, permits = asyncio.Queue(), asyncio.Queue()
    clock = [0.0]
    tasks = []

    def create_task(coro):
        task = asyncio.create_task(coro)
        tasks.append(task)
        return task

    async def sleep(seconds):
        assert seconds == 15
        await checkpoints.put(None)
        await permits.get()

    monkeypatch.setattr(server, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(
        server,
        "asyncio",
        SimpleNamespace(**{**vars(asyncio), "sleep": sleep, "create_task": create_task}),
    )
    app = server.create_app(
        MemoryTools(client, index), "r" * 48, "w" * 48, ["localhost:3001"], [], poll=True
    )
    async with app.app.router.lifespan_context(app.app):
        await asyncio.wait_for(checkpoints.get(), 2)

        async def advance(seconds=15):
            clock[0] += seconds
            await permits.put(None)
            await asyncio.wait_for(checkpoints.get(), 2)

        yield advance
    assert tasks and all(task.cancelled() for task in tasks), "poll task must not leak"


@pytest.mark.parametrize(
    "raw,reason",
    [(b"x" * 65537, "page_too_large"), (b"\xff", "invalid_markdown_encoding")],
    ids=["oversized", "invalid-utf8"],
)
def test_permanent_rejection_completes_once_removes_old_content_and_survives_restart(
    tmp_path, monkeypatch, raw, reason
):
    async def run():
        space = Space()
        path = tmp_path / "memory.sqlite"
        index = MemoryIndex(path)
        async with client_for(space) as client:
            await index.sync(client)
            assert index.get("Business/b.md") is not None
            space.pages["Business/b.md"] = raw
            marker = tmp_path / "rebuild-request"
            marker.write_text("synthetic request")
            async with polling(index, client, monkeypatch) as advance:
                status = index.status()
                assert status["ready"] is True
                assert status["stale"] is False
                assert status["documents"] == 1
                assert status["skipped"] == 1
                assert status["skipped_details"] == [{"path": "Business/b.md", "reason": reason}]
                assert index.get("Business/b.md") is None
                assert all(row["path"] != "Business/b.md" for row in index.search("bitcoin"))
                assert not marker.exists(), "accepted rebuild request must be consumed"
                reads = list(space.reads)
                await advance()
                assert space.reads == reads, (
                    "unchanged permanent pages must not force a full refetch"
                )
            index.close()
            index = MemoryIndex(path)
            async with polling(index, client, monkeypatch):
                assert index.status()["ready"] is True
                assert index.status()["skipped"] == 1
                assert space.reads == reads, "consumed request must not rebuild on restart"
            space.pages["Business/b.md"] = b"readable again bitcoin"
            await index.sync(client)
            assert index.status()["skipped"] == 0
            assert index.get("Business/b.md")["content"] == "readable again bitcoin"
            index.close()

    asyncio.run(run())


def test_incremental_permanent_rejection_removes_indexed_text_and_bounds_status(tmp_path):
    async def run():
        space = Space()
        index = MemoryIndex(tmp_path / "memory.sqlite")
        async with client_for(space) as client:
            await index.sync(client)
            space.pages["Business/a.md"] = b"\xff"
            space.pages.update({f"Business/rejected-{n}.md": b"x" * 65537 for n in range(25)})
            await index.sync(client)
            assert index.status()["ready"] is True
            assert index.status()["skipped"] == 26
            assert len(index.status()["skipped_details"]) <= 10
            assert index.get("Business/a.md") is None
            assert len(index.search("bitcoin")) == 1
            space.pages = {"Business/b.md": b"bitcoin plan"}
            await index.sync(client)
            assert index.status()["skipped"] == 0
            index.close()

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["network", "etag", "inventory"])
def test_transient_failures_remain_stale_and_retry(tmp_path, monkeypatch, failure):
    async def run():
        space = Space()
        index = MemoryIndex(tmp_path / "memory.sqlite")
        async with client_for(space) as client:
            await index.sync(client)
            space.pages["Business/b.md"] = b"changed bitcoin"
            space.fail = {"Business/b.md"} if failure == "network" else set()
            space.bad_etag = {"Business/b.md"} if failure == "etag" else set()
            space.inventory_failure = failure == "inventory"
            (tmp_path / "rebuild-request").write_text("retry request")
            async with polling(index, client, monkeypatch) as advance:
                assert index.status()["stale"] is True
                assert index.status()["ready"] is False
                assert index.status().get("skipped", 0) == 0
                space.fail.clear()
                space.bad_etag.clear()
                space.inventory_failure = False
                await advance()
                assert index.status()["stale"] is True
                await advance()
                assert index.status()["ready"] is True
                assert index.get("Business/b.md")["content"] == "changed bitcoin"
                assert not (tmp_path / "rebuild-request").exists()
                reads = list(space.reads)
                await advance()
                assert space.reads == reads
            index.close()

    asyncio.run(run())


def test_new_rebuild_request_during_attempt_is_not_lost(tmp_path, monkeypatch):
    async def run():
        space = Space()
        index = MemoryIndex(tmp_path / "memory.sqlite")
        marker = tmp_path / "rebuild-request"
        marker.write_text("first")
        created = False

        def new_request():
            nonlocal created
            if not created:
                created = True
                temporary = tmp_path / "new-request.tmp"
                temporary.write_text("second")
                temporary.replace(marker)

        space.on_get = new_request
        async with client_for(space) as client:
            async with polling(index, client, monkeypatch) as advance:
                assert marker.exists(), "must not unlink a newly created concurrent request"
                reads = len(space.reads)
                await advance()
                assert len(space.reads) == reads + 2, (
                    "second request must cause exactly one rebuild"
                )
                assert not marker.exists()
                reads = len(space.reads)
                await advance()
                assert len(space.reads) == reads
            index.close()

    asyncio.run(run())


def test_unknown_page_exception_fails_closed(tmp_path):
    async def run():
        space = Space()
        index = MemoryIndex(tmp_path / "memory.sqlite")
        async with client_for(space) as client:
            await index.sync(client)
            space.pages["Business/b.md"] = b"changed"

            def fail():
                raise RuntimeError("unknown synthetic failure")

            space.on_get = fail
            with pytest.raises(RuntimeError):
                await index.sync(client)
            assert index.status()["stale"] is True
            assert index.status()["ready"] is False
            index.close()

    asyncio.run(run())


def test_permanent_rejection_never_keeps_old_text_during_transient_failed_rebuild(tmp_path):
    async def run():
        space = Space()
        index = MemoryIndex(tmp_path / "memory.sqlite")
        async with client_for(space) as client:
            await index.sync(client)
            space.pages["Business/a.md"] = b"x" * 65537
            space.fail.add("Business/b.md")
            await index.sync(client, rebuild=True)
            assert index.status()["stale"] is True
            assert index.status()["skipped"] == 1
            assert index.get("Business/a.md") is None
            assert index.get("Business/b.md") is not None
            assert all(row["path"] != "Business/a.md" for row in index.search("bitcoin"))
            index.close()

    asyncio.run(run())


def test_exact_64_kib_page_limit_is_unchanged(tmp_path):
    async def run():
        space = Space()
        space.pages["Business/a.md"] = b"x" * 65536
        index = MemoryIndex(tmp_path / "memory.sqlite")
        async with client_for(space) as client:
            await index.sync(client)
            assert index.status()["ready"] is True
            assert index.status()["skipped"] == 0
            assert len(index.get("Business/a.md")["content"].encode()) == 65536
            index.close()

    asyncio.run(run())


def test_inventory_size_failure_is_not_a_permanent_page_skip(tmp_path):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, content=b"x" * (8 * 1024 * 1024 + 1))
            )
        ) as http:
            client = SilverBulletClient("http://silverbullet.test", "synthetic", http)
            with pytest.raises(UpstreamError):
                await client.inventory()
            index = MemoryIndex(tmp_path / "memory.sqlite")
            await index.sync(client)
            assert not index.status()["ready"]
            assert index.status().get("skipped", 0) == 0
            index.close()

    asyncio.run(run())
