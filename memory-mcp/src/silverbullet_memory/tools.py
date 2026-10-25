"""Six-tool v1 contract. This release cannot mutate upstream, by construction."""

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from .index import MemoryIndex, metadata
from .security import validate_content, validate_path


class MemoryTools:
    def __init__(self, client: Any, index: MemoryIndex, managed_prefixes: tuple[str, ...] = ()):
        self.client = client
        self.index = index
        self.managed_prefixes = managed_prefixes

    def memory_status(self) -> dict[str, Any]:
        return self.index.status()

    def memory_search(
        self,
        query: str,
        limit: int = 5,
        path_prefix: str = "",
        kinds: list[str] | None = None,
        tags: list[str] | None = None,
        updated_after: float | None = None,
        exclude_unreviewed: bool = False,
    ) -> list[dict[str, Any]]:
        return self.index.search(
            query, limit, path_prefix, kinds, tags, updated_after, exclude_unreviewed
        )

    async def memory_get(
        self, path: str, include_content: bool = True, max_chars: int = 8000
    ) -> dict[str, Any]:
        if not 1 <= max_chars <= 16000:
            raise ValueError("result_bounds")
        page = await self.client.get(validate_path(path))
        content = page.pop("content")
        return {
            **page,
            **metadata(content, path),
            "content": content[:max_chars] if include_content else "",
            "truncated": include_content and len(content) > max_chars,
        }

    def memory_backlinks(self, path: str, limit: int = 20) -> list[dict[str, Any]]:
        return self.index.backlinks(path, limit)

    def memory_create(
        self,
        path: str,
        content: str,
        kind: str,
        provenance: dict[str, str],
        idempotency_key: str,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        validate_path(path, create=True)
        validate_content(content)
        if kind not in {"source", "claim", "note", "decision", "entity", "conversation"}:
            raise ValueError("invalid_kind")
        if (
            not 1 <= len(idempotency_key) <= 256
            or not provenance.get("agent_id")
            or not provenance.get("source")
            or not provenance.get("created_at")
        ):
            raise ValueError("provenance_required")
        if (
            any(not isinstance(v, str) or len(v) > 1024 for v in provenance.values())
            or len(provenance) > 16
        ):
            raise ValueError("provenance_bounds")
        datetime.fromisoformat(provenance["created_at"].replace("Z", "+00:00"))
        if set(provenance) - {
            "agent_id",
            "source",
            "created_at",
            "source_url",
            "source_id",
            "session_id",
            "retrieved_at",
        }:
            raise ValueError("provenance_fields")
        identity = hashlib.sha256(idempotency_key.encode()).hexdigest()
        target = path.split("/")[0] + "/" + identity + ".md"
        fields = {
            **provenance,
            "id": "mem_" + identity,
            "kind": kind,
            "status": "inbox",
            "attribution": "self_asserted",
        }
        rendered = (
            "---\n"
            + "\n".join(k + ": " + json.dumps(v) for k, v in sorted(fields.items()))
            + "\n---\n"
            + content
        )
        validate_content(rendered)
        if not dry_run:
            return {
                "error": "writes_disabled",
                "required_gate": "real_image_content_and_concurrency_verification",
            }
        return {
            "path": target,
            "sha256": hashlib.sha256(rendered.encode()).hexdigest(),
            "dry_run": True,
            "conditional_header": "If-None-Match: *",
            "untrusted_content": True,
            "content": rendered,
        }

    async def memory_replace_text(
        self,
        path: str,
        expected_etag: str,
        old_text: str,
        new_text: str,
        reason: str,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        validate_path(path)
        if not any(path.startswith(prefix) for prefix in self.managed_prefixes):
            raise ValueError("path_not_agent_managed")
        if (
            not re.fullmatch(r'"sha256:[0-9a-f]{64}"', expected_etag)
            or not reason.strip()
            or len(reason) > 1024
            or not old_text
        ):
            raise ValueError("replace_preconditions_required")
        page = await self.client.get(path)
        if page["etag"] != expected_etag:
            return {"error": "conflict", "path": path}
        if page["content"].count(old_text) != 1:
            raise ValueError("exact_single_match_required")
        replacement = page["content"].replace(old_text, new_text, 1)
        validate_content(replacement)
        if not dry_run:
            return {
                "error": "writes_disabled",
                "required_gate": "real_client_concurrency_verification",
            }
        return {
            "path": path,
            "expected_etag": expected_etag,
            "dry_run": True,
            "sha256": hashlib.sha256(replacement.encode()).hexdigest(),
            "untrusted_content": True,
            "content": replacement,
        }
