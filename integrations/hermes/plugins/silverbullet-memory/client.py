"""Read-only stateless MCP client; stdlib only, no implicit proxy/redirect forwarding."""

import json
import time
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class MemoryClient:
    def __init__(self, endpoint, token):
        self.endpoint = endpoint
        self._token = token
        self._opener = build_opener(ProxyHandler({}), NoRedirect())

    def search(self, query):
        deadline = time.monotonic() + 2
        headers = {
            "Authorization": "Bearer " + self._token,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }

        def post(payload, notification=False):
            request = Request(
                self.endpoint,
                data=json.dumps(payload).encode(),
                headers=headers,
                method="POST",
            )
            with self._opener.open(
                request, timeout=max(0.05, deadline - time.monotonic())
            ) as response:
                raw = response.read(65537)
                if len(raw) > 65536:
                    raise ValueError("response_bounds")
                return None if notification else json.loads(raw)

        init = post(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "silverbullet-memory-hermes",
                        "version": "0.1.0",
                    },
                },
            }
        )
        if not init or "error" in init:
            raise ValueError("initialization_failed")
        headers["MCP-Protocol-Version"] = init["result"]["protocolVersion"]
        post(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}, notification=True
        )
        result = post(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "memory_search",
                    "arguments": {
                        "query": query[:256],
                        "limit": 5,
                        "exclude_unreviewed": True,
                    },
                },
            }
        )
        if not result or "error" in result or result.get("result", {}).get("isError"):
            raise ValueError("search_unavailable")
        # Official SDK structured output wraps list results under result.
        tool = result["result"]
        structured = tool.get("structuredContent")
        if structured is not None:
            return (
                structured.get("result", [])
                if isinstance(structured, dict)
                else structured
            )
        text = next(c["text"] for c in tool["content"] if c.get("type") == "text")
        value = json.loads(text)
        return value.get("result", []) if isinstance(value, dict) else value
