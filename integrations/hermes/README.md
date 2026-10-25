# Hermes integration 0.1.0

Independent optional artifact, excluded from integration-only s9pk release pushes.
Do not replace an existing GBrain/other memory provider unless explicitly requested.
The portable MCP path plus skills works with any selected provider.

The directory plugins/silverbullet-memory/ implements the documented MemoryProvider
contract. It exposes no tools; MCP owns the six tool names. It keeps only the read
token, accessed with agent.secret_scope.get_secret. Configuration contains only an
exact private endpoint and a token environment-variable NAME. A malicious or wrong
endpoint can receive that token; verify the private URL before setup. No redirects
or implicit environment HTTP proxy forwarding are used.

For separately approved installation, copy only this plugin directory to the chosen
profile's documented plugin location. Use hermes memory setup and native setup/config
commands; do not hand-edit another profile's config. Provide endpoint and token_env
(default SILVERBULLET_READ_TOKEN) and put the read token in that profile's protected
secret environment. Never pass the internal or read/write token. Only one external
memory provider may be selected at a time. No installation was performed by this PR.

is_available uses only local config/secret checks. initialize binds hermes_home and
agent_context. queue_prefetch uses spawn_context_thread for context propagation;
prefetch never blocks on network. Hermes queues the completed turn's user query and
consumes recall on the next turn, whose query normally differs. The provider returns
the latest generation once for the same session, not only on exact query equality;
an expired/missing result returns an empty string while warming. The first turn can
have no recall. One worker plus one coalesced latest pending request makes bounded
search (with protocol initialization), excludes Inbox/Sources before top-k, and caps
injected output at 4,000 characters including the explicit untrusted-data fence.
Snippets and paths are JSON-quoted with escaped fence delimiters/newlines. Additional client-side filtering is defense in
depth. Cached recall expires after 15 seconds; stale-index results and search failures
yield a safe degraded marker without exception contents.
New generations invalidate old cached/in-flight results; session changes cannot read
another session's cache. Initialization and shutdown discard recall and invalidate
old workers' results. Cached data is labeled previous-turn recall, not evidence that
it is relevant to a new topic; use MCP search for a new current-query lookup.
No sync_turn, pre-compression or session-end writes occur.

Install the single skills/silverbullet-memory/SKILL.md only with approval. It covers
retrieval, citations, untrusted content and approval-gated curation. The current s9pk
is read-only; preview output is not a write. The host-ABI test harness does not prove
live Hermes discovery or gateway profile isolation. Verify in a disposable profile,
with hermes mcp test and actual read-only tool calls, before adopting this provider.
