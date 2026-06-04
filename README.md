<p align="center">
  <img src="icon.png" alt="SilverBullet Logo" width="21%">
</p>

# SilverBullet on StartOS

> **Upstream repo:** <https://github.com/silverbulletmd/silverbullet>
> **Upstream docs:** <https://silverbullet.md/>
>
> Everything not listed in this document behaves the same as upstream
> SilverBullet 2.8.1. If a feature, setting, or behavior is not mentioned here,
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
| Image         | `ghcr.io/silverbulletmd/silverbullet:2.8.1`      |
| Architectures | x86_64, aarch64                                  |
| Entrypoint    | Upstream default (`tini` → `docker-entrypoint.sh` → `silverbullet`) |

The official multi-arch image is used unmodified. The server is configured
entirely through the upstream `SB_*` environment variables (see below).

---

## Volume and Data Layout

| Volume | Mount Point | Purpose                                        |
| ------ | ----------- | ---------------------------------------------- |
| `main` | `/space`    | Your SilverBullet space (Markdown + attachments) |

- The `main` volume's `space/` subpath is mounted at `/space` (SilverBullet's
  `SB_FOLDER`). Mounting a subpath — rather than the volume root — keeps the
  package's own state file out of your notes.
- `store.json` lives at the **root** of the `main` volume (outside `/space`) and
  holds the generated login password. It never appears as a note.

---

## Installation and First-Run Flow

- On a fresh install, a random 22-character password is generated and stored in
  `store.json`. It is supplied to SilverBullet as `SB_USER=admin:<password>`,
  enabling built-in authentication out of the box.
- A **critical task** prompts you to run the **Get Credentials** action to
  retrieve your username and password.
- There is no upstream setup wizard — log in and start writing.

---

## Configuration Management

| StartOS-Managed (env vars)                        | Upstream-Managed                          |
| ------------------------------------------------- | ----------------------------------------- |
| `SB_HOSTNAME`, `SB_PORT`, `SB_FOLDER`, `SB_USER`  | Everything else (Space Lua config, themes, settings pages, libraries, etc.) |

The login username is fixed to `admin`; the password is generated at install.
All other SilverBullet behavior is configured from within the app, exactly as
documented upstream.

---

## Network Access and Interfaces

| Interface | Port | Protocol | Purpose                |
| --------- | ---- | -------- | ---------------------- |
| Web UI    | 3000 | HTTP     | SilverBullet web app   |

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

---

## Backups and Restore

**Included in backup:**

- `main` volume — your entire space (notes and attachments) plus `store.json`
  (the generated password).

**Restore behavior:** The volume is fully restored before the service starts, so
your notes and existing credentials are preserved.

---

## Health Checks

| Check         | Method                | Messages                                                                        |
| ------------- | --------------------- | ------------------------------------------------------------------------------- |
| Web Interface | Port listening (3000) | Success: "The web interface is ready" / Error: "The web interface is not ready" |

---

## Dependencies

None.

---

## Limitations and Differences

1. **Authentication is always on.** Unlike a bare `docker run`, this package
   always sets `SB_USER`, so a login is required. Retrieve the password via the
   Get Credentials action.
2. **Single fixed user.** The username is `admin`. Multi-user setups and custom
   `SB_USER` values are not exposed.
3. **Port is fixed at 3000** internally; StartOS maps it to its own interfaces.
4. **`CONTAINER_BOOT.md` auto-execution** (an upstream entrypoint feature) is
   untested in this package and not recommended.

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
upstream_version: 2.8.1
image: ghcr.io/silverbulletmd/silverbullet:2.8.1
architectures: [x86_64, aarch64]
volumes:
  main: /space
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
