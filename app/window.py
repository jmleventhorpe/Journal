"""JournalWindow: the main application window - calendar, entry editor,
template mode, autosave, and window/splitter state persistence."""

import re

import requests

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QStatusBar,
    QSplitter,
    QToolButton,
    QMenu,
)
from PySide6.QtGui import QTextCharFormat, QFont, QImage, QTextDocument, QAction, QColor
from PySide6.QtCore import Qt, QDate, QTimer, QUrl, QSettings

import db as jdb
from paths import APP_DIR
from theme import FONT_OPTIONS, DEFAULT_FONT_POINT_SIZE
from editor import JournalTextEdit
from calendar_widget import JournalCalendar

IMG_SRC_RE = re.compile(r'src="([^"]+)"')


class JournalWindow(QMainWindow):
    YEAR_CHOICES = 10
    # "Special pages" are entries not tied to a date, edited in the exact
    # same editor as any day. Keyed by name; each entry is (button label,
    # server get function, server save function).
    SPECIAL_PAGES = {
        "template": ("Template", jdb.get_template, jdb.save_template),
        "info": ("Info", jdb.get_info, jdb.save_info),
    }

    def __init__(self, conn, key):
        super().__init__()
        self.conn = conn
        self.key = key
        self.current_date = QDate.currentDate()
        self.current_images = {}  # {resource_id: raw_bytes} for the entry on screen
        self.loading = False  # guard against autosave firing while we load an entry
        self.current_special_page = None  # None, "template", or "info" - see SPECIAL_PAGES
        self.settings = QSettings(str(APP_DIR / "settings.ini"), QSettings.IniFormat)

        self.setWindowTitle("Journal")
        self.resize(1000, 650)  # default; overridden by _restore_window_state() below if saved

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self.splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter)
        self.splitter.addWidget(self._build_calendar_panel())
        self.splitter.addWidget(self._build_editor_panel())
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([320, 680])

        self.status = QStatusBar()
        self.status.setSizeGripEnabled(False)
        self.setStatusBar(self.status)

        # Debounce autosave: restart a 1s timer on every keystroke
        self.autosave_timer = QTimer()
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.timeout.connect(self._save_current_entry)

        self._refresh_calendar_highlights()
        self._load_entry(self.current_date)
        self._restore_window_state()

    def _build_calendar_panel(self):
        self.calendar = JournalCalendar()
        self.calendar.setGridVisible(True)
        self.calendar.setMinimumWidth(260)
        self.calendar.setNavigationBarVisible(False)
        self.calendar.selectionChanged.connect(self._on_date_selected)
        # selectionChanged only fires when the selected date actually changes,
        # so it misses re-clicking the day already showing (e.g. to leave the
        # template view and go back to it); clicked fires on every click.
        self.calendar.clicked.connect(self._switch_to_date)

        weekend_fmt = QTextCharFormat()
        weekend_fmt.setForeground(QColor("#999999"))
        self.calendar.setWeekdayTextFormat(Qt.Saturday, weekend_fmt)
        self.calendar.setWeekdayTextFormat(Qt.Sunday, weekend_fmt)

        calendar_panel = QWidget()
        calendar_panel.setObjectName("calendarPanel")
        calendar_panel_layout = QVBoxLayout(calendar_panel)
        calendar_panel_layout.setContentsMargins(0, 0, 0, 0)
        calendar_panel_layout.setSpacing(0)
        calendar_panel_layout.addWidget(self._build_calendar_nav_bar())
        calendar_panel_layout.addWidget(self.calendar)
        return calendar_panel

    def _build_editor_panel(self):
        editor_container = QWidget()
        editor_layout = QVBoxLayout(editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(4)

        date_row = QWidget()
        date_row_layout = QHBoxLayout(date_row)
        date_row_layout.setContentsMargins(0, 0, 0, 0)

        self.date_label = QLabel("")
        self.date_label.setObjectName("dateLabel")
        self.date_label.setAlignment(Qt.AlignCenter)
        date_row_layout.addWidget(self.date_label, 1)

        self.import_template_button = QToolButton()
        self.import_template_button.setObjectName("importTemplateButton")
        self.import_template_button.setText("Import Template")
        self.import_template_button.clicked.connect(self._import_template)
        date_row_layout.addWidget(self.import_template_button)

        editor_layout.addWidget(date_row)

        self.editor = JournalTextEdit()
        self.editor.setObjectName("journalEditor")
        self.editor.setMinimumWidth(320)
        default_font = QFont()
        default_font.setFamilies(FONT_OPTIONS[0][1])
        default_font.setPointSize(DEFAULT_FONT_POINT_SIZE)
        self.editor.setFont(default_font)
        self.editor.document().setDefaultFont(default_font)
        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.imageDropped.connect(self._on_image_dropped)
        editor_layout.addWidget(self.editor)

        return editor_container

    def _restore_window_state(self):
        geometry = self.settings.value("windowGeometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        splitter_state = self.settings.value("splitterState")
        if splitter_state is not None:
            self.splitter.restoreState(splitter_state)

    def _on_image_dropped(self, resource_id, data):
        self.current_images[resource_id] = data

    def _import_template(self):
        try:
            html, images = jdb.get_template(self.conn, self.key)
        except requests.exceptions.RequestException as e:
            self.status.showMessage(f"Could not load template: {e}", 5000)
            return
        if not html and not images:
            self.status.showMessage("No template saved yet - click Template in the calendar to create one.", 3000)
            return

        doc = self.editor.document()
        for resource_id, raw_bytes in images.items():
            if resource_id not in self.current_images:
                img = QImage()
                img.loadFromData(raw_bytes)
                doc.addResource(QTextDocument.ImageResource, QUrl(resource_id), img)
                self.current_images[resource_id] = raw_bytes

        self.editor.textCursor().insertHtml(html)
        self.status.showMessage("Template imported", 1500)

    # ---------- calendar / navigation ----------

    def _build_calendar_nav_bar(self):
        bar = QWidget()
        bar.setObjectName("calendarNavBar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(4, 4, 4, 4)

        prev_button = QToolButton()
        prev_button.setText("◀")
        prev_button.setAutoRaise(True)
        prev_button.clicked.connect(self.calendar.showPreviousMonth)
        bar_layout.addWidget(prev_button)

        self.month_button = QToolButton()
        self.month_button.setAutoRaise(True)
        self.month_button.setPopupMode(QToolButton.InstantPopup)
        month_menu = QMenu(self.month_button)
        for month in range(1, 13):
            name = QDate(2000, month, 1).toString("MMMM")
            action = QAction(name, month_menu)
            action.triggered.connect(lambda checked=False, m=month: self._go_to_month(m))
            month_menu.addAction(action)
        self.month_button.setMenu(month_menu)
        bar_layout.addWidget(self.month_button)

        self.year_button = QToolButton()
        self.year_button.setAutoRaise(True)
        self.year_button.setPopupMode(QToolButton.InstantPopup)
        year_menu = QMenu(self.year_button)
        current_year = QDate.currentDate().year()
        for year in range(current_year, current_year + self.YEAR_CHOICES):
            action = QAction(str(year), year_menu)
            action.triggered.connect(lambda checked=False, y=year: self._go_to_year(y))
            year_menu.addAction(action)
        self.year_button.setMenu(year_menu)
        bar_layout.addWidget(self.year_button)

        bar_layout.addStretch()

        next_button = QToolButton()
        next_button.setText("▶")
        next_button.setAutoRaise(True)
        next_button.clicked.connect(self.calendar.showNextMonth)
        bar_layout.addWidget(next_button)

        self.template_button = QToolButton()
        self.template_button.setObjectName("templateButton")
        self.template_button.setAutoRaise(True)
        self.template_button.setCheckable(True)
        self.template_button.setText("Template")
        self.template_button.clicked.connect(lambda: self._show_special_page("template"))
        bar_layout.addWidget(self.template_button)

        self.info_button = QToolButton()
        self.info_button.setObjectName("infoButton")
        self.info_button.setAutoRaise(True)
        self.info_button.setCheckable(True)
        self.info_button.setText("Info")
        self.info_button.clicked.connect(lambda: self._show_special_page("info"))
        bar_layout.addWidget(self.info_button)

        self.special_page_buttons = {"template": self.template_button, "info": self.info_button}

        self.calendar.currentPageChanged.connect(self._on_calendar_page_changed)
        self._on_calendar_page_changed(self.calendar.yearShown(), self.calendar.monthShown())

        return bar

    def _go_to_month(self, month):
        self.calendar.setCurrentPage(self.calendar.yearShown(), month)

    def _go_to_year(self, year):
        self.calendar.setCurrentPage(year, self.calendar.monthShown())

    def _on_calendar_page_changed(self, year, month):
        self.month_button.setText(QDate(year, month, 1).toString("MMMM"))
        self.year_button.setText(str(year))

    def _on_date_selected(self):
        self._switch_to_date(self.calendar.selectedDate())

    def _switch_to_date(self, new_date):
        if self.current_special_page is None and new_date == self.current_date:
            return
        self._save_current_entry()  # flush any pending edits on whatever we're leaving
        self.current_date = new_date
        self._load_entry(new_date)

    def _refresh_calendar_highlights(self):
        dates = set()
        for date_str in jdb.list_entry_dates(self.conn):
            y, m, d = (int(x) for x in date_str.split("-"))
            dates.add(QDate(y, m, d))
        self.calendar.set_entry_dates(dates)

    def _show_special_page(self, page_name):
        self._save_current_entry()  # flush any pending edits on whatever we're leaving
        if self.current_special_page == page_name:
            self._load_entry(self.current_date)  # toggle back to the day we came from
        else:
            self._load_special_page(page_name)

    def _sync_special_page_buttons(self):
        """Force each button's visual checked state back to match
        current_special_page. Needed after a failed load: a checkable
        QToolButton auto-toggles its own checked state the instant it's
        clicked, before our slot even runs, so on an early-return failure
        the just-clicked button is left visually wrong unless we explicitly
        correct it back here."""
        for name, button in self.special_page_buttons.items():
            button.setChecked(name == self.current_special_page)

    def _load_entry(self, date: QDate):
        date_str = date.toString("yyyy-MM-dd")
        # Fetch before touching any UI state: if the server call fails, the
        # button/label/current_special_page must stay exactly as they were,
        # not end up half-switched to a page that never actually loaded.
        try:
            html, images = jdb.get_entry(self.conn, self.key, date_str)
        except requests.exceptions.RequestException as e:
            self.status.showMessage(f"Could not load {date_str}: {e}", 5000)
            self._sync_special_page_buttons()
            return

        self.loading = True
        self.current_special_page = None
        for button in self.special_page_buttons.values():
            button.setChecked(False)
        self.import_template_button.setVisible(True)
        self.date_label.setText(date.toString("dddd, d MMMM yyyy"))
        self._load_html_and_images(html, images)

    def _load_special_page(self, page_name):
        label, get_fn, _save_fn = self.SPECIAL_PAGES[page_name]
        try:
            html, images = get_fn(self.conn, self.key)
        except requests.exceptions.RequestException as e:
            self.status.showMessage(f"Could not load {label}: {e}", 5000)
            self._sync_special_page_buttons()
            return

        self.loading = True
        self.current_special_page = page_name
        for name, button in self.special_page_buttons.items():
            button.setChecked(name == page_name)
        self.import_template_button.setVisible(False)
        self.date_label.setText(label)
        self._load_html_and_images(html, images)

    def _load_html_and_images(self, html, images):
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
        html = self.editor.toHtml()

        # Only keep images actually still referenced in the current HTML,
        # so deleting an image from the text also drops it from storage.
        referenced_ids = set(IMG_SRC_RE.findall(html))
        images_to_save = {
            rid: data for rid, data in self.current_images.items() if rid in referenced_ids
        }

        try:
            if self.current_special_page is not None:
                _label, _get_fn, save_fn = self.SPECIAL_PAGES[self.current_special_page]
                save_fn(self.conn, self.key, html, images_to_save)
            else:
                date_str = self.current_date.toString("yyyy-MM-dd")
                plain_text_present = bool(self.editor.toPlainText().strip()) or images_to_save
                if plain_text_present:
                    jdb.save_entry(self.conn, self.key, date_str, html, images_to_save)
                else:
                    jdb.delete_entry(self.conn, date_str)
                self._refresh_calendar_highlights()
        except requests.exceptions.RequestException as e:
            self.status.showMessage(f"Could not save: {e}", 5000)
            return

        self.status.showMessage("Saved", 1500)

    def closeEvent(self, event):
        self._save_current_entry()
        self.settings.setValue("windowGeometry", self.saveGeometry())
        self.settings.setValue("splitterState", self.splitter.saveState())
        event.accept()
