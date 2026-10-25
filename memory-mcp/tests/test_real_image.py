"""Phase 0: disposable exact-image evidence, NEVER run against an operator URL."""

import hashlib
import os
import subprocess
import time
import uuid

import httpx
import pytest

IMAGE = "ghcr.io/silverbulletmd/silverbullet:2.12.1"
pytestmark = pytest.mark.skipif(
    os.getenv("SB_REAL_IMAGE") != "1", reason="requires disposable Docker + browser"
)
TOKEN = "synthetic-phase0-internal-token-00000000"


@pytest.fixture(scope="module")
def upstream(tmp_path_factory):
    subprocess.run(["docker", "info"], check=True, capture_output=True)
    name = "sb-spike-" + uuid.uuid4().hex
    space_dir = tmp_path_factory.mktemp("real-image-space")
    subprocess.run(
        [
            "docker",
            "run",
            "--detach",
            "--name",
            name,
            "--mount",
            f"type=bind,source={space_dir},target=/data",
            "-p",
            "127.0.0.1::3000",
            "-e",
            "SB_USER=spike:synthetic-browser-password",
            "-e",
            "SB_RUNTIME_API=0",
            "-e",
            "SB_FOLDER=/data",
            "-e",
            "SB_AUTH_TOKEN=" + TOKEN,
            IMAGE,
        ],
        check=True,
        capture_output=True,
    )
    try:
        port = (
            subprocess.check_output(["docker", "port", name, "3000/tcp"], text=True)
            .strip()
            .split(":")[-1]
        )
        with httpx.Client(
            base_url="http://127.0.0.1:" + port,
            headers={"Authorization": "Bearer " + TOKEN, "X-Sync-Mode": "true"},
            timeout=15,
        ) as client:
            for _ in range(120):
                try:
                    if client.get("/.ping").text == "OK":
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            assert client.get("/.ping").status_code == 200
            client.startup_logs = subprocess.check_output(
                ["docker", "logs", name], stderr=subprocess.STDOUT, text=True
            )
            client.space_dir = space_dir
            yield client
    finally:
        subprocess.run(["docker", "rm", "--force", name], check=True, capture_output=True)


def test_runtime_disabled(upstream):
    # 2.12.1 single-space mode retains a runtime wrapper without a transport.
    # Its 503 body is not disable proof: require the exact multi.rs startup log.
    assert "runtime API disabled by SB_RUNTIME_API=0" in getattr(upstream, "startup_logs", ""), (
        "container startup log does not prove Runtime API env disable"
    )
    for attempt in range(2):
        if attempt:
            time.sleep(5)  # A delayed transport must not turn execution on.
        for endpoint in ["/.runtime/lua", "/.runtime/lua_script"]:
            for auth in ["", "Bearer " + TOKEN]:
                r = upstream.post(endpoint, headers={"Authorization": auth}, content="1 + 1")
                assert r.status_code == (503 if auth else 401), (endpoint, r.status_code)


def test_conditional_writes(upstream):
    path = "/.fs/Inbox/phase0.md"
    r = upstream.put(path, content="first", headers={"If-None-Match": "*"})
    assert r.status_code == 200
    etag = upstream.get(path).headers["etag"]
    assert etag.startswith('"sha256:') and etag.endswith('"')
    assert upstream.put(path, content="second", headers={"If-None-Match": "*"}).status_code == 412
    assert upstream.put(path, content="second", headers={"If-Match": etag}).status_code == 200
    assert upstream.put(path, content="lost", headers={"If-Match": etag}).status_code == 412
    assert upstream.get(path).text == "second"
    assert upstream.get("/.fs").status_code == 200


def _page_url(upstream, page):
    return str(upstream.base_url.join("/" + page))


def test_upstream_conflict_preservation_keeps_mcp_mutations_disabled(upstream, tmp_path):
    # This disposable-image-only PUT preserves both edits in a conflict requiring
    # human resolution, not a safe automatic merge or permission to enable writes.
    # v1 MCP mutations must remain hard-disabled; do not turn this into skip/xfail.
    import asyncio
    from playwright.sync_api import expect, sync_playwright
    from silverbullet_memory.client import SilverBulletClient
    from silverbullet_memory.index import MemoryIndex
    from silverbullet_memory.tools import MemoryTools

    path = "/.fs/Inbox/ConcurrencySpike.md"
    assert upstream.put(path, content="initial concurrency text").status_code == 200
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(_page_url(upstream, "Inbox/ConcurrencySpike"))
            page.locator('input[name="username"]').fill("spike")
            page.locator('input[name="password"]').fill("synthetic-browser-password")
            page.locator('button[type="submit"]').click()
            editor = page.locator(".cm-content")
            editor.wait_for(timeout=60000)
            # Visibility precedes asynchronous page loading in 2.12.1.
            expect(editor).to_contain_text("initial concurrency text", timeout=60000)
            etag = upstream.get(path).headers["etag"]
            editor.click()
            page.keyboard.press("Control+End")
            page.keyboard.insert_text("\nhuman-local-change")
            assert "human-local-change" in editor.inner_text()
            assert "human-local-change" not in upstream.get(path).text
            result = upstream.put(
                path,
                content="initial concurrency text\nagent-conditional-change",
                headers={"If-Match": etag},
            )
            assert result.status_code == 200, "upstream concurrency gate needs reevaluation"
            page.wait_for_timeout(7000)
            server_bytes = upstream.get(path).content
            server_text = server_bytes.decode("utf-8")
            assert "agent-conditional-change" in server_text
            assert "human-local-change" in server_text
            for marker in ["<<<<<<< SB", "||||||| SB BASE", "=======", ">>>>>>> SB"]:
                assert any(
                    line == marker or line.startswith(marker + " ")
                    for line in server_text.splitlines()
                ), (marker, server_text)
        finally:
            browser.close()

    async def verify_mcp_read_only():
        async with httpx.AsyncClient() as http:
            client = SilverBulletClient(str(upstream.base_url), TOKEN, http)
            index = MemoryIndex(tmp_path / "concurrency.sqlite")
            try:
                # Test-only managed prefix reaches replacement validation;
                # production has no managed prefixes and is stricter still.
                tools = MemoryTools(client, index, managed_prefixes=("Inbox/",))
                assert tools.memory_status()["writes_enabled"] is False
                note = path.removeprefix("/.fs/")
                before = await client.get(note)
                assert before["content"] == server_text
                from mcp.server.fastmcp.exceptions import ToolError

                with pytest.raises(ToolError, match="^writes_disabled$"):
                    tools.memory_create(
                        "Inbox/BlockedConcurrency.md",
                        "Safe but blocked",
                        "note",
                        {
                            "agent_id": "test",
                            "source": "user",
                            "created_at": "2026-01-01T00:00:00Z",
                        },
                        "concurrency-gate",
                        dry_run=False,
                    )
                assert await client.get(note) == before
                with pytest.raises(ToolError, match="^writes_disabled$"):
                    await tools.memory_replace_text(
                        note,
                        before["etag"],
                        "agent-conditional-change",
                        "mcp-must-not-write",
                        "Verify concurrency stop condition",
                        dry_run=False,
                    )
                # Dry-run still validates raw '<' conflict markers; it cannot write.
                with pytest.raises(ValueError, match="^executable_content_not_allowed$"):
                    await tools.memory_replace_text(
                        note,
                        before["etag"],
                        "agent-conditional-change",
                        "mcp-must-not-write",
                        "Verify concurrency stop condition",
                        dry_run=True,
                    )
                assert await client.get(note) == before
                assert upstream.get(path).content == server_bytes
            finally:
                index.close()

    asyncio.run(verify_mcp_read_only())


def test_real_index_and_rejected_content(upstream, tmp_path):
    import asyncio
    from silverbullet_memory.client import SilverBulletClient
    from silverbullet_memory.index import MemoryIndex
    from silverbullet_memory.security import validate_content
    from silverbullet_memory.tools import MemoryTools

    for payload in ['```space-lua\nprint("blocked")\n```', "${1+1}", "<script>1</script>"]:
        with pytest.raises(ValueError):
            validate_content(payload)
    path = "/.fs/Business/AcceptedSpike.md"
    assert upstream.put(path, content="A plain bitcoin memory note").status_code == 200

    async def run():
        async with httpx.AsyncClient() as http:
            client = SilverBulletClient(str(upstream.base_url), TOKEN, http)
            index = MemoryIndex(tmp_path / "real-image.sqlite")
            try:
                await index.sync(client)
                assert index.status()["ready"]
                tools = MemoryTools(client, index)
                assert tools.memory_search("bitcoin")
                assert (await tools.memory_get("Business/AcceptedSpike.md"))["untrusted_content"]
                from mcp.server.fastmcp.exceptions import ToolError

                with pytest.raises(ToolError, match="^writes_disabled$"):
                    tools.memory_create(
                        "Inbox/Preview.md",
                        "Safe preview",
                        "note",
                        {
                            "agent_id": "test",
                            "source": "user",
                            "created_at": "2026-01-01T00:00:00Z",
                        },
                        "real-spike",
                        dry_run=False,
                    )
            finally:
                index.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "case,raw,reason",
    [
        ("oversized", b"x" * 65537, "page_too_large"),
        ("invalid-utf8", b"invalid markdown: \xff\xfe\n", "invalid_markdown_encoding"),
    ],
    ids=["oversized", "invalid-utf8"],
)
def test_real_image_permanent_page_rejection(upstream, tmp_path, case, raw, reason):
    """No fake transport: demand exact listing, bytes, ETag and production skip behavior."""
    import asyncio

    from silverbullet_memory.client import PermanentPageError, SilverBulletClient
    from silverbullet_memory.index import MemoryIndex

    note = f"Business/Rejected-{case}.md"
    good = f"Business/Readable-{case}.md"
    path = "/.fs/" + note
    assert upstream.put(path, content="oldrejectedneedle").status_code == 200
    assert upstream.put("/.fs/" + good, content="readablecorpusneedle").status_code == 200

    async def run():
        reads = []

        async def record(request):
            reads.append(request.url.path)

        async with httpx.AsyncClient(event_hooks={"request": [record]}, trust_env=False) as http:
            client = SilverBulletClient(str(upstream.base_url), TOKEN, http)
            index = MemoryIndex(tmp_path / "rejected.sqlite")
            try:
                await index.sync(client)
                assert index.status()["ready"] is True
                assert index.get(note)["content"] == "oldrejectedneedle"
                previous_skips = index.status()["skipped"]
                if case == "invalid-utf8":
                    # Upstream 2.12.1 DiskSpace reads bytes; avoid text PUT decoding entirely.
                    target = upstream.space_dir / note
                    temporary = target.with_name(".invalid-byte-page.tmp")
                    temporary.write_bytes(raw)
                    temporary.replace(target)
                else:
                    assert upstream.put(path, content=raw).status_code == 200
                listed = {entry["name"]: entry for entry in await client.inventory()}
                assert listed[note]["size"] == len(raw)
                response = upstream.get(path)
                assert response.status_code == 200
                assert response.content == raw
                assert (
                    response.headers["etag"] == '"sha256:' + hashlib.sha256(raw).hexdigest() + '"'
                )
                with pytest.raises(PermanentPageError, match="^" + reason + "$"):
                    await client.get(note)
                reads.clear()
                await index.sync(client)
                assert reads.count(path) == 1
                status = index.status()
                assert status["ready"] is True and status["stale"] is False
                assert status["skipped"] == previous_skips + 1
                assert {"path": note, "reason": reason} in status["skipped_details"]
                assert index.get(note) is None
                assert not index.search("oldrejectedneedle")
                assert any(row["path"] == good for row in index.search("readablecorpusneedle"))
                for _ in range(2):
                    reads.clear()
                    await index.sync(client)
                    assert path not in reads, "unchanged rejection must not be fetched again"
                    assert index.status()["ready"] is True
            finally:
                index.close()

    try:
        asyncio.run(run())
    finally:
        # Only these synthetic fixture pages; never an operator space.
        for relative in (note, good):
            (upstream.space_dir / relative).unlink(missing_ok=True)


def test_browser_execution(upstream):
    # Demonstrates why path-only trust is unsafe; only a disposable space is used.
    from playwright.sync_api import sync_playwright

    r = upstream.put(
        "/.fs/Inbox/ExecutionSpike.md", content='```space-lua\nprint("SB_EXECUTION_SPIKE")\n```'
    )
    assert r.status_code == 200
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        messages = []
        page.on("console", lambda msg: messages.append(msg.text))
        page.goto(str(upstream.base_url))
        page.locator('input[name="username"]').fill("spike")
        page.locator('input[name="password"]').fill("synthetic-browser-password")
        page.locator('button[type="submit"]').click()
        page.locator(".cm-content").wait_for(timeout=60000)
        for _ in range(60):
            if any("SB_EXECUTION_SPIKE" in m for m in messages):
                break
            page.wait_for_timeout(1000)
        assert any("SB_EXECUTION_SPIKE" in m for m in messages)
        browser.close()
