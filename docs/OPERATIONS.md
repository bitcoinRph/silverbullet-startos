# Operations, verification and remaining gates

No live service installation, credential rotation, infrastructure change or release
publication is authorized by this branch. The PR stays draft; do not merge until
all exact-head gates and independent review pass.

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
   the API and restarts the package; do not invoke it without operator approval.
5. Use Get MCP Credentials, which masks external read/read-write tokens and resolves
   current non-local MCP URLs using the SDK interface API. If no URL is available,
   inspect the StartOS Interfaces tab; append /mcp only once. Never fabricate a proxy
   URL. Store the read token in
   the consumer's protected secret environment, never a URL or committed config.
6. Call memory_status, then inspect tools/list and perform read-only search/get.
   Test wrong/missing/query tokens and read-token writes, Host and Origin errors,
   status/body health checks and index lag through the REAL proxy, not just loopback.
7. Keep actual mutations disabled. Current six-tool API cannot create or replace
   canonical content. Create previews are not a committed result.

Enable/disable and both rotation actions restart the package and invalidate active
requests. External rotation leaves login/internal token intact; internal rotation
leaves login/external tokens intact. Serialize operator actions: cross-RPC action
concurrency has not been proven. Disabling removes bearer auth, daemon and interface.
Missing/corrupt API state leaves SilverBullet running but MCP closed with a critical
task. Recover a known-good agent-api.json backup; do not delete store.json.

## Index, backup and downgrade

Use Rebuild Memory Index to request a new validated derived index on the next poll.
No delete/reindex MCP tool exists. A failed read retains its old entry and marks stale;
readiness becomes HTTP 503. A failed rebuild retains the previous DB. Review the
safe process/audit logs and credential/loopback/auth status without printing secrets.

Backup main: canonical main/space, store.json and agent-api.json. Never back up the
live derived index as canonical memory. It rebuilds after restore. Test password
byte-identity during install/update/restore/rebuild/enable/disable/rotations with a
disposable StartOS node before production adoption.

The :1 -> :0 migration is intentionally a no-op: :0 ignores the extra state and index.
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
2.12.1:1, image set/architectures, non-root runtime, interface declarations, checksum,
source gitHash and absence of node_modules in the MCP image. CI is the artifact gate.

## Mandatory unverified gates before merge/deploy

- Default-image Runtime API reproduction; disabled Runtime behavior with/without bearer.
- Exact-image bearer CRUD/conditional ETag semantics and hidden paths.
- Real browser malicious-page boot reproduction, accepted/rejected content execution,
  and unsaved human-editor concurrency/reconciliation (no silent reversion).
- StartOS same-package loopback, actual proxy Host/Origin, sidecar lifecycle/task visibility,
  secret masking, volume ownership, upgrade/restore and accepted no-op downgrade.
- Both architecture images/packages, universal package, package metadata/signatures and
  actual arm64 runtime. Wheel availability alone is not a successful image build.
- Real Hermes plugin discovery/activation in a disposable profile; never install into
  existing profiles as an implementation shortcut. Host ABI harness is not this gate.
- Independent exact-diff Opus high-effort audit and all required exact-head CI checks.
- Baseline npm audit reports two high findings through SDK 1.5.3's Zod collection
  validator (GHSA-mrhx-c7xc-m3w5). Do not call the dependency scan clean. A major SDK
  upgrade is outside this wrapper slice; assess StartOS action/config exposure and
  resolve or explicitly accept this before merge. Python audit is a separate result.

Any real-image gate disproving conditional writes or content safety keeps the service
read-only. Silent browser reversion would prohibit replacement (create-only maximum).
No future change may enable writes solely because unit tests or package builds pass.
