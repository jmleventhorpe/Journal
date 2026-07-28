"""
Journal - a small encrypted, offline, local-only journal.

Run with: python main.py

Everything lives in one SQLite file at ~/.simplejournal/journal.db.
No network code anywhere in this app - nothing to disable, nothing
for any other tool to connect to.
"""

import sys

from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtGui import QFont, QIcon

import db as jdb
from paths import APP_DIR, DB_PATH, ICON_PATH
from theme import STYLE_SHEET, UI_FONT_FAMILIES
from dialogs import SetPasswordDialog, UnlockDialog
from window import JournalWindow


def launch():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    conn = jdb.connect(str(DB_PATH))

    if not jdb.is_initialized(conn):
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
                dialog.show_error("Incorrect password.")

    global _window
    _window = JournalWindow(conn, key)
    _window.show()


_window = None  # kept alive here - without this, the window is garbage-collected
                # right after show() returns, closing it before it ever renders


def main():
    app = QApplication(sys.argv)
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
