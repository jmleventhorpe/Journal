"""Local filesystem locations used by the desktop client - just its own
window/UI settings and icon now that journal.db lives on the server (see
server/app.py). Kept separate so both main.py (bootstrap) and window.py
(settings persistence) can import them without importing each other."""

from pathlib import Path

APP_DIR = Path.home() / ".simplejournal"
ICON_PATH = Path(__file__).resolve().parent / "assets" / "icon.svg"
