# Business Memory architecture and v1 security decision

Upstream SilverBullet 2.12.1 remains canonical. Wrapper ExVer 2.12.1:1 adds a
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

The exact-image/browser executable-content and unsaved-editor concurrency spikes
cannot run locally without Docker. Therefore actual mutations are hard-disabled,
including for write-token callers. The upstream client has no PUT or DELETE methods;
no runtime configuration can turn mutations on. This is a deliberate v1 read-only
release, not a claim that the original full-write plan is complete.

The six tools remain exactly memory_status, memory_search, memory_get,
memory_backlinks, memory_create and memory_replace_text. The write scope permits
create previews. Replacement is refused by default (empty managed-prefix tuple);
its exact-single-match/ETag/content preview implementation is exercised with an
explicit synthetic prefix in unit tests. A non-dry-run call returns writes_disabled.
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
Outsize notes make the index stale rather than silently current. Search is bounded
20 results, 500 escaped characters each; get is capped at 16,000 characters. Index
metadata parsing deliberately supports flat v1 scalars and inline tags, not all YAML.

Non-root MCP UID/GID 10001 with graceful termination. A root initialization chown
prepares only the index volume root; the daemon never mounts main. SDK 1.5.3 does
not support read-only-rootfs or package CPU/memory controls; no such claim is made.

## Derived index

A dedicated excluded-from-backup index volume holds SQLite FTS5/WAL with a busy
 timeout and schema version. Poll inventory every 15 seconds; fetch changed Markdown
only. Keep a failed read's previous entry and mark stale. Reconcile deletion only
from a successful complete inventory. Check integrity on open and rebuild corruption.
Operator rebuilds use a marker; rebuild writes a temporary DB, validates/checkpoints,
then atomically replaces the derived DB. No canonical data or durable idempotency
state is held here. Readiness is false after every process start until a full sync.

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

No canonical schema changes. :1 includes a no-op down migration to :0, tested at
function/VersionGraph level. Actual StartOS upgrade/downgrade and treatment of the
extra index volume still require disposable StartOS evidence, not just unit tests.

Primary contracts: upstream 2.12.1 docs/HTTP API.md, docs/Space Lua.md,
docs/Runtime API.md; docs.start9.com/packaging/0.4.0.x main/manifest/versions;
hermes-agent.nousresearch.com/docs/developer-guide/memory-provider-plugin.
