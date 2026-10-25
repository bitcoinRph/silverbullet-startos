import asyncio
import pytest
from test_index import Corpus


def fixture(tmp_path):
    from silverbullet_memory.index import MemoryIndex
    from silverbullet_memory.tools import MemoryTools

    client = Corpus()
    index = MemoryIndex(tmp_path / "memory.sqlite")
    asyncio.run(index.sync(client))
    return MemoryTools(client, index, managed_prefixes=("Inbox/Agent/",)), client, index


def test_read_tools_and_previews(tmp_path):
    tools, corpus, index = fixture(tmp_path)
    assert tools.memory_status()["documents"] == 3
    assert tools.memory_search("bitcoin")
    assert tools.memory_backlinks("Business/B.md")
    assert asyncio.run(tools.memory_get("Business/A.md"))["untrusted_content"] is True
    provenance = {
        "agent_id": "synthetic-agent",
        "source": "user",
        "created_at": "2026-01-01T00:00:00Z",
    }
    first = tools.memory_create("Inbox/a.md", "A harmless note", "note", provenance, "request-1")
    second = tools.memory_create("Inbox/a.md", "A harmless note", "note", provenance, "request-1")
    assert first == second and first["dry_run"] is True
    assert first["path"].startswith("Inbox/") and first["path"].endswith(".md")
    assert first["sha256"]
    assert (
        tools.memory_create("Inbox/a.md", "Safe", "note", provenance, "request-1", dry_run=False)[
            "error"
        ]
        == "writes_disabled"
    )
    assert len(corpus.pages) == 3
    index.close()


def test_replace_exact_etag_path_and_content_gates(tmp_path):
    tools, corpus, index = fixture(tmp_path)
    corpus.pages["Inbox/Agent/a.md"] = "plain note once"
    page = asyncio.run(corpus.get("Inbox/Agent/a.md"))

    async def replace(**kw):
        args = dict(
            path="Inbox/Agent/a.md",
            expected_etag=page["etag"],
            old_text="once",
            new_text="twice",
            reason="User correction",
        )
        args.update(kw)
        return await tools.memory_replace_text(**args)

    assert asyncio.run(replace())["dry_run"] is True
    assert asyncio.run(replace(dry_run=False))["error"] == "writes_disabled"
    assert asyncio.run(replace(expected_etag='"sha256:' + "0" * 64 + '"'))["error"] == "conflict"
    for args in [dict(old_text="absent"), dict(new_text="${1}"), dict(path="Business/A.md")]:
        with pytest.raises(ValueError):
            asyncio.run(replace(**args))
    assert corpus.pages["Inbox/Agent/a.md"] == "plain note once"
    index.close()
