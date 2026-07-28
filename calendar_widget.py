"""JournalCalendar: a QCalendarWidget that marks days with a journal entry
using a small dot below the date number."""

from PySide6.QtWidgets import QCalendarWidget
from PySide6.QtGui import QColor, QPainter
from PySide6.QtCore import Qt, QRect


class JournalCalendar(QCalendarWidget):
    """Calendar that marks days with a journal entry using a small dot
    below the date number, rather than recoloring/bolding the text."""

    ENTRY_DOT_COLOR = QColor("#89d185")

    def __init__(self):
        super().__init__()
        self.entry_dates = set()

    def set_entry_dates(self, dates):
        self.entry_dates = set(dates)
        self.updateCells()

    def paintCell(self, painter, rect, date):
        super().paintCell(painter, rect, date)
        if date not in self.entry_dates:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.ENTRY_DOT_COLOR)
        dot_size = 6
        cx = rect.center().x()
        cy = rect.bottom() - 7
        painter.drawEllipse(QRect(cx - dot_size // 2, cy - dot_size // 2, dot_size, dot_size))
        painter.restore()
