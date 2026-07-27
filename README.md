# SimpleJournal

A small, encrypted, offline-only journal for Linux. No cloud, no
sync, no network code anywhere in the app - nothing for anything
else on your machine to connect to.

## Setup (Ubuntu)

```bash
cd simplejournal
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

First run asks you to set a password - this encrypts everything.
**There is no password recovery.** If you lose it, your entries are
gone for good (this is a direct consequence of real encryption, not
a missing feature). Keep the password somewhere durable - a password
manager, or written down somewhere safe.

## Where your data lives

Everything is in a single SQLite file:

```
~/.simplejournal/journal.db
```

Every entry's text and every embedded image is encrypted before it's
written to that file. Back this single file up however you like
(copy it to a USB drive, an encrypted external disk, etc.) - the
backup is only ever ciphertext without your password.

## Using it

- Click a date on the calendar to jump to that day's entry.
- Type - it autosaves about a second after you stop typing, and also
  saves when you switch dates or close the app.
- **Bold** / *Italic* buttons in the toolbar, or the usual
  Ctrl+B / Ctrl+I shortcuts.
- **Insert Image** opens a file picker; the image gets embedded
  inline at your cursor.
- **Lock** re-locks the journal and asks for your password again -
  use this before stepping away from your machine.
- Dates with an entry are shown bold and green on the calendar.

## Optional: a desktop launcher

To get a normal clickable icon instead of typing the command each
time, create `~/.local/share/applications/simplejournal.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=SimpleJournal
Exec=/full/path/to/simplejournal/venv/bin/python /full/path/to/simplejournal/main.py
Icon=accessories-text-editor
Terminal=false
Categories=Utility;
```

Replace the two `/full/path/to/...` bits with wherever you put this
folder, then it'll show up in your app launcher like any other
installed program.

## Extending it later

The whole app is three files (`main.py`, `db.py`, `crypto.py`) on
purpose, so it's easy to read end to end. Ideas if you want to grow
it:

- **Search**: would need to store a plaintext (or per-word hashed)
  index alongside the encrypted content, which is its own design
  tradeoff between searchability and what stays encrypted. Worth
  deciding deliberately rather than bolting on.
- **Password change**: re-encrypt the verifier and all existing
  entries/images under a new key derived from the new password.
- **Tags or multiple entries per day**: would mean moving from
  `date` as the primary key to a proper `id`, with date as a
  separate indexed column.
- **Export**: dump decrypted entries to Markdown/JSON - straightforward
  since you already have `get_entry()` for every date.

## Security model, plainly

- Password → scrypt (a slow, memory-hard KDF - resists brute force
  better than a fast hash) → a Fernet key (AES-128-CBC + HMAC-SHA256,
  from the `cryptography` library).
- The password itself is never stored - only a random salt and a
  small "verifier" token used to check a password is correct on
  unlock.
- No custom crypto anywhere - both scrypt and Fernet are established,
  independently reviewed primitives, not something invented for this
  app.
- No network code at all in this codebase - it structurally cannot
  phone home, because there's no code path that tries to.
