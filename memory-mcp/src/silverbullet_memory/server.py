"""Stateless MCP over real Streamable HTTP with bounds ahead of JSON parsing."""

import asyncio
import errno
import json
import logging
import os
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager, suppress
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .client import SilverBulletClient
from .index import MemoryIndex
from .security import MAX_BODY, authenticate, bounded_json
from .tools import MemoryTools

LOG = logging.getLogger("memory.audit")
WRITES = {"memory_create", "memory_replace_text"}
POLL_SECONDS = 15
REBUILD_RETRY_INITIAL_SECONDS = 30
REBUILD_RETRY_MAX_SECONDS = 15 * 60
REBUILD_RETRY_MAX_ATTEMPT = 6


def _read_rebuild_marker(pending: Path) -> bytes:
    with pending.open("rb") as file:
        raw = file.read(257)
    if len(raw) > 256:
        raise ValueError("rebuild_marker_too_large")
    return raw


def _rebuild_retry_delay(attempt: int) -> int:
    return min(REBUILD_RETRY_INITIAL_SECONDS * 2 ** (attempt - 1), REBUILD_RETRY_MAX_SECONDS)


def _load_rebuild_retry(pending: Path) -> tuple[int, float]:
    """Untrusted disposable state: invalid/legacy data permits one immediate retry."""
    try:
        state = bounded_json(_read_rebuild_marker(pending))
        if not isinstance(state, dict):
            return 0, 0.0
        version, attempt = state.get("version"), state.get("attempt")
        if (
            type(version) is not int
            or version not in (1, 2)
            or type(attempt) is not int
            or not 1 <= attempt <= REBUILD_RETRY_MAX_ATTEMPT
        ):
            return 0, 0.0
        if version == 2 and state.get("phase") == "in_progress":
            if set(state) != {"version", "phase", "attempt"}:
                return 0, 0.0
            # The interrupted attempt has already been counted. Start its wait now,
            # not at attempt start: a long rebuild must not spend its own retry wait.
            delay = _rebuild_retry_delay(attempt)
            retry_at = time.monotonic() + delay
            try:
                _persist_rebuild_retry(pending, attempt, delay)
            except Exception:
                LOG.warning("rebuild_retry_persist_failed")
            return attempt, retry_at
        keys = {"version", "attempt", "retry_at"}
        if version == 2:
            keys.add("phase")
            if state.get("phase") != "waiting":
                return 0, 0.0
        if set(state) != keys:
            return 0, 0.0
        deadline = state["retry_at"]
        if (
            type(deadline) not in (int, float)
            # Also rejects NaN/infinity; year 9999 is the largest accepted wall deadline.
            or not 0 <= deadline <= 253402300799
        ):
            return 0, 0.0
        remaining = max(0.0, min(deadline - time.time(), REBUILD_RETRY_MAX_SECONDS))
        return attempt, time.monotonic() + remaining
    except (OSError, ValueError, UnicodeError):
        return 0, 0.0


def _persist_rebuild_retry(pending: Path, attempt: int, delay: int) -> None:
    _persist_rebuild_state(
        pending,
        {"version": 2, "phase": "waiting", "attempt": attempt, "retry_at": time.time() + delay},
    )


def _persist_rebuild_state(pending: Path, state: dict[str, Any]) -> None:
    _replace_rebuild_marker(
        pending, json.dumps(state, allow_nan=False, separators=(",", ":")).encode("utf-8")
    )


def _replace_rebuild_marker(pending: Path, raw: bytes) -> None:
    """Replace only the claim, never a concurrent rebuild-request; no failure text."""
    temporary = pending.with_name(f".{pending.name}-{uuid.uuid4().hex}.tmp")
    try:
        with os.fdopen(
            os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
        ) as file:
            file.write(raw)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, pending)
        directory = os.open(pending.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            try:
                os.fsync(directory)
            except OSError as error:
                if error.errno not in (errno.EINVAL, errno.ENOTSUP):
                    raise
        finally:
            os.close(directory)
    finally:
        with suppress(FileNotFoundError):
            temporary.unlink()


class Boundary:
    def __init__(self, app: ASGIApp, read: str, write: str, hosts: list[str], origins: list[str]):
        self.app, self.read, self.write = app, read, write
        self.hosts, self.origins = hosts, origins
        self.windows: dict[str, deque[float]] = {s: deque() for s in ("auth", "read", "write")}
        self.concurrent = asyncio.Semaphore(8)

    def permitted(self, scope: str, limit: int) -> bool:
        queue = self.windows[scope]
        now = time.monotonic()
        while queue and queue[0] < now - 60:
            queue.popleft()
        if len(queue) >= limit:
            return False
        queue.append(now)
        return True

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in ("/health/live", "/health/ready"):
            await self.app(scope, receive, send)
            return

        async def error(status: int, code: str) -> None:
            await JSONResponse({"error": code}, status_code=status)(scope, receive, send)

        request = Request(scope, receive)
        if any(
            len(request.headers.getlist(h)) > 1
            for h in ("authorization", "host", "origin", "content-length", "content-type")
        ):
            await error(400, "duplicate_header")
            return
        try:
            role = authenticate(request.headers.get("authorization", ""), self.read, self.write)
            if scope.get("query_string"):
                raise PermissionError()
        except PermissionError:
            await error(401 if self.permitted("auth", 60) else 429, "unauthorized")
            return
        if not any(fnmatchcase(request.headers.get("host", ""), h) for h in self.hosts) or (
            "origin" in request.headers and request.headers["origin"] not in self.origins
        ):
            await error(403, "origin_or_host_not_allowed")
            return
        if not self.permitted(role, 120):
            await error(429, "rate_limited")
            return
        raw = bytearray()
        tool = ""
        if request.method == "POST":
            try:
                if int(request.headers.get("content-length", "0")) > MAX_BODY:
                    await error(413, "body_too_large")
                    return
                async with asyncio.timeout(5):
                    async for chunk in request.stream():
                        raw.extend(chunk)
                        if len(raw) > MAX_BODY:
                            await error(413, "body_too_large")
                            return
                data = bounded_json(bytes(raw))
                if not isinstance(data, dict):
                    raise ValueError()
            except TimeoutError:
                await error(408, "body_timeout")
                return
            except (ValueError, UnicodeError):
                await error(400, "invalid_bounded_json")
                return
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                await error(415, "application_json_required")
                return
            if data.get("method") == "tools/call":
                params = data.get("params")
                if not isinstance(params, dict) or not isinstance(params.get("name"), str):
                    await error(400, "invalid_tool_call")
                    return
                tool = params["name"]
                if tool in WRITES and role != "write":
                    await error(403, "write_scope_required")
                    return
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered and request.method == "POST":
                delivered = True
                return {"type": "http.request", "body": bytes(raw), "more_body": False}
            return await receive()

        request_id = uuid.uuid4().hex
        # Tool names are allowlisted before logging; never log supplied identifiers or arguments.
        safe_tool = (
            tool
            if tool in WRITES | {"memory_status", "memory_search", "memory_get", "memory_backlinks"}
            else "protocol"
        )
        status = 500

        async def track(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            async with asyncio.timeout(20):
                async with self.concurrent:
                    await self.app(scope, replay, track)
        finally:
            LOG.info("request=%s tool=%s scope=%s status=%s", request_id, safe_tool, role, status)


def create_app(
    tools: MemoryTools,
    read: str,
    write: str,
    hosts: list[str],
    origins: list[str],
    *,
    poll: bool = False,
) -> ASGIApp:
    if len(read) < 32 or len(write) < 32 or read == write or not hosts:
        raise ValueError("invalid_mcp_configuration")
    mcp = FastMCP(
        "SilverBullet Business Memory",
        stateless_http=True,
        json_response=True,
        max_request_body_size=MAX_BODY,
        log_level="ERROR",
        transport_security=TransportSecuritySettings(allowed_hosts=hosts, allowed_origins=origins),
    )
    for name in (
        "memory_status",
        "memory_search",
        "memory_get",
        "memory_backlinks",
        "memory_create",
        "memory_replace_text",
    ):
        mcp.tool(name=name)(getattr(tools, name))

    @mcp.custom_route("/health/live", methods=["GET"])
    async def live(request: Request) -> JSONResponse:
        return JSONResponse({"live": True})

    @mcp.custom_route("/health/ready", methods=["GET"])
    async def ready(request: Request) -> JSONResponse:
        status = tools.memory_status()
        return JSONResponse(
            {"ready": status["ready"], "stale": status["stale"], "documents": status["documents"]},
            status_code=200 if status["ready"] else 503,
        )

    app = mcp.streamable_http_app()
    original = app.router.lifespan_context

    async def poll_index() -> None:
        marker = tools.index.path.parent / "rebuild-request"
        pending = marker.with_name("rebuild-in-progress")
        retry_at = 0.0
        retry_attempt = 0
        retry_loaded = False
        while True:
            rebuild = attempted = False
            try:
                # Atomic claim: a new request published during this attempt stays
                # at marker and is never deleted by completion of the old work.
                if not os.path.lexists(pending):
                    with suppress(FileNotFoundError):
                        marker.rename(pending)
                rebuild = os.path.lexists(pending)
                if rebuild and not retry_loaded:
                    retry_attempt, retry_at = _load_rebuild_retry(pending)
                    retry_loaded = True
                if rebuild and time.monotonic() < retry_at:
                    # Do not let an incremental sync clear stale while claimed work waits.
                    tools.index.stale = True
                else:
                    attempted = True
                    prior = None
                    if rebuild:
                        retry_attempt = min(retry_attempt + 1, REBUILD_RETRY_MAX_ATTEMPT)
                        try:
                            # Retain exact bounded prior bytes for graceful cancellation.
                            # If capture/publication fails, keep ownership and still try sync.
                            prior = _read_rebuild_marker(pending)
                            _persist_rebuild_state(
                                pending,
                                {"version": 2, "phase": "in_progress", "attempt": retry_attempt},
                            )
                        except Exception:
                            LOG.warning("rebuild_retry_persist_failed")
                    try:
                        await tools.index.sync(tools.client, rebuild=rebuild)
                    except asyncio.CancelledError:
                        if rebuild and prior is not None:
                            try:
                                _replace_rebuild_marker(pending, prior)
                            except Exception:
                                # Keep the claim: an unrestored in-progress record receives
                                # a bounded interrupted-attempt wait on the next process.
                                LOG.warning("rebuild_retry_restore_failed")
                        raise
                    if rebuild and not tools.index.stale:
                        pending.unlink()
                        retry_at = 0.0
                        retry_attempt = 0
                        retry_loaded = False
            except Exception:
                tools.index.stale = True
                LOG.warning("index_sync_failed")
            if rebuild and attempted and tools.index.stale:
                retry_delay = _rebuild_retry_delay(retry_attempt)
                # Normal failure waits start after sync, even if write-ahead failed.
                retry_at = time.monotonic() + retry_delay
                try:
                    _persist_rebuild_retry(pending, retry_attempt, retry_delay)
                except Exception:
                    LOG.warning("rebuild_retry_persist_failed")
            await asyncio.sleep(POLL_SECONDS)

    @asynccontextmanager
    async def lifespan(application: Any):
        async with original(application):
            task = asyncio.create_task(poll_index()) if poll else None
            try:
                yield
            finally:
                if task:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task

    app.router.lifespan_context = lifespan
    return Boundary(app, read, write, hosts, origins)


async def serve() -> None:
    index = MemoryIndex(Path(os.environ["MEMORY_INDEX"]))
    async with httpx.AsyncClient(trust_env=False, limits=httpx.Limits(max_connections=8)) as http:
        client = SilverBulletClient(os.environ["SB_BASE_URL"], os.environ["SB_API_TOKEN"], http)
        app = create_app(
            MemoryTools(client, index),
            os.environ["MCP_READ_TOKEN"],
            os.environ["MCP_WRITE_TOKEN"],
            json.loads(os.environ["MCP_ALLOWED_HOSTS"]),
            json.loads(os.environ["MCP_ALLOWED_ORIGINS"]),
            poll=True,
        )
        try:
            await uvicorn.Server(
                uvicorn.Config(
                    app, host="0.0.0.0", port=3001, access_log=False, log_level="warning"
                )
            ).serve()
        finally:
            index.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(serve())
