# SilverBullet

You've installed SilverBullet — an open-source, self-hosted notebook where your
notes live as plain Markdown files in a single folder ("space"). This page
covers how to log in and where to read more.

## Getting set up

SilverBullet is protected by a generated password, so there's one quick step
before you start writing:

1. Open SilverBullet's **Actions** tab and run **Get Credentials**.
2. Copy the **Username** (`admin`) and **Password**.
3. Open SilverBullet's **Dashboard** tab and click the **Web UI** interface.
4. Log in with those credentials.

That's it — start a new page and your notes are saved automatically as Markdown
files in your space.

## What you get on StartOS

- **A running SilverBullet server** with its web editor, live preview,
  wiki-style links, the built-in query language, and Space Lua scripting.
- **Authentication enabled by default** — a random password is generated at
  install and supplied to SilverBullet, so your space isn't left open. Retrieve
  it any time with the **Get Credentials** action.
- **Your space on the `main` volume** — all notes and attachments are stored
  under `/data` (the unchanged main/space subpath) and are included in StartOS backups.

## Agent Business Memory (optional)

The Agent API starts disabled. An operator can run Enable Agent Memory API with
exact private proxy Host and browser Origin allowlists, then retrieve masked MCP
credentials and use the masked `/mcp` interface. Use the read token by default.
Never put tokens in URLs. Enable/disable and rotations restart the package.
The MCP interface appears/disappears reactively when enabled changes, without a
reboot or update; token rotation keeps the interface. Verify on your StartOS node.

The MCP daemon indexes Markdown through authenticated `/.fs`, not a mounted space.
Its separate index volume is disposable and excluded from backup; agent-api.json
is backed up on main. Login store.json is not rewritten by Agent API operations.
Rebuild Memory Index requests a rebuild without touching notes or login.
Unreadable pages over 64 KiB or with invalid UTF-8 are skipped and reported by
memory_status; they do not disable the rest of the index. Old indexed text for those
pages is removed. Network/inventory/ETag failures still mark stale and retry.

This release permits reads and validated create previews only; actual writes are
disabled in v1 and return MCP tool errors (isError=true, writes_disabled). Replacement
dry-run still requires a managed prefix, none configured in this release. Retrieved notes are
untrusted data. The experimental SilverBullet Runtime API is always disabled.
See docs/OPERATIONS.md in the package repository before enabling this feature.

## Credential recovery

If credentials are missing, empty, invalid, or unreadable, the package refuses
to start SilverBullet rather than exposing notes without authentication. A
critical task explains the recovery step: restore a known-good StartOS backup
that includes the main volume root `store.json`, then start the service and run
**Get Credentials**. Do not delete the store or reinstall to fix this error.
Restore does not generate a replacement password or alter your notes.

## Documentation

- [SilverBullet documentation](https://silverbullet.md/) — full guide to the
  editor, queries, templates, and Space Lua.
- [SilverBullet source](https://github.com/silverbulletmd/silverbullet) — the
  upstream project this package runs.

## Notes and limitations

- The login username is fixed to `admin`; the password is managed by this
  package (see the **Get Credentials** action). Other SilverBullet settings are
  configured from within the app, exactly as described in the upstream docs.
- Get Credentials shows the StartOS-managed login. Agent token rotation does not
  change that login. Restore a known-good backup for credential recovery; do not
  delete or overwrite store.json to troubleshoot the Agent API.
