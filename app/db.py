"""
HTTP client for the Journal server (server/app.py) - the same public
function signatures as the original sqlite-based db.py (now server/db.py),
so main.py/window.py don't need to know or care that entries live on a
server instead of a local file.

`conn` is an authenticated requests.Session (see connect()). `key` is kept
only for call-site compatibility with the desktop app's existing code -
the server holds the real decryption key in memory, scoped to the session
cookie already carried inside `conn`, so these functions never see it.

Network failures beyond unlock() (which is called in a retry loop) are
intentionally left to raise rather than fail silently - a broken save
should be loud, not invisible.
"""

import base64

import requests


def connect(base_url: str):
    session = requests.Session()
    session.base_url = base_url.rstrip("/")
    return session


def is_initialized(conn) -> bool:
    resp = conn.get(f"{conn.base_url}/api/status", timeout=10)
    resp.raise_for_status()
    return resp.json()["initialized"]


def setup_password(conn, password: str):
    """Returns a truthy placeholder "key" on success, or None if the
    journal was already set up."""
    resp = conn.post(f"{conn.base_url}/api/setup", json={"password": password}, timeout=10)
    if resp.status_code != 200:
        return None
    return True


def unlock(conn, password: str):
    """Returns a truthy placeholder "key" if the password is correct, else
    None (also on a network failure, so the login retry loop in launch()
    doesn't crash the app over a flaky connection)."""
    try:
        resp = conn.post(f"{conn.base_url}/login", json={"password": password}, timeout=10)
    except requests.exceptions.RequestException:
        return None
    if resp.status_code != 200:
        return None
    return True


def list_entry_dates(conn) -> set:
    resp = conn.get(f"{conn.base_url}/api/dates", timeout=10)
    resp.raise_for_status()
    return set(resp.json()["dates"])


def get_entry(conn, key, date: str):
    """Returns (html_text, {image_id: raw_bytes}) or (None, {}) if no entry exists."""
    resp = conn.get(f"{conn.base_url}/entries/{date}", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    images = {rid: base64.b64decode(b64) for rid, b64 in data["images"].items()}
    return data["html"], images


def save_entry(conn, key, date: str, html_text: str, images: dict):
    payload = {
        "html": html_text,
        "images": {rid: base64.b64encode(raw).decode("ascii") for rid, raw in images.items()},
    }
    resp = conn.post(f"{conn.base_url}/entries/{date}", json=payload, timeout=30)
    resp.raise_for_status()


def delete_entry(conn, date: str):
    resp = conn.delete(f"{conn.base_url}/entries/{date}", timeout=10)
    resp.raise_for_status()


def get_template(conn, key):
    """Returns (html_text, {image_id: raw_bytes}) or (None, {}) if no template is saved."""
    resp = conn.get(f"{conn.base_url}/template", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    images = {rid: base64.b64decode(b64) for rid, b64 in data["images"].items()}
    return data["html"], images


def save_template(conn, key, html_text: str, images: dict):
    payload = {
        "html": html_text,
        "images": {rid: base64.b64encode(raw).decode("ascii") for rid, raw in images.items()},
    }
    resp = conn.post(f"{conn.base_url}/template", json=payload, timeout=30)
    resp.raise_for_status()


def get_info(conn, key):
    """Returns (html_text, {image_id: raw_bytes}) or (None, {}) if no info page is saved."""
    resp = conn.get(f"{conn.base_url}/info", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    images = {rid: base64.b64decode(b64) for rid, b64 in data["images"].items()}
    return data["html"], images


def save_info(conn, key, html_text: str, images: dict):
    payload = {
        "html": html_text,
        "images": {rid: base64.b64encode(raw).decode("ascii") for rid, raw in images.items()},
    }
    resp = conn.post(f"{conn.base_url}/info", json=payload, timeout=30)
    resp.raise_for_status()
