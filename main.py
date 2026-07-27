"""
SimpleJournal - a small encrypted, offline, local-only journal.

Run with: python main.py

Everything lives in one SQLite file at ~/.simplejournal/journal.db.
No network code anywhere in this app - nothing to disable, nothing
for any other tool to connect to.
"""

import sys
import os
import re
import uuid
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QCalendarWidget,
    QTextEdit,
    QToolBar,
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QFileDialog,
    QStatusBar,
)
from PySide6.QtGui import QTextCharFormat, QFont, QImage, QTextDocument, QAction, QTextCursor
from PySide6.QtCore import Qt, QDate, QTimer, QUrl

import db as jdb

APP_DIR = Path.home() / ".simplejournal"
DB_PATH = APP_DIR / "journal.db"

IMG_SRC_RE = re.compile(r'src="([^"]+)"')


# ---------------------------------------------------------------- Password dialogs

class SetPasswordDialog(QDialog):
    """Shown once, the very first time the journal is created."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Create your journal password")
        self.setMinimumWidth(380)
        self.password = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "This password encrypts your journal.\n"
            "There is no recovery - if you lose it, your entries cannot be read again."
        ))

        self.pw1 = QLineEdit()
        self.pw1.setEchoMode(QLineEdit.Password)
        self.pw1.setPlaceholderText("Password")
        layout.addWidget(self.pw1)

        self.pw2 = QLineEdit()
        self.pw2.setEchoMode(QLineEdit.Password)
        self.pw2.setPlaceholderText("Confirm password")
        layout.addWidget(self.pw2)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #c0392b;")
        layout.addWidget(self.error_label)

        btn = QPushButton("Create Journal")
        btn.clicked.connect(self._submit)
        layout.addWidget(btn)

    def _submit(self):
        p1, p2 = self.pw1.text(), self.pw2.text()
        if len(p1) < 4:
            self.error_label.setText("Password must be at least 4 characters.")
            return
        if p1 != p2:
            self.error_label.setText("Passwords don't match.")
            return
        self.password = p1
        self.accept()


class UnlockDialog(QDialog):
    """Shown every launch after the journal already exists."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Unlock journal")
        self.setMinimumWidth(320)
        self.password = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Enter your journal password:"))

        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        self.pw.returnPressed.connect(self._submit)
        layout.addWidget(self.pw)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #c0392b;")
        layout.addWidget(self.error_label)

        btn = QPushButton("Unlock")
        btn.clicked.connect(self._submit)
        layout.addWidget(btn)

        self.pw.setFocus()

    def _submit(self):
        self.password = self.pw.text()
        self.accept()

    def show_error(self, msg):
        self.error_label.setText(msg)
        self.pw.clear()
        self.pw.setFocus()


# ---------------------------------------------------------------- Main window

class JournalWindow(QMainWindow):
    def __init__(self, conn, key):
        super().__init__()
        self.conn = conn
        self.key = key
        self.current_date = QDate.currentDate()
        self.current_images = {}  # {resource_id: raw_bytes} for the entry on screen
        self.loading = False  # guard against autosave firing while we load an entry

        self.setWindowTitle("SimpleJournal")
        self.resize(1000, 650)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        # --- Calendar (left) ---
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.setMaximumWidth(320)
        self.calendar.selectionChanged.connect(self._on_date_selected)
        layout.addWidget(self.calendar)

        # --- Editor (right) ---
        editor_container = QWidget()
        editor_layout = QVBoxLayout(editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)

        self.date_label = QLabel("")
        self.date_label.setStyleSheet("font-size: 16px; font-weight: bold; padding: 4px;")
        editor_layout.addWidget(self.date_label)

        self.editor = QTextEdit()
        self.editor.textChanged.connect(self._on_text_changed)
        editor_layout.addWidget(self.editor)

        layout.addWidget(editor_container)

        self._build_toolbar()

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        # Debounce autosave: restart a 1s timer on every keystroke
        self.autosave_timer = QTimer()
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.timeout.connect(self._save_current_entry)

        self._refresh_calendar_highlights()
        self._load_entry(self.current_date)

    # ---------- toolbar ----------

    def _build_toolbar(self):
        toolbar = QToolBar("Formatting")
        self.addToolBar(toolbar)

        bold_action = QAction("Bold", self)
        bold_action.setCheckable(True)
        bold_action.triggered.connect(self._toggle_bold)
        toolbar.addAction(bold_action)

        italic_action = QAction("Italic", self)
        italic_action.setCheckable(True)
        italic_action.triggered.connect(self._toggle_italic)
        toolbar.addAction(italic_action)

        toolbar.addSeparator()

        image_action = QAction("Insert Image", self)
        image_action.triggered.connect(self._insert_image)
        toolbar.addAction(image_action)

        toolbar.addSeparator()

        lock_action = QAction("Lock", self)
        lock_action.triggered.connect(self._lock_now)
        toolbar.addAction(lock_action)

    def _toggle_bold(self):
        fmt = QTextCharFormat()
        cursor = self.editor.textCursor()
        fmt.setFontWeight(QFont.Bold if cursor.charFormat().fontWeight() != QFont.Bold else QFont.Normal)
        cursor.mergeCharFormat(fmt)
        self.editor.setTextCursor(cursor)

    def _toggle_italic(self):
        fmt = QTextCharFormat()
        cursor = self.editor.textCursor()
        fmt.setFontItalic(not cursor.charFormat().fontItalic())
        cursor.mergeCharFormat(fmt)
        self.editor.setTextCursor(cursor)

    def _insert_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Insert Image", str(Path.home()), "Images (*.png *.jpg *.jpeg *.gif *.bmp)"
        )
        if not path:
            return
        image = QImage(path)
        if image.isNull():
            QMessageBox.warning(self, "Insert Image", "Could not load that image.")
            return

        resource_id = uuid.uuid4().hex
        self.editor.document().addResource(
            QTextDocument.ImageResource, QUrl(resource_id), image
        )
        cursor = self.editor.textCursor()
        cursor.insertImage(resource_id)

        with open(path, "rb") as f:
            self.current_images[resource_id] = f.read()

    # ---------- calendar / navigation ----------

    def _on_date_selected(self):
        new_date = self.calendar.selectedDate()
        if new_date == self.current_date:
            return
        self._save_current_entry()  # flush any pending edits on the day we're leaving
        self.current_date = new_date
        self._load_entry(new_date)

    def _refresh_calendar_highlights(self):
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Bold)
        fmt.setForeground(Qt.darkGreen)
        # Clear then reapply - QCalendarWidget has no easy "clear all" so
        # we just reset the currently visible month range generously.
        default_fmt = QTextCharFormat()
        for offset in range(-370, 370):
            d = QDate.currentDate().addDays(offset)
            self.calendar.setDateTextFormat(d, default_fmt)

        for date_str in jdb.list_entry_dates(self.conn):
            y, m, d = (int(x) for x in date_str.split("-"))
            self.calendar.setDateTextFormat(QDate(y, m, d), fmt)

    def _load_entry(self, date: QDate):
        self.loading = True
        date_str = date.toString("yyyy-MM-dd")
        self.date_label.setText(date.toString("dddd, d MMMM yyyy"))

        html, images = jdb.get_entry(self.conn, self.key, date_str)
        self.current_images = images

        self.editor.clear()
        doc = self.editor.document()
        for resource_id, raw_bytes in images.items():
            img = QImage()
            img.loadFromData(raw_bytes)
            doc.addResource(QTextDocument.ImageResource, QUrl(resource_id), img)

        if html:
            self.editor.setHtml(html)
        self.loading = False
        self.status.showMessage("")

    # ---------- saving ----------

    def _on_text_changed(self):
        if self.loading:
            return
        self.autosave_timer.start(1000)  # 1s after the user stops typing

    def _save_current_entry(self):
        self.autosave_timer.stop()
        date_str = self.current_date.toString("yyyy-MM-dd")
        html = self.editor.toHtml()

        # Only keep images actually still referenced in the current HTML,
        # so deleting an image from the text also drops it from storage.
        referenced_ids = set(IMG_SRC_RE.findall(html))
        images_to_save = {
            rid: data for rid, data in self.current_images.items() if rid in referenced_ids
        }

        plain_text_present = bool(self.editor.toPlainText().strip()) or images_to_save
        if plain_text_present:
            jdb.save_entry(self.conn, self.key, date_str, html, images_to_save)
        else:
            jdb.delete_entry(self.conn, date_str)

        self._refresh_calendar_highlights()
        self.status.showMessage("Saved", 1500)

    def closeEvent(self, event):
        self._save_current_entry()
        event.accept()

    def _lock_now(self):
        self._save_current_entry()
        self.close()
        launch()  # re-prompt for password from scratch


# ---------------------------------------------------------------- Entry point

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
    launch()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
