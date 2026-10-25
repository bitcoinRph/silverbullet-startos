<p align="center">
  <img src="icon.png" alt="SilverBullet Logo" width="21%">
</p>

# SilverBullet Business Memory on StartOS

Wrapper `2.12.1:1` keeps upstream `2.12.1` and adds an opt-in, authenticated
Streamable HTTP MCP daemon with a disposable SQLite FTS5 index. The Agent API is
disabled by default: no extra daemon, interface or `SB_AUTH_TOKEN`. The experimental
Runtime API is now unconditionally disabled (`SB_RUNTIME_API=0`), including when
MCP is enabled. This is an intentional change from the previous wrapper.

Safety downgrade: actual MCP mutations are hard-disabled pending real-image
executable-content and browser-concurrency evidence. The six tools are
`memory_status`, `memory_search`, `memory_get`, `memory_backlinks`, `memory_create`
and `memory_replace_text`; create provides validated previews, replacement has no
operator-managed prefixes in this release. No environment flag bypasses this gate.

See [Architecture](docs/ARCHITECTURE.md) and [Operations](docs/OPERATIONS.md) for
the security model, exact tool contracts, operational actions and unverified gates.
The optional [Hermes integration](integrations/hermes/README.md) is independently
versioned `0.1.0` and excluded from integration-only automatic s9pk publication.

> **Upstream repo:** <https://github.com/silverbulletmd/silverbullet>
> **Upstream docs:** <https://silverbullet.md/>
>
> Everything not listed in this document behaves the same as upstream
> SilverBullet 2.12.1. If a feature, setting, or behavior is not mentioned here,
> the upstream documentation is accurate and fully applicable.

[SilverBullet](https://silverbullet.md/) is an open-source, self-hosted personal
knowledge management app. Your notes live as plain Markdown files in a single
folder ("space"), enriched with wiki-style linking, a built-in query language,
and the Space Lua scripting environment.

---

## Table of Contents

- [Image and Container Runtime](#image-and-container-runtime)
- [Volume and Data Layout](#volume-and-data-layout)
- [Installation and First-Run Flow](#installation-and-first-run-flow)
- [Configuration Management](#configuration-management)
- [Network Access and Interfaces](#network-access-and-interfaces)
- [Actions (StartOS UI)](#actions-startos-ui)
- [Backups and Restore](#backups-and-restore)
- [Health Checks](#health-checks)
- [Dependencies](#dependencies)
- [Limitations and Differences](#limitations-and-differences)
- [What Is Unchanged from Upstream](#what-is-unchanged-from-upstream)
- [Quick Reference for AI Consumers](#quick-reference-for-ai-consumers)

---

## Image and Container Runtime

| Property      | Value                                            |
| ------------- | ------------------------------------------------ |
| Image         | `ghcr.io/silverbulletmd/silverbullet:2.12.1`     |
| Architectures | x86_64, aarch64                                  |
| Entrypoint    | Upstream default (`tini` → `docker-entrypoint.sh` → `silverbullet`) |

The official multi-arch image is used unmodified. The server is configured
entirely through the upstream `SB_*` environment variables (see below).

---

## Volume and Data Layout

| Volume | Mount Point | Purpose                                        |
| ------ | ----------- | ---------------------------------------------- |
| `main` | `/data`     | Your SilverBullet space (Markdown + attachments) |

- The `main` volume's `space/` subpath is mounted at `/data` (SilverBullet's
  `SB_FOLDER`). Mounting a subpath — rather than the volume root — keeps the
  package's own state file out of your notes. SilverBullet 2.11.0 still honors
  `/space` as a legacy mount point, but `/data` is now the upstream-preferred
  container data folder.
- `store.json` lives at the **root** of the `main` volume (outside `/data`) and
  holds the generated login password. It never appears as a note.
- `agent-api.json` holds the opt-in setting and three distinct generated tokens,
  with atomic temp-file/fsync/rename writes. Install/update/restore generate it
  only if absent; malformed state is not silently replaced. `store.json` is never
  rewritten after initial install. The separate `index` volume is derived and
  excluded from backups; MCP never mounts the canonical space.

---

## Installation and First-Run Flow

- On a fresh install, a random 22-character password is generated and stored in
  `store.json`. It is supplied to SilverBullet as `SB_USER=admin:<password>`,
  enabling built-in authentication out of the box.
- A **critical task** prompts you to run the **Get Credentials** action to
  retrieve your username and password.
- SilverBullet includes an upstream setup wizard for unmanaged fresh installs.
  This StartOS package continues to provide StartOS-managed
  single-space credentials through `SB_USER`, so the first-run flow remains:
  run **Get Credentials**, log in as `admin`, and start writing.
- Startup fails closed before creating a container if the credential store is
  missing, malformed, unreadable, or contains unusable credentials. A critical
  recovery task directs you to restore a known-good backup including root
  `store.json`. The package never silently replaces restored credentials.

---

## Configuration Management

| StartOS-Managed (env vars)                        | Upstream-Managed                          |
| ------------------------------------------------- | ----------------------------------------- |
| `SB_HOSTNAME`, `SB_PORT`, `SB_FOLDER`, `SB_USER`, `SB_RUNTIME_API`; opt-in `SB_AUTH_TOKEN` | In-app Space Lua config, themes, settings pages and libraries |

The login username is fixed to `admin`; the password is generated at install.
All other SilverBullet behavior is configured from within the app, exactly as
documented upstream.

---

## Network Access and Interfaces

| Interface | Port | Protocol | Purpose                |
| --------- | ---- | -------- | ---------------------- |
| Web UI    | 3000 | HTTP     | SilverBullet web app   |
| Memory MCP (opt-in) | 3001 | HTTP | Masked API interface at `/mcp` |

**Access methods:**

- LAN IP with unique port
- `<hostname>.local` with unique port
- Tor `.onion` address
- Custom domains (if configured)

---

## Actions (StartOS UI)

| Action            | Purpose                                   | Visibility | Availability | Output                |
| ----------------- | ----------------------------------------- | ---------- | ------------ | --------------------- |
| **Get Credentials** | Retrieve the login username and password | Enabled    | Any status   | Username + masked password |

Agent actions: Enable/Disable Agent Memory API, Get MCP Credentials (external tokens
masked), Rotate MCP Tokens, Rotate Internal API Token, Rebuild Memory Index. Enable
requires exact private proxy Host and Origin allowlists; browser origins default
to none. Enable/disable/rotations restart only when invoked by an operator.

---

## Backups and Restore

**Included in backup:**

- `main` volume — your entire space, `store.json` and separate `agent-api.json`.
- Not included: the dedicated, rebuildable `index` volume.

**Restore behavior:** The volume is fully restored before the service starts, so
your notes and existing credentials are preserved.

---

## Health Checks

| Check         | Method                | Messages                                                                        |
| ------------- | --------------------- | ------------------------------------------------------------------------------- |
| Web Interface | Bounded `/.ping`, HTTP 200 and body `OK` | Fails on other statuses or bodies |
| Memory index | `/health/ready`, HTTP 200 and `ready: true` | HTTP 503 until a full authenticated sync; stale syncs are not ready |

---

## Dependencies

None.

---

## Limitations and Differences

1. **Authentication is always on.** Unlike a bare `docker run`, this package
   always sets `SB_USER`, so a login is required. Retrieve the password via the
   Get Credentials action.
2. **Single fixed StartOS-managed user.** The username is `admin`. SilverBullet
   2.11.0 includes upstream multi-account, multi-space, collaboration, SSO,
   permissions, comments, and revision features, but this
   package does not yet expose StartOS actions for managing them. Use the
   upstream UI with care and back up before changing space/account topology.
3. **Port is fixed at 3000** internally; StartOS maps it to its own interfaces.
4. **`CONTAINER_BOOT.md` auto-execution** (an upstream entrypoint feature) is
   untested in this package and not recommended.
5. **Health is checked against the documented 2.12.1 `/.ping` response.** If
   routing behaves oddly behind a proxy, verify the StartOS URL/scheme forwarding.
6. **2.11.0 changes the upstream container entrypoint/data-folder behavior.**
   The image now prefers `/data` and treats `/space` as legacy. This package
   mounts the same persistent StartOS `main/space` subpath at `/data`, so notes
   and credentials remain in the same StartOS volume while avoiding upstream's
   legacy-path warning.

---

## What Is Unchanged from Upstream

- The Markdown editor, live preview, wiki links, page navigation.
- The built-in `query`/`template` system and Space Lua scripting.
- Libraries, plugs, themes, and all in-app settings.
- The on-disk format: plain Markdown files in your space folder.

---

## Quick Reference for AI Consumers

```yaml
package_id: silverbullet
upstream_version: 2.12.1
image: ghcr.io/silverbulletmd/silverbullet:2.12.1
architectures: [x86_64, aarch64]
volumes:
  main: /data
ports:
  ui: 3000
dependencies: none
startos_managed_env_vars:
  - SB_HOSTNAME
  - SB_PORT
  - SB_FOLDER
  - SB_USER
actions:
  - get-credentials
```
