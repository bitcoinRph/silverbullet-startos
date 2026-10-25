"""Offline regression tests for CI fixture plumbing, not real-image evidence."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest


def spike():
    path = Path(__file__).with_name("test_real_image.py")
    spec = importlib.util.spec_from_file_location("image_spike_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DISABLE_LOG = "runtime API disabled by SB_RUNTIME_API=0"


def test_runtime_probe_requires_startup_log_and_repeats_bearer_checks(monkeypatch):
    module = spike()
    seen = []
    waits = []
    monkeypatch.setattr(module.time, "sleep", waits.append)

    def handler(request):
        seen.append((request.url.path, request.headers.get("authorization")))
        if not request.headers.get("authorization"):
            return httpx.Response(401)
        return httpx.Response(503, json={"error": "runtime not ready"})

    with httpx.Client(
        base_url="http://127.0.0.1:3000", transport=httpx.MockTransport(handler)
    ) as client:
        client.startup_logs = "INFO " + DISABLE_LOG + "\n"
        module.test_runtime_disabled(client)
    expected = [
        (endpoint, auth)
        for endpoint in ["/.runtime/lua", "/.runtime/lua_script"]
        for auth in ["", "Bearer " + module.TOKEN]
    ]
    assert seen == expected * 2
    assert len(waits) == 1 and 0 < waits[0] <= 10


@pytest.mark.parametrize("logs", [None, "", "runtime starting", "SB_RUNTIME_API=0"])
def test_runtime_503_without_exact_disable_log_remains_a_blocker(logs):
    module = spike()

    def handler(request):
        if not request.headers.get("authorization"):
            return httpx.Response(401)
        return httpx.Response(503, json={"error": "Runtime API is not enabled"})

    with httpx.Client(
        base_url="http://127.0.0.1:3000", transport=httpx.MockTransport(handler)
    ) as client:
        if logs is not None:
            client.startup_logs = logs
        with pytest.raises(AssertionError, match="startup log"):
            module.test_runtime_disabled(client)


@pytest.mark.parametrize("endpoint", ["/.runtime/lua", "/.runtime/lua_script"])
@pytest.mark.parametrize("delayed", [False, True])
@pytest.mark.parametrize("status", [200, 400, 401, 500])
def test_runtime_execution_or_unexpected_status_remains_a_blocker(
    monkeypatch, endpoint, delayed, status
):
    module = spike()
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    calls = 0

    def handler(request):
        nonlocal calls
        if not request.headers.get("authorization"):
            return httpx.Response(401)
        if request.url.path == endpoint:
            calls += 1
            if not delayed or calls == 2:
                return httpx.Response(status, text="unexpected runtime response")
        return httpx.Response(503, json={"error": "runtime not ready"})

    with httpx.Client(
        base_url="http://127.0.0.1:3000", transport=httpx.MockTransport(handler)
    ) as client:
        client.startup_logs = DISABLE_LOG
        with pytest.raises(AssertionError):
            module.test_runtime_disabled(client)
    assert calls == (2 if delayed else 1)


def test_disposable_fixture_captures_container_logs_before_cleanup(monkeypatch):
    module = spike()
    commands = []

    def output(command, **kwargs):
        commands.append(command)
        return DISABLE_LOG if command[1] == "logs" else "127.0.0.1:32768\n"

    monkeypatch.setattr(module.subprocess, "check_output", output)
    monkeypatch.setattr(
        module.subprocess, "run", lambda command, **kwargs: commands.append(command)
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        module.httpx,
        "Client",
        lambda **kwargs: real_client(
            **kwargs, transport=httpx.MockTransport(lambda _: httpx.Response(200, text="OK"))
        ),
    )
    fixture = module.upstream.__wrapped__()
    try:
        client = next(fixture)
        assert getattr(client, "startup_logs", None) == DISABLE_LOG
    finally:
        fixture.close()
    log_command = next(command for command in commands if command[1] == "logs")
    assert log_command[2] == commands[-1][-1]
    assert commands[-1][:3] == ["docker", "rm", "--force"]


def test_conflict_preservation_characterization_exercises_both_disabled_mcp_writes(
    monkeypatch, tmp_path
):
    import hashlib
    import playwright.sync_api

    module = spike()
    text = "initial concurrency text"
    browser_text = text
    editor_loaded = False
    requests = []

    def handler(request):
        nonlocal text, browser_text
        requests.append((request.method, request.url.path))
        if request.method == "PUT":
            if "human-local-change" in browser_text:
                # Simulate preservation with a human-resolution conflict, not
                # safe automatic merging or permission to enable MCP writes.
                text = "\n".join(
                    [
                        "<<<<<<< SB synthetic-agent",
                        request.content.decode(),
                        "||||||| SB BASE synthetic-base",
                        text,
                        "=======",
                        browser_text,
                        ">>>>>>> SB synthetic-human",
                        "",
                    ]
                )
            else:
                text = request.content.decode()
            browser_text = text
        etag = '"sha256:' + hashlib.sha256(text.encode()).hexdigest() + '"'
        return httpx.Response(200, text=text, headers={"etag": etag})

    locator = SimpleNamespace(
        fill=lambda _: None,
        click=lambda: None,
        wait_for=lambda **_: None,
        inner_text=lambda: browser_text,
    )

    def insert_text(value):
        nonlocal browser_text
        assert editor_loaded, "must wait for note content, not only visible CodeMirror"
        browser_text += value

    def expect_editor(target):
        assert target is locator

        def to_contain_text(expected, timeout):
            nonlocal editor_loaded
            assert expected == "initial concurrency text"
            assert 0 < timeout <= 60000
            editor_loaded = True

        return SimpleNamespace(to_contain_text=to_contain_text)

    page = SimpleNamespace(
        goto=lambda _: None,
        locator=lambda _: locator,
        keyboard=SimpleNamespace(press=lambda _: None, insert_text=insert_text),
        wait_for_timeout=lambda _: None,
    )
    browser = SimpleNamespace(new_page=lambda: page, close=lambda: None)

    class Playwright:
        def __enter__(self):
            return SimpleNamespace(chromium=SimpleNamespace(launch=lambda: browser))

        def __exit__(self, *_):
            pass

    monkeypatch.setattr(playwright.sync_api, "sync_playwright", Playwright)
    monkeypatch.setattr(playwright.sync_api, "expect", expect_editor)
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        module.httpx,
        "AsyncClient",
        lambda **kwargs: real_async_client(**kwargs, transport=httpx.MockTransport(handler)),
    )
    from silverbullet_memory.tools import MemoryTools

    invoked = []
    create = MemoryTools.memory_create
    replace = MemoryTools.memory_replace_text

    def checked_create(self, *args, **kwargs):
        assert kwargs["dry_run"] is False
        result = create(self, *args, **kwargs)
        invoked.append(("create", result["error"]))
        return result

    async def checked_replace(self, *args, **kwargs):
        assert kwargs["dry_run"] is False
        try:
            return await replace(self, *args, **kwargs)
        except ValueError as exc:
            # Conflict markers hit the content validator before writes_disabled.
            invoked.append(("replace", str(exc)))
            raise

    monkeypatch.setattr(MemoryTools, "memory_create", checked_create)
    monkeypatch.setattr(MemoryTools, "memory_replace_text", checked_replace)
    with httpx.Client(
        base_url="http://127.0.0.1:32768", transport=httpx.MockTransport(handler)
    ) as client:
        module.test_upstream_conflict_preservation_keeps_mcp_mutations_disabled(client, tmp_path)
    assert invoked == [
        ("create", "writes_disabled"),
        ("replace", "executable_content_not_allowed"),
    ]
    assert [method for method, _ in requests if method != "GET"] == ["PUT", "PUT"]
    assert "agent-conditional-change" in text
    assert "human-local-change" in text
    for marker in ["<<<<<<< SB", "||||||| SB BASE", "=======", ">>>>>>> SB"]:
        assert marker in text


def test_browser_page_url_preserves_port_separator():
    module = spike()
    with httpx.Client(base_url="http://127.0.0.1:32768") as client:
        assert (
            module._page_url(client, "Inbox/ConcurrencySpike")
            == "http://127.0.0.1:32768/Inbox/ConcurrencySpike"
        )
