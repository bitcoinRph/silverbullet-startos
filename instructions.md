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
  under `/space` and are included in StartOS backups.

## Documentation

- [SilverBullet documentation](https://silverbullet.md/) — full guide to the
  editor, queries, templates, and Space Lua.
- [SilverBullet source](https://github.com/silverbulletmd/silverbullet) — the
  upstream project this package runs.

## Notes and limitations

- The login username is fixed to `admin`; the password is managed by this
  package (see the **Get Credentials** action). Other SilverBullet settings are
  configured from within the app, exactly as described in the upstream docs.
- To change your password, you can update it through SilverBullet's own
  mechanisms; the **Get Credentials** action always shows the password this
  package configured at install.
