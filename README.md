# Journal

A small, encrypted journal: a PySide6 desktop app talking over HTTP to a
Flask server that owns the actual database and does all the encryption.
No cloud, no third-party sync - the server is yours, wherever you run it.

## Architecture

```
Flask server (server/app.py)         <- the only process that ever touches journal.db
  owns journal.db, decrypts entries server-side,
  holds the decryption key in memory for your session only
    |
    | HTTP (JSON API + a small web UI)
    |
    +-- Desktop app (app/main.py)      <- PySide6 client, talks to the server via app/db.py
    +-- Web browser                   <- calendar + Quill.js editor, served by the same Flask app
```

`app/db.py` is an HTTP client with the exact same function signatures the
original SQLite version had, so the desktop UI code (`window.py`,
`editor.py`, etc.) doesn't know or care that entries live on a server now
instead of a local file.

## Running the server

```bash
cd server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# dev (auto-reload, one process, fine for testing):
python app.py

# production:
gunicorn --workers 1 --threads 4 --bind 0.0.0.0:8420 app:app
```

`--workers 1` is required, not just a default: the decryption key for an
unlocked session lives in an in-memory dict inside this one process, and
sqlite3 access is guarded by a single lock rather than built for
multi-process use. This is meant for one person's low-traffic personal
journal, not concurrent multi-user load - `--threads 4` is enough to keep
one slow request from blocking others.

Data (journal.db + the Flask session secret) is written to `JOURNAL_DATA_DIR`
(defaults to `server/data/`). Point that at a mounted volume in Docker so it
survives container rebuilds.

### Docker

`server/Dockerfile` builds a self-contained image from the `server/`
directory alone. `server/docker-compose.example.yml` is a service block
meant to be merged into an existing compose stack - it builds straight from
GitHub (`context: https://github.com/<you>/Journal.git#main:server`), so
`docker compose build journal` re-pulls and rebuilds without a separate
registry or CI step. It deliberately publishes no host port: your reverse
proxy (nginx, Caddy, whatever) reaches it over the internal Docker network
by service name.

### Reachability

The server has no built-in exposure story of its own - LAN-only, behind a
reverse proxy + Cloudflare, behind Tailscale, whatever you already do for
your other self-hosted services applies here too. `JOURNAL_COOKIE_SECURE=1`
should be set once it's actually served over HTTPS (see the comment next to
it in `app.py` for why it's off by default).

## Running the desktop client

```bash
cd app
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
JOURNAL_SERVER_URL=http://your-server:8420 python3 main.py
```

Defaults to `http://localhost:8420` if `JOURNAL_SERVER_URL` isn't set.

First run against a fresh server asks you to set a password - this is what
encrypts everything server-side. **There is no password recovery.** If you
lose it, your entries are gone for good (a consequence of real encryption,
not a missing feature). Keep it somewhere durable - a password manager, or
written down safely.

### Optional: a desktop launcher

```ini
[Desktop Entry]
Type=Application
Name=Journal
Exec=/full/path/to/Journal/app/venv/bin/python /full/path/to/Journal/app/main.py
Icon=/full/path/to/Journal/app/assets/icon.svg
Path=/full/path/to/Journal/app
Terminal=false
Categories=Office;
```

Save as `~/.local/share/applications/journal.desktop`, swap in your actual
path, and it'll show up in your app launcher like any other installed
program. Set `JOURNAL_SERVER_URL` in your shell profile (or add
`Environment=` lines / wrap the `Exec` in `env`) if it's not `localhost`.

## Using it

- Click a date on the calendar to jump to that day's entry, or use the
  month/year dropdowns and ◀/▶ to navigate.
- Type - it autosaves about a second after you stop typing, and also saves
  when you switch dates, toggle the template, or close the app.
- Right-click the entry for formatting: **Bold**, *Italic*, headings, font
  size, font family, and (right-click an image) resize presets.
- Drag an image file into the entry to embed it - it's scaled to a
  reasonable default size automatically; right-click it to resize.
- **Template** (top of the calendar panel) switches to a reusable template
  page, edited exactly like any day's entry. **Import Template** (top of
  the entry pane) inserts it into whatever day you're on.
- Dates with an entry are marked with a small dot on the calendar.
- Window size and the calendar/editor split are remembered between runs.

The web UI (open the server's URL in a browser) covers the same core
flow - calendar, entry editor, template - via Quill.js instead of the
desktop's native text widget.

## Where your data lives

Everything is in one SQLite file on the server:

```
$JOURNAL_DATA_DIR/journal.db   (defaults to server/data/journal.db)
```

Every entry's text and every embedded image is encrypted before it's
written to that file. Back this one file up however you like - the backup
is only ever ciphertext without the password.

## Security model, plainly

- Password → scrypt (a slow, memory-hard KDF - resists brute force better
  than a fast hash) → a Fernet key (AES-128-CBC + HMAC-SHA256, from the
  `cryptography` library). This happens entirely server-side now.
- The password itself is never stored - only a random salt and a small
  "verifier" token used to check a password is correct on unlock.
- The derived key lives only in the server process's memory, scoped to an
  opaque session token in a signed cookie. The key itself never reaches
  the browser or the desktop client, and is never written to disk.
- No custom crypto anywhere - both scrypt and Fernet are established,
  independently reviewed primitives, not something invented for this app.
- This is a deliberately low-effort security posture for a personal
  self-hosted tool, not a hardened multi-user service - see `server/app.py`'s
  module docstring for the specific tradeoffs (single worker, in-memory
  sessions, no rate limiting on login).

## Repo layout

```
app/main.py, window.py, editor.py, calendar_widget.py,
    dialogs.py, theme.py, paths.py    desktop app (PySide6)
app/db.py                             HTTP client the desktop app talks to db through
server/app.py                         Flask server - the only thing that touches journal.db
server/db.py, server/crypto.py        SQLite storage + encryption (server-side only)
server/templates/, server/static/     web UI (calendar + Quill.js editor)
server/Dockerfile, docker-compose.example.yml
```

## Extending it later

- **Search**: would need a plaintext (or per-word hashed) index alongside
  the encrypted content - its own design tradeoff between searchability
  and what stays encrypted, worth deciding deliberately rather than
  bolting on.
- **Password change**: re-encrypt the verifier and all existing
  entries/images under a new key derived from the new password.
- **Rate limiting on /login**: currently unlimited attempts - fine for a
  single-user LAN/Tailscale setup, worth adding before exposing more
  broadly.
- **Tags or multiple entries per day**: would mean moving from `date` as
  the primary key to a proper `id`, with date as a separate indexed column.
- **Export**: dump decrypted entries to Markdown/JSON - straightforward
  since you already have `get_entry()` for every date.
