"""Disposable FTS5 index. All returned text is data, never agent instructions."""

import html
import json
import os
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .client import PermanentPageError, UpstreamError
from .security import validate_path


def metadata(content: str, path: str) -> dict[str, Any]:
    # Deliberately parse only v1 scalar/list metadata, not YAML objects or aliases.
    front = (
        content.split("---", 2)[1][:4096]
        if content.startswith("---\n") and content.count("---") >= 2
        else ""
    )

    def scalar(key: str, default: str = "") -> str:
        match = re.search(r"^" + key + r":\s*([^\n]+)", front, re.M)
        return match[1].strip().strip("\"'")[:256] if match else default

    tags = re.findall(r"[\w/-]+", scalar("tags"))[:32]
    return {
        "id": scalar("id", path),
        "kind": scalar("kind", "source" if path.startswith("Sources/") else "note"),
        "status": scalar(
            "status", "inbox" if path.startswith(("Inbox/", "Sources/")) else "reviewed"
        ),
        "tags": tags,
        "source_url": scalar("source_url"),
        "source_id": scalar("source_id"),
        "agent_id": scalar("agent_id"),
        "attribution": "self_asserted",
        "untrusted_content": True,
    }


class MemoryIndex:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.ready = False
        self.stale = True
        self.last_sync: str | None = None
        try:
            self.db = self._open(path)
            if self.db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError()
            if self.db.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise sqlite3.DatabaseError()
        except sqlite3.DatabaseError:
            if hasattr(self, "db"):
                self.db.close()
            for suffix in ("", "-wal", "-shm"):
                Path(str(path) + suffix).unlink(missing_ok=True)
            self.db = self._open(path)

    @staticmethod
    def _open(path: Path) -> sqlite3.Connection:
        db = sqlite3.connect(path, timeout=3)
        db.row_factory = sqlite3.Row
        try:
            if db.execute("PRAGMA user_version").fetchone()[0] not in (0, 1):
                raise sqlite3.DatabaseError("unsupported_derived_schema")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA busy_timeout=3000")
            db.execute(
                "CREATE TABLE IF NOT EXISTS pages(path TEXT PRIMARY KEY, content TEXT, etag TEXT, sha256 TEXT, stamp TEXT, meta TEXT, links TEXT, updated REAL)"
            )
            db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(path, title, tags, body)")
            db.execute(
                "CREATE TABLE IF NOT EXISTS skipped(path TEXT PRIMARY KEY, stamp TEXT, reason TEXT)"
            )
            if [r[1] for r in db.execute("PRAGMA table_info(pages)")] != [
                "path",
                "content",
                "etag",
                "sha256",
                "stamp",
                "meta",
                "links",
                "updated",
            ]:
                raise sqlite3.DatabaseError("invalid_derived_schema")
            db.execute("PRAGMA user_version=1")
            db.commit()
            return db
        except Exception:
            db.close()
            raise

    def status(self) -> dict[str, Any]:
        return {
            "ready": self.ready and not self.stale,
            "stale": self.stale,
            "last_complete_sync": self.last_sync,
            "documents": self.db.execute("SELECT COUNT(*) FROM pages").fetchone()[0],
            "skipped": self.db.execute("SELECT COUNT(*) FROM skipped").fetchone()[0],
            "skipped_details": [
                {"path": row["path"][:512], "reason": row["reason"]}
                for row in self.db.execute(
                    "SELECT path, reason FROM skipped ORDER BY path LIMIT 10"
                )
            ],
            "upstream_version": "2.12.1",
            "package_version": "2.12.1:2",
            "writes_enabled": False,
            "degraded_capabilities": ["mutations_disabled_pending_real_client_gates"],
        }

    async def sync(self, client: Any, *, rebuild: bool = False) -> None:
        # Unknown failures must never leave a previously ready index marked current.
        self.stale = True
        try:
            inventory = await client.inventory()
        except UpstreamError:
            self.stale = True
            return
        existing = {r["path"]: dict(r) for r in self.db.execute("SELECT * FROM pages")}
        rejected = {r["path"]: dict(r) for r in self.db.execute("SELECT * FROM skipped")}
        skipped: dict[str, Any] = {}
        rows: dict[str, Any] = {}
        failed = False
        for entry in inventory:
            path = entry["name"]
            try:
                validate_path(path)
            except ValueError:
                continue
            stamp = json.dumps([entry["lastModified"], entry.get("size")])
            if not rebuild and path in rejected and rejected[path]["stamp"] == stamp:
                skipped[path] = rejected[path]
                continue
            if not rebuild and path in existing and existing[path]["stamp"] == stamp:
                rows[path] = existing[path]
                continue
            try:
                page = await client.get(path)
                meta = metadata(page["content"], path)
                links = sorted(set(re.findall(r"\[\[([^\]|#]+)(?:[^\]]*)\]\]", page["content"])))[
                    :1024
                ]
                rows[path] = dict(
                    page,
                    stamp=stamp,
                    meta=json.dumps(meta),
                    links=json.dumps(links),
                    updated=entry["lastModified"],
                )
            except PermanentPageError as error:
                skipped[path] = {"path": path, "stamp": stamp, "reason": str(error)}
                # Never serve old text after a permanent rejection, even if another
                # page or the later rebuild swap fails. This state is disposable.
                with self.db:
                    self.db.execute("DELETE FROM pages WHERE path=?", (path,))
                    self.db.execute("DELETE FROM fts WHERE path=?", (path,))
                    self.db.execute(
                        "INSERT OR REPLACE INTO skipped VALUES(?,?,?)", (path, stamp, str(error))
                    )
            except (UpstreamError, ValueError):
                failed = True
                if path in existing:
                    rows[path] = existing[path]
        if rebuild and failed:
            self.stale = True
            return
        # Complete inventory controls deletion; only transient reads retain old entries.
        target = self.path
        if rebuild:
            fd, name = tempfile.mkstemp(prefix=".memory-rebuild-", dir=self.path.parent)
            os.close(fd)
            target = Path(name)
        db = self._open(target) if rebuild else self.db
        try:
            with db:
                db.execute("DELETE FROM pages")
                db.execute("DELETE FROM fts")
                db.execute("DELETE FROM skipped")
                db.executemany(
                    "INSERT INTO skipped VALUES(?,?,?)",
                    [(p, row["stamp"], row["reason"]) for p, row in sorted(skipped.items())],
                )
                for path, row in sorted(rows.items()):
                    db.execute(
                        "INSERT INTO pages VALUES(?,?,?,?,?,?,?,?)",
                        tuple(
                            row[k]
                            for k in (
                                "path",
                                "content",
                                "etag",
                                "sha256",
                                "stamp",
                                "meta",
                                "links",
                                "updated",
                            )
                        ),
                    )
                    meta = json.loads(row["meta"])
                    title = (
                        path.removesuffix(".md")
                        + "\n"
                        + "\n".join(re.findall(r"^#+ (.+)", row["content"], re.M))
                    )
                    db.execute(
                        "INSERT INTO fts VALUES(?,?,?,?)",
                        (path, title, " ".join(meta["tags"]), row["content"]),
                    )
            if rebuild:
                assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                db.close()
                self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self.db.close()
                try:
                    os.replace(target, self.path)
                finally:
                    self.db = self._open(self.path)
        except Exception:
            self.stale = True
            raise
        finally:
            if rebuild:
                db.close()
                for suffix in ("", "-wal", "-shm"):
                    Path(str(target) + suffix).unlink(missing_ok=True)
        self.stale = failed
        if not failed:
            self.ready = True
            self.last_sync = datetime.now(timezone.utc).isoformat()

    def get(self, path: str) -> dict[str, Any] | None:
        validate_path(path)
        row = self.db.execute("SELECT * FROM pages WHERE path=?", (path,)).fetchone()
        if row is None:
            return None
        return {
            "path": path,
            "content": row["content"],
            "etag": row["etag"],
            "sha256": row["sha256"],
            **json.loads(row["meta"]),
        }

    def search(
        self,
        query: str,
        limit: int = 5,
        path_prefix: str = "",
        kinds: list[str] | None = None,
        tags: list[str] | None = None,
        updated_after: float | None = None,
        exclude_unreviewed: bool = False,
    ) -> list[dict[str, Any]]:
        if len(query) > 256 or not 1 <= limit <= 20:
            raise ValueError("search_bounds")
        words = re.findall(r"\w+", query)[:32]
        if not words:
            return []
        match = " AND ".join('"' + w + '"' for w in words)
        # Metadata predicates are applied in SQL before LIMIT, not post-filtered top-k.
        sql = """SELECT p.*, snippet(fts,3,'','', '…',40) AS snippet
                 FROM fts JOIN pages p ON p.path=fts.path WHERE fts MATCH ?
                 AND substr(p.path,1,length(?))=?"""
        values: list[Any] = [match, path_prefix, path_prefix]
        if kinds:
            sql += " AND json_extract(p.meta,'$.kind') IN (" + ",".join("?" for _ in kinds) + ")"
            values.extend(kinds)
        for tag in tags or []:
            sql += " AND EXISTS (SELECT 1 FROM json_each(p.meta,'$.tags') WHERE value=?)"
            values.append(tag)
        if updated_after is not None:
            sql += " AND p.updated>?"
            values.append(updated_after)
        if exclude_unreviewed:
            sql += " AND p.path NOT LIKE 'Inbox/%' AND p.path NOT LIKE 'Sources/%' AND json_extract(p.meta,'$.status')!='inbox' AND json_extract(p.meta,'$.kind')!='source'"
        sql += " ORDER BY bm25(fts,0,5,3,1), p.path LIMIT ?"
        values.append(limit)
        return [
            {
                "path": r["path"],
                "etag": r["etag"],
                "sha256": r["sha256"],
                "snippet": html.escape(r["snippet"])[:500],
                "index_stale": self.stale,
                "last_complete_sync": self.last_sync,
                **json.loads(r["meta"]),
            }
            for r in self.db.execute(sql, values)
        ]

    def backlinks(self, path: str, limit: int = 20) -> list[dict[str, Any]]:
        validate_path(path)
        if not 1 <= limit <= 20:
            raise ValueError("result_bounds")
        return [
            {"path": r["path"], "untrusted_content": True, "index_stale": self.stale}
            for r in self.db.execute(
                "SELECT path FROM pages WHERE EXISTS (SELECT 1 FROM json_each(pages.links) WHERE value IN (?,?)) ORDER BY path LIMIT ?",
                (path, path.removesuffix(".md"), limit),
            )
        ]

    def close(self) -> None:
        self.db.close()
