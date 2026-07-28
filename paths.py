"""Filesystem locations used by the app - kept separate so both main.py
(bootstrap) and window.py (settings persistence) can import them without
importing each other."""

from pathlib import Path

APP_DIR = Path.home() / ".simplejournal"
DB_PATH = APP_DIR / "journal.db"
ICON_PATH = Path(__file__).resolve().parent / "assets" / "icon.svg"
