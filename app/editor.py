"""JournalTextEdit: the rich-text editor used for day entries, the
template, and the info page - drag-drop image insertion plus a right-click
formatting menu (bold/italic/heading/size/font/image resize/spell check)."""

import re
import uuid
from pathlib import Path

from PySide6.QtWidgets import QTextEdit, QInputDialog
from PySide6.QtGui import (
    QTextCharFormat,
    QFont,
    QImage,
    QTextDocument,
    QAction,
    QTextCursor,
    QTextImageFormat,
    QColor,
)
from PySide6.QtCore import Qt, QUrl, Signal, QTimer
from spellchecker import SpellChecker

from theme import FONT_OPTIONS

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp"}

# Loaded once at import time (~80ms) and shared by every editor instance -
# in practice there's only ever one JournalTextEdit alive at a time anyway
# (the same widget is reused for dates, the template, and the info page).
_SPELL_CHECKER = SpellChecker()
_WORD_RE = re.compile(r"[A-Za-z']+")
SPELLCHECK_UNDERLINE_COLOR = QColor("#ff5555")


class JournalTextEdit(QTextEdit):
    """QTextEdit that accepts image files dropped anywhere in the panel
    (inserting them at the drop position), and provides its own right-click
    formatting menu (bold/italic/heading/size/font)."""

    FONT_SIZES = [10, 12, 14, 18, 24]
    HEADING_SIZES = [
        ("Heading 1", 18),
        ("Heading 2", 16),
        ("Heading 3", 14),
    ]
    # Presets target an on-screen *area* (in px^2) rather than a fixed width
    # or a percentage of the original, so a tall photo and a wide screenshot
    # picked at the same preset end up with a similar visual footprint.
    STANDARD_IMAGE_AREA = 400 * 400  # newly dropped images default to this
    IMAGE_RESIZE_PRESETS = [
        ("Small", STANDARD_IMAGE_AREA // 4),
        ("Standard", STANDARD_IMAGE_AREA),
        ("Large", round(STANDARD_IMAGE_AREA * 2.25)),
    ]

    imageDropped = Signal(str, bytes)  # resource_id, raw bytes

    def __init__(self):
        super().__init__()
        # Must be wired on self, not the viewport: QAbstractScrollArea
        # forwards viewport ContextMenu events up to self's contextMenuEvent,
        # so a CustomContextMenu policy set only on the viewport is never
        # consulted and Qt's native menu (Cut/Copy/Paste only) shows instead.
        # `pos` still arrives in viewport-local coordinates either way, which
        # is what cursorForPosition()/mapToGlobal() below expect.
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self._misspelled_spans = []  # [(start, end, word), ...] from the last scan
        self._session_dictionary = set()  # words added via "Add to Dictionary" (lowercase)
        self._applying_spellcheck_format = False  # guards against re-triggering ourselves
        # Detection always runs (right-click suggestions work regardless);
        # this only controls whether misspelled words get the red squiggly
        # underline. Off by default - toggle via the right-click menu.
        self._spellcheck_highlight_enabled = False
        self._spell_timer = QTimer()
        self._spell_timer.setSingleShot(True)
        self._spell_timer.timeout.connect(self._run_spellcheck)
        self.textChanged.connect(self._schedule_spellcheck)

    def canInsertFromMimeData(self, source):
        if self._dropped_image_urls(source):
            return True
        return super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        urls = self._dropped_image_urls(source)
        if not urls:
            super().insertFromMimeData(source)
            return

        for url in urls:
            path = url.toLocalFile()
            image = QImage(path)
            if image.isNull():
                continue
            resource_id = uuid.uuid4().hex
            self.document().addResource(QTextDocument.ImageResource, QUrl(resource_id), image)

            width, height = self._scaled_size_for_area(image.width(), image.height(), self.STANDARD_IMAGE_AREA)
            img_fmt = QTextImageFormat()
            img_fmt.setName(resource_id)
            img_fmt.setWidth(width)
            img_fmt.setHeight(height)
            self.textCursor().insertImage(img_fmt)

            with open(path, "rb") as f:
                self.imageDropped.emit(resource_id, f.read())

    @staticmethod
    def _dropped_image_urls(source):
        if not source.hasUrls():
            return []
        return [
            url for url in source.urls()
            if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in IMAGE_SUFFIXES
        ]

    # ---------- formatting ----------

    def _toggle_bold(self):
        fmt = QTextCharFormat()
        cursor = self.textCursor()
        fmt.setFontWeight(QFont.Bold if cursor.charFormat().fontWeight() != QFont.Bold else QFont.Normal)
        cursor.mergeCharFormat(fmt)
        self.setTextCursor(cursor)

    def _toggle_italic(self):
        fmt = QTextCharFormat()
        cursor = self.textCursor()
        fmt.setFontItalic(not cursor.charFormat().fontItalic())
        cursor.mergeCharFormat(fmt)
        self.setTextCursor(cursor)

    def _set_font_size(self, size):
        fmt = QTextCharFormat()
        fmt.setFontPointSize(size)
        cursor = self.textCursor()
        cursor.mergeCharFormat(fmt)
        self.setTextCursor(cursor)

    def _apply_heading(self, size):
        fmt = QTextCharFormat()
        fmt.setFontPointSize(size)
        fmt.setFontWeight(QFont.Bold)
        cursor = self.textCursor()
        cursor.mergeCharFormat(fmt)
        self.setTextCursor(cursor)

    def _set_font_family(self, families):
        fmt = QTextCharFormat()
        fmt.setFontFamilies(families)
        cursor = self.textCursor()
        cursor.mergeCharFormat(fmt)
        self.setTextCursor(cursor)

    # ---------- spell check ----------

    def _schedule_spellcheck(self):
        if self._applying_spellcheck_format:
            return  # this textChanged was caused by _run_spellcheck itself
        self._spell_timer.start(500)

    def _run_spellcheck(self):
        # Detection always runs, regardless of _spellcheck_highlight_enabled,
        # so right-click suggestions work even with highlighting off.
        text = self.toPlainText()
        matches = list(_WORD_RE.finditer(text))
        words = {m.group().lower() for m in matches} - self._session_dictionary
        unknown = _SPELL_CHECKER.unknown(words) if words else set()

        self._misspelled_spans = [
            (m.start(), m.end(), m.group()) for m in matches if m.group().lower() in unknown
        ]

        self._applying_spellcheck_format = True
        try:
            # Always clear first - covers both a normal rescan (previous
            # underlines may no longer be valid) and highlighting having
            # just been turned off (need to remove what's already there).
            clear_fmt = QTextCharFormat()
            clear_fmt.setUnderlineStyle(QTextCharFormat.NoUnderline)
            doc_cursor = QTextCursor(self.document())
            doc_cursor.select(QTextCursor.Document)
            doc_cursor.mergeCharFormat(clear_fmt)

            if not self._spellcheck_highlight_enabled:
                return

            spell_fmt = QTextCharFormat()
            spell_fmt.setUnderlineStyle(QTextCharFormat.SpellCheckUnderline)
            spell_fmt.setUnderlineColor(SPELLCHECK_UNDERLINE_COLOR)
            for start, end, _word in self._misspelled_spans:
                span_cursor = QTextCursor(self.document())
                span_cursor.setPosition(start)
                span_cursor.setPosition(end, QTextCursor.KeepAnchor)
                span_cursor.mergeCharFormat(spell_fmt)
        finally:
            self._applying_spellcheck_format = False

    def _toggle_spellcheck_highlight(self):
        self._spellcheck_highlight_enabled = not self._spellcheck_highlight_enabled
        self._run_spellcheck()

    def _misspelled_word_at(self, pos):
        """Returns (start, end, word) for the misspelled word at `pos`
        (from the most recent scan), or None if there isn't one there."""
        click_pos = self.cursorForPosition(pos).position()
        doc_len = self.document().characterCount()
        for start, end, word in self._misspelled_spans:
            if end > doc_len:
                continue  # stale span from before a full document reload
            if start <= click_pos <= end:
                return start, end, word
        return None

    @staticmethod
    def _spelling_suggestions(word, limit=5):
        candidates = _SPELL_CHECKER.candidates(word.lower())
        if not candidates:
            return []
        ranked = sorted(candidates, key=lambda w: -_SPELL_CHECKER.word_frequency.dictionary.get(w, 0))
        return ranked[:limit]

    def _apply_spelling_suggestion(self, start, end, suggestion, original):
        if original[:1].isupper():
            suggestion = suggestion[:1].upper() + suggestion[1:]
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        cursor.insertText(suggestion)

    def _add_to_dictionary(self, word):
        self._session_dictionary.add(word.lower())
        self._run_spellcheck()

    def _add_spelling_menu(self, menu, start, end, word):
        suggestions = self._spelling_suggestions(word)
        if suggestions:
            for suggestion in suggestions:
                action = QAction(suggestion, menu)
                action.triggered.connect(
                    lambda checked=False, s=start, e=end, sug=suggestion, w=word:
                        self._apply_spelling_suggestion(s, e, sug, w)
                )
                menu.addAction(action)
        else:
            no_suggestions = QAction("No suggestions", menu)
            no_suggestions.setEnabled(False)
            menu.addAction(no_suggestions)

        add_action = QAction(f'Add "{word}" to Dictionary', menu)
        add_action.triggered.connect(lambda checked=False, w=word: self._add_to_dictionary(w))
        menu.addAction(add_action)

    def _image_cursor_at(self, pos):
        """Returns a QTextCursor selecting exactly the image character at
        `pos`, or None if there isn't one there. Checks both sides of the
        nearest cursor position since images are single characters and the
        click may land fractionally before or after one."""
        click_cursor = self.cursorForPosition(pos)
        doc_len = self.document().characterCount()
        for direction in (QTextCursor.NextCharacter, QTextCursor.PreviousCharacter):
            probe = QTextCursor(click_cursor)
            probe.movePosition(direction, QTextCursor.KeepAnchor)
            if probe.position() == probe.anchor():
                continue  # at a document boundary - move was a no-op, nothing selected
            if not probe.charFormat().isImageFormat():
                continue
            start = min(probe.position(), probe.anchor())
            end = start + 1
            if end >= doc_len:
                continue  # defensive: never hand back an out-of-range position
            image_cursor = QTextCursor(self.document())
            image_cursor.setPosition(start)
            image_cursor.setPosition(end, QTextCursor.KeepAnchor)
            return image_cursor
        return None

    def _add_resize_image_menu(self, menu, image_cursor):
        img_fmt = image_cursor.charFormat().toImageFormat()
        resource_id = img_fmt.name()
        natural = self.document().resource(QTextDocument.ImageResource, QUrl(resource_id))
        natural_w, natural_h = natural.width(), natural.height()

        resize_menu = menu.addMenu("Resize Image")
        for label, target_area in self.IMAGE_RESIZE_PRESETS:
            action = QAction(label, resize_menu)
            action.triggered.connect(
                lambda checked=False, c=image_cursor, rid=resource_id, w=natural_w, h=natural_h, area=target_area:
                    self._resize_image_to_area(c, rid, w, h, area)
            )
            resize_menu.addAction(action)

        custom_action = QAction("Custom Width...", resize_menu)
        custom_action.triggered.connect(
            lambda checked=False, c=image_cursor, rid=resource_id, w=natural_w, h=natural_h:
                self._resize_image_custom(c, rid, w, h)
        )
        resize_menu.addAction(custom_action)

    @staticmethod
    def _scaled_size_for_area(natural_w, natural_h, target_area):
        natural_area = natural_w * natural_h
        if natural_area <= 0:
            return natural_w, natural_h
        scale = (target_area / natural_area) ** 0.5
        return max(1, round(natural_w * scale)), max(1, round(natural_h * scale))

    def _resize_image_to_area(self, image_cursor, resource_id, natural_w, natural_h, target_area):
        width, height = self._scaled_size_for_area(natural_w, natural_h, target_area)
        self._apply_image_size(image_cursor, resource_id, width, height)

    def _resize_image_custom(self, image_cursor, resource_id, natural_w, natural_h):
        current_w = round(image_cursor.charFormat().toImageFormat().width()) or natural_w
        width, ok = QInputDialog.getInt(
            self, "Resize Image", "Width (px):", current_w, 10, 4000, 1
        )
        if not ok:
            return
        height = round(width * (natural_h / natural_w)) if natural_w else width
        self._apply_image_size(image_cursor, resource_id, width, height)

    def _apply_image_size(self, image_cursor, resource_id, width, height):
        fmt = QTextImageFormat()
        fmt.setName(resource_id)
        fmt.setWidth(width)
        fmt.setHeight(height)
        image_cursor.mergeCharFormat(fmt)

    def _show_context_menu(self, pos):
        menu = self.createStandardContextMenu()
        menu.addSeparator()

        misspelled = self._misspelled_word_at(pos)
        if misspelled is not None:
            self._add_spelling_menu(menu, *misspelled)
            menu.addSeparator()

        image_cursor = self._image_cursor_at(pos)
        if image_cursor is not None:
            self._add_resize_image_menu(menu, image_cursor)
            menu.addSeparator()

        cursor = self.textCursor()
        char_fmt = cursor.charFormat()

        bold_action = QAction("Bold", menu)
        bold_action.setCheckable(True)
        bold_action.setChecked(char_fmt.fontWeight() == QFont.Bold)
        bold_action.triggered.connect(self._toggle_bold)
        menu.addAction(bold_action)

        italic_action = QAction("Italic", menu)
        italic_action.setCheckable(True)
        italic_action.setChecked(char_fmt.fontItalic())
        italic_action.triggered.connect(self._toggle_italic)
        menu.addAction(italic_action)

        menu.addSeparator()

        heading_menu = menu.addMenu("Heading")
        for label, size in self.HEADING_SIZES:
            heading_action = QAction(label, heading_menu)
            heading_action.triggered.connect(lambda checked=False, s=size: self._apply_heading(s))
            heading_menu.addAction(heading_action)

        size_menu = menu.addMenu("Font Size")
        for size in self.FONT_SIZES:
            size_action = QAction(str(size), size_menu)
            size_action.triggered.connect(lambda checked=False, s=size: self._set_font_size(s))
            size_menu.addAction(size_action)

        font_menu = menu.addMenu("Font")
        # An explicit per-character format is only set once the user picks a
        # font from this menu; until then fall back to the applied default
        # (currentFont() reflects the widget/document default font too).
        current_families = char_fmt.fontFamilies() or self.currentFont().families()
        current_primary = next(iter(current_families), None)
        for label, families in FONT_OPTIONS:
            font_action = QAction(label, font_menu)
            font_action.setCheckable(True)
            font_action.setChecked(current_primary == families[0])
            font_action.triggered.connect(lambda checked=False, f=families: self._set_font_family(f))
            font_menu.addAction(font_action)

        menu.addSeparator()
        highlight_action = QAction("Highlight Misspelled Words", menu)
        highlight_action.setCheckable(True)
        highlight_action.setChecked(self._spellcheck_highlight_enabled)
        highlight_action.triggered.connect(self._toggle_spellcheck_highlight)
        menu.addAction(highlight_action)

        menu.exec(self.viewport().mapToGlobal(pos))
