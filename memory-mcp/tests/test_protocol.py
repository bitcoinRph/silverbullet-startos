import asyncio

import socket
from contextlib import asynccontextmanager

import httpx
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from test_index import Corpus


@asynccontextmanager
async def authenticated_transport(url, headers):
    async with httpx.AsyncClient(headers=headers) as http:
        async with streamable_http_client(url, http_client=http) as streams:
            yield streams


@asynccontextmanager
async def running(tmp_path):
    from silverbullet_memory.index import MemoryIndex
    from silverbullet_memory.tools import MemoryTools
    from silverbullet_memory.server import create_app

    index = MemoryIndex(tmp_path / "memory.sqlite")
    await index.sync(Corpus())
    app = create_app(
        MemoryTools(Corpus(), index),
        "r" * 48,
        "w" * 48,
        ["127.0.0.1:*"],
        ["https://memory.example"],
    )
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="critical", access_log=False, lifespan="on")
    )
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        for _ in range(100):
            if server.started:
                break
            if task.done():
                await task
            await asyncio.sleep(0.01)
        assert server.started
        yield "http://127.0.0.1:" + str(port)
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 5)
        index.close()
        sock.close()


def test_real_http_inspect_and_call_all_six_tools(tmp_path):
    async def run():
        async with running(tmp_path) as base:
            async with authenticated_transport(
                base + "/mcp", headers={"Authorization": "Bearer " + "w" * 48}
            ) as (read, write, session_id):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    names = {t.name for t in (await session.list_tools()).tools}
                    assert names == {
                        "memory_status",
                        "memory_search",
                        "memory_get",
                        "memory_backlinks",
                        "memory_create",
                        "memory_replace_text",
                    }
                    assert session_id() is None
                    calls = {
                        "memory_status": {},
                        "memory_search": {"query": "bitcoin"},
                        "memory_get": {"path": "Business/A.md"},
                        "memory_backlinks": {"path": "Business/B.md"},
                        "memory_create": {
                            "path": "Inbox/a.md",
                            "content": "Safe note",
                            "kind": "note",
                            "provenance": {
                                "agent_id": "test",
                                "source": "user",
                                "created_at": "2026-01-01T00:00:00Z",
                            },
                            "idempotency_key": "one",
                        },
                        "memory_replace_text": {
                            "path": "Business/A.md",
                            "expected_etag": '"sha256:' + "0" * 64 + '"',
                            "old_text": "x",
                            "new_text": "y",
                            "reason": "test",
                        },
                    }
                    for name, args in calls.items():
                        result = await session.call_tool(name, args)
                        if name == "memory_replace_text":
                            assert (
                                result.isError
                            )  # empty operator-managed prefixes: release denies replacement
                        else:
                            assert not result.isError, name

    asyncio.run(run())


def test_hermes_read_client_through_real_transport(tmp_path):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).parents[2] / "integrations/hermes/plugins/silverbullet-memory/client.py"
    spec = importlib.util.spec_from_file_location("read_client_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    async def run():
        async with running(tmp_path) as base:
            client = module.MemoryClient(base + "/mcp", "r" * 48)
            result = await asyncio.to_thread(client.search, "bitcoin")
            assert len(result) == 2
            assert all(row["untrusted_content"] for row in result)
            assert all(not row["path"].startswith("Inbox/") for row in result)

    asyncio.run(run())


def test_http_auth_origin_size_depth_and_readiness(tmp_path):
    async def run():
        async with running(tmp_path) as base:
            async with httpx.AsyncClient(base_url=base, timeout=5) as http:
                body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
                for header in ["", "Bearer wrong"]:
                    assert (
                        await http.post("/mcp", headers={"Authorization": header}, json=body)
                    ).status_code == 401
                read = {
                    "Authorization": "Bearer " + "r" * 48,
                    "Accept": "application/json, text/event-stream",
                }
                assert (
                    await http.post("/mcp?token=anything", headers=read, json=body)
                ).status_code == 401
                assert (
                    await http.post(
                        "/mcp", headers={**read, "Origin": "https://evil.example"}, json=body
                    )
                ).status_code == 403
                assert (
                    await http.post("/mcp", headers={**read, "Host": "evil.example"}, json=body)
                ).status_code == 403
                assert (
                    await http.post("/mcp", headers=read, content=b" " * 131073)
                ).status_code == 413
                assert (
                    await http.post("/mcp", headers=read, content=b"[" * 20 + b"0" + b"]" * 20)
                ).status_code == 400
                assert (
                    await http.post(
                        "/mcp",
                        headers={**read, "Content-Type": "application/json"},
                        json={
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "tools/call",
                            "params": {"name": "memory_create", "arguments": {}},
                        },
                    )
                ).status_code == 403
                assert (await http.get("/health/ready")).status_code == 200

    asyncio.run(run())
