# Operations, verification and remaining gates

No live service installation, credential rotation, infrastructure change or release
publication is authorized by this branch. The PR stays draft; do not merge until
all exact-head gates and independent review pass.

This branch targets wrapper 2.12.1:3, based on merge 9dc537489afe5febde32edaa965614fc469c0b28.
Only the three approved follow-ups from :2 are addressed: bounded failed-rebuild
retry/backoff, real-image oversized/invalid-UTF-8 tests, and Hermes in-flight dedupe
regression tests (no provider production change). Upstream remains 2.12.1. Published
assets are immutable. No release/merge automation is enabled or changed by this PR.

## Enable safely (separately approved deployment)

1. Verify a restorable main-volume backup, package checksum/manifest, upstream pin
   and package ExVer. Snapshot page count/hashes without note bodies or credentials.
2. After separately approved deployment, confirm existing browser login and notes.
   Confirm SB_RUNTIME_API=0 rejects /.runtime/* with and without the internal bearer.
3. Confirm API disabled means no SB_AUTH_TOKEN, MCP daemon or interface. Agent state
   is generated once on install/update/restore/null init; never edit store.json.
4. For opt-in, run Enable Agent Memory API. Set exact Host headers seen through the
   private StartOS proxy (including mapped port), plus exact http(s) browser origins
   or leave origins empty. Never use wildcard host/origin values. This action enables
   the API and restarts main; its reactive interface dependency independently
   exports MCP without reboot/update. Do not invoke it without operator approval.
5. Use Get MCP Credentials, which masks external read/read-write tokens and resolves
   current non-local MCP URLs using the SDK interface API. If no URL is available,
   inspect the StartOS Interfaces tab; append /mcp only once. Never fabricate a proxy
   URL. Store the read token in
   the consumer's protected secret environment, never a URL or committed config.
6. Call memory_status, then inspect tools/list and perform read-only search/get.
   Test wrong/missing/query tokens and read-token writes, Host and Origin errors,
   status/body health checks and index lag through the REAL proxy, not just loopback.
7. Keep actual mutations disabled. Current six-tool API cannot create or replace
   canonical content. Create previews are not a committed result. tools/list describes
   every tool; both mutation descriptions explicitly say preview/fail-closed only,
   writes disabled in v1. Non-dry-run calls fail with MCP isError=true and writes_disabled.
   Replacement fails before managed-prefix checks; dry-run still enforces that policy.

Enable/disable and both rotation actions restart the package and invalidate active
requests. External rotation leaves login/internal token intact; internal rotation
leaves login/external tokens intact. Serialize operator actions: cross-RPC action
concurrency has not been proven. Disabling removes bearer auth, daemon and interface.
Token-only rotations leave the exported interface intact. The package harness drives
actual enable/disable/rotate/credentials actions with the pinned SDK's FileHelper
watcher and context retry. It never manually reruns setInterfaces after an action.
On a disposable StartOS node, verify interface appearance/removal and fresh masked
credentials after rotation, without reboot/update; source tests are not that live gate.
Missing/corrupt API state leaves SilverBullet running but MCP closed with a critical
task. Recover a known-good agent-api.json backup; do not delete store.json.

## Index, backup and downgrade

Use Rebuild Memory Index to request a new validated derived index on the next poll.
No delete/reindex MCP tool exists. Pages over 64 KiB or with invalid UTF-8 are
permanently skipped, reported by memory_status as skipped plus up to ten path/reason
details. Their previous indexed text is removed, including during a failed rebuild;
they do not keep the readable corpus stale or readiness false. Unchanged skips are
cached in the disposable DB across process restarts and retried on a changed inventory
stamp or explicit rebuild. Counts include all skips; details deliberately truncate.
Transient inventory/network/inconsistent SHA-256 ETag failures still mark stale,
return readiness HTTP 503 and retain retry behavior. Unknown errors fail closed.

The action publishes a complete rebuild-request with temp-file/fsync/rename; the
poller atomically renames it to rebuild-in-progress. Completed work (including skipped
pages) removes only that claimed marker. A new concurrent request survives at its
original path for the next poll. Transient failed rebuilds retain the previous DB
(except permanently rejected old text) and claimed work for retry. A completed rebuild
does not full-refetch unchanged pages on the next poll or restart. Review safe logs
and credential/loopback/auth status without printing secrets.

Failed claimed rebuild retry delays are deterministic: 30, 60, 120, 240, 480, then
900 seconds, capped at 15 minutes without jitter. The deadline uses monotonic time
after each failed attempt. The regular 15-second poll does no inventory/page reads
before that deadline; the requested rebuild keeps the index stale and readiness 503.
Success consumes only rebuild-in-progress and resets the schedule; a concurrent
rebuild-request is claimed on the next poll. Scheduling is in-process, not persisted
or distributed: a process restart may retry the recoverable claim immediately once.
Normal incremental sync timing is unchanged. HTTP 403/404/500 remain transient:
the production reader exposes only generic UpstreamError status strings, and a
listed-page status does not prove permanent deletion or rejection. No reclassification
or per-page stale workaround is introduced. Cancellation still propagates.

Backup main: canonical main/space, store.json and agent-api.json. Never back up the
live derived index as canonical memory. It rebuilds after restore. Test password
byte-identity during install/update/restore/rebuild/enable/disable/rotations with a
disposable StartOS node before production adoption.

The :3 -> :2 -> :1 -> :0 migrations are intentionally no-ops: :0 ignores the extra state and index.
Source tests prove the migration graph reaches :0 without mutating the files; actual
StartOS downgrade acceptance and retained-volume behavior remain unverified. If
StartOS refuses it, STOP and obtain approval for uninstall-and-restore from the
verified backup; do not force a reset, overwrite state or claim an in-place rollback.
Returning to :0 also restores its old Runtime API defaults: reconsider that risk.

## Reproduce source verification

Use an isolated local venv and synthetic values only. Example command family:

    npm ci
    npm test
    npm run check
    npm run build
    python -m venv .venv
    .venv/bin/python -m pip install --require-hashes -r memory-mcp/requirements-dev.txt
    PYTHONPATH=memory-mcp/src .venv/bin/python -m pytest memory-mcp/tests integrations/hermes/tests -q
    .venv/bin/python -m ruff check memory-mcp integrations/hermes
    .venv/bin/python -m ruff format --check memory-mcp integrations/hermes
    .venv/bin/python -m mypy --ignore-missing-imports memory-mcp/src
    git diff --check

Use a scoped TMPDIR/pytest basetemp under your evidence directory. Lockfiles are
hash-locked using pip-tools 7.5.3 with pip 25.3; pip 26.2 removed an internal API
pip-tools requires. Resolve in an isolated environment; do not alter global Python.
The MCP SDK is deliberately pinned at 1.30.0, not an untested MCP 2.x port.

Exact-image CI runs SB_REAL_IMAGE=1 pytest memory-mcp/tests/test_real_image.py. It
must fail, not skip, if Docker/browser prerequisites are missing when enabled. Local
runs explicitly skip it without the opt-in. Local Docker is unavailable. Unit fake
HTTP/corpus tests are not real-image evidence. Build both package architectures and
universal; inspect with start-cli s9pk inspect FILE manifest --format json. Verify
2.12.1:3, image set/architectures, non-root runtime, interface declarations, checksum,
source gitHash and absence of node_modules in the MCP image. CI is the artifact gate.

## Required exact-head CI and review before merge

- Source/protocol/package-contract tests, lint/type/build and dependency scans on :3.
- Re-run exact-image bearer/read/conditional ETag, hidden-path, Runtime-disabled
  rejection and browser execution/concurrency checks on the final :3 SHA, including
  both new permanent-page cases described below. Prior CI is not final-SHA evidence.
- Build both architecture packages and inspect their version/metadata/checksums.
  The universal package remains a separately authorized release-build gate.
- Independent exact-diff Opus high-effort audit and all required exact-head CI checks;
  local coder verification does not substitute for that final review.

Exact-image permanent-page coverage (Docker-gated locally, mandatory in the existing
CI real-image job and release gate) uses ghcr.io/silverbulletmd/silverbullet:2.12.1:

- A 65,537-byte Markdown page is uploaded to the disposable /.fs fixture. Assert it
  is listed with the exact size and served byte-for-byte with the matching SHA-256 ETag.
  The production SilverBulletClient must raise PermanentPageError(page_too_large).
- A page containing literal 0xff/0xfe bytes is atomically written through the fixture's
  mounted /data volume, bypassing any text PUT decoding. Assert the same exact listing,
  HTTP 200/raw bytes/ETag; the production client must raise
  PermanentPageError(invalid_markdown_encoding). There is no alternate outcome/xfail.
  Source basis: upstream tag 2.12.1 server-common/src/space/disk.rs read_file uses
  fs::read; server/src/handlers/fs.rs handle_fs_get hashes bytes and returns Body::from(data).
- Both cases first index valid old content, then use production MemoryIndex.sync to
  remove it, report the exact skip reason, keep the readable corpus ready/searchable,
  and prove two subsequent syncs do not fetch the unchanged rejected page. HTTP request
  hooks only count real requests; no transport/client/index mock is substituted.
- All pre-existing Runtime/auth/conditional-write/browser concurrency tests remain.
  Local collection/skips are not image execution evidence. If CI cannot create/list/serve
  the invalid-byte page exactly as asserted, stop for review; do not broaden accepted
  responses or weaken UTF-8/64 KiB rejection to make the gate green.

The scoped npm advisory acceptance below is unchanged from :2; this revision changes
neither npm dependencies nor lockfiles.

## Remaining separately approved live deployment gates

- StartOS same-package loopback, actual proxy Host/Origin, dynamic interface lifecycle,
  sidecar/task visibility, masked fresh credentials, volume ownership and backup/restore.
- Upgrade/downgrade acceptance with canonical notes and login byte-preserved.
- Final package signatures/source gitHash, universal package and actual arm64 runtime.
  Wheel availability and cross-architecture image packing are not native runtime proof.
- Real Hermes discovery/activation in a disposable profile. Never install into existing
  profiles as an implementation shortcut; the host ABI harness is not this live gate.

## Explicit scoped dependency risk acceptance

For this requested 2.12.1:2 fix-forward, retain and explicitly accept the pre-existing
GHSA-mrhx-c7xc-m3w5 (CVE-2023-54404) HIGH advisory through Start SDK 1.5.3/Zod.
The SDK and npm lockfile are unchanged from :1. npm audit reports two HIGH findings
(Zod plus its SDK dependency chain), not a clean scan. This is a scoped acceptance,
not a patched-vulnerability claim or authorization to expand input reachability.

Exposure basis: Node Zod here handles only StartOS-admin action input and package-written
agent-api.json. Enable caps host/origin arrays at 16 and validates exact hosts/origins
before passing them to state validation; package-written arrays are bounded, and the
state schema also caps both arrays at 16. These are trusted administrator/configuration
surfaces, not untrusted network payloads. No network-reachable MCP path invokes Node
Zod: the sidecar is Python with its existing byte/depth/element/auth/Host/Origin bounds.
Administrator-controlled malformed state and SDK-internal parsing remain residual
availability risks; schema .max alone must not be described as a universal early-abort
mitigation. Reassess before adding input arrays, exposing Node validation remotely or
upgrading the SDK. A major SDK/Zod migration is outside this surgical release.
Advisory: https://github.com/advisories/GHSA-mrhx-c7xc-m3w5.
Python pip-audit is a separate scan; do not infer its result from npm audit.

Any real-image gate disproving conditional writes or content safety keeps the service
read-only. Silent browser reversion would prohibit replacement (create-only maximum).
No future change may enable writes solely because unit tests or package builds pass.
