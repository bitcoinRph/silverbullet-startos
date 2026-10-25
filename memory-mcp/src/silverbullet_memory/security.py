"""Fail-closed boundaries. Rejection, never executable-content escaping."""

import hashlib
import hmac
import json
import re
import unicodedata
from typing import Any

MAX_BODY = 131072
MAX_NOTE = 65536


def validate_path(path: str, *, create: bool = False) -> str:
    parts = path.split("/")
    if (
        not path
        or len(path) > 512
        or not path.endswith(".md")
        or any(c in path for c in ("%", "\\", ":", "?", "#"))
        or any(unicodedata.category(c).startswith("C") for c in path)
        or any(
            not p
            or p.startswith((".", "_"))
            or p.lower().removesuffix(".md") in {"config", "library"}
            for p in parts
        )
        or (create and parts[0] not in {"Inbox", "Sources"})
    ):
        raise ValueError("path_not_allowed")
    return path


def validate_content(content: str) -> None:
    if len(content.encode("utf-8")) > MAX_NOTE:
        raise ValueError("note_too_large")
    # Intentionally conservative: raw HTML and active URL schemes are not a v1 feature.
    if re.search(
        r"space[- ](?:lua|style)|\$\{|\b(?:query|template)\s*(?:\[|\{|:)|(?:`{3,}|~{3,})\s*(?:query|template)|meta/|<|\b(?:javascript|data|vbscript)\s*:",
        content,
        re.I,
    ):
        raise ValueError("executable_content_not_allowed")


def authenticate(header: str, read: str, write: str) -> str:
    candidate = header.removeprefix("Bearer ") if header.startswith("Bearer ") else ""
    digest = hashlib.sha256(candidate.encode()).digest()
    # Always perform both fixed-length comparisons, even for malformed credentials.
    is_read = hmac.compare_digest(digest, hashlib.sha256(read.encode()).digest())
    is_write = hmac.compare_digest(digest, hashlib.sha256(write.encode()).digest())
    if is_write and candidate:
        return "write"
    if is_read and candidate:
        return "read"
    raise PermissionError("unauthorized")


def bounded_json(raw: bytes) -> Any:
    """Scan byte/depth/aggregate element bounds before allocating a JSON tree."""
    if len(raw) > MAX_BODY:
        raise ValueError("body_too_large")
    stack: list[int] = []
    quoted = escaped = False
    elements = 0
    for char in raw:
        if quoted:
            if escaped:
                escaped = False
            elif char == 92:
                escaped = True
            elif char == 34:
                quoted = False
            continue
        if char == 34:
            quoted = True
        elif char in (91, 123):
            stack.append(1)
            if len(stack) > 16:
                raise ValueError("json_too_deep")
        elif char in (93, 125):
            if not stack:
                raise ValueError("invalid_json")
            stack.pop()
        elif char in (44, 58):
            elements += 1
            if elements > 1024:
                raise ValueError("json_too_many_elements")
            if char == 44 and stack:
                stack[-1] += 1
                if stack[-1] > 256:
                    raise ValueError("json_container_too_large")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result

    return json.loads(
        raw,
        object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid_number")),
    )
