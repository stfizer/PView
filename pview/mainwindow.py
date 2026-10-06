"""P view main window: Win11 Photos-style chrome + full viewer logic."""
from __future__ import annotations

import ctypes
import json
import os
import random
import shutil
import subprocess
import sys

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (QAction, QCursor, QDesktopServices, QGuiApplication,
                           QFont, QImage, QKeySequence, QPainter, QPixmap,
                           QShortcut, QTransform)
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QFrame,
                               QHBoxLayout, QInputDialog, QLabel, QMenu,
                               QMessageBox, QSizePolicy, QSlider, QSpinBox,
                               QStackedWidget, QToolButton, QVBoxLayout,
                               QWidget)

from . import APP_NAME, icons, settings as S
from .archive import (IMG_EXTS, RAW_EXTS, ARCHIVE_EXTS, Entry, ImageSource,
                      WrongPasswordError, ext_of, is_archive_path,
                      is_image_name)
from .dialogs import (AdjustDialog, BookmarkManagerDialog, ConvertDialog,
                      PasswordDialog, SettingsDialog, WallpaperDialog)
from .gallery import FilmStrip, NavigatorDialog
from .i18n import tr, set_language
from .infopanel import InfoPanel
from .loader import DOC_CACHE, THUMBS, ImageDoc, load_doc
from .theme import (FramelessMixin, apply_dwm_theme, build_qss, palette,
                    use_mica)
from .viewer import ImageViewCanvas, WebtoonView
from .widgets import (CaptionButton, CloseButton, IconButton, Toast,
                      apply_toast_style, retint_all)

CAPTION_H = 46


def _app_icon() -> "QIcon":
    """The real application icon (assets/pview.ico), frozen-aware.

    PyInstaller 6 onedir packs datas under <exe>/_internal (sys._MEIPASS).
    """
    from PySide6.QtGui import QIcon
    candidates = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            candidates.append(os.path.join(meipass, "assets", "pview.ico"))
        candidates.append(os.path.join(os.path.dirname(sys.executable),
                                       "assets", "pview.ico"))
        candidates.append(os.path.join(os.path.dirname(sys.executable),
                                       "_internal", "assets", "pview.ico"))
    else:
        candidates.append(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "assets", "pview.ico"))
    for p in candidates:
        if p and os.path.exists(p):
            return QIcon(p)
    return QIcon()


def _store_path(name: str) -> str:
    from .settings import app_data_dir
    return os.path.join(app_data_dir(), name)


def _load_json(name: str, default):
    try:
        with open(_store_path(name), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(name: str, data):
    try:
        with open(_store_path(name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


class MainWindow(QWidget, FramelessMixin):
    _docReady = Signal(object, int, int, int)  # doc, index, token, request_kind

    def nativeEvent(self, etype, message):  # noqa: N802
        # Must be defined on the class itself for PySide6 to register the
        # virtual override (mixin-provided overrides are not dispatched).
        return FramelessMixin.nativeEvent(self, etype, message)

    def __init__(self, open_path: str = ""):
        super().__init__()
        self.setObjectName("RootWindow")
        self.setWindowIcon(_app_icon())
        self.setup_frameless(CAPTION_H)
        self.setAcceptDrops(True)
        self.setMinimumSize(560, 380)

        self._source: ImageSource | None = None
        self._idx = -1
        self._doc: ImageDoc | None = None
        self._token = 0
        self._pending: set = set()
        self._webtoon_mode = False
        self._double_mode = ""          # "", "l2r", "r2l"
        self._fx: dict = {}
        self._slideshow_on = False
        self._fullscreen = False
        self._bars_hidden = False
        self._bookmarks = _load_json("bookmarks.json", [])
        self._recents = _load_json("recents.json", [])
        self._positions = _load_json("positions.json", {})
        self._filter_mode = "none"

        lang = S.get("lang")
        if not lang:
            import locale
            try:
                loc = locale.getlocale()[0] or ""
                lang = "zh" if "Chinese" in loc or "China" in loc else "en"
            except Exception:
                lang = "en"
        set_language(lang)

        self._build_ui()
        self._build_shortcuts()

        self._docReady.connect(self._on_doc_ready)

        self._slideshow_timer = QTimer(self)
        self._slideshow_timer.timeout.connect(self._slideshow_step)

        self._ss_effect = "none"
        self.apply_theme()

        if S.get("remember_window"):
            geo = S.get("geometry")
            if geo:
                try:
                    from PySide6.QtCore import QByteArray
                    ba = QByteArray.fromBase64(geo.encode())
                    self.restoreGeometry(ba)
                except Exception:
                    pass
            else:
                self.resize(1180, 760)
        else:
            self.resize(1180, 760)

        if open_path:
            QTimer.singleShot(60, lambda: self.open_path(open_path))

    # ================================================================ UI
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- top bar ----
        self.topbar = QFrame()
        self.topbar.setObjectName("TopBar")
        self.topbar.setFixedHeight(CAPTION_H)
        tl = QHBoxLayout(self.topbar)
        tl.setContentsMargins(12, 0, 0, 0)
        tl.setSpacing(4)
        self.app_btn = IconButton("image", "", 34, 18)
        self.app_btn.setToolTip(APP_NAME)
        app_ico = _app_icon()
        if not app_ico.isNull():
            # show the real program icon instead of the generic SVG glyph;
            # _static_icon keeps theme retint from replacing it
            self.app_btn._static_icon = True
            self.app_btn.setIcon(app_ico)
            self.app_btn.setIconSize(QSize(18, 18))
        tl.addWidget(self.app_btn)
        self.title_label = QLabel(APP_NAME)
        self.title_label.setObjectName("TitleLabel")
        f = self.title_label.font()
        f.setWeight(f.Weight.DemiBold)
        self.title_label.setFont(f)
        tl.addWidget(self.title_label)
        self.folder_label = QLabel("")
        self.folder_label.setObjectName("Dim")
        self.folder_label.setMinimumWidth(0)
        self.folder_label.setContentsMargins(10, 0, 0, 0)  # gap after "P view"
        bf = QFont(self.folder_label.font())
        bf.setWeight(QFont.Weight.Bold)
        self.folder_label.setFont(bf)
        self.folder_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.folder_label.setToolTip(tr("open_folder"))
        # opt out of WM_NCHITTEST caption drag so real clicks reach the label
        self.folder_label._caption_block = True
        self.folder_label.installEventFilter(self)
        tl.addWidget(self.folder_label)
        self.file_label = QLabel("")
        self.file_label.setObjectName("Dim")
        self.file_label.setMinimumWidth(10)
        tl.addWidget(self.file_label, 1)
        self.btn_info_top = IconButton("info", tr("exif_info"))
        self.btn_info_top.clicked.connect(self.toggle_info)
        tl.addWidget(self.btn_info_top)
        self.btn_menu = IconButton("more", tr("settings"))
        self.btn_menu.clicked.connect(self.show_main_menu)
        tl.addWidget(self.btn_menu)
        self.btn_min = CaptionButton("win-min", "")
        self.btn_max = CaptionButton("win-max", "")
        self.btn_close = CloseButton("")
        self.btn_min.clicked.connect(self.showMinimized)
        self.btn_max.clicked.connect(self._toggle_max)
        self.btn_close.clicked.connect(self.close)
        for b in (self.btn_min, self.btn_max, self.btn_close):
            b._caption_block = True
            tl.addWidget(b)
        root.addWidget(self.topbar)

        # ---- canvas stack ----
        self.stack = QStackedWidget()
        self.canvas = ImageViewCanvas()
        self.webtoon = WebtoonView()
        self.stack.addWidget(self.canvas)
        self.stack.addWidget(self.webtoon)
        root.addWidget(self.stack, 1)

        # canvas overlays (floating children of self)
        self._empty = QLabel(tr("drop_hint"), self)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setStyleSheet("color: rgba(128,128,128,0.9); font-size: 13pt;")
        self._empty.hide()

        # ---- bottom control bar ----
        self.bottombar = QFrame(self)
        self.bottombar.setObjectName("OverlayCard")
        bl = QHBoxLayout(self.bottombar)
        bl.setContentsMargins(8, 6, 8, 6)
        bl.setSpacing(2)
        self.btn_gallery = IconButton("grid", tr("gallery"), checkable=True)
        self.btn_gallery.toggled.connect(self.toggle_filmstrip)
        bl.addWidget(self.btn_gallery)
        bl.addSpacing(6)
        self.btn_prev = IconButton("chev-left", tr("prev_image"))
        self.btn_prev.clicked.connect(lambda: self.go_prev())
        bl.addWidget(self.btn_prev)
        self.btn_next = IconButton("chev-right", tr("next_image"))
        self.btn_next.clicked.connect(lambda: self.go_next())
        bl.addWidget(self.btn_next)
        bl.addSpacing(6)
        self.btn_zoom_out = IconButton("zoom-out", tr("zoom_out"))
        self.btn_zoom_out.clicked.connect(lambda: self.canvas.zoom_out())
        bl.addWidget(self.btn_zoom_out)
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(0, 100)
        self.zoom_slider.setFixedWidth(140)
        self.zoom_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.zoom_slider.valueChanged.connect(self._slider_zoom)
        bl.addWidget(self.zoom_slider)
        self.btn_zoom_in = IconButton("zoom-in", tr("zoom_in"))
        self.btn_zoom_in.clicked.connect(lambda: self.canvas.zoom_in())
        bl.addWidget(self.btn_zoom_in)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(48)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.zoom_label.setToolTip(tr("zoom_input_tip"))
        self.zoom_label.installEventFilter(self)
        bl.addWidget(self.zoom_label)
        # inline editor: click the percentage to type an exact zoom level
        self.zoom_edit = QSpinBox()
        self.zoom_edit.setRange(5, 4000)
        self.zoom_edit.setSuffix("%")
        self.zoom_edit.setFixedWidth(64)
        self.zoom_edit.hide()
        self.zoom_edit.installEventFilter(self)
        self.zoom_edit.editingFinished.connect(self._zoom_edit_done)
        bl.addWidget(self.zoom_edit)
        self.btn_fit = IconButton("fit-window", tr("fit_best"))
        self.btn_fit.clicked.connect(self._cycle_fit)
        bl.addWidget(self.btn_fit)
        bl.addSpacing(6)
        self.btn_ss = IconButton("slideshow", tr("slideshow"))
        self.btn_ss.clicked.connect(self.toggle_slideshow)
        bl.addWidget(self.btn_ss)
        self.btn_full = IconButton("fullscreen", tr("fullscreen"))
        self.btn_full.clicked.connect(self.toggle_fullscreen)
        bl.addWidget(self.btn_full)
        bl.addSpacing(6)
        self.btn_delete = IconButton("delete", tr("delete"))
        self.btn_delete.clicked.connect(self.delete_current)
        bl.addWidget(self.btn_delete)
        self.btn_star = IconButton("star", tr("bookmark_add"))
        self.btn_star.clicked.connect(self.bookmark_add)
        bl.addWidget(self.btn_star)
        bl.addStretch(1)

        # ---- side arrows (auto-hide behind invisible hover hot zones) ----
        self.arrow_left = QFrame(self)
        self.arrow_left.setObjectName("SideArrow")
        self.arrow_left.setFixedSize(44, 72)
        al = QVBoxLayout(self.arrow_left)
        al.setContentsMargins(0, 0, 0, 0)
        self.al_btn = IconButton("chev-left", "", 42, 22)
        self.al_btn.clicked.connect(lambda: self.go_prev())
        al.addWidget(self.al_btn)
        self.arrow_right = QFrame(self)
        self.arrow_right.setObjectName("SideArrow")
        self.arrow_right.setFixedSize(44, 72)
        ar = QVBoxLayout(self.arrow_right)
        ar.setContentsMargins(0, 0, 0, 0)
        self.ar_btn = IconButton("chev-right", "", 42, 22)
        self.ar_btn.clicked.connect(lambda: self.go_next())
        ar.addWidget(self.ar_btn)
        # invisible fixed hot zones: entering them reveals both arrows at once
        self._hot_l = QFrame(self)
        self._hot_r = QFrame(self)
        for hz in (self._hot_l, self._hot_r):
            hz.setStyleSheet("background: transparent; border: none;")
            hz.installEventFilter(self)
        self.arrow_left.installEventFilter(self)
        self.arrow_right.installEventFilter(self)
        self.arrow_left.hide()
        self.arrow_right.hide()
        self._nav_shown = False
        self._nav_hide_timer = QTimer(self)
        self._nav_hide_timer.setSingleShot(True)
        self._nav_hide_timer.setInterval(280)
        self._nav_hide_timer.timeout.connect(self._nav_do_hide)

        # ---- mini title ----
        self.mini_title = QLabel("", self)
        self.mini_title.setObjectName("OverlayTitle")
        self.mini_title.hide()
        self._mini_timer = QTimer(self)
        self._mini_timer.setSingleShot(True)
        self._mini_timer.timeout.connect(
            lambda: self.mini_title.setVisible(self._mini_persist))
        self._mini_persist = bool(S.get("mini_title"))

        # ---- filmstrip / info / toast ----
        self.filmstrip = FilmStrip(self)
        self.filmstrip.hide()
        self.filmstrip.jumpRequested.connect(self._filmstrip_jump)
        self.filmstrip.autoHideRequested.connect(self._filmstrip_autohide)
        THUMBS.ready.connect(self.filmstrip.on_thumb_ready)

        self.info_panel = InfoPanel(self)
        self.info_panel.hide()
        self.info_panel._close_btn.clicked.connect(self.toggle_info)

        self.toast = Toast(self)

        self.canvas.zoomChanged.connect(self._on_zoom_changed)
        self.canvas.pageRequested.connect(self._step)
        self.stack.currentChanged.connect(lambda _i: self._relayout_overlays())

    # ================================================================ theme
    def apply_theme(self):
        p = palette()
        mica = use_mica()
        self.setStyleSheet(build_qss(p, icons._icon_dir))
        apply_toast_style(self.toast, p)
        self.filmstrip.retint(p)
        self.info_panel.retint(p)
        self.topbar.setStyleSheet(
            f"QFrame#TopBar {{ background: {'rgba(0,0,0,0)' if mica else p['window']}; }}"
            f"QLabel#TitleLabel {{ color: {p['accent']}; }}"
            f"QLabel#Dim {{ color: {p['text2']}; }}")
        retint_all(self)
        self._palette = p
        if self.isVisible():
            self.apply_theme_dwm(p["dark"], mica)
        else:
            if mica:
                self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def showEvent(self, ev):
        super().showEvent(ev)
        # keep the maximize glyph in sync if the window ever starts maximized
        self.btn_max.set_icon_name("win-restore" if self.isMaximized()
                                   else "win-max")
        self.apply_theme_dwm(self._palette["dark"], use_mica())
        self._relayout_overlays()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._relayout_overlays()

    def _relayout_overlays(self):
        w, h = self.width(), self.height()
        show_bar = (not self._fullscreen) and S.get("bottom_bar") and bool(self._doc)
        self.bottombar.setVisible(show_bar)
        if show_bar:
            self.bottombar.adjustSize()
            self.bottombar.move((w - self.bottombar.width()) // 2,
                                h - self.bottombar.height() - 14)
        show_arrows = (not self._fullscreen and S.get("side_arrow")
                       and bool(self._doc) and not self._webtoon_mode
                       and self._source and len(self._source.entries) > 1)
        mid = (h - CAPTION_H) // 2 + CAPTION_H - 36
        self._hot_l.setVisible(show_arrows)
        self._hot_r.setVisible(show_arrows)
        if show_arrows:
            self._hot_l.setGeometry(0, mid - 40, 64, 152)
            self._hot_r.setGeometry(w - 64, mid - 40, 64, 152)
            self._hot_l.raise_()
            self._hot_r.raise_()
            self.arrow_left.move(10, mid)
            self.arrow_right.move(w - 54, mid)
            self.arrow_left.setVisible(self._nav_shown)
            self.arrow_right.setVisible(self._nav_shown)
            if self._nav_shown:
                self.arrow_left.raise_()
                self.arrow_right.raise_()
        else:
            self._nav_shown = False
            self._nav_hide_timer.stop()
            self.arrow_left.hide()
            self.arrow_right.hide()
        strip_visible = self.filmstrip.isVisible() or self.btn_gallery.isChecked()
        if strip_visible and self._source:
            self.filmstrip.move(16, h - self.filmstrip.height() - (84 if show_bar else 20))
            self.filmstrip.setFixedWidth(w - 32)
        if self.info_panel.isVisible():
            self.info_panel.fit_height(h - 90)
            self.info_panel.move(w - self.info_panel.width() - 16, 64)
        if self._doc or (self._source and self._source.entries):
            self._empty.hide()
        elif self._source is None:
            self._empty.setGeometry(0, CAPTION_H, w, h - CAPTION_H)
            self._empty.show()

    # ---- side-arrow auto show/hide ----
    def eventFilter(self, obj, ev):
        hot_l = getattr(self, "_hot_l", None)
        if hot_l is not None and obj in (hot_l, self._hot_r,
                                         self.arrow_left, self.arrow_right):
            t = ev.type()
            if t == QEvent.Type.Enter:
                self._nav_show()
            elif t == QEvent.Type.Leave:
                self._nav_schedule_hide()
        elif obj is getattr(self, "folder_label", None) \
                and ev.type() == QEvent.Type.MouseButtonPress:
            self._open_containing_folder()
        elif obj is getattr(self, "zoom_label", None) \
                and ev.type() == QEvent.Type.MouseButtonPress:
            self._zoom_edit_start()
        elif obj is getattr(self, "zoom_edit", None) \
                and ev.type() == QEvent.Type.ShortcutOverride \
                and ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # claim Enter here, otherwise the navigator QShortcut consumes the
            # key and the spinbox never sees it (apply-zoom then does nothing)
            ev.accept()
            return True
        elif obj is getattr(self, "zoom_edit", None) \
                and ev.type() == QEvent.Type.KeyPress \
                and ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # apply the zoom here and swallow the key so the navigator
            # shortcut (also Enter) never sees it
            ev.accept()
            QTimer.singleShot(0, self._zoom_edit_done)
            return True
        return super().eventFilter(obj, ev)

    def _open_containing_folder(self):
        """Open the folder that contains the current image (Explorer)."""
        if not self._source:
            return
        p = self._source.path
        folder = p if os.path.isdir(p) else os.path.dirname(p)
        if folder and os.path.isdir(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _zoom_edit_start(self):
        if not self._doc or self.zoom_edit.isVisible():
            return
        self.zoom_edit.setValue(int(round(self.canvas.zoom() * 100)))
        self.zoom_label.hide()
        self.zoom_edit.show()
        self.zoom_edit.selectAll()
        self.zoom_edit.setFocus()
        self.bottombar.adjustSize()

    def _zoom_edit_done(self):
        # hide() below re-triggers editingFinished via focus loss -> guard
        if not self.zoom_edit.isVisible():
            return
        z = self.zoom_edit.value() / 100.0
        self.zoom_edit.hide()
        self.zoom_label.show()
        self.bottombar.adjustSize()
        self.canvas.set_zoom(z)

    def _nav_show(self):
        self._nav_hide_timer.stop()
        if not self._nav_shown:
            self._nav_shown = True
            self.arrow_left.show()
            self.arrow_right.show()
            self.arrow_left.raise_()
            self.arrow_right.raise_()

    def _nav_schedule_hide(self):
        if self._nav_shown:
            self._nav_hide_timer.start()

    def _nav_do_hide(self):
        self._nav_shown = False
        self.arrow_left.hide()
        self.arrow_right.hide()

    # ================================================================ opening
    def open_path(self, path: str, entry_hint: str = ""):
        path = os.path.normpath(os.path.abspath(path))
        if os.path.isdir(path):
            self._open_source(ImageSource(path), entry_hint)
            return
        if is_archive_path(path):
            self._open_archive_with_password(path, "", entry_hint)
            return
        if is_image_name(path):
            folder = os.path.dirname(path)
            src = ImageSource(folder)
            self._open_source(src, os.path.basename(path))
            return
        self._toast(tr("not_supported"))

    def _open_archive_with_password(self, path, password, entry_hint=""):
        src = ImageSource(path, password=password)
        while src.need_password:
            dlg = PasswordDialog(path, self)
            if dlg.exec() != PasswordDialog.DialogCode.Accepted or not dlg.password():
                self._toast(tr("cancel"))
                return
            src = ImageSource(path, password=dlg.password())
            if not src.need_password and not src.entries and src.error:
                self._toast(tr("wrong_password"))
        if src.error and not src.entries:
            self._toast(tr("open_archive_failed") + " " + src.error)
            return
        if not src.entries:
            self._toast(tr("no_image_in_archive"))
            return
        self._open_source(src, entry_hint)

    def _open_source(self, source: ImageSource, entry_hint: str = ""):
        if self._source:
            self._source.close()
        self._source = source
        self._webtoon_mode = False
        self.stack.setCurrentWidget(self.canvas)
        self._add_recent(source.path)
        # restore position
        idx = 0
        hint_key = entry_hint
        if not hint_key:
            pos_store = ""
            if source.archive and S.get("remember_pos_archive"):
                pos_store = self._positions.get(source.path, "")
            elif (not source.archive) and S.get("remember_pos_folder"):
                pos_store = self._positions.get("folder::" + source.path, "")
            hint_key = pos_store
        if hint_key:
            for i, e in enumerate(source.entries):
                if e.key == hint_key or e.name == hint_key:
                    idx = i
                    break
        self.filmstrip.set_source(source, idx)
        self.btn_gallery.setChecked(False)
        self._goto(idx)
        self._relayout_overlays()

    def _current_key(self) -> str:
        if self._source and 0 <= self._idx < len(self._source.entries):
            return self._source.entries[self._idx].key
        return ""

    def _goto(self, i: int, effect: str = "none", force: bool = False):
        if not self._source or not self._source.entries:
            return
        i = max(0, min(len(self._source.entries) - 1, i))
        if i == self._idx and not force and self._doc is not None:
            return
        self._idx = i
        entry = self._source.entries[i]
        self._remember_position()
        # BandiView-style title: "<folder> > <name> [i/N]"  (top bar shows no
        # app-name suffix; the native window title keeps it for the taskbar)
        parent = os.path.basename(os.path.dirname(self._source.path)) \
            or self._source.path
        if getattr(self._source, "archive", None):
            parent = f"{parent} > {os.path.basename(self._source.path)}"
        title = (f"{parent} > {entry.name} "
                 f"[{i + 1}/{len(self._source.entries)}]")
        self.folder_label.setText(parent)
        self.file_label.setText(f" > {entry.name} "
                                f"[{i + 1}/{len(self._source.entries)}]")
        self.setWindowTitle(f"{title} - {APP_NAME}")
        if self._webtoon_mode:
            self.webtoon.scroll_center_on(i)
            return
        key = (self._source.path, entry.key)
        doc = DOC_CACHE.get(key)
        if doc is not None:
            self._apply_doc(doc, effect)
        else:
            self._request_doc(i, effect)
        if S.get("prefetch_next"):
            self._prefetch(i + 1)
            self._prefetch(i - 1)
        if self.filmstrip.isVisible():
            self.filmstrip.highlight(i)
        if self.info_panel.isVisible():
            self.info_panel.show_entry(self._source, i,
                                       doc or self._doc,
                                       zoom=self.canvas.zoom())
        self._relayout_overlays()

    def _request_doc(self, i: int, effect: str = "none"):
        entry = self._source.entries[i]
        key = (self._source.path, entry.key)
        self._token += 1
        token = self._token
        self._pending.add(i)
        self._pending_effect = effect

        def job():
            try:
                data = self._source.read_bytes(entry)
            except WrongPasswordError:
                self._docReady.emit(None, i, token, 2)
                return
            except Exception as e:
                doc = ImageDoc(ok=False, error=str(e))
                self._docReady.emit(doc, i, token, 0)
                return
            doc = load_doc(data, ext_of(entry.name), entry.name)
            DOC_CACHE.put(key, doc)
            self._docReady.emit(doc, i, token, 0)
        from .loader import _prefetch_pool
        _prefetch_pool.submit(job)

    def _on_doc_ready(self, doc, i, token, kind):
        if i in self._pending:
            self._pending.discard(i)
        if token != self._token or not self._source:
            return
        if i != self._idx:
            return
        if doc is None:
            self._toast(tr("wrong_password"))
            return
        if not doc.ok:
            self._toast(tr("cant_open") + (f" ({doc.error})" if doc.error else ""))
        effect = getattr(self, "_pending_effect", "none") or "none"
        self._apply_doc(doc, effect)

    def _apply_doc(self, doc: ImageDoc, effect: str = "none"):
        self._doc = doc
        if not S.get("keep_effects"):
            self._fx = {}
        if self._double_mode:
            # BandiView-style separate cover: first image alone in spread mode
            if S.get("double_cover") and self._idx == 0:
                d2 = None
            else:
                d2 = self._pair_doc()
            if self._double_mode == "r2l":
                self.canvas.set_pair(d2, doc, self._current_key(), effect)
            else:
                self.canvas.set_pair(doc, d2, self._current_key(), effect)
        else:
            self.canvas.set_effects(self._fx)
            self.canvas.set_doc(doc, self._current_key(), effect)
        self._update_star()
        self._relayout_overlays()

    def _set_fx(self, fx: dict):
        self._fx = dict(fx)
        self.canvas.set_effects(self._fx)

    def _pair_doc(self):
        if not self._source or not self._double_mode:
            return None
        j = self._idx + 1
        if j >= len(self._source.entries):
            return None
        entry = self._source.entries[j]
        key = (self._source.path, entry.key)
        doc = DOC_CACHE.get(key)
        if doc is not None:
            return doc
        self._request_doc(j)
        return None

    def _prefetch(self, i: int):
        if not self._source or not (0 <= i < len(self._source.entries)):
            return
        if i in self._pending:
            return
        entry = self._source.entries[i]
        key = (self._source.path, entry.key)
        if DOC_CACHE.get(key) is not None:
            return
        self._pending.add(i)

        def job():
            try:
                data = self._source.read_bytes(entry)
                doc = load_doc(data, ext_of(entry.name), entry.name)
                DOC_CACHE.put(key, doc)
            except Exception:
                pass
            finally:
                self._pending.discard(i)
                if self._webtoon_mode:
                    QTimer.singleShot(0, self._webtoon_kick)
        from .loader import _prefetch_pool
        _prefetch_pool.submit(job)

    def _webtoon_kick(self):
        if self._webtoon_mode:
            self.webtoon._load_visible()

    def _remember_position(self):
        if not self._source:
            return
        if self._source.archive and S.get("remember_pos_archive"):
            self._positions[self._source.path] = self._current_key()
            _save_json("positions.json", self._positions)
        elif (not self._source.archive) and S.get("remember_pos_folder"):
            self._positions["folder::" + self._source.path] = self._current_key()
            _save_json("positions.json", self._positions)

    # ================================================================ navigation
    def go_next(self, effect: str = ""):
        self._step(+1, effect)

    def go_prev(self, effect: str = ""):
        self._step(-1, effect)

    def _step(self, delta: int, effect: str = ""):
        if not self._source or not self._source.entries:
            return
        n = len(self._source.entries)
        step = 2 if self._double_mode else 1
        i = self._idx + delta * step
        if 0 <= i < n:
            self._goto(i, effect)
            return
        # boundary behaviour
        action = S.get("last_action")
        if action == "loop":
            self._goto(0 if delta > 0 else n - 1, effect)
        elif action == "next_folder":
            (self.next_folder if delta > 0 else self.prev_folder)()
        else:
            self._toast(tr("last_image_msg") if delta > 0 else tr("first_image_msg"))

    def go_first(self):
        self._goto(0)

    def go_last(self):
        if self._source:
            self._goto(len(self._source.entries) - 1)

    def go_next10(self):
        self._goto(self._idx + 10)

    def go_prev10(self):
        self._goto(self._idx - 10)

    def go_random_next(self):
        if not self._source or len(self._source.entries) < 2:
            return
        i = self._idx
        while i == self._idx:
            i = random.randrange(len(self._source.entries))
        self._goto(i)

    def next_folder(self):
        self._nav_sibling(+1)

    def prev_folder(self):
        self._nav_sibling(-1)

    def _nav_sibling(self, delta: int):
        if not self._source:
            return
        if self._source.archive:
            sibs = self._source.sibling_archives()
            cur = self._source.path
        else:
            sibs = [f for f in self._source.sibling_folders()]
            cur = self._source.path
        if cur not in sibs:
            sibs = [cur] + sibs
        try:
            i = sibs.index(cur)
        except ValueError:
            return
        j = i + delta
        if not (0 <= j < len(sibs)):
            self._toast(tr("first_image_msg") if delta < 0 else tr("last_image_msg"))
            return
        target = sibs[j]
        if is_archive_path(target):
            self._open_archive_with_password(target, "")
        else:
            src = ImageSource(target)
            if not src.entries:
                # skip empty folders recursively
                self._source_path_skip(target, delta)
                return
            self._open_source(src)
        self._toast(("→ " if delta > 0 else "← ") + os.path.basename(target))

    def _source_path_skip(self, from_folder: str, delta: int):
        # keep walking in the same direction until a folder with images is found
        if not self._source:
            return
        if self._source.archive:
            sibs = self._source.sibling_archives()
        else:
            sibs = self._source.sibling_folders()
        try:
            i = sibs.index(from_folder)
        except ValueError:
            return
        j = i + delta
        while 0 <= j < len(sibs):
            t = sibs[j]
            if is_archive_path(t):
                self._open_archive_with_password(t, "")
                return
            src = ImageSource(t)
            if src.entries:
                self._open_source(src)
                return
            j += delta
        self._toast(tr("no_image_in_folder"))

    # ================================================================ view modes
    def set_view_mode(self, mode: str):
        if mode == "webtoon":
            self._double_mode = ""
            self._enter_webtoon()
            return
        self._exit_webtoon()
        if mode in ("l2r", "r2l"):
            self._double_mode = mode
            if self._doc:
                self._apply_doc(self._doc)
            return
        was_double = bool(self._double_mode)
        self._double_mode = ""
        if was_double and self._doc:
            self._apply_doc(self._doc)
        else:
            self.canvas.set_fit_mode(mode)

    def _enter_webtoon(self):
        if not self._source:
            return
        self._webtoon_mode = True
        self.stack.setCurrentWidget(self.webtoon)
        self.webtoon.set_provider(len(self._source.entries), self._webtoon_provider)
        self._relayout_overlays()

    def _exit_webtoon(self):
        if not self._webtoon_mode:
            return
        self._webtoon_mode = False
        self.stack.setCurrentWidget(self.canvas)
        self._relayout_overlays()

    def _webtoon_provider(self, i: int):
        if not self._source or not (0 <= i < len(self._source.entries)):
            return None
        entry = self._source.entries[i]
        key = (self._source.path, entry.key)
        doc = DOC_CACHE.get(key)
        if doc is not None:
            return doc
        if i not in self._pending:
            self._prefetch(i)
        return None

    def _cycle_fit(self):
        order = ["fit", "width", "height", "original"]
        cur = self.canvas.fit_mode()
        nxt = order[(order.index(cur) + 1) % len(order)]
        self.set_view_mode(nxt)
        self._toast({"fit": tr("vm_fit"), "width": tr("vm_fit_width"),
                     "height": tr("vm_fit_height"),
                     "original": tr("vm_original")}[nxt])

    def toggle_stretch_small(self):
        on = self.canvas.toggle_stretch_small()
        self._toast((tr("vm_stretch_small") + ": ") + ("On" if on else "Off"))

    # ================================================================ zoom
    def _slider_zoom(self, v):
        if self.canvas.doc() is None:
            return
        zoom = 0.05 * (2 ** (v / 100 * 7.5))   # 0.05 .. ~9
        self.canvas.set_zoom(zoom)

    def _on_zoom_changed(self, z):
        self.zoom_label.setText(tr("zoom_percent").format(int(round(z * 100))))
        import math
        v = int(max(0, min(100, math.log2(z / 0.05) / 7.5 * 100)))
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(v)
        self.zoom_slider.blockSignals(False)
        if self.info_panel.isVisible():
            self.info_panel.update_zoom(z)
        if S.get("zoom_lock") or S.get("zoom_lock_save"):
            S.set("zoom_lock_value", z)

    def zoom_lock_toggle(self):
        on = not S.get("zoom_lock")
        S.set("zoom_lock", on)
        self._toast(tr("zoom_lock_on") if on else tr("zoom_lock_off"))

    # ================================================================ rotation & fx
    def rotate(self, deg: int):
        rot, fh, fv = self.canvas.rotation()
        self.canvas.set_rotation((rot + deg) % 360, fh, fv)

    def set_rotation(self, deg: int):
        rot, fh, fv = self.canvas.rotation()
        self.canvas.set_rotation(deg, fh, fv)

    def toggle_flip(self, horizontal: bool):
        rot, fh, fv = self.canvas.rotation()
        if horizontal:
            self.canvas.set_rotation(rot, not fh, fv)
        else:
            self.canvas.set_rotation(rot, fh, not fv)

    def reset_rotation(self):
        self.canvas.reset_rotation()

    def fx_toggle(self, key: str):
        self._fx[key] = not self._fx.get(key, False)
        self._set_fx(self._fx)

    def set_filter(self, mode: str):
        self._filter_mode = mode
        self._fx["sharpen"] = (mode == "sharpen")
        self._set_fx(self._fx)
        names = {"none": tr("filter_none"), "soften": tr("filter_soften"),
                 "sharpen": tr("filter_sharpen")}
        self._toast(names[mode])

    def cycle_trans_bg(self):
        order = ["grid", "white", "black"]
        cur = S.get("trans_bg")
        nxt = order[(order.index(cur) + 1) % 3]
        S.set("trans_bg", nxt)
        self.canvas.update()
        self._toast({"grid": tr("trans_grid"), "white": tr("trans_white"),
                     "black": tr("trans_black")}[nxt])

    def show_adjust(self):
        dlg = AdjustDialog(self.canvas, self)
        dlg.fxChanged.connect(lambda fx: self._set_fx(fx))
        dlg.exec()
        self._fx = dlg.fx()

    # ================================================================ animation
    def anim_play_pause(self):
        self.canvas.play()

    def anim_step(self, delta: int):
        self.canvas.step_frame(delta)

    # ================================================================ slideshow
    def toggle_slideshow(self):
        if self._slideshow_on:
            self.stop_slideshow()
        else:
            self.start_slideshow()

    def start_slideshow(self, seconds: int | None = None):
        if not self._source:
            return
        sec = seconds or int(S.get("ss_interval"))
        self._slideshow_on = True
        self._slideshow_timer.start(sec * 1000)
        self._ss_effect = S.get("ss_effect") or "none"
        if not self._fullscreen:
            self.toggle_fullscreen()
        self._toast(tr("slideshow_started").format(sec))

    def stop_slideshow(self):
        if not self._slideshow_on:
            return
        self._slideshow_on = False
        self._slideshow_timer.stop()
        self._toast(tr("slideshow_stopped"))

    def _slideshow_step(self):
        if not self._source or not self._source.entries:
            self.stop_slideshow()
            return
        n = len(self._source.entries)
        if S.get("ss_random") and n > 1:
            i = self._idx
            while i == self._idx:
                i = random.randrange(n)
            self._goto(i, self._ss_effect)
            return
        nxt = self._idx + 1
        if nxt >= n:
            if S.get("ss_loop"):
                nxt = 0
            else:
                self.stop_slideshow()
                return
        self._goto(nxt, self._ss_effect)

    # ================================================================ fullscreen
    def toggle_fullscreen(self):
        if self._fullscreen:
            self._fullscreen = False
            self.showNormal()
            self.topbar.show()
        else:
            self._fullscreen = True
            self.topbar.hide()
            self.showFullScreen()
        self._relayout_overlays()

    def mouseMoveEvent(self, ev):
        super().mouseMoveEvent(ev)
        if self._fullscreen:
            near = ev.position().y() < 60
            self.topbar.setVisible(near)
            if near:
                QTimer.singleShot(2600, self._auto_hide_bars)

    def _auto_hide_bars(self):
        if self._fullscreen and not self._bars_hidden:
            if self.mapFromGlobal(QCursor.pos()).y() > 60:
                self.topbar.hide()

    def toggle_mini_title(self):
        self._mini_persist = not self._mini_persist
        S.set("mini_title", self._mini_persist)
        self._show_mini_title()

    def _show_mini_title(self):
        if not self._doc:
            return
        e = self._source.entries[self._idx] if self._source else None
        self.mini_title.setText(e.name if e else "")
        self.mini_title.adjustSize()
        self.mini_title.move((self.width() - self.mini_title.width()) // 2, 56)
        self.mini_title.setVisible(True)
        self.mini_title.raise_()
        if not self._mini_persist:
            self._mini_timer.start(1600)

    # ================================================================ window ops
    def _toggle_max(self):
        # Win11 convention: single frame when maximizable, stacked frames
        # while maximized (restore glyph)
        if self.isMaximized():
            self.showNormal()
            self.btn_max.set_icon_name("win-max")
        else:
            self.showMaximized()
            self.btn_max.set_icon_name("win-restore")

    def always_on_top(self):
        flags = self.windowFlags()
        on = not (flags & Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowFlags(flags ^ Qt.WindowType.WindowStaysOnTopHint)
        self.show()
        S.set("_aot", on)
        self._toast(tr("alwaystop_on") if on else tr("alwaystop_off"))

    def fit_window_to_image(self):
        doc = self.canvas.doc()
        if not doc or doc.size.isEmpty():
            return
        rot = self.canvas.rotation()[0] in (90, 270)
        iw, ih = (doc.size.height(), doc.size.width()) if rot else (
            doc.size.width(), doc.size.height())
        scr = self.screen().availableGeometry()
        w = min(int(iw) + 40, scr.width() - 40)
        h = min(int(ih) + CAPTION_H + 40, scr.height() - 40)
        self.resize(w, h)

    # ================================================================ info panel / filmstrip
    def toggle_info(self):
        if self.info_panel.isVisible():
            self.info_panel.hide()
        else:
            if self._source and self._doc:
                self.info_panel.show_entry(self._source, self._idx, self._doc,
                                           zoom=self.canvas.zoom())
            self.info_panel.slide_in()

    def toggle_filmstrip(self, on: bool):
        if on and self._source:
            self.filmstrip.show()
            self.filmstrip.raise_()
            self.filmstrip.highlight(self._idx)
            self.filmstrip.arm_autohide()
        else:
            self.filmstrip.hide()
        self._relayout_overlays()

    def _filmstrip_autohide(self):
        self.filmstrip.hide()
        if self.btn_gallery.isChecked():
            self.btn_gallery.setChecked(False)   # triggers toggle_filmstrip(False)

    def _filmstrip_jump(self, i: int):
        self._goto(i)

    def show_navigator(self):
        # the inline zoom editor consumes Enter for "apply zoom" — when it is
        # open, Enter must NOT also open the navigator (two different Enters)
        if getattr(self, "zoom_edit", None) is not None and \
                self.zoom_edit.isVisible():
            return
        if not self._source:
            return
        dlg = NavigatorDialog(self._source, self._idx, self)
        dlg.jumpRequested.connect(lambda i: self._goto(i))
        dlg.exec()

    # ================================================================ menus
    def show_main_menu(self):
        # the "..." caption button is a direct shortcut to Settings
        self._show_settings()

    def contextMenuEvent(self, ev):
        if self._doc is None and self._source is None:
            return
        m = self._build_menu()
        m.exec(ev.globalPos())

    def _add_item(self, m: QMenu, text: str, cb, key: str = "", icon_name: str = ""):
        a = QAction(text, self)
        if key:
            a.setText(f"{text}\t{key}")   # hint only; real shortcuts are QShortcut
        if icon_name:
            a.setIcon(icons.icon(icon_name, self._palette["text"], 32))
        a.triggered.connect(cb)
        m.addAction(a)
        return a

    def _build_menu(self) -> QMenu:
        p = self._palette
        m = QMenu(self)
        has = self._doc is not None
        # file
        self._add_item(m, tr("open_image") + "...", self._dlg_open, "Ctrl+O", "open")
        self._add_item(m, tr("open_folder") + "...", self._dlg_open_folder, "F",
                       "folder")
        recent = m.addMenu(icons.icon("more", p["text"], 32), tr("open_recent"))
        if self._recents:
            for r in self._recents[:15]:
                self._add_item(recent, os.path.basename(r), lambda checked=False,
                               r=r: self.open_path(r))
        else:
            recent.addAction(tr("recent_empty")).setEnabled(False)
        m.addSeparator()
        fi = self._add_item(m, tr("close_image"), self._close_image, "F4")
        fi.setEnabled(has)
        m.addSeparator()
        r = self._add_item(m, tr("rename"), self.rename_current, "F2", "rename")
        r.setEnabled(has and not (self._source and self._source.archive))
        d = self._add_item(m, tr("delete"), self.delete_current, "Del", "delete")
        d.setEnabled(has)
        self._add_item(m, tr("open_location"), self._show_in_explorer,
                       "Ctrl+Enter", "folder-open")
        m.addSeparator()
        c = self._add_item(m, tr("convert") + "...", self._show_convert, "Ctrl+T",
                           "convert")
        c.setEnabled(has)
        sa = self._add_item(m, tr("save_as") + "...", self._save_as, "Ctrl+S", "save")
        sa.setEnabled(has)
        pr = self._add_item(m, tr("print") + "...", self._print, "Ctrl+P", "print")
        pr.setEnabled(has)
        m.addSeparator()
        self._add_item(m, tr("new_window"), self._new_window, "")
        m.addSeparator()
        self._add_item(m, tr("exit"), self.close, "")
        # navigation
        nav = m.addMenu(icons.icon("compass", p["text"], 32), tr("nav"))
        self._add_item(nav, tr("next_image"), lambda: self.go_next(), "Right")
        self._add_item(nav, tr("prev_image"), lambda: self.go_prev(), "Left")
        self._add_item(nav, tr("first_image"), self.go_first, "Home")
        self._add_item(nav, tr("last_image"), self.go_last, "End")
        self._add_item(nav, tr("next_10"), self.go_next10, "Ctrl+PgDown")
        self._add_item(nav, tr("prev_10"), self.go_prev10, "Ctrl+PgUp")
        self._add_item(nav, tr("random_next"), self.go_random_next,
                       "Ctrl+Alt+PgDown", "shuffle")
        nav.addSeparator()
        self._add_item(nav, tr("next_folder"), self.next_folder, "]")
        self._add_item(nav, tr("prev_folder"), self.prev_folder, "[")
        nav.addSeparator()
        self._add_item(nav, tr("navigator"), self.show_navigator, "Enter", "grid")
        # view
        vm = m.addMenu(icons.icon("image", p["text"], 32), tr("viewmode"))
        self._add_item(vm, tr("vm_original"), lambda: self.set_view_mode("original"), "0")
        self._add_item(vm, tr("vm_fit"), lambda: self.set_view_mode("fit"), "9")
        self._add_item(vm, tr("vm_fit_width"), lambda: self.set_view_mode("width"), "8")
        self._add_item(vm, tr("vm_fit_height"), lambda: self.set_view_mode("height"), "")
        vm.addSeparator()
        self._add_item(vm, tr("vm_double_l2r"), lambda: self.set_view_mode("l2r"), "7",
                       "double-page")
        self._add_item(vm, tr("vm_double_r2l"), lambda: self.set_view_mode("r2l"), "6")
        self._add_item(vm, tr("vm_webtoon"), lambda: self.set_view_mode("webtoon"), "5",
                       "webtoon")
        vm.addSeparator()
        self._add_item(vm, tr("vm_stretch_small"), self.toggle_stretch_small, "Z")
        zm = m.addMenu(icons.icon("zoom-in", p["text"], 32), tr("zoom"))
        self._add_item(zm, tr("zoom_in"), lambda: self.canvas.zoom_in(), "+")
        self._add_item(zm, tr("zoom_out"), lambda: self.canvas.zoom_out(), "-")
        self._add_item(zm, tr("zoom_100"), self.canvas.zoom_100, "")
        self._add_item(zm, tr("zoom_lock"), self.zoom_lock_toggle, "")
        zm.addSeparator()
        self._add_item(zm, tr("fit_window_image"), self.fit_window_to_image, "")
        interp = m.addMenu(icons.icon("sliders", p["text"], 32), tr("interpolation"))
        i_fast = interp.addAction(tr("inter_fast"))
        i_fast.setCheckable(True)
        i_fast.setChecked(not S.get("inter_high"))
        i_fast.triggered.connect(lambda: S.set("inter_high", False))
        i_hq = interp.addAction(tr("inter_high"))
        i_hq.setCheckable(True)
        i_hq.setChecked(bool(S.get("inter_high")))
        i_hq.triggered.connect(lambda: S.set("inter_high", True))
        filt = m.addMenu(icons.icon("theme", p["text"], 32), tr("filter"))
        for mode, name, key in (("none", tr("filter_none"), "U"),
                                ("soften", tr("filter_soften"), "I"),
                                ("sharpen", tr("filter_sharpen"), "S")):
            a = filt.addAction(name)
            a.setCheckable(True)
            a.setChecked(self._filter_mode == mode)
            a.triggered.connect(lambda _c=False, mode=mode: self.set_filter(mode))
        transm = m.addMenu(icons.icon("grid", p["text"], 32), tr("set_trans_bg"))
        for val, name in (("grid", tr("trans_grid")), ("white", tr("trans_white")),
                          ("black", tr("trans_black"))):
            a = transm.addAction(name)
            a.setCheckable(True)
            a.setChecked(S.get("trans_bg") == val)
            a.triggered.connect(lambda _c=False, v=val: (S.set("trans_bg", v),
                                                         self.canvas.update()))
        view = m
        self._add_item(m, tr("fullscreen"), self.toggle_fullscreen, "F11",
                       "fullscreen")
        self._add_item(m, tr("always_on_top"), self.always_on_top, "Ctrl+A", "pin")
        # rotate
        rm = m.addMenu(icons.icon("rotate-right", p["text"], 32), tr("rotate"))
        self._add_item(rm, tr("rotate_l"), lambda: self.rotate(-90), "Alt+Left")
        self._add_item(rm, tr("rotate_r"), lambda: self.rotate(90), "Alt+Right")
        self._add_item(rm, tr("rotate_180"), lambda: self.rotate(180), "Alt+Down")
        self._add_item(rm, tr("rotate_none"), self.reset_rotation, "Alt+Up")
        rm.addSeparator()
        self._add_item(rm, tr("flip_h"), lambda: self.toggle_flip(True), "Ctrl+M")
        self._add_item(rm, tr("flip_v"), lambda: self.toggle_flip(False), "Ctrl+F")
        # image
        im = m.addMenu(icons.icon("sliders", p["text"], 32), tr("effect"))
        for key, name, hot in (("invert", tr("eff_invert"), "Ctrl+I"),
                               ("gray", tr("eff_gray"), "Ctrl+Y"),
                               ("sepia", tr("eff_sepia"), "Ctrl+Shift+S")):
            a = self._add_item(im, name, lambda _c=False, k=key: self.fx_toggle(k), hot)
            a.setCheckable(True)
            a.setChecked(bool(self._fx.get(key)))
        chm = im.addMenu(icons.icon("theme", p["text"], 32), tr("channel_rgb"))
        for val, name in (("rgb", tr("channel_rgb")), ("r", tr("channel_r")),
                          ("g", tr("channel_g")), ("b", tr("channel_b"))):
            a = chm.addAction(name)
            a.setCheckable(True)
            a.setChecked(self._fx.get("channel", "rgb") == val)
            a.triggered.connect(lambda _c=False, v=val: (
                self._fx.__setitem__("channel", v), self.canvas.set_effects(self._fx)))
        self._add_item(im, tr("eff_gamma") + "...", self.show_adjust, "Ctrl+G")
        im.addSeparator()
        self._add_item(im, tr("anim_play") + "/" + tr("anim_pause"),
                       self.anim_play_pause, "")
        self._add_item(im, tr("anim_prev"), lambda: self.anim_step(-1), "")
        self._add_item(im, tr("anim_next"), lambda: self.anim_step(1), "")
        # slideshow
        sm = m.addMenu(icons.icon("slideshow", p["text"], 32), tr("slideshow"))
        self._add_item(sm, tr("ss_stop"), self.stop_slideshow, "")
        secs = sm.addMenu(icons.icon("slideshow", p["text"], 32), tr("ss_interval"))
        for s in range(1, 11):
            self._add_item(secs, tr("ss_seconds").format(s),
                           lambda _c=False, s=s: self.start_slideshow(s), "")
        a_loop = secs.addAction(tr("ss_loop"))
        a_loop.setCheckable(True)
        a_loop.setChecked(S.get("ss_loop"))
        a_loop.triggered.connect(lambda c: S.set("ss_loop", c))
        a_rand = secs.addAction(tr("ss_random"))
        a_rand.setCheckable(True)
        a_rand.setChecked(S.get("ss_random"))
        a_rand.triggered.connect(lambda c: S.set("ss_random", c))
        fxm = sm.addMenu(icons.icon("theme", p["text"], 32), tr("ss_effect"))
        for val, name in (("none", tr("fx_none")), ("fade", tr("fx_fade")),
                          ("slide", tr("fx_slide"))):
            a = fxm.addAction(name)
            a.setCheckable(True)
            a.setChecked(S.get("ss_effect") == val)
            a.triggered.connect(lambda _c=False, v=val: S.set("ss_effect", v))
        # tools
        tm = m.addMenu(icons.icon("copy", p["text"], 32), tr("copy"))
        self._add_item(tm, tr("copy_image"), self._copy_image, "Ctrl+C")
        self._add_item(tm, tr("copy_path"), self._copy_path, "")
        self._add_item(tm, tr("copy_file"), self._copy_file, "")
        self._add_item(m, tr("paste"), self._paste, "Ctrl+V")
        pfm = m.addMenu(icons.icon("folder", p["text"], 32), tr("photo_folder"))
        self._add_item(pfm, tr("pf_copy1"), lambda: self._to_photo_folder(1, False),
                       "Ins")
        self._add_item(pfm, tr("pf_copy2"), lambda: self._to_photo_folder(2, False),
                       "Shift+Ins")
        self._add_item(pfm, tr("pf_move1"), lambda: self._to_photo_folder(1, True),
                       "Ctrl+Ins")
        wp = self._add_item(m, tr("set_wallpaper"), self._set_wallpaper, "", "wallpaper")
        wp.setEnabled(has)
        ed = self._add_item(m, tr("open_with_editor"), self._open_editor, "Ctrl+E",
                            "edit")
        ed.setEnabled(has)
        bm = m.addMenu(icons.icon("star", p["text"], 32), tr("bookmark"))
        self._add_item(bm, tr("bookmark_add"), self.bookmark_add, "B", "star")
        self._add_item(bm, tr("bookmark_manager"), self._bookmark_manager, "")
        m.addSeparator()
        self._add_item(m, tr("settings") + "...", self._show_settings, "F5",
                       "settings")
        helpm = m.addMenu(icons.icon("info", p["text"], 32), tr("help"))
        self._add_item(helpm, tr("set_keys"), self._show_keys_help, "F1")
        self._add_item(m, tr("about"), self._show_about, "")
        return m

    # ================================================================ file dialogs
    def _dlg_open(self):
        exts = " ".join("*" + e for e in sorted(IMG_EXTS | RAW_EXTS | ARCHIVE_EXTS))
        f, _ = QFileDialog.getOpenFileName(
            self, tr("open_image"), S.get("last_dir") or "",
            f"{tr('file')} ({exts})")
        if f:
            if not S.get("no_save_lastdir"):
                S.set("last_dir", os.path.dirname(f))
            self.open_path(f)

    def _dlg_open_folder(self):
        d = QFileDialog.getExistingDirectory(self, tr("open_folder"),
                                             S.get("last_dir") or "")
        if d:
            if not S.get("no_save_lastdir"):
                S.set("last_dir", d)
            self.open_path(d)

    def _close_image(self):
        self._source = None
        self._doc = None
        self.canvas.set_doc(None)
        self.folder_label.setText("")
        self.file_label.setText("")
        self.setWindowTitle(APP_NAME)
        self.filmstrip.set_source(None)
        self._relayout_overlays()

    def _add_recent(self, path: str):
        if path in self._recents:
            self._recents.remove(path)
        self._recents.insert(0, path)
        self._recents = self._recents[:20]
        _save_json("recents.json", self._recents)

    # ================================================================ file ops
    def _show_in_explorer(self):
        if not self._source:
            return
        if self._source.archive:
            target = self._source.path
            subprocess.Popen(["explorer", "/select,", target])
        else:
            subprocess.Popen(["explorer", "/select,", self._current_key()])

    def rename_current(self):
        if not self._source or self._source.archive or not self._doc:
            self._toast(tr("rename_archived"))
            return
        entry = self._source.entries[self._idx]
        old = entry.key
        base = os.path.basename(old)
        stem, ext = os.path.splitext(base)
        new, ok = QInputDialog.getText(self, tr("rename_title"), tr("fi_name"),
                                       text=base)
        if not ok or not new or new == base:
            return
        if any(ch in new for ch in '\\/:*?"<>|'):
            self._toast(tr("rename_failed"))
            return
        new_path = os.path.join(os.path.dirname(old), new)
        try:
            os.rename(old, new_path)
        except OSError as e:
            self._toast(tr("rename_failed") + f" ({e})")
            return
        src = ImageSource(self._source.path)
        self._open_source(src, new)

    def delete_current(self):
        if not self._source or not self._doc:
            return
        is_arch = self._source.archive
        target = self._source.path if is_arch else self._current_key()
        if S.get("confirm_delete"):
            msg = tr("confirm_delete_archive") if is_arch else tr("confirm_delete")
            r = QMessageBox.question(self, tr("delete"), msg)
            if r != QMessageBox.StandardButton.Yes:
                return
        if self._delete_to_trash(target):
            self._toast(tr("deleted"))
            if is_arch:
                self._close_image()
                return
            src = ImageSource(self._source.path)
            if src.entries:
                self._open_source(src, src.entries[min(self._idx, len(src.entries) - 1)].name)
            else:
                self._toast(tr("no_image_in_folder"))
                self._close_image()

    @staticmethod
    def _delete_to_trash(path: str) -> bool:
        try:
            from ctypes import wintypes

            class SHFILEOPSTRUCTW(ctypes.Structure):
                _fields_ = [("hwnd", wintypes.HWND),
                            ("wFunc", wintypes.UINT),
                            ("pFrom", wintypes.LPCWSTR),
                            ("pTo", wintypes.LPCWSTR),
                            ("fFlags", wintypes.WORD),
                            ("fAnyOperationsAborted", wintypes.BOOL),
                            ("hNameMappings", ctypes.c_void_p),
                            ("lpszProgressTitle", wintypes.LPCWSTR)]
            op = SHFILEOPSTRUCTW()
            op.hwnd = None
            op.wFunc = 3  # FO_DELETE
            op.pFrom = path + "\0"
            op.pTo = None
            op.fFlags = 0x40 | 0x10 | 0x14  # ALLOWUNDO | NOCONFIRMATION | NOERRORUI
            op.fAnyOperationsAborted = False
            op.hNameMappings = None
            op.lpszProgressTitle = None
            rv = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
            return rv == 0 and not op.fAnyOperationsAborted
        except Exception:
            try:
                os.remove(path)
                return True
            except OSError:
                return False

    def _copy_image(self):
        if not self._doc or not self._doc.frames:
            return
        img = self.canvas._processed_frame(self._doc, self.canvas.frame_index(), "")
        QApplication.clipboard().setImage(img)
        self._toast(tr("copied"))

    def _copy_path(self):
        if not self._source:
            return
        path = self._source.path if self._source.archive else self._current_key()
        QApplication.clipboard().setText(path)
        self._toast(tr("copied_path"))

    def _copy_file(self):
        if not self._source:
            return
        from PySide6.QtCore import QMimeData, QUrl
        md = QMimeData()
        if self._source.archive:
            data = self._source.read_bytes(self._source.entries[self._idx])
            tmp = os.path.join(os.path.dirname(os.path.abspath(
                sys.argv[0])), "PView_clip.png")
            name, ext = os.path.splitext(self._source.entries[self._idx].name)
            tmp = os.path.join(os.environ.get("TEMP", "."), "PView_" + name + ext)
            with open(tmp, "wb") as f:
                f.write(data)
            md.setUrls([QUrl.fromLocalFile(tmp)])
        else:
            md.setUrls([QUrl.fromLocalFile(self._current_key())])
        QApplication.clipboard().setMimeData(md)
        self._toast(tr("copied_file"))

    def _paste(self):
        cb = QApplication.clipboard()
        md = cb.mimeData()
        if md.hasUrls():
            for u in md.urls()[:1]:
                if u.isLocalFile():
                    self.open_path(u.toLocalFile())
            return
        img = cb.image()
        if not img.isNull():
            import tempfile
            p = os.path.join(tempfile.gettempdir(), "PView_paste.png")
            img.save(p, "PNG")
            self.open_path(p)

    def _baked_image(self) -> QImage | None:
        """Current image with rotation/flip (and effects) applied."""
        if not self._doc or not self._doc.frames:
            return None
        img = self.canvas._processed_frame(self._doc, self.canvas.frame_index(), "")
        rot, fh, fv = self.canvas.rotation()
        t = QTransform()
        if fh or fv:
            t.scale(-1 if fh else 1, -1 if fv else 1)
        if rot:
            t.rotate(rot)
        if not t.isIdentity():
            img = img.transformed(t, Qt.TransformationMode.SmoothTransformation)
        return img

    def _save_as(self):
        img = self._baked_image()
        if img is None:
            return
        entry = self._source.entries[self._idx] if self._source else None
        stem = os.path.splitext(entry.name)[0] if entry else "image"
        f, sel = QFileDialog.getSaveFileName(
            self, tr("save_as"), os.path.join(os.path.dirname(self._source.path)
                                              if self._source else "", stem + ".png"),
            "PNG (*.png);;JPEG (*.jpg);;WebP (*.webp);;BMP (*.bmp)")
        if not f:
            return
        ext = os.path.splitext(f)[1].lower()
        ok = False
        if ext in (".jpg", ".jpeg"):
            ok = img.convertToFormat(QImage.Format.Format_RGB32).save(f, "JPEG", 92)
        elif ext == ".webp":
            ok = img.save(f, "WEBP", 92)
        elif ext == ".bmp":
            ok = img.save(f, "BMP")
        else:
            ok = img.save(f, "PNG")
        self._toast(tr("wallpaper_done") if ok else tr("cant_open"))

    def _print(self):
        img = self._baked_image()
        if img is None:
            return
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintDialog(printer, self)
        dlg.setWindowTitle(tr("print_title"))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        p = QPainter(printer)
        rect = p.viewport()
        size = img.size()
        scaled = size.scaled(rect.size(), Qt.AspectRatioMode.KeepAspectRatio)
        p.setViewport(rect.x(), rect.y(), scaled.width(), scaled.height())
        p.setWindow(img.rect())
        p.drawImage(0, 0, img)
        p.end()

    def _set_wallpaper(self):
        img = self._baked_image()
        if img is None:
            return
        dlg = WallpaperDialog(self)
        if dlg.exec() != WallpaperDialog.DialogCode.Accepted:
            return
        path = _store_path("wallpaper.jpg")
        img.convertToFormat(QImage.Format.Format_RGB32).save(path, "JPEG", 95)
        import winreg
        style = dlg.style.currentData()
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                               r"Control Panel\Desktop", 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(k, "WallpaperStyle", 0, winreg.REG_SZ, str(style))
            winreg.SetValueEx(k, "TileWallpaper", 0, winreg.REG_SZ, "0")
            winreg.CloseKey(k)
        except OSError:
            pass
        SPI_SETDESKWALLPAPER = 20
        rv = ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER, 0, path, 3)
        self._toast(tr("wallpaper_done") if rv else tr("wallpaper_failed"))

    def _open_editor(self):
        editor = S.get("editor_path")
        if not editor or not os.path.exists(editor):
            self._toast(tr("editor_not_set"))
            return
        if not self._source:
            return
        if self._source.archive:
            data = self._source.read_bytes(self._source.entries[self._idx])
            name = self._source.entries[self._idx].name
            tmp = os.path.join(os.environ.get("TEMP", "."), "PView_" + name)
            with open(tmp, "wb") as f:
                f.write(data)
            subprocess.Popen([editor, tmp])
        else:
            subprocess.Popen([editor, self._current_key()])

    def _to_photo_folder(self, which: int, move: bool):
        dests = {1: S.get("photo_folder1"), 2: S.get("photo_folder2")}
        dest = dests.get(which, "")
        if not dest or not os.path.isdir(dest):
            self._toast(tr("pf_not_set"))
            return
        if not self._source:
            return
        entry = self._source.entries[self._idx]
        try:
            if self._source.archive:
                data = self._source.read_bytes(entry)
                out = os.path.join(dest, entry.name)
                with open(out, "wb") as f:
                    f.write(data)
                src_file = out
            else:
                src_file = entry.key
                if move:
                    shutil.move(src_file, os.path.join(dest, entry.name))
                else:
                    shutil.copy2(src_file, os.path.join(dest, entry.name))
        except OSError as e:
            self._toast(str(e))
            return
        self._toast(tr("pf_done") + ": " + dest)

    def _show_convert(self):
        if not self._source or not self._source.entries:
            return
        entries = self._source.entries if not self._source.archive else \
            self._source.entries
        dlg = ConvertDialog(self._source, entries, self)
        dlg.exec()

    # ================================================================ bookmarks
    def bookmark_add(self):
        if not self._source:
            return
        entry = self._source.entries[self._idx]
        b = {"path": self._source.path, "key": entry.key, "name": entry.name}
        if b not in self._bookmarks:
            self._bookmarks.insert(0, b)
            self._bookmarks = self._bookmarks[:200]
            _save_json("bookmarks.json", self._bookmarks)
        self._toast(tr("bookmark_added"))
        self._update_star(True)

    def _bookmark_manager(self):
        dlg = BookmarkManagerDialog(self._bookmarks, self)
        dlg.openBookmark.connect(lambda b: self.open_path(
            b.get("path", ""), b.get("key", "")))
        if dlg.exec():
            self._bookmarks = [dlg.list.item(i).data(Qt.ItemDataRole.UserRole)
                               for i in range(dlg.list.count())]
            _save_json("bookmarks.json", self._bookmarks)
            self._update_star()

    def _update_star(self, on: bool | None = None):
        if on is None:
            cur = self._current_key()
            on = any(b.get("key") == cur and b.get("path") == (self._source.path
                     if self._source else "") for b in self._bookmarks)
        self.btn_star.set_icon_name("star", filled=on)

    # ================================================================ settings/about
    def _show_settings(self):
        dlg = SettingsDialog(self)
        dlg.languageChangeRequested.connect(lambda _lang: self._restart())
        dlg.exec()
        # live-apply
        self.apply_theme()
        self._relayout_overlays()
        self.canvas.update()
        self._rebuild_shortcuts()

    def _show_keys_help(self):
        dlg = SettingsDialog(self)
        dlg.nav.setCurrentRow(4)
        dlg.exec()

    def _show_about(self):
        dlg = SettingsDialog(self)
        dlg.nav.setCurrentRow(6)
        dlg.exec()

    def _restart(self):
        S.set("_restart", True)
        self.stop_slideshow()
        DOC_CACHE.clear()
        QApplication.quit()
        args = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
        os.execl(sys.executable, sys.executable, *args)

    def _new_window(self):
        w = MainWindow(self._source.path if self._source else "")
        w.show()

    # ================================================================ toast
    def _toast(self, text: str):
        self.toast.show_message(text)

    # ================================================================ DnD
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        urls = ev.mimeData().urls()
        if not urls:
            return
        p = urls[0].toLocalFile()
        if p:
            self.open_path(p)

    # ================================================================ shortcuts
    def _sc(self, key: str, cb, ctx=Qt.ShortcutContext.WindowShortcut):
        s = QShortcut(QKeySequence(key), self)
        s.setContext(ctx)
        s.activated.connect(cb)
        return s

    def _command_defs(self):
        """Ordered registry: cmd_id -> (default keys, callback, description)."""
        d = {}
        d["nav_next"] = (["Right", "Down", "Space", "PgDown"],
                         lambda: self._kbd_step(+1), tr("next_image"))
        d["nav_prev"] = (["Left", "Up", "PgUp"],
                         lambda: self._kbd_step(-1), tr("prev_image"))
        d["go_first"] = (["Home"], self.go_first, tr("first_image"))
        d["go_last"] = (["End"], self.go_last, tr("last_image"))
        d["next10"] = (["Ctrl+PgDown"], self.go_next10, tr("next_10"))
        d["prev10"] = (["Ctrl+PgUp"], self.go_prev10, tr("prev_10"))
        d["random_next"] = (["Ctrl+Alt+PgDown"], self.go_random_next,
                            tr("cmd_random_next"))
        d["prev_folder"] = (["["], self.prev_folder, tr("prev_folder"))
        d["next_folder"] = (["]"], self.next_folder, tr("next_folder"))
        d["zoom_in"] = (["+", "="], lambda: self.canvas.zoom_in(),
                        tr("zoom_in"))
        d["zoom_out"] = (["-"], lambda: self.canvas.zoom_out(),
                         tr("zoom_out"))
        d["vm_original"] = (["0"], lambda: self.set_view_mode("original"),
                            tr("vm_original"))
        d["vm_fit"] = (["9"], lambda: self.set_view_mode("fit"), tr("vm_fit"))
        d["vm_width"] = (["8"], lambda: self.set_view_mode("width"),
                         tr("vm_fit_width"))
        d["vm_l2r"] = (["7"], lambda: self.set_view_mode("l2r"),
                       tr("vm_double_l2r"))
        d["vm_r2l"] = (["6"], lambda: self.set_view_mode("r2l"),
                       tr("vm_double_r2l"))
        d["vm_webtoon"] = (["5"], lambda: self.set_view_mode("webtoon"),
                           tr("vm_webtoon"))
        d["stretch_small"] = (["Z"], self.toggle_stretch_small,
                              tr("vm_stretch_small"))
        d["rot_cw"] = (["Alt+Right"], lambda: self.rotate(90), tr("rotate_r"))
        d["rot_ccw"] = (["Alt+Left"], lambda: self.rotate(-90), tr("rotate_l"))
        d["rot_180"] = (["Alt+Down"], lambda: self.rotate(180),
                        tr("rotate_180"))
        d["rot_reset"] = (["Alt+Up"], self.reset_rotation, tr("rotate_none"))
        d["flip_h"] = (["Ctrl+M"], lambda: self.toggle_flip(True),
                       tr("flip_h"))
        d["flip_v"] = (["Ctrl+F"], lambda: self.toggle_flip(False),
                       tr("flip_v"))
        d["fx_invert"] = (["Ctrl+I"], lambda: self.fx_toggle("invert"),
                          tr("eff_invert"))
        d["fx_gray"] = (["Ctrl+Y"], lambda: self.fx_toggle("gray"),
                        tr("eff_gray"))
        d["fx_sepia"] = (["Ctrl+Shift+S"], lambda: self.fx_toggle("sepia"),
                         tr("eff_sepia"))
        d["adjust"] = (["Ctrl+G"], self.show_adjust, tr("eff_gamma"))
        d["filter_none"] = (["U"], lambda: self.set_filter("none"),
                            tr("filter_none"))
        d["filter_soften"] = (["I"], lambda: self.set_filter("soften"),
                              tr("filter_soften"))
        d["filter_sharpen"] = (["S"], lambda: self.set_filter("sharpen"),
                               tr("filter_sharpen"))
        d["cycle_trans"] = (["Alt+T"], self.cycle_trans_bg, tr("set_trans_bg"))
        d["slideshow"] = (["F8"], self.toggle_slideshow, tr("slideshow"))
        for n in range(1, 10):
            d[f"ss_speed_{n}"] = (
                [f"Ctrl+{n}"],
                lambda n=n: self.start_slideshow(n),
                f"{tr('slideshow')} {n}s")
        d["fullscreen"] = (["F11", "Alt+Return", "F"], self.toggle_fullscreen,
                           tr("fullscreen"))
        d["navigator"] = (["Return"], self.show_navigator, tr("navigator"))
        d["info"] = (["Tab"], self.toggle_info, tr("exif_info"))
        d["mini_title"] = (["Shift+Tab"], self.toggle_mini_title,
                           tr("cmd_mini_title"))
        d["bookmark_add"] = (["B"], self.bookmark_add, tr("bookmark_add"))
        d["rename"] = (["F2"], self.rename_current, tr("rename"))
        d["delete"] = (["Del"], self.delete_current, tr("delete"))
        d["copy_image"] = (["Ctrl+C"], self._copy_image, tr("copy_image"))
        d["paste"] = (["Ctrl+V"], self._paste, tr("paste"))
        d["convert"] = (["Ctrl+T"], self._show_convert, tr("convert"))
        d["print"] = (["Ctrl+P"], self._print, tr("print"))
        d["save_as"] = (["Ctrl+S"], self._save_as, tr("save"))
        d["open_editor"] = (["Ctrl+E"], self._open_editor,
                            tr("open_with_editor"))
        d["to_photo1"] = (["Ins"], lambda: self._to_photo_folder(1, False),
                          tr("photo_folder"))
        d["to_photo2"] = (["Shift+Ins"],
                          lambda: self._to_photo_folder(2, False),
                          tr("photo_folder"))
        d["copy_photo1"] = (["Ctrl+Ins"],
                            lambda: self._to_photo_folder(1, True),
                            tr("photo_folder"))
        d["always_top"] = (["Ctrl+A"], self.always_on_top,
                           tr("always_on_top"))
        d["show_explorer"] = (["Ctrl+Return"], self._show_in_explorer,
                              tr("open_location"))
        d["settings"] = (["F5"], self._show_settings, tr("settings"))
        d["help"] = (["F1"], self._show_keys_help, tr("help"))
        d["close_image"] = (["F4", "Ctrl+W"], self._close_image,
                            tr("close_image"))
        d["open_file"] = (["Ctrl+O"], self._dlg_open, tr("open_image"))
        d["new_window"] = (["Ctrl+N"], self._new_window, tr("cmd_new_window"))
        d["esc"] = (["Esc"], self._esc, tr("exit"))
        d["gps"] = (["Ctrl+Shift+G"], self._open_gps, tr("cmd_gps"))
        return d

    def _effective_keys(self) -> dict:
        """cmd -> effective key list honouring user overrides."""
        defs = self._command_defs()
        overrides = S.get("key_overrides") or {}
        out = {}
        for cmd, (dkeys, _cb, _desc) in defs.items():
            # an empty override list means "no bindings" — do NOT fall back
            out[cmd] = list(overrides[cmd]) if cmd in overrides else list(dkeys)
        return out

    def _build_shortcuts(self):
        # drop previous shortcuts (rebuilt from overrides map)
        for sc in getattr(self, "_sc_objs", []):
            try:
                sc.setParent(None)
                sc.deleteLater()
            except Exception:
                pass
        self._sc_objs = []
        self._sc_map = self._effective_keys()
        defs = self._command_defs()
        for cmd, keys in self._sc_map.items():
            cb = defs[cmd][1]
            for k in keys:
                try:
                    self._sc_objs.append(self._sc(k, cb))
                except Exception:
                    pass

    def _rebuild_shortcuts(self):
        self._build_shortcuts()

    def _kbd_step(self, delta: int):
        if self._webtoon_mode:
            self.webtoon.scroll_by(0, delta * self.height() * 0.85)
            return
        self._step(delta)

    def _esc(self):
        if self._fullscreen:
            self.toggle_fullscreen()
        elif S.get("esc_exit"):
            self.close()

    def _open_gps(self):
        if self._doc and self._doc.exif and self._doc.exif.gps:
            lat, lon = self._doc.exif.gps
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl(
                f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=16/{lat}/{lon}"))

    # ================================================================ lifecycle
    def closeEvent(self, ev):
        if S.get("remember_window"):
            from PySide6.QtCore import QByteArray
            S.set("geometry", bytes(
                self.saveGeometry().toBase64()).decode("ascii"))
        self._remember_position()
        self.stop_slideshow()
        self.canvas._fx_worker.stop()
        DOC_CACHE.clear()
        if self._source:
            self._source.close()
        super().closeEvent(ev)
