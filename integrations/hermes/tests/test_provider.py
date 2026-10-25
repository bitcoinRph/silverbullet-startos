"""Hermes host edges are synthetic; no live profile/config/secret access."""

import importlib.util
import json
import sys
import threading
import types
from pathlib import Path

import pytest


@pytest.fixture
def provider(monkeypatch, tmp_path):
    # Host ABI harness, not a claim that a live Hermes profile was configured.
    from abc import ABC

    memory = types.ModuleType("agent.memory_provider")
    memory.MemoryProvider = ABC

    def spawn(target, *, name, **kwargs):
        return threading.Thread(target=target, name=name, daemon=True)

    memory.spawn_context_thread = spawn
    monkeypatch.setitem(sys.modules, "agent", types.ModuleType("agent"))
    monkeypatch.setitem(sys.modules, "agent.memory_provider", memory)
    secrets = types.ModuleType("agent.secret_scope")
    secrets.get_secret = lambda name: "synthetic-read-token-0000000000000000"
    monkeypatch.setitem(sys.modules, "agent.secret_scope", secrets)
    constants = types.ModuleType("hermes_constants")
    constants.get_hermes_home = lambda: tmp_path
    monkeypatch.setitem(sys.modules, "hermes_constants", constants)
    utils = types.ModuleType("utils")
    utils.read_json_or_empty = (
        lambda p: json.loads(Path(p).read_text()) if Path(p).exists() else {}
    )
    utils.atomic_json_write = lambda p, data, **kw: Path(p).write_text(json.dumps(data))
    monkeypatch.setitem(sys.modules, "utils", utils)
    root = Path(__file__).parents[1] / "plugins/silverbullet-memory"
    spec = importlib.util.spec_from_file_location(
        "test_sb_provider", root / "__init__.py", submodule_search_locations=[str(root)]
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "test_sb_provider", module)
    spec.loader.exec_module(module)
    obj = module.SilverBulletMemoryProvider()
    obj.save_config(
        {
            "endpoint": "https://memory.example/mcp",
            "token_env": "SILVERBULLET_READ_TOKEN",
        },
        str(tmp_path),
    )
    return obj, module, tmp_path


def test_contract_registration_local_availability_and_config(provider, monkeypatch):
    obj, module, home = provider
    monkeypatch.setattr(
        module.MemoryClient,
        "search",
        lambda *a, **kw: pytest.fail("network during availability"),
    )
    assert obj.is_available()
    assert obj.get_config_schema()
    obj.initialize("session", hermes_home=str(home), agent_context="cron")
    assert obj.agent_context == "cron"
    assert obj.get_tool_schemas() == []
    assert (
        json.loads(obj.handle_tool_call("memory_get", {}))["error"]
        == "no_provider_tools"
    )
    found = []
    module.register(types.SimpleNamespace(register_memory_provider=found.append))
    module.register(types.SimpleNamespace(register_memory_provider=found.append))
    assert found[0] is not found[1]
    assert "synthetic-read-token" not in (home / "silverbullet-memory.json").read_text()
    with pytest.raises(ValueError):
        obj.save_config(
            {"endpoint": "https://memory.example/mcp?token=bad", "token_env": "TOKEN"},
            str(home),
        )
    with pytest.raises(ValueError):
        obj.save_config(
            {
                "endpoint": "https://memory.example/mcp",
                "token_env": "TOKEN",
                "token": "secret",
            },
            str(home),
        )
    obj.shutdown()


def test_cache_expiry_refreshes_same_query(provider, monkeypatch):
    obj, module, home = provider
    calls = []
    clock = [10.0]
    monkeypatch.setattr(
        module, "time", types.SimpleNamespace(monotonic=lambda: clock[0]), raising=False
    )
    monkeypatch.setattr(
        module.MemoryClient, "search", lambda self, query: calls.append(query) or []
    )
    obj.initialize("session", hermes_home=str(home))
    obj.queue_prefetch("same")
    obj._worker.join(timeout=2)
    clock[0] = 30.0
    obj.prefetch("same")
    obj._worker.join(timeout=2)
    assert calls == ["same", "same"]
    obj.shutdown()


def test_bounded_background_prefetch_fail_soft_no_writes(provider, monkeypatch):
    obj, module, home = provider
    calls = []

    def search(self, query):
        calls.append(query)
        return [
            {
                "path": "Business/a.md",
                "snippet": "x" * 10000,
                "kind": "note",
                "status": "canonical",
                "untrusted_content": True,
            },
            {
                "path": "Inbox/a.md",
                "snippet": "untrusted inbox",
                "kind": "source",
                "status": "inbox",
            },
        ]

    monkeypatch.setattr(module.MemoryClient, "search", search)
    obj.initialize("session", hermes_home=str(home), agent_context="primary")
    obj.queue_prefetch("bitcoin plan")
    obj._worker.join(timeout=2)
    result = obj.prefetch("bitcoin plan")
    assert (
        len(result) <= 4000
        and "Business/a.md" in result
        and "untrusted inbox" not in result
    )
    assert "UNTRUSTED" in result
    obj.sync_turn("private user text", "private assistant text")
    obj.on_pre_compress([])
    assert len(calls) == 1
    monkeypatch.setattr(
        module.MemoryClient,
        "search",
        lambda *a: (_ for _ in ()).throw(OSError("sensitive-error-marker")),
    )
    obj.queue_prefetch("outage")
    obj._worker.join(timeout=2)
    assert obj.prefetch("outage") == "[SilverBullet memory unavailable]"
    obj.shutdown()
