"""Only the authenticated /.fs read API; redirects and arbitrary endpoints are forbidden."""

import hashlib
import json
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from .security import MAX_NOTE, validate_path


class UpstreamError(Exception):
    pass


class PermanentPageError(UpstreamError):
    """Bounded content cannot be indexed; retry only when its inventory stamp changes."""


class SilverBulletClient:
    def __init__(self, base_url: str, token: str, http: httpx.AsyncClient):
        url = urlsplit(base_url)
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in ("", "/")
        ):
            raise ValueError("invalid_upstream_url")
        self.base = base_url.rstrip("/")
        self.headers = {"Authorization": "Bearer " + token, "X-Sync-Mode": "true"}
        self.http = http

    async def _get(
        self, suffix: str, limit: int, *, page: bool = False
    ) -> tuple[bytes, httpx.Headers]:
        try:
            async with self.http.stream(
                "GET",
                self.base + "/.fs" + suffix,
                headers=self.headers,
                follow_redirects=False,
                timeout=10,
            ) as response:
                if response.status_code != 200:
                    raise UpstreamError("upstream_http_" + str(response.status_code))
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > limit:
                        if page:
                            raise PermanentPageError("page_too_large")
                        raise UpstreamError("upstream_response_too_large")
                return bytes(body), response.headers
        except httpx.HTTPError:
            raise UpstreamError("upstream_unavailable") from None

    async def inventory(self) -> list[dict[str, Any]]:
        raw, _ = await self._get("", 8 * 1024 * 1024)
        try:
            result = json.loads(raw)
            if not isinstance(result, list) or len(result) > 50000:
                raise ValueError()
            if any(
                not isinstance(row, dict)
                or not isinstance(row.get("name"), str)
                or not isinstance(row.get("lastModified"), (int, float))
                for row in result
            ):
                raise ValueError()
            return result
        except (ValueError, RecursionError):
            raise UpstreamError("invalid_inventory") from None

    async def get(self, path: str) -> dict[str, Any]:
        validate_path(path)
        raw, headers = await self._get("/" + quote(path, safe="/"), MAX_NOTE, page=True)
        digest = hashlib.sha256(raw).hexdigest()
        etag = headers.get("etag", "")
        if etag != '"sha256:' + digest + '"':
            raise UpstreamError("invalid_etag")
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise PermanentPageError("invalid_markdown_encoding") from None
        return {"path": path, "content": content, "etag": etag, "sha256": digest}
