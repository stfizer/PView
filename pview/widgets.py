"""Reusable Win11-style widgets."""
from __future__ import annotations

from PySide6.QtCore import (QEasingCurve, QPoint, QPropertyAnimation, QRectF,
                            QSize, Qt, QTimer, Signal)
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QSizePolicy,
                               QToolButton, QVBoxLayout, QWidget)

from . import icons
from .theme import current_theme, palette

_TEXT_KEY = "text"


def _text_color() -> str:
    p = palette()
    return p["text"]


class IconButton(QToolButton):
    """Flat icon button that retints on theme change."""

    def __init__(self, name: str, tooltip: str = "", size: int = 36,
                 icon_size: int = 18, parent=None, checkable: bool = False):
        super().__init__(parent)
        self._icon_name = name
        self._icon_px = icon_size
        self._filled = False
        # never let WM_NCHITTEST claim an icon button as drag-caption area,
        # otherwise real mouse clicks never reach the button
        self._caption_block = True
        self.setFixedSize(size, size)
        self.setToolTip(tooltip)
        self.setCheckable(checkable)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet("QToolButton { border: none; background: transparent; }")
        self.retint()
        if tooltip:
            self.setToolTip(tooltip)

    def set_icon_name(self, name: str, filled: bool | None = None):
        self._icon_name = name
        if filled is not None:
            self._filled = filled
        self.retint()

    def retint(self):
        if getattr(self, "_static_icon", False):
            return   # icon set from a file (e.g. app icon); keep it
        self.setIcon(icons.icon(self._icon_name, _text_color(), 48, self._filled))
        self.setIconSize(QSize(self._icon_px, self._icon_px))


class CaptionButton(IconButton):
    """Window min/max/close button."""

    def __init__(self, name: str, tooltip: str, parent=None):
        super().__init__(name, tooltip, size=46, icon_size=17, parent=parent)
        self.setObjectName("WinBtn")
        self.setStyleSheet(
            "QToolButton { border: none; background: transparent; border-radius: 0; }"
            "QToolButton:hover { background: rgba(128,128,128,0.25); }")


class CloseButton(CaptionButton):
    def __init__(self, tooltip: str, parent=None):
        super().__init__("win-close", tooltip, parent=parent)
        self.setStyleSheet(
            "QToolButton { border: none; background: transparent; border-radius: 0; }"
            "QToolButton:hover { background: #c42b1c; color: white; }")


def retint_all(root: QWidget):
    for w in root.findChildren(IconButton):
        w.retint()


class Toast(QFrame):
    """Top-center transient notification, Photos-style."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("ToastCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._label = QLabel(self)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(18, 10, 18, 10)
        self._lay.addWidget(self._label)
        self.hide()
        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)

    def show_message(self, text: str, ms: int = 2200):
        self._label.setText(text)
        fm = self._label.fontMetrics()
        self.setFixedWidth(min(560, fm.horizontalAdvance(text) + 40))
        self.adjustSize()
        parent = self.parentWidget()
        if parent:
            x = (parent.width() - self.width()) // 2
            self.move(x, 64)
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        self._timer.start(ms)

    def _fade_out(self):
        self._anim.stop()
        self._anim.setDuration(300)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        try:
            self._anim.finished.disconnect()
        except Exception:
            pass
        self._anim.finished.connect(self.hide)
        self._anim.start()


def apply_toast_style(toast: Toast, p: dict):
    toast.setStyleSheet(f"""
        QFrame#ToastCard {{
            background: {p['card']};
            border: 1px solid {p['stroke']};
            border-radius: 8px;
        }}
        QFrame#ToastCard QLabel {{ background: transparent; color: {p['text']}; }}
    """)
