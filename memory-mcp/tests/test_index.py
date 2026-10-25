import asyncio
import hashlib
import sqlite3


class Corpus:
    def __init__(self):
        self.pages = {
            "Business/A.md": "---\nkind: decision\nstatus: canonical\ntags: [business]\n---\n# Alpha\nBitcoin plan [[Business/B]]",
            "Inbox/B.md": "Bitcoin source",
            "Business/B.md": "Bitcoin plan",
        }
        self.failed = set()
        self.reads = 0

    async def inventory(self):
        return [
            {
                "name": p,
                "lastModified": int(hashlib.sha256(c.encode()).hexdigest()[:8], 16),
                "size": len(c),
            }
            for p, c in self.pages.items()
        ]

    async def get(self, path):
        from silverbullet_memory.client import UpstreamError

        self.reads += 1
        if path in self.failed:
            raise UpstreamError("synthetic_failure")
        content = self.pages[path]
        digest = hashlib.sha256(content.encode()).hexdigest()
        return {
            "path": path,
            "content": content,
            "etag": '"sha256:' + digest + '"',
            "sha256": digest,
        }


def test_future_schema_is_rebuilt_not_relabelled(tmp_path):
    from silverbullet_memory.index import MemoryIndex

    path = tmp_path / "future.sqlite"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE pages(unsupported TEXT)")
    db.execute("PRAGMA user_version=99")
    db.commit()
    db.close()
    index = MemoryIndex(path)
    asyncio.run(index.sync(Corpus()))
    assert index.status()["documents"] == 3
    index.close()


def test_failed_rebuild_swap_keeps_previous_database_usable(tmp_path, monkeypatch):
    from silverbullet_memory.index import MemoryIndex

    index = MemoryIndex(tmp_path / "memory.sqlite")
    corpus = Corpus()
    asyncio.run(index.sync(corpus))
    corpus.pages["Business/C.md"] = "new plan"

    def fail(*args):
        raise OSError("synthetic swap failure")

    monkeypatch.setattr("silverbullet_memory.index.os.replace", fail)
    try:
        asyncio.run(index.sync(corpus, rebuild=True))
    except OSError:
        pass
    assert index.status()["stale"]
    assert index.status()["documents"] == 3
    assert index.get("Business/C.md") is None
    index.close()


def test_index_lifecycle(tmp_path):
    from silverbullet_memory.index import MemoryIndex

    corpus = Corpus()
    index = MemoryIndex(tmp_path / "memory.sqlite")
    assert index.status()["ready"] is False
    asyncio.run(index.sync(corpus))
    assert index.status()["ready"] is True
    assert index.status()["documents"] == 3
    reads = corpus.reads
    asyncio.run(index.sync(corpus))
    assert corpus.reads == reads
    corpus.pages["Business/A.md"] += "\nChanged"
    corpus.pages["Sources/C.md"] = "New bitcoin source"
    del corpus.pages["Business/B.md"]
    asyncio.run(index.sync(corpus))
    assert index.status()["documents"] == 3
    assert "Changed" in index.get("Business/A.md")["content"]
    assert index.get("Business/B.md") is None
    corpus.pages["Business/A.md"] += "\nFailed change"
    corpus.failed.add("Business/A.md")
    asyncio.run(index.sync(corpus))
    assert index.status()["stale"] is True
    assert index.search("bitcoin")[0]["index_stale"] is True
    assert "Failed change" not in index.get("Business/A.md")["content"]
    index.close()


def test_search_filters_backlinks_and_bounds(tmp_path):
    from silverbullet_memory.index import MemoryIndex

    index = MemoryIndex(tmp_path / "memory.sqlite")
    asyncio.run(index.sync(Corpus()))
    first = index.search("bitcoin", limit=20)
    assert first == index.search("bitcoin", limit=20)
    assert len(first) == 3
    assert all(x["untrusted_content"] is True for x in first)
    assert all(len(x["snippet"]) <= 500 for x in first)
    assert len(index.search("bitcoin", kinds=["decision"], tags=["business"])) == 1
    assert len(index.search("bitcoin", path_prefix="Business/")) == 2
    assert len(index.search("bitcoin", exclude_unreviewed=True)) == 2
    assert index.backlinks("Business/B.md")[0]["path"] == "Business/A.md"
    assert index.search('" ) OR *') == []
    index.close()


def test_corrupt_database_rebuild_and_atomic_rebuild(tmp_path):
    from silverbullet_memory.index import MemoryIndex

    path = tmp_path / "memory.sqlite"
    path.write_bytes(b"broken")
    index = MemoryIndex(path)
    assert not index.status()["ready"]
    asyncio.run(index.sync(Corpus(), rebuild=True))
    assert index.status()["ready"]
    assert index.status()["documents"] == 3
    index.close()
    index = MemoryIndex(path)
    assert not index.status()["ready"]  # must reauthenticate/reconcile after every process start
    asyncio.run(index.sync(Corpus()))
    assert index.status()["ready"]
    index.close()
