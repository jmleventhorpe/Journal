"""App-wide fonts and the Qt stylesheet."""

# App-wide chrome font: a UI-optimized sans stack, falling back to whatever's
# actually installed (Inter/Segoe UI are rarely present on Linux).
UI_FONT_FAMILIES = ["Inter", "Segoe UI", "Noto Sans", "DejaVu Sans", "sans-serif"]

# Offered in the editor's right-click "Font" menu. Each is a research-backed
# readable typeface (Georgia and Verdana are purpose-built for on-screen
# reading; Inter for UI text) with a fallback stack for whatever's installed.
FONT_OPTIONS = [
    ("Verdana (Wide Sans)", ["Verdana", "DejaVu Sans", "Liberation Sans", "sans-serif"]),
    ("Georgia (Serif)", ["Georgia", "Noto Serif", "DejaVu Serif", "Liberation Serif", "serif"]),
    ("Inter (Sans)", ["Inter", "Segoe UI", "Noto Sans", "DejaVu Sans", "sans-serif"]),
]
DEFAULT_FONT_POINT_SIZE = 12

# A dark theme in the vein of VS Code's "Dark+": near-black editor/panel
# surfaces, a slightly lighter chrome tone for chrome/sidebar-like widgets,
# and the same blue accent VS Code uses for focus/selection.
STYLE_SHEET = """
QWidget {
    background-color: #1e1e1e;
    color: #cccccc;
    font-size: 10pt;
}

QMainWindow {
    background-color: #1e1e1e;
}

QLabel#dateLabel {
    font-size: 15pt;
    font-weight: 600;
    color: #ffffff;
    padding: 10px 4px;
}

/* --- Calendar --- */
QWidget#calendarPanel {
    background-color: #252526;
    border: 1px solid #3c3c3c;
    border-radius: 8px;
}
QWidget#calendarNavBar {
    background-color: #2d2d2d;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    border-bottom: 1px solid #3c3c3c;
}
QWidget#calendarNavBar QToolButton {
    color: #cccccc;
    background-color: transparent;
    border: none;
    border-radius: 4px;
    padding: 4px 8px;
    font-weight: 600;
}
QWidget#calendarNavBar QToolButton:hover {
    background-color: #37373d;
}
QWidget#calendarNavBar QToolButton#templateButton:checked,
QWidget#calendarNavBar QToolButton#infoButton:checked {
    background-color: #007acc;
    color: #ffffff;
}
QWidget#calendarNavBar QToolButton#templateButton:checked:hover,
QWidget#calendarNavBar QToolButton#infoButton:checked:hover {
    background-color: #1177bb;
}
QCalendarWidget {
    background-color: transparent;
    border: none;
}
QCalendarWidget QAbstractItemView:enabled {
    background-color: #252526;
    color: #cccccc;
    gridline-color: #333333;
    selection-background-color: #094771;
    selection-color: #ffffff;
}
QCalendarWidget QAbstractItemView:disabled {
    color: #656565;
}

/* --- Editor --- */
QTextEdit#journalEditor {
    background-color: #1e1e1e;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    padding: 16px;
    selection-background-color: #264f78;
    selection-color: #ffffff;
}

QToolButton#importTemplateButton {
    background-color: #0e639c;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 4px 10px;
    font-weight: 600;
}
QToolButton#importTemplateButton:hover {
    background-color: #1177bb;
}

/* --- Splitter --- */
QSplitter::handle {
    background-color: #3c3c3c;
}
QSplitter::handle:horizontal {
    width: 6px;
}
QSplitter::handle:hover {
    background-color: #007acc;
}

/* --- Status bar --- */
QStatusBar {
    background-color: #252526;
    color: #a0a0a0;
    border-top: 1px solid #3c3c3c;
}

/* --- Buttons / inputs (password dialogs) --- */
QPushButton {
    background-color: #0e639c;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #1177bb;
}
QPushButton:pressed {
    background-color: #0d5789;
}

QLineEdit {
    background-color: #3c3c3c;
    color: #cccccc;
    border: 1px solid #3c3c3c;
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: #264f78;
}
QLineEdit:focus {
    border: 1px solid #007acc;
}

QDialog {
    background-color: #252526;
}

/* --- Menus --- */
QMenu {
    background-color: #252526;
    border: 1px solid #3c3c3c;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #094771;
}
QMenu::separator {
    height: 1px;
    background: #3c3c3c;
    margin: 4px 8px;
}

/* --- Scrollbars --- */
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #424242;
    border-radius: 5px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #4f4f4f;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""
