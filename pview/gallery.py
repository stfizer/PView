"""Filmstrip drawer and image-navigator dialog (thumbnail browsing)."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QFrame,
                               QHBoxLayout, QListWidget, QListWidgetItem,
                               QScrollArea, QVBoxLayout, QWidget)

from . import settings as S
from .i18n import tr
from .loader import THUMBS, ImageSource


def _thumb_key(source: ImageSource, entry) -> tuple:
    return (source.path, entry.key, id(source))


class FilmStrip(QFrame):
    """Bottom drawer with thumbnails of the current source.

    While the pointer stays over the strip it stays visible; after the
    pointer leaves it for `filmstrip_hide_secs` seconds it auto-hides.
    """

    jumpRequested = Signal(int)
    autoHideRequested = Signal()
    THUMB = 84

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FilmStrip")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._inner = QWidget()
        self._lay = QHBoxLayout(self._inner)
        self._lay.setContentsMargins(10, 8, 10, 8)
        self._lay.setSpacing(6)
        self._scroll.setWidget(self._inner)
        # keep the FilmStrip's rounded corners visible: the scroll viewport
        # and inner widget must not paint opaque rectangles over them
        self._scroll.viewport().setAutoFillBackground(False)
        self._inner.setAutoFillBackground(False)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._scroll)
        self._cells: list[ThumbCell] = []
        self._keys: list[tuple] = []
        self._src_id = 0
        self._hover = False
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._on_hide_timeout)
        self.setFixedHeight(self.THUMB + 22)

    # ---------- hover / auto-hide ----------
    def arm_autohide(self):
        """Called when the strip is shown: hide later if never hovered."""
        self._hide_timer.start(max(3, min(10, int(S.get("filmstrip_hide_secs") or 5)))
                               * 1000)

    def enterEvent(self, ev):
        self._hover = True
        self._hide_timer.stop()
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self._hover = False
        self._hide_timer.start(max(3, min(10, int(S.get("filmstrip_hide_secs") or 5)))
                               * 1000)
        super().leaveEvent(ev)

    def _on_hide_timeout(self):
        if not self._hover:
            self.autoHideRequested.emit()

    def wheelEvent(self, e):
        # vertical wheel -> horizontal strip scrolling
        d = e.angleDelta().y()
        hsb = self._scroll.horizontalScrollBar()
        if d:
            hsb.setValue(hsb.value() - d)
            e.accept()
            return
        e.ignore()

    def set_source(self, source: ImageSource | None, current: int = -1):
        for c in self._cells:
            c.setParent(None)
            c.deleteLater()
        self._cells.clear()
        self._keys.clear()
        if not source:
            self.hide()
            return
        self._src_id = id(source)
        for i, entry in enumerate(source.entries):
            cell = ThumbCell(i)
            cell.clicked.connect(self.jumpRequested)
            self._lay.addWidget(cell)
            self._cells.append(cell)
            key = _thumb_key(source, entry)
            self._keys.append(key)
            cell.attach(self._src_id, entry.key)
            THUMBS.request(key, source, entry)
        self._lay.addStretch(1)
        if current >= 0:
            self.highlight(current)

    def on_thumb_ready(self, key):
        if key[2] != self._src_id:
            return
        for c in self._cells:
            if c._entry_key == key[1]:
                pm = THUMBS.get(key)
                if pm:
                    c.set_pixmap(pm)

    def highlight(self, index: int):
        for i, c in enumerate(self._cells):
            c.set_active(i == index)
        if 0 <= index < len(self._cells):
            self._scroll.ensureWidgetVisible(self._cells[index], 60, 0)

    def retint(self, p: dict):
        self.setStyleSheet(f"""
            QFrame#FilmStrip {{
                background: rgba(28,28,28,0.86);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 12px;
            }}
            QScrollArea {{ background: transparent; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
        """)


class ThumbCell(QFrame):
    clicked = Signal(int)

    def __init__(self, index: int, size: int = FilmStrip.THUMB):
        super().__init__()
        self._index = index
        self._pm: QPixmap | None = None
        self._active = False
        self._src_id = 0
        self._entry_key = ""
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def attach(self, src_id: int, entry_key: str):
        self._src_id = src_id
        self._entry_key = entry_key

    def set_pixmap(self, pm: QPixmap):
        self._pm = pm
        self.update()

    def set_active(self, on: bool):
        self._active = on
        self.update()

    def mousePressEvent(self, e):
        self.clicked.emit(self._index)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = self.rect().adjusted(1, 1, -1, -1)
        pen = QPen(QColor(0, 120, 215) if self._active else QColor(255, 255, 255, 30))
        pen.setWidth(2 if self._active else 1)
        p.setPen(pen)
        p.setBrush(QColor(255, 255, 255, 12))
        p.drawRoundedRect(r, 6, 6)
        if self._pm and not self._pm.isNull():
            pm = self._pm.scaled(r.width() - 6, r.height() - 6,
                                 Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            x = r.x() + (r.width() - pm.width()) / 2
            y = r.y() + (r.height() - pm.height()) / 2
            p.drawPixmap(int(x), int(y), pm)
        p.end()


class NavigatorDialog(QDialog):
    """Grid thumbnail navigator (BandiView 'Select Image')."""

    jumpRequested = Signal(int)

    def __init__(self, source: ImageSource, current: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("navigator"))
        self.resize(880, 580)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        self._list = QListWidget()
        self._list.setViewMode(QListWidget.ViewMode.IconMode)
        self._list.setIconSize(QSize(120, 120))
        self._list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._list.setSpacing(10)
        self._list.setUniformItemSizes(True)
        lay.addWidget(self._list)
        self._items: list[QListWidgetItem] = []
        self._src_id = id(source)
        for i, entry in enumerate(source.entries):
            it = QListWidgetItem(entry.name)
            it.setData(Qt.ItemDataRole.UserRole, i)
            it.setSizeHint(QSize(136, 152))
            it.setToolTip(entry.key)
            self._list.addItem(it)
            self._items.append(it)
            key = _thumb_key(source, entry)
            # request() returns silently on a cache hit (no ready signal),
            # so pick up already-cached thumbnails here or cells stay blank
            pm = THUMBS.get(key)
            if pm is not None:
                it.setIcon(QIcon(pm))
            else:
                THUMBS.request(key, source, entry)
        if 0 <= current < len(self._items):
            self._list.setCurrentRow(current)
            self._list.scrollToItem(self._items[current],
                                    QAbstractItemView.ScrollHint.PositionAtCenter)
        self._list.itemDoubleClicked.connect(self._open)
        THUMBS.ready.connect(self._on_thumb)

    def _on_thumb(self, key):
        if key[2] != self._src_id:
            return
        pm = THUMBS.get(key)
        if pm is None:
            return
        for it in self._items:
            if it.toolTip() == key[1]:
                it.setIcon(QIcon(pm))
                return

    def _open(self, item):
        self.jumpRequested.emit(item.data(Qt.ItemDataRole.UserRole))
        self.accept()
