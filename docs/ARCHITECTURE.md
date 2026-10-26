# Business Memory architecture and v1 security decision

Upstream SilverBullet 2.12.1 remains canonical. Wrapper ExVer 2.12.1:4 fixes the
same-package sidecar using documented StartOS SDK 1.5.3 loopback/dependency patterns.
The image context is memory-mcp/, not the repository root. Both images declare
x86_64 and aarch64. Actual image/package execution is an independent CI gate.

## Trust boundaries

- StartOS administrator: controls API opt-in, exact Host/Origin allowlists, tokens,
  backup/restore and index rebuild. Agent API is off on first install/update.
- SilverBullet UI writers: code-trusted. Space Lua on any page can execute globally.
- MCP callers: bearer read or write scope, fixed-length SHA-256 constant-time token
  comparisons. Both comparisons always run. No query-string credentials; in fact all
  query strings on MCP are rejected. Tokens have 48 generated alphanumeric characters.
- Sidecar: holds a full-space internal bearer token. That token is never returned by
  actions, but SilverBullet accepts it on the existing UI HTTP interface when enabled;
  this is not a network-isolated upstream credential. Runtime API is always off.
- Retrieved notes: untrusted data; provenance is self-asserted, never authenticated
  per-agent attribution. No per-page ACLs. Shared tokens permit only coarse revocation.

## Read-only release downgrade (binding audit stop condition)

Actual mutations remain hard-disabled by v1 policy, including for write-token callers.
Exact-image/browser and unsaved-editor concurrency checks must run on the final SHA
in CI. The upstream client has no PUT or DELETE methods;
no runtime configuration can turn mutations on. This is a deliberate v1 read-only
release, not a claim that the original full-write plan is complete.

The six tools remain exactly memory_status, memory_search, memory_get,
memory_backlinks, memory_create and memory_replace_text. The write scope permits
create previews. Replacement is refused by default (empty managed-prefix tuple);
its exact-single-match/ETag/content preview implementation is exercised with an
explicit synthetic prefix in unit tests. Every tool has an agent-readable description.
Both mutation descriptions explicitly say preview/fail-closed only and writes disabled
in v1. A non-dry-run call raises a FastMCP ToolError with writes_disabled, conveyed as
MCP isError=true. Replacement checks this before path/managed-prefix checks or reads;
dry-run still validates the existing managed-prefix policy and cannot write.
There is no Runtime API, fetch URL, SQL, Lua, shell, reindex or delete tool.

Create paths must be Markdown in Inbox/ or Sources/. The effective target is
namespace/SHA256(idempotency_key).md. Generated frontmatter is stable for identical
inputs; timestamp/provenance must remain fixed across retries. A future reviewed
write release must use If-None-Match: * and compare actual stored content hash after
412, never a durable idempotency table or read-compare-write. Replacement must use
If-Match and be restricted to explicit operator-managed prefixes. Neither conditional
mutation nor idempotent upstream retry is claimed to work in this read-only release.

Path gates reject absolute/traversal/hidden/underscore/CONFIG/Library/non-Markdown,
control characters, percent encodings and backslashes before upstream calls.
Content gates reject Space Lua/style, ${ expressions, query/template directives,
meta/ executable metadata, all raw HTML and active data/javascript/vbscript schemes.
This is deliberately over-restrictive; a regex gate is not real-client execution
proof. Raw HTML is not a supported agent-write format.

## Transport and resource bounds

Official MCP Python SDK 1.30.0 FastMCP, stateless Streamable HTTP, JSON responses,
no session state. Middleware caps bytes (128 KiB), depth (16), container elements
(256) and aggregate separators (1024) before JSON parsing. Duplicate keys and
nonfinite constants are rejected. POSTs require application/json. Exact Origin
and configured Host checks precede dispatch; no Origin is permitted for nonbrowser
clients. StartOS proxy header observations are an unverified deployment gate.

Body read timeout 5 seconds, request timeout 20 seconds, 8 concurrent handlers,
120 authenticated requests per scope per minute and 60 failed auth responses before
429. These global windows are bounded and intentionally simple; a hostile client can
consume a shared quota. Failures do not log credentials/content. Audit records carry
only generated request ID, allowlisted tool, scope and HTTP outcome. MCP tool errors
can be conveyed as HTTP 200 by protocol convention; audit HTTP outcome is not a
complete business-level audit trail. Uvicorn access logging is disabled.

Upstream reads are streaming and capped at 64 KiB per note and 8 MiB/50,000 listing
entries, 10-second operation timeouts, redirects disabled. No server-side URL fetch.
Oversized pages and invalid UTF-8 are permanent per-page rejections: skip them and
report a bounded status summary, without disabling readiness for readable pages.
An inconsistent SHA-256 ETag stays transient, not skipped: it can reflect a concurrent
or inconsistent upstream response, and must be retried. Search is bounded
20 results, 500 escaped characters each; get is capped at 16,000 characters. Index
metadata parsing deliberately supports flat v1 scalars and inline tags, not all YAML.

Non-root MCP UID/GID 10001 with graceful termination. A root initialization chown
prepares only the index volume root; the daemon never mounts main. SDK 1.5.3 does
not support read-only-rootfs or package CPU/memory controls; no such claim is made.

## Derived index

A dedicated excluded-from-backup index volume holds SQLite FTS5/WAL with a busy
 timeout and schema version. Poll inventory every 15 seconds; fetch changed Markdown
only. Keep a transient failed read's previous entry and mark stale. Reconcile deletion only
from a successful complete inventory. Check integrity on open and rebuild corruption.
Permanent rejections delete previously indexed content immediately (including during
a later failed rebuild); persisted path/stamp/reason records avoid refetching unchanged
rejected pages. They are retried on stamp change or explicit rebuild and removed on
deletion. memory_status reports the total skipped count and at most ten path/reason
details (512 characters per path), never page bodies. Unknown exceptions fail closed.
Operator actions publish rebuild-request using temp-file/fsync/rename. The poller
atomically claims it as rebuild-in-progress; a concurrent new request remains untouched.
Failed claimed rebuilds retain work and retry after 30, 60, 120, 240, 480, then 900
seconds, capped at 15 minutes. The monotonic deadline starts after each failed attempt;
15-second polls before it do no inventory/page reads and keep the index stale/fail-closed.
No incremental sync can clear stale while the requested rebuild is incomplete. Success
resets backoff and the next poll may claim a concurrent new request. Only claimed-rebuild
retry state is persisted, in the existing internal rebuild-in-progress marker on the
rebuildable index volume. Before each claimed full rebuild, atomic write-ahead publishes
exactly version=2, phase="in_progress", attempt (integer 1..6, saturated at 6).
On fresh-process recovery, that interrupted attempt is counted as failed, with its
derived 30..900-second delay starting at recovery, not attempt start. Recovery atomically
publishes the waiting deadline so further restarts preserve the same wait. Waiting
records have exactly version=2, phase="waiting", attempt and retry_at (finite nonnegative
wall-clock seconds, at most 253402300799). Version-1 waiting records with exactly version,
attempt and retry_at remain supported without losing their waits. Normal failure
deadlines start after failure. No secrets or exception text are stored.
Reads are capped at 256 bytes and reject duplicate/extra keys, wrong types/versions,
non-objects, nonfinite/negative/out-of-range values and malformed JSON. Invalid state,
including an empty :3 or oversized marker, permits one immediate attempt with the
schedule reset. Best-effort prior-byte capture is separate from write-ahead: unreadable
prior bytes do not prevent publication or its bounded recovery wait.
On loading a valid claim once, expired deadlines permit immediate retry; future delays
are clamped to 900 seconds from current wall time and converted once to a monotonic
deadline. The next failure continues the persisted attempt, including across restarts.
Atomic persistence uses same-directory mode-0600 exclusive temp, file fsync, replace,
and directory fsync where supported. Failures log only rebuild_retry_persist_failed,
retain stale/claimed state, clean temporary files where possible and use bounded
in-memory backoff. Successful write-ahead closes the during-attempt crash loop. A crash
before write-ahead or write-ahead persistence failure may allow immediate retry; repeated
persistence failures cannot offer a durable guarantee. A crash after index commit but
before claim unlink causes an idempotent rebuild after the bounded wait. This is not distributed
scheduling or perfect power-loss durability. Cancellation propagates after atomic
restoration of the exact prior marker bytes when captured, including empty legacy and
valid waiting state, without recording a failure. If capture failed, cancellation leaves
the valid in-progress record when published; no prior bytes are fabricated. If restoration
fails, ownership is retained and a bounded fail-closed interrupted state can remain;
only rebuild_retry_restore_failed is logged, never exception text. Normal incremental
failures still retry every 15 seconds.
HTTP 403/404/500, transport failures and unknown exceptions remain non-permanent;
no status classification, per-page stale policy or content bound is relaxed.
A completed rebuild, including
permanent skips, removes only the claimed marker; restart cannot replay consumed work.
A rebuild writes a temporary DB, validates/checkpoints,
then atomically replaces the derived DB. No canonical data or durable idempotency
state is held here. Readiness is false after every process start until a full sync.
Once ready, the prior index stays available during inventory/read waits on normal
polls and rebuilds; only a known transient/unknown failure marks it stale.

Lexical BM25 weights title/headings 5, tags 3, body 1 with canonical-path tie-break.
Filters run before LIMIT; backlinks are a bounded derived wikilink index. There are
no embeddings. No page-chunk embedding/token-budget claims are made.

## Durable state and rollback

store.json remains password-only and byte-identical after install. Separate
agent-api.json uses strict validation, temp-file mode 0600, fsync and rename, then
directory fsync. Operations serialize within one runtime process; concurrent StartOS
RPC-process actions are NOT a proven distributed lock. Administrators must serialize
configuration/rotation actions. Corrupt state fails MCP closed but does not block the
SilverBullet daemon; critical recovery tasks contain no secret material.

No canonical schema changes. :4 adds no-op up/down migrations from/to :3 (:3 ignores
marker content), retaining the historical no-op :3 -> :2 -> :1 -> :0 path, tested at
function/VersionGraph level. Actual StartOS upgrade/downgrade and treatment of the
extra index volume still require disposable StartOS evidence, not just unit tests.

## Interface lifecycle and Hermes recall

SDK 1.5.3 Effects.restart restarts main only. setupInterfaces therefore reads a
FileHelper.string view of agent-api.json mapped to the validated enabled flag with
.const(effects). Only flag changes re-export interfaces; malformed state maps to
disabled, and the unrelated UI remains exported. Atomic token rotations do not change
that dependency. The harness drives the actual actions and observes pinned SDK file
watching/context retries/exports, not a manual setInterfaces call after each action.
Official contract: https://docs.start9.com/packaging/0.4.0.x/interfaces.html.

The independent Hermes provider follows the official MemoryProvider contract:
queue_prefetch runs after turn N using its user query; prefetch consumes it for N+1,
whose query normally differs. Verified in official Hermes source at
8084684936a951e6c539675f8f81e5b5c35b866f (agent/memory_provider.py:138-144,
agent/turn_context.py:929, run_agent.py:922). The cache is session-scoped, latest
generation, one-shot, expires 30 minutes after fetch completion, and is invalidated on initialization
and shutdown. One background worker plus one coalesced pending request bounds work;
superseded results cannot publish. Re-queuing the same completed query replaces the
payload and timestamp. Identical in-flight queue calls coalesce to one search; event/fake-clock
tests pin both direct queue calls and the prefetch-miss/post-turn queue lifecycle, worker
termination, single payloads and fresh completed-query timestamps. No-network is_available
and no write hooks remain.
Recall is explicitly previous-turn context, not a claim of relevance to a new topic;
MCP search remains the current-query retrieval path. JSON-quoted bounded snippets
cannot break the untrusted-content fence. See integrations/hermes/README.md.

Primary contracts: upstream 2.12.1 docs/HTTP API.md, docs/Space Lua.md,
docs/Runtime API.md; docs.start9.com/packaging/0.4.0.x main/manifest/versions;
hermes-agent.nousresearch.com/docs/developer-guide/memory-provider-plugin.
