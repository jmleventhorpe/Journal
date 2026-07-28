"""JournalTextEdit: the rich-text editor used for both day entries and the
template - drag-drop image insertion plus a right-click formatting menu
(bold/italic/heading/size/font/image resize)."""

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
)
from PySide6.QtCore import Qt, QUrl, Signal

from theme import FONT_OPTIONS

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp"}


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

        menu.exec(self.viewport().mapToGlobal(pos))
