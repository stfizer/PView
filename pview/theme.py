"""Windows 11 theming: palette, QSS, Mica backdrop, frameless native chrome."""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import winreg

from PySide6.QtCore import QObject, Qt, QPoint
from PySide6.QtGui import QColor

from . import settings as S

# ---------------- registry ----------------

def system_uses_dark() -> bool:
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        v, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
        return v == 0
    except OSError:
        return True


def system_accent() -> QColor:
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent")
        v, _ = winreg.QueryValueEx(k, "AccentColorMenu")
        v = int(v) & 0xFFFFFF
        r = v & 0xFF
        g = (v >> 8) & 0xFF
        b = (v >> 16) & 0xFF
        return QColor(r, g, b)
    except OSError:
        pass
    return QColor(0x00, 0x67, 0xC0)


# ---------------- palette ----------------

def current_theme() -> str:
    t = S.get("theme")
    if t == "system":
        return "dark" if system_uses_dark() else "light"
    return t if t in ("dark", "light") else "dark"


def palette() -> dict:
    dark = current_theme() == "dark"
    accent = system_accent()
    if dark:
        p = {
            "dark": True,
            "window": "#202020",
            "chrome": "rgba(255,255,255,0.048)",
            "card": "#2c2c2c",
            "card2": "#333333",
            "hover": "rgba(255,255,255,0.06)",
            "pressed": "rgba(255,255,255,0.03)",
            "stroke": "rgba(255,255,255,0.085)",
            "stroke_strong": "rgba(255,255,255,0.16)",
            "text": "#ffffff",
            "text2": "rgba(255,255,255,0.65)",
            "text3": "rgba(255,255,255,0.38)",
            "canvas": "#1d1d1d",
            "shadow": "rgba(0,0,0,0.55)",
            "tooltip_bg": "#3b3b3b",
        }
    else:
        p = {
            "dark": False,
            "window": "#f3f3f3",
            "chrome": "rgba(255,255,255,0.55)",
            "card": "#ffffff",
            "card2": "#fbfbfb",
            "hover": "rgba(0,0,0,0.045)",
            "pressed": "rgba(0,0,0,0.025)",
            "stroke": "rgba(0,0,0,0.075)",
            "stroke_strong": "rgba(0,0,0,0.14)",
            "text": "#1a1a1a",
            "text2": "rgba(0,0,0,0.6)",
            "text3": "rgba(0,0,0,0.36)",
            "canvas": "#f5f5f5",
            "shadow": "rgba(0,0,0,0.18)",
            "tooltip_bg": "#ffffff",
        }
    p["accent"] = accent.name()
    lum = 0.299 * accent.red() + 0.587 * accent.green() + 0.114 * accent.blue()
    p["accent_text"] = "#000000" if lum > 150 else "#ffffff"
    p["accent_hover"] = accent.lighter(112).name()
    p["accent_pressed"] = accent.darker(112).name()
    p["accent_soft"] = QColor(accent.red(), accent.green(), accent.blue(), 32).name(QColor.HexArgb)
    return p


def use_mica() -> bool:
    """Mica only when the app theme follows the system theme (avoids mismatch)."""
    return S.get("use_mica") and S.get("theme") == "system"


# ---------------- QSS ----------------

def build_qss(p: dict, icon_dir: str = "") -> str:
    d = icon_dir.replace("\\", "/") if icon_dir else ""
    url = lambda n: f"url({d}/{n}.svg)" if d else "none"  # noqa: E731
    return f"""
* {{
    font-family: "Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI";
    font-size: 10pt;
    outline: none;
}}
QMainWindow, QWidget#RootWindow {{
    background: {p['window']};
}}
QWidget {{
    color: {p['text']};
    selection-background-color: {p['accent']};
    selection-color: {p['accent_text']};
}}
QLabel {{ background: transparent; }}
QLabel#Dim {{ color: {p['text2']}; }}
QLabel#Faint {{ color: {p['text3']}; }}
QLabel#SectionTitle {{
    color: {p['accent']}; font-weight: 600; background: transparent;
    padding: 6px 0 2px 0;
}}
QLabel#OverlayTitle {{
    color: #ffffff; font-weight: 600; font-size: 10pt;
    background: rgba(0,0,0,0.45); border-radius: 6px; padding: 4px 10px;
}}

/* ---------- buttons ---------- */
QPushButton, QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 5px 10px;
    color: {p['text']};
}}
QToolButton {{
    padding: 5px;
}}
QPushButton:hover, QToolButton:hover {{ background: {p['hover']}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {p['pressed']}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {p['text3']}; }}
QToolButton:checked {{ background: {p['accent_soft']}; border-color: {p['accent']}; }}

QPushButton#Accent {{
    background: {p['accent']}; color: {p['accent_text']};
    border: none; border-radius: 6px; padding: 6px 16px; font-weight: 600;
}}
QPushButton#Accent:hover {{ background: {p['accent_hover']}; }}
QPushButton#Accent:pressed {{ background: {p['accent_pressed']}; }}

QPushButton#Card {{
    background: {p['card']}; border: 1px solid {p['stroke']};
    border-bottom: 1px solid {p['stroke_strong']}; border-radius: 6px;
}}
QPushButton#Card:hover {{ background: {p['card2']}; }}

QToolButton#WinBtn {{ border-radius: 0; padding: 0; width: 46px; height: 34px; }}
QToolButton#WinBtn:hover {{ background: rgba(255,255,255,0.06); }}
QToolButton#WinBtn:hover#CloseBtn {{ }}
QToolButton#CloseBtn:hover {{ background: #c42b1c; }}

QToolButton#IconOnly {{
    border-radius: 6px; padding: 6px;
}}

/* ---------- overlays on canvas ---------- */
QWidget#OverlayBar {{
    background: transparent;
}}
QFrame#OverlayCard {{
    background: rgba(32,32,32,0.72);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 10px;
}}
QFrame#OverlayCard QToolButton {{
    color: #ffffff; border-radius: 6px; padding: 5px;
}}
QFrame#OverlayCard QToolButton:hover {{ background: rgba(255,255,255,0.10); }}
QFrame#OverlayCard QToolButton:pressed {{ background: rgba(255,255,255,0.06); }}
QFrame#OverlayCard QToolButton:checked {{ background: {p['accent_soft']}; }}
QFrame#OverlayCard QLabel {{ color: #ffffff; }}
QFrame#SideArrow {{
    background: rgba(32,32,32,0.55); border-radius: 18px;
}}
QFrame#SideArrow QToolButton {{ color: #ffffff; }}

/* ---------- inputs ---------- */
QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {p['card']};
    border: 1px solid {p['stroke']};
    border-bottom: 1px solid {p['stroke_strong']};
    border-radius: 4px;
    padding: 4px 8px;
    color: {p['text']};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-bottom: 2px solid {p['accent']};
}}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{
    image: {url('chevdown')};
    width: 12px; height: 12px;
}}
QComboBox QAbstractItemView {{
    background: {p['card']};
    border: 1px solid {p['stroke']};
    border-radius: 8px;
    selection-background-color: {p['hover']};
    selection-color: {p['text']};
    outline: 0;
    padding: 4px;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background: transparent; border: none; width: 18px;
}}
QSpinBox::up-arrow {{ image: {url('chevup')}; width: 10px; height: 10px; }}
QSpinBox::down-arrow {{ image: {url('chevdown')}; width: 10px; height: 10px; }}

/* ---------- sliders ---------- */
QSlider {{ background: transparent; min-height: 20px; }}
QSlider::groove:horizontal {{
    height: 4px; border-radius: 2px;
    background: {p['stroke_strong']};
}}
QSlider::sub-page:horizontal {{ background: {p['accent']}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 18px; height: 18px; margin: -7px 0;
    border-radius: 9px; background: {p['accent']};
}}
QSlider::handle:horizontal:hover {{ background: {p['accent_hover']}; }}
QSlider::groove:vertical {{ width: 4px; border-radius: 2px; background: {p['stroke_strong']}; }}
QSlider::sub-page:vertical {{ background: {p['accent']}; border-radius: 2px; }}
QSlider::handle:vertical {{
    height: 18px; width: 18px; margin: 0 -7px;
    border-radius: 9px; background: {p['accent']};
}}

/* ---------- checkbox / radio ---------- */
QCheckBox, QRadioButton {{ background: transparent; spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 18px; height: 18px;
    border: 1px solid {p['stroke_strong']};
    background: {p['card']};
}}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ background: {p['hover']}; }}
QCheckBox::indicator:checked {{
    background: {p['accent']}; border-color: {p['accent']};
    image: {url('check')};
}}
QRadioButton::indicator:checked {{
    background: {p['accent']}; border-color: {p['accent']};
    image: {url('dot')};
}}

/* ---------- menus ---------- */
QMenu {{
    background: {p['card']};
    border: 1px solid {p['stroke']};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 7px 26px 7px 12px;
    border-radius: 5px;
    background: transparent;
}}
QMenu::item:selected {{ background: {p['hover']}; }}
QMenu::item:disabled {{ color: {p['text3']}; }}
QMenu::separator {{
    height: 1px; background: {p['stroke']};
    margin: 4px 8px;
}}
QMenu::icon {{ padding-left: 8px; }}

/* ---------- scrollbar ---------- */
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{
    background: transparent; width: 12px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {p['stroke_strong']}; border-radius: 4px;
    min-height: 30px; margin: 2px 3px;
}}
QScrollBar::handle:vertical:hover {{ background: {p['text3']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{
    background: transparent; height: 12px; margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {p['stroke_strong']}; border-radius: 4px;
    min-width: 30px; margin: 3px 2px;
}}
QScrollBar::handle:horizontal:hover {{ background: {p['text3']}; }}

/* ---------- lists / tables ---------- */
QListWidget, QTableWidget, QTreeWidget {{
    background: transparent;
    border: none;
    alternate-background-color: transparent;
}}
QListWidget::item, QTableWidget {{
    border-radius: 5px;
}}
QListWidget::item {{ padding: 6px 8px; }}
QListWidget::item:hover {{ background: {p['hover']}; }}
QListWidget::item:selected {{
    background: {p['accent_soft']};
    color: {p['text']};
}}
QTableWidget {{ gridline-color: {p['stroke']}; }}
QHeaderView::section {{
    background: transparent; color: {p['text2']};
    border: none; border-bottom: 1px solid {p['stroke']};
    padding: 6px 8px; font-weight: 600;
}}

/* ---------- progress ---------- */
QProgressBar {{
    background: {p['stroke']}; border: none; border-radius: 2px;
    min-height: 4px; max-height: 4px; text-align: right; color: transparent;
}}
QProgressBar::chunk {{ background: {p['accent']}; border-radius: 2px; }}

/* ---------- tabs / sidebar list ---------- */
QListWidget#NavList {{
    background: transparent; padding: 4px;
}}
QListWidget#NavList::item {{
    padding: 8px 12px; margin: 1px 0; border-radius: 6px;
}}
QListWidget#NavList::item:selected {{ background: {p['chrome']}; }}

QToolTip {{
    background: {p['tooltip_bg']};
    color: {p['text']};
    border: 1px solid {p['stroke']};
    border-radius: 4px;
    padding: 5px 8px;
}}
QDialog {{ background: {p['window']}; }}
QSplitter::handle {{ background: transparent; }}
"""


# ---------------- native Win11 chrome ----------------

WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
WM_SYSCOMMAND = 0x0112
SC_MAXIMIZE = 0xF032
HTCLIENT = 1
HTCAPTION = 2
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17
SM_CXSIZEFRAME = 32
SM_CXPADDEDBORDER = 92

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMWCP_ROUND = 2
DWMSBT_MAINWINDOW = 2

_user32 = ctypes.windll.user32
_dwmapi = ctypes.windll.dwmapi


def _frame_border() -> int:
    return (_user32.GetSystemMetrics(SM_CXSIZEFRAME) +
            _user32.GetSystemMetrics(SM_CXPADDEDBORDER))


def _dwm_set(hwnd: int, attr: int, val: int) -> bool:
    try:
        return _dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), ctypes.c_int(attr),
                                             ctypes.byref(ctypes.c_int(val)),
                                             ctypes.sizeof(ctypes.c_int)) == 0
    except Exception:
        return False


def apply_dwm_theme(hwnd: int, dark: bool, mica: bool):
    _dwm_set(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 1 if dark else 0)
    _dwm_set(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)
    if mica:
        _dwm_set(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_MAINWINDOW)


class _MSG(wt.MSG):
    pass


def _get_x(lparam: int) -> int:
    return ctypes.c_short(lparam & 0xFFFF).value


def _get_y(lparam: int) -> int:
    return ctypes.c_short((lparam >> 16) & 0xFFFF).value


class FramelessMixin:
    """Mixin for top-level QWidget windows: Win11 custom chrome with native
    resize borders, aero snap, taskbar behavior and optional Mica backdrop."""

    caption_height: int = 48
    _chrome_ready: bool = False

    def setup_frameless(self, caption_height: int = 48):
        self.caption_height = caption_height
        self.setWindowTitle("P view")
        self._chrome_ready = True
        self._cached_hwnd = 0

    def apply_theme_dwm(self, dark: bool, mica: bool):
        hwnd = int(self.winId())
        self._cached_hwnd = hwnd
        apply_dwm_theme(hwnd, dark, mica)

    def _is_maximized(self, hwnd: int) -> bool:
        return bool(_user32.IsZoomed(hwnd))

    def nativeEvent(self, etype, message):  # noqa: N802
        import os as _os
        if not getattr(self, "_chrome_ready", False):
            return False, 0
        try:
            msg = wt.MSG.from_address(int(message))
        except Exception:
            return False, 0
        if msg.message == WM_NCCALCSIZE and msg.wParam:
            hwnd = int(msg.hWnd)
            if _os.environ.get("PVIEW_DEBUG"):
                print("NCCALCSIZE wParam=1 -> returning True,0", flush=True)
            if self._is_maximized(hwnd) and not self.isFullScreen():
                bw = _frame_border()
                try:
                    rc = wt.RECT.from_address(int(msg.lParam))
                    rc.left += bw
                    rc.top += bw
                    rc.right -= bw
                    rc.bottom -= bw
                except Exception:
                    pass
            return True, 0
        if msg.message == WM_NCHITTEST:
            if self.isFullScreen():
                return False, 0
            x = _get_x(msg.lParam)
            y = _get_y(msg.lParam)
            rect = wt.RECT()
            _user32.GetWindowRect(int(msg.hWnd), ctypes.byref(rect))
            rel_x = x - rect.left
            rel_y = y - rect.top
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            bw = 0 if self._is_maximized(int(msg.hWnd)) else _frame_border()
            if bw:
                if rel_y < bw:
                    if rel_x < bw:
                        return True, HTTOPLEFT
                    if rel_x >= w - bw:
                        return True, HTTOPRIGHT
                    return True, HTTOP
                if rel_y >= h - bw:
                    if rel_x < bw:
                        return True, HTBOTTOMLEFT
                    if rel_x >= w - bw:
                        return True, HTBOTTOMRIGHT
                    return True, HTBOTTOM
                if rel_x < bw:
                    return True, HTLEFT
                if rel_x >= w - bw:
                    return True, HTRIGHT
            # caption zone
            gp = self.mapFromGlobal(QPoint(x, y))
            if rel_y < self.caption_height and self._hit_in_caption(gp):
                return True, HTCAPTION
            return False, 0
        return False, 0

    def _hit_in_caption(self, local_pt: QPoint) -> bool:
        """Return True if the point is in a draggable caption area (not on an
        interactive child widget)."""
        w = self.childAt(local_pt)
        while w is not None and w is not self:
            if getattr(w, "_caption_block", False):
                return False
            w = w.parentWidget()
        return True
