"""
Journal - a small encrypted journal, backed by a Flask server (see
server/app.py) that owns the actual journal.db and does all encryption
and decryption. This app is just a client - it never touches the
database or a decryption key directly.

Run with: python main.py
Point it at your server via the JOURNAL_SERVER_URL environment variable
(defaults to http://localhost:8420 for local dev against `python server/app.py`).
"""

import os
import sys

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from PySide6.QtGui import QFont, QIcon
import requests

import db as jdb
from paths import APP_DIR, ICON_PATH
from theme import STYLE_SHEET, UI_FONT_FAMILIES
from dialogs import SetPasswordDialog, UnlockDialog
from window import JournalWindow

SERVER_URL = os.environ.get("JOURNAL_SERVER_URL", "http://localhost:8420")


def launch():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    conn = jdb.connect(SERVER_URL)

    try:
        initialized = jdb.is_initialized(conn)
    except requests.exceptions.RequestException:
        QMessageBox.critical(
            None,
            "Can't reach Journal server",
            f"Could not connect to {SERVER_URL}.\n\n"
            "Check that the server is running and reachable, or set the "
            "JOURNAL_SERVER_URL environment variable to point at it.",
        )
        sys.exit(1)

    if not initialized:
        dialog = SetPasswordDialog()
        if dialog.exec() != QDialog.Accepted:
            sys.exit(0)
        key = jdb.setup_password(conn, dialog.password)
    else:
        key = None
        dialog = UnlockDialog()
        while key is None:
            if dialog.exec() != QDialog.Accepted:
                sys.exit(0)
            key = jdb.unlock(conn, dialog.password)
            if key is None:
                dialog.show_error("Incorrect password (or server unreachable).")

    global _window
    _window = JournalWindow(conn, key)
    _window.show()


_window = None  # kept alive here - without this, the window is garbage-collected
                # right after show() returns, closing it before it ever renders


def main():
    app = QApplication(sys.argv)
    # Without these, Qt reports the running process's identity as "python3"
    # (the actual interpreter binary) rather than the app itself, so
    # GNOME/Wayland's dock falls back to showing "python3" instead of
    # matching this window to journal.desktop for its name/icon.
    app.setApplicationName("Journal")
    app.setDesktopFileName("journal")
    app.setWindowIcon(QIcon(str(ICON_PATH)))
    ui_font = QFont()
    ui_font.setFamilies(UI_FONT_FAMILIES)
    ui_font.setPointSize(10)
    app.setFont(ui_font)
    app.setStyleSheet(STYLE_SHEET)
    launch()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
