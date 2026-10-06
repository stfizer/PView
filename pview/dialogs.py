"""Dialogs: settings, convert, wallpaper, password, bookmarks, effects, about."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog,
                               QFormLayout, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QMessageBox,
                               QProgressBar, QPushButton, QRadioButton,
                               QSlider, QSpinBox, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from . import APP_NAME, APP_VERSION
from . import settings as S
from .i18n import tr
from .loader import CODEC_ERRORS

# ---------------------------------------------------------------- helpers

def _sep():
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet("background: rgba(128,128,128,0.25); border: none;")
    return f


# ------------------------------------------------------- file associations
ASSOC_PROGID = "Pview.Image"
ASSOC_GROUPS = [
    ("assoc_g_common", ["jpg", "jpeg", "jpe", "jfif", "bmp", "gif", "tga",
                        "png", "tif", "tiff", "dds", "pcx", "pbm", "pgm",
                        "ppm", "pnm"]),
    ("assoc_g_editor", ["psd", "psb", "clip"]),
    ("assoc_g_modern", ["jp2", "jpc", "jpx", "j2k", "j2c", "jpf", "jpm",
                        "jxr", "hdp", "wdp", "webp", "heic", "heif", "hif",
                        "avif", "avifs", "bpg", "ugoira", "apng", "qoi",
                        "exr", "jxl", "svg", "hdr"]),
    ("assoc_g_raw", ["dng", "cr2", "cr3", "crw", "nef", "nrw", "orf", "rw2",
                     "pef", "sr2", "srw", "3fr", "arw", "erf", "kdc", "mef",
                     "mos", "raf", "x3f", "mrw"]),
    ("assoc_g_comic", ["cbr", "cbz", "cbt", "cb7"]),
    ("assoc_g_other", ["ico"]),
]


def _assoc_exe() -> str:
    import sys
    return sys.executable


def _progid_app_name(progid: str) -> str:
    """Human-readable app name behind a ProgID (fallback: the ProgID)."""
    if not progid:
        return ""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                            progid + r"\shell\open\command") as k:
            cmd = winreg.QueryValueEx(k, "")[0]
        exe = cmd.strip().strip('"').split('"')[0].strip()
        if not exe:
            exe = cmd.split(" ")[0].strip('"')
        return os.path.splitext(os.path.basename(exe))[0]
    except Exception:
        return progid.rsplit(".", 1)[0] if "." in progid else progid


def _read_assoc(ext: str) -> str:
    """Effective app name for an extension ('' = not associated)."""
    try:
        import winreg
        # user choice (Windows "Default apps") wins over classes
        try:
            with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer"
                    fr"\FileExts\.{ext}\UserChoice") as k:
                progid = winreg.QueryValueEx(k, "ProgId")[0]
                if progid:
                    return _progid_app_name(progid)
        except OSError:
            pass
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "." + ext) as k:
            progid = winreg.QueryValueEx(k, "")[0]
        return _progid_app_name(progid)
    except Exception:
        return ""


def _write_assoc(ext: str) -> None:
    """Associate <ext> with P view for the current user (no admin needed)."""
    import sys
    import winreg
    exe = sys.executable
    if not getattr(sys, "frozen", False):
        # running from source: point the association at the packaged exe so
        # double-clicking doesn't launch a bare python interpreter
        cand = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "dist", "Pview", "Pview.exe")
        if os.path.exists(cand):
            exe = cand
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                          fr"Software\Classes\.{ext}") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, ASSOC_PROGID)
    base = fr"Software\Classes\{ASSOC_PROGID}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                          base + r"\shell\open\command") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'"{exe}" "%1"')
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                          base + r"\DefaultIcon") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'"{exe}",0')
    # Windows prefers the per-user UserChoice (written by "Default apps" /
    # "Open with -> always") over the Classes chain, so drop it for this
    # extension or the new association never takes effect on double-click.
    # Deleting the whole UserChoice key is allowed (only rewriting its
    # ProgId requires the protected hash).
    try:
        uc_key = (r"Software\Microsoft\Windows\CurrentVersion\Explorer"
                  fr"\FileExts\.{ext}\UserChoice")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, uc_key)
    except OSError:
        pass
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
    except Exception:
        pass


# ------------------------------------------------- explorer context menu
_CTX_KEY = (r"Software\Classes\SystemFileAssociations\image\shell"
            r"\Pview.Open")


def _ctx_menu_enabled() -> bool:
    try:
        import winreg
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CTX_KEY)
        return True
    except OSError:
        return False


def _set_ctx_menu(enabled: bool) -> None:
    import sys
    import winreg
    if enabled:
        exe = sys.executable
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _CTX_KEY) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "Open with P view")
            winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, f'"{exe}",0')
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                              _CTX_KEY + r"\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'"{exe}" "%1"')
    else:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER,
                             _CTX_KEY + r"\command")
        except OSError:
            pass
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, _CTX_KEY)
        except OSError:
            pass


def _title(text: str) -> QLabel:
    l = QLabel(text)
    l.setObjectName("SectionTitle")
    return l


class PathRow(QWidget):
    def __init__(self, label: str, value: str = "", dir_mode: bool = True):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel(label))
        self.edit = QLineEdit(value)
        lay.addWidget(self.edit, 1)
        btn = QPushButton(tr("browse"))
        btn.setObjectName("Card")
        btn.clicked.connect(self._browse)
        self._dir = dir_mode
        lay.addWidget(btn)

    def _browse(self):
        if self._dir:
            d = QFileDialog.getExistingDirectory(self, tr("browse"), self.edit.text())
            if d:
                self.edit.setText(d)
        else:
            f, _ = QFileDialog.getOpenFileName(self, tr("browse"), self.edit.text(),
                                               "Executable (*.exe)")
            if f:
                self.edit.setText(f)

    def text(self) -> str:
        return self.edit.text().strip()


# ---------------------------------------------------------------- settings

class SettingsDialog(QDialog):
    settingsChanged = Signal()
    languageChangeRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("set_title"))
        self.resize(840, 720)
        root = QVBoxLayout(self)
        body = QHBoxLayout()
        root.addLayout(body, 1)

        from PySide6.QtWidgets import QListWidget
        self.nav = QListWidget()
        self.nav.setObjectName("NavList")
        self.nav.setFixedWidth(170)
        for name in (tr("set_general"), tr("set_view"), tr("set_image"),
                     tr("set_assoc"), tr("set_keys"), tr("set_mouse"),
                     tr("set_bookmark"), tr("set_ctx"), tr("set_folders"),
                     tr("set_misc"), tr("set_language"), tr("set_about")):
            self.nav.addItem(name)
        self.stack = QStackedWidget()
        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)

        self.stack.addWidget(self._page_general())
        self.stack.addWidget(self._page_view())
        self.stack.addWidget(self._page_image())
        self.stack.addWidget(self._page_assoc())
        self.stack.addWidget(self._page_keys())
        self.stack.addWidget(self._page_mouse())
        self.stack.addWidget(self._page_bookmark())
        self.stack.addWidget(self._page_contextmenu())
        self.stack.addWidget(self._page_folders())
        self.stack.addWidget(self._page_misc())
        self.stack.addWidget(self._page_language())
        self.stack.addWidget(self._page_about())
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        btns = QHBoxLayout()
        btns.addStretch(1)
        reset_btn = QPushButton(tr("set_reset_all"))
        reset_btn.clicked.connect(self._reset)
        ok = QPushButton(tr("ok"))
        ok.setObjectName("Accent")
        ok.clicked.connect(self._apply_and_close)
        cancel = QPushButton(tr("cancel"))
        cancel.clicked.connect(self.reject)
        btns.addWidget(reset_btn)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        root.addLayout(btns)

    # ---------- pages ----------
    def _page_general(self) -> QWidget:
        w = QWidget()
        f = QVBoxLayout(w)
        f.addWidget(_title(tr("set_general")))
        self.chk_del = QCheckBox(tr("set_confirm_del"))
        self.chk_del.setChecked(S.get("confirm_delete"))
        self.chk_esc = QCheckBox(tr("set_esc"))
        self.chk_esc.setChecked(S.get("esc_exit"))
        self.chk_win = QCheckBox(tr("set_remember_win"))
        self.chk_win.setChecked(S.get("remember_window"))
        self.chk_single = QCheckBox(tr("set_single_instance"))
        self.chk_single.setChecked(S.get("single_instance"))
        for c in (self.chk_esc, self.chk_single, self.chk_del, self.chk_win):
            f.addWidget(c)
        f.addStretch(1)
        return w

    def _page_view(self) -> QWidget:
        w = QWidget()
        f = QVBoxLayout(w)
        f.addWidget(_title(tr("set_view")))
        self.chk_side = QCheckBox(tr("set_side_arrow"))
        self.chk_side.setChecked(S.get("side_arrow"))
        self.chk_bar = QCheckBox(tr("set_bottom_bar"))
        self.chk_bar.setChecked(S.get("bottom_bar"))
        self.chk_mini = QCheckBox(tr("cmd_mini_title"))
        self.chk_mini.setChecked(S.get("mini_title"))
        self.chk_inter = QCheckBox(tr("inter_high"))
        self.chk_inter.setChecked(S.get("inter_high"))
        self.chk_zlock = QCheckBox(tr("set_zoom_lock"))
        self.chk_zlock.setChecked(S.get("zoom_lock_save"))
        f.addWidget(self.chk_side)
        f.addWidget(self.chk_bar)
        f.addWidget(self.chk_mini)
        f.addWidget(self.chk_inter)
        f.addWidget(self.chk_zlock)
        f.addWidget(_sep())
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("set_filmstrip_hide")))
        self.fs_hide = QSpinBox()
        self.fs_hide.setRange(3, 10)
        self.fs_hide.setValue(int(S.get("filmstrip_hide_secs") or 5))
        self.fs_hide.setSuffix(" s")
        row.addWidget(self.fs_hide)
        row.addStretch(1)
        f.addLayout(row)
        f.addWidget(_sep())
        # theme color lives at the bottom of the browsing page (BandiView)
        f.addWidget(QLabel(tr("set_theme")))
        self.theme = QComboBox()
        self.theme.addItems([tr("theme_system"), tr("theme_light"), tr("theme_dark")])
        self.theme.setCurrentIndex(
            {"system": 0, "light": 1, "dark": 2}.get(S.get("theme"), 0))
        f.addWidget(self.theme)
        f.addStretch(1)
        return w

    def _page_image(self) -> QWidget:
        w = QWidget()
        f = QVBoxLayout(w)
        f.addWidget(_title(tr("set_image")))
        self.chk_exifrot = QCheckBox(tr("set_exif_rotate"))
        self.chk_exifrot.setChecked(S.get("exif_rotate"))
        self.chk_anim = QCheckBox(tr("set_auto_play"))
        self.chk_anim.setChecked(S.get("auto_play_anim"))
        self.chk_prog = QCheckBox(tr("set_progressive"))
        self.chk_prog.setChecked(S.get("progressive"))
        self.chk_iccf = QCheckBox(tr("set_icc_file"))
        self.chk_iccf.setChecked(S.get("icc_file"))
        self.chk_iccm = QCheckBox(tr("set_icc_monitor"))
        self.chk_iccm.setChecked(S.get("icc_monitor"))
        self.chk_keepfx = QCheckBox(tr("set_keep_effects"))
        self.chk_keepfx.setChecked(S.get("keep_effects"))
        self.chk_group = QCheckBox(tr("set_group_rawjpg"))
        self.chk_group.setChecked(S.get("group_raw_jpg"))
        for c in (self.chk_exifrot, self.chk_prog, self.chk_iccf,
                  self.chk_iccm, self.chk_anim, self.chk_keepfx,
                  self.chk_group):
            f.addWidget(c)
        # next-image cache with an adjustable budget (BandiView)
        row = QHBoxLayout()
        self.chk_prefetch = QCheckBox(tr("set_prefetch"))
        self.chk_prefetch.setChecked(S.get("prefetch_next"))
        row.addWidget(self.chk_prefetch)
        row.addStretch(1)
        row.addWidget(QLabel(tr("set_cache_mb")))
        self.cache_mb = QSpinBox()
        self.cache_mb.setRange(64, 4096)
        self.cache_mb.setValue(int(S.get("cache_mb") or 600))
        self.cache_mb.setSuffix(" MB")
        row.addWidget(self.cache_mb)
        f.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("set_raw_or_jpg")))
        self.rawjpg = QComboBox()
        self.rawjpg.addItem(tr("show_jpg"), True)
        self.rawjpg.addItem(tr("show_raw"), False)
        self.rawjpg.setCurrentIndex(0 if S.get("group_show_jpg") else 1)
        row.addWidget(self.rawjpg)
        row.addStretch(1)
        f.addLayout(row)
        f.addWidget(_sep())
        # background colour belongs to image processing (BandiView layout)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("set_bkcolor")))
        self.bkcolor = QComboBox()
        self.bkcolor.addItems([tr("bk_auto"), tr("bk_dark"), tr("bk_light"),
                               tr("bk_white"), tr("bk_black"), tr("bk_grid")])
        self.bkcolor.setCurrentIndex({"auto": 0, "dark": 1, "light": 2, "white": 3,
                                      "black": 4, "grid": 5}.get(S.get("bkcolor"), 0))
        row.addWidget(self.bkcolor)
        row.addStretch(1)
        f.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("set_trans_bg") + " (Alt+T)"))
        self.trans = QComboBox()
        self.trans.addItems([tr("trans_grid"), tr("trans_white"), tr("trans_black")])
        self.trans.setCurrentIndex({"grid": 0, "white": 1, "black": 2}.get(
            S.get("trans_bg"), 0))
        row.addWidget(self.trans)
        row.addStretch(1)
        f.addLayout(row)
        f.addWidget(_sep())
        # spacing options (webtoon / double page) — BandiView layout
        row = QHBoxLayout()
        self.chk_wgap = QCheckBox(tr("set_webtoon_gap"))
        self.chk_wgap.setChecked(S.get("webtoon_gap"))
        row.addWidget(self.chk_wgap)
        self.wgap_px = QSpinBox()
        self.wgap_px.setRange(0, 200)
        self.wgap_px.setValue(int(S.get("webtoon_gap_px") or 10))
        row.addWidget(self.wgap_px)
        row.addStretch(1)
        f.addLayout(row)
        row = QHBoxLayout()
        self.chk_dgap = QCheckBox(tr("set_double_gap"))
        self.chk_dgap.setChecked(S.get("double_gap"))
        row.addWidget(self.chk_dgap)
        self.dgap_px = QSpinBox()
        self.dgap_px.setRange(0, 200)
        self.dgap_px.setValue(int(S.get("double_gap_px") or 10))
        row.addWidget(self.dgap_px)
        row.addStretch(1)
        f.addLayout(row)
        self.chk_cover = QCheckBox(tr("set_double_cover"))
        self.chk_cover.setChecked(S.get("double_cover"))
        f.addWidget(self.chk_cover)
        f.addStretch(1)
        return w

    def _page_mouse(self) -> QWidget:
        w = QWidget()
        f = QVBoxLayout(w)
        f.addWidget(_title(tr("set_mouse")))
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("set_wheel")))
        self.wheel = QComboBox()
        self.wheel.addItem(tr("wheel_page"), "page")
        self.wheel.addItem(tr("wheel_zoom"), "zoom")
        self.wheel.setCurrentIndex(0 if S.get("wheel_mode") == "page" else 1)
        row.addWidget(self.wheel)
        row.addStretch(1)
        f.addLayout(row)
        self.chk_dbl = QCheckBox(tr("set_dbl_max"))
        self.chk_dbl.setChecked(S.get("dbl_click_max"))
        self.chk_edge = QCheckBox(tr("set_edge_page"))
        self.chk_edge.setChecked(S.get("edge_page"))
        f.addWidget(self.chk_dbl)
        f.addWidget(self.chk_edge)
        f.addStretch(1)
        return w

    def _page_bookmark(self) -> QWidget:
        w = QWidget()
        f = QVBoxLayout(w)
        f.addWidget(_title(tr("set_bookmark")))
        btn_mgr = QPushButton(tr("bookmark_open_mgr"))
        btn_mgr.clicked.connect(self._open_bookmark_mgr)
        btn_bv = QPushButton(tr("import_bv"))
        btn_bv.clicked.connect(lambda: self._import_bookmarks("BandiView"))
        btn_hv = QPushButton(tr("import_hv"))
        btn_hv.clicked.connect(lambda: self._import_bookmarks("Honeyview"))
        for b in (btn_mgr, btn_bv, btn_hv):
            f.addWidget(b)
        f.addWidget(_sep())
        f.addWidget(QLabel(tr("bm_history")))
        self.chk_posa = QCheckBox(tr("set_remember_pos_archive"))
        self.chk_posa.setChecked(S.get("remember_pos_archive"))
        self.chk_posf = QCheckBox(tr("set_remember_pos_folder"))
        self.chk_posf.setChecked(S.get("remember_pos_folder"))
        f.addWidget(self.chk_posa)
        f.addWidget(self.chk_posf)
        f.addStretch(1)
        return w

    def _open_default_apps(self):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl("ms-settings:defaultapps"))

    def _import_bookmarks(self, app_name: str):
        """Scan the usual BandiView / Honeyview data locations for bookmark
        entries and merge absolute image paths into the bookmark list."""
        import re as _re
        import winreg
        host = self.parent()
        if host is None or not hasattr(host, "_bookmarks"):
            return
        cand_files = []
        bases = []
        for env in ("LOCALAPPDATA", "APPDATA"):
            base = os.environ.get(env)
            if base:
                bases.append(os.path.join(base, app_name))
        # portable / install-dir config via registry
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                fr"Software\Bandisoft\{app_name}") as k:
                for i in range(winreg.QueryInfoKey(k)[1]):
                    try:
                        v = winreg.EnumValue(k, i)[1]
                        if isinstance(v, str) and os.path.isdir(v):
                            bases.append(v)
                    except OSError:
                        continue
        except OSError:
            pass
        for base in bases:
            if not os.path.isdir(base):
                continue
            for fn in ("config.ini", "bookmark.ini", "bookmark.dat",
                       "bookmarks.ini"):
                p = os.path.join(base, fn)
                if os.path.exists(p):
                    cand_files.append(p)
        img_exts = {".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".gif", ".bmp",
                    ".webp", ".avif", ".tif", ".tiff", ".heic", ".jxl"}
        paths = []
        for p in cand_files:
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except Exception:
                continue
            for line in text.splitlines():
                s = line.split("=", 1)[-1].strip().strip('"').rstrip("\\/")
                if _re.match(r"^[A-Za-z]:\\", s) and \
                        os.path.splitext(s)[1].lower() in img_exts \
                        and os.path.exists(s):
                    paths.append(s)
        merged = list(host._bookmarks or [])
        known = {b.get("path", "") for b in merged}
        added = 0
        for p in paths:
            if p in known:
                continue
            merged.append({"path": p, "key": p, "name": os.path.basename(p)})
            known.add(p)
            added += 1
        if added:
            host._bookmarks = merged[:200]
            host._toast(tr("bm_import_ok").format(added))
        else:
            host._toast(tr("bm_import_none"))

    def _open_bookmark_mgr(self):
        w = self.parent()
        if w is None or not hasattr(w, "_bookmarks"):
            return
        dlg = BookmarkManagerDialog(w._bookmarks, self)
        dlg.openBookmark.connect(lambda b: w.open_path(
            b.get("path", ""), b.get("key", "")))
        if dlg.exec():
            w._bookmarks = [dlg.list.item(i).data(Qt.ItemDataRole.UserRole)
                            for i in range(dlg.list.count())]

    def _page_folders(self) -> QWidget:
        w = QWidget()
        f = QVBoxLayout(w)
        f.addWidget(_title(tr("set_folders")))
        self.pf1 = PathRow(tr("set_pf1"), S.get("photo_folder1"))
        self.pf2 = PathRow(tr("set_pf2"), S.get("photo_folder2"))
        f.addWidget(self.pf1)
        f.addWidget(self.pf2)
        f.addStretch(1)
        return w

    def _page_contextmenu(self) -> QWidget:
        w = QWidget()
        f = QVBoxLayout(w)
        f.addWidget(_title(tr("set_ctx")))
        self.chk_ctx = QCheckBox(tr("ctx_enable"))
        self.chk_ctx.setChecked(_ctx_menu_enabled())
        self.chk_ctx.toggled.connect(_set_ctx_menu)
        f.addWidget(self.chk_ctx)
        f.addWidget(_sep())
        hint = QLabel(tr("ctx_hint"))
        hint.setObjectName("Dim")
        hint.setWordWrap(True)
        f.addWidget(hint)
        f.addStretch(1)
        return w

    def _page_misc(self) -> QWidget:
        w = QWidget()
        f = QVBoxLayout(w)
        f.addWidget(_title(tr("set_misc")))
        f.addWidget(QLabel(tr("misc_slideshow")))
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("ss_interval")))
        self.ss_interval = QSpinBox()
        self.ss_interval.setRange(1, 60)
        self.ss_interval.setValue(int(S.get("ss_interval")))
        self.ss_interval.setSuffix(" s")
        row.addWidget(self.ss_interval)
        row.addStretch(1)
        f.addLayout(row)
        self.ss_loop = QCheckBox(tr("ss_loop"))
        self.ss_loop.setChecked(S.get("ss_loop"))
        self.ss_random = QCheckBox(tr("ss_random"))
        self.ss_random.setChecked(S.get("ss_random"))
        f.addWidget(self.ss_loop)
        f.addWidget(self.ss_random)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("ss_effect")))
        self.ss_effect = QComboBox()
        self.ss_effect.addItems([tr("fx_none"), tr("fx_fade"), tr("fx_slide")])
        self.ss_effect.setCurrentIndex({"none": 0, "fade": 1, "slide": 2}.get(
            S.get("ss_effect"), 1))
        row.addWidget(self.ss_effect)
        row.addStretch(1)
        f.addLayout(row)
        f.addWidget(_sep())
        f.addWidget(QLabel(tr("misc_editor")))
        self.editor = PathRow(tr("set_editor"), S.get("editor_path"), dir_mode=False)
        f.addWidget(self.editor)
        self.chk_nolastdir = QCheckBox(tr("set_no_save_lastdir"))
        self.chk_nolastdir.setChecked(S.get("no_save_lastdir"))
        f.addWidget(self.chk_nolastdir)
        f.addStretch(1)
        return w

    def _page_keys(self) -> QWidget:
        w = QWidget()
        f = QVBoxLayout(w)
        f.addWidget(_title(tr("keys_customize")))
        host = self.parent()
        # command registry lives on the main window
        self._keys_host = host if hasattr(host, "_command_defs") else None

        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels([tr("keys_col_cmd"),
                                         tr("keys_col_desc"),
                                         tr("keys_col_keys")])
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.setColumnWidth(0, 150)
        table.setColumnWidth(1, 230)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._keys_table = table
        self._keys_pending = dict(S.get("key_overrides") or {})
        f.addWidget(table, 1)

        side = QVBoxLayout()
        for text, fn in ((tr("keys_add"), self._keys_add),
                         (tr("keys_modify"), self._keys_modify),
                         (tr("keys_del"), self._keys_del),
                         (tr("keys_reset"), self._keys_reset)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            side.addWidget(b)
        hint = QLabel(tr("keys_pick"))
        hint.setObjectName("Dim")
        hint.setWordWrap(True)
        side.addWidget(hint)
        side.addStretch(1)
        body = QHBoxLayout()
        body.addWidget(table, 1)
        body.addLayout(side)
        f.addLayout(body, 1)
        self._keys_fill()
        return w

    def _keys_eff(self) -> dict:
        """cmd -> effective keys honouring the (unsaved) pending overrides."""
        if self._keys_host is None:
            return {}
        defs = self._keys_host._command_defs()
        out = {}
        for cmd, (dkeys, _cb, _desc) in defs.items():
            # an empty pending list means "no bindings" — do NOT fall back
            out[cmd] = list(self._keys_pending[cmd]) \
                if cmd in self._keys_pending else list(dkeys)
        return out

    def _keys_fill(self):
        """Refresh the shortcut table from the pending override state."""
        t = self._keys_table
        if self._keys_host is None:
            return
        eff = self._keys_eff()
        defs = self._keys_host._command_defs()
        t.setRowCount(0)
        for cmd, (_dkeys, _cb, desc) in defs.items():
            r = t.rowCount()
            t.insertRow(r)
            for col, text in ((0, cmd), (1, desc),
                              (2, ",  ".join(eff.get(cmd, [])) or tr("assoc_none"))):
                it = QTableWidgetItem(text)
                it.setFlags(Qt.ItemFlag.ItemIsEnabled
                            | Qt.ItemFlag.ItemIsSelectable)
                t.setItem(r, col, it)

    def _keys_selected_cmd(self):
        r = self._keys_table.currentRow()
        if r < 0:
            return ""
        it = self._keys_table.item(r, 0)
        return it.text() if it else ""

    def _keys_ask_sequence(self) -> str:
        """Modal mini-dialog with a QKeySequenceEdit; returns the sequence."""
        from PySide6.QtWidgets import (QDialog, QDialogButtonBox,
                                       QKeySequenceEdit, QVBoxLayout)
        d = QDialog(self)
        d.setWindowTitle(tr("keys_conflict"))
        lay = QVBoxLayout(d)
        lay.addWidget(QLabel(tr("keys_pick")))
        ed = QKeySequenceEdit()
        lay.addWidget(ed)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        lay.addWidget(bb)
        d.resize(360, 120)
        if d.exec() == QDialog.DialogCode.Accepted:
            return ed.keySequence().toString(QKeySequence.SequenceFormat.NativeText)
        return ""

    def _keys_owner_of(self, seq_text: str, exclude_cmd: str = "") -> str:
        """Command id currently owning the given sequence ('' = none)."""
        for cmd, keys in self._keys_eff().items():
            if cmd != exclude_cmd and seq_text in keys:
                return cmd
        return ""

    def _keys_set_binding(self, cmd: str, new_seq: str, replace_all: bool):
        """Assign new_seq to cmd, resolving conflicts after confirmation."""
        if self._keys_host is None or not new_seq:
            return
        owner = self._keys_owner_of(new_seq, exclude_cmd=cmd)
        if owner:
            desc = self._keys_host._command_defs()[owner][2]
            target = self._keys_host._command_defs()[cmd][2]
            r = QMessageBox.question(
                self, tr("keys_conflict"),
                tr("keys_conflict_msg").format(new_seq, desc, target),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if r != QMessageBox.StandardButton.Yes:
                return
            # remove from the old owner (stage a pending override without it)
            self._keys_remove_key(owner, new_seq)
        if replace_all:
            self._keys_pending[cmd] = [new_seq]
        else:
            cur = list(self._keys_pending.get(cmd)
                       or self._keys_eff().get(cmd) or [])
            cur.append(new_seq)
            self._keys_pending[cmd] = cur
        self._keys_fill()

    def _keys_remove_key(self, cmd: str, seq_text: str):
        if cmd in self._keys_pending:
            self._keys_pending[cmd] = [k for k in self._keys_pending[cmd]
                                       if k != seq_text]
        else:
            dkeys = self._keys_host._command_defs()[cmd][0]
            self._keys_pending[cmd] = [k for k in dkeys if k != seq_text]
        self._keys_fill()

    def _keys_add(self):
        cmd = self._keys_selected_cmd()
        if not cmd:
            return
        seq = self._keys_ask_sequence()
        if seq:
            self._keys_set_binding(cmd, seq, replace_all=False)

    def _keys_modify(self):
        cmd = self._keys_selected_cmd()
        if not cmd:
            return
        seq = self._keys_ask_sequence()
        if seq:
            self._keys_set_binding(cmd, seq, replace_all=True)

    def _keys_del(self):
        cmd = self._keys_selected_cmd()
        r = self._keys_table.currentRow()
        if not cmd or r < 0:
            return
        keys = self._keys_eff().get(cmd, [])
        if not keys:
            return
        # remove the last listed binding
        self._keys_remove_key(cmd, keys[-1])

    def _keys_reset(self):
        cmd = self._keys_selected_cmd()
        if not cmd:
            return
        self._keys_pending.pop(cmd, None)
        self._keys_fill()

    def _page_assoc(self) -> QWidget:
        w = QWidget()
        f = QVBoxLayout(w)
        f.addWidget(_title(tr("set_assoc")))
        body = QHBoxLayout()
        f.addLayout(body, 1)

        self.assoc_table = QTableWidget(0, 2)
        self.assoc_table.setHorizontalHeaderLabels(
            [tr("assoc_col_type"), tr("assoc_col_app")])
        self.assoc_table.verticalHeader().setVisible(False)
        self.assoc_table.horizontalHeader().setStretchLastSection(True)
        try:
            from PySide6.QtWidgets import QHeaderView
            self.assoc_table.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeMode.Interactive)
            self.assoc_table.setColumnWidth(0, 150)
        except Exception:
            pass
        self.assoc_table.setEditTriggers(
            self.assoc_table.EditTrigger.NoEditTriggers)
        self.assoc_table.setSelectionBehavior(
            self.assoc_table.SelectionBehavior.SelectRows)
        body.addWidget(self.assoc_table, 1)

        side = QVBoxLayout()
        btn_all = QPushButton(tr("assoc_apply_all"))
        btn_all.setObjectName("Accent")
        btn_all.clicked.connect(self._assoc_apply_all)
        btn_one = QPushButton(tr("assoc_apply_one"))
        btn_one.clicked.connect(self._assoc_apply_selected)
        side.addWidget(btn_all)
        side.addWidget(btn_one)
        hint = QLabel(tr("assoc_hint"))
        hint.setObjectName("Dim")
        hint.setWordWrap(True)
        side.addWidget(hint)
        # jpg/png/gif are Windows-protected: the OS may silently restore its
        # own UserChoice, so offer a jump to the system settings page
        btn_sys = QPushButton(tr("assoc_open_sys"))
        btn_sys.clicked.connect(self._open_default_apps)
        side.addWidget(btn_sys)
        hint2 = QLabel(tr("assoc_hint_protected"))
        hint2.setObjectName("Dim")
        hint2.setWordWrap(True)
        side.addWidget(hint2)
        side.addStretch(1)
        body.addLayout(side)

        self._assoc_fill()
        return w

    def _assoc_fill(self):
        from PySide6.QtGui import QBrush, QColor
        t = self.assoc_table
        t.setRowCount(0)
        accent = QColor("#4cc2ff")
        dim = QColor(128, 128, 128, 200)
        row = 0
        for gkey, exts in ASSOC_GROUPS:
            # group header row spanning both columns
            t.insertRow(row)
            head = QTableWidgetItem(tr(gkey))
            head.setForeground(QBrush(accent))
            head.setFlags(Qt.ItemFlag.ItemIsEnabled)
            t.setItem(row, 0, head)
            t.setSpan(row, 0, 1, 2)
            row += 1
            for ext in exts:
                t.insertRow(row)
                it_ext = QTableWidgetItem("." + ext)
                it_ext.setFlags(Qt.ItemFlag.ItemIsEnabled
                                | Qt.ItemFlag.ItemIsSelectable)
                app = _read_assoc(ext)
                it_app = QTableWidgetItem(app or tr("assoc_none"))
                it_app.setFlags(Qt.ItemFlag.ItemIsEnabled
                                | Qt.ItemFlag.ItemIsSelectable)
                if not app:
                    it_app.setForeground(QBrush(accent))
                else:
                    it_app.setForeground(QBrush(dim))
                t.setItem(row, 0, it_ext)
                t.setItem(row, 1, it_app)
                row += 1
        t.resizeColumnsToContents()
        t.setColumnWidth(0, max(150, t.columnWidth(0) + 16))

    def _assoc_apply_selected(self):
        rows = sorted({i.row() for i in self.assoc_table.selectedIndexes()})
        changed = False
        for r in rows:
            it = self.assoc_table.item(r, 0)
            if it and it.text().startswith("."):
                ext = it.text()[1:]
                _write_assoc(ext)
                changed = True
        if changed:
            self._assoc_fill()

    def _assoc_apply_all(self):
        for _gkey, exts in ASSOC_GROUPS:
            for ext in exts:
                _write_assoc(ext)
        self._assoc_fill()

    def _page_language(self) -> QWidget:
        w = QWidget()
        f = QVBoxLayout(w)
        f.addWidget(_title(tr("set_language")))
        self.rb_sys = QRadioButton(tr("lang_system"))
        self.rb_zh = QRadioButton("简体中文")
        self.rb_en = QRadioButton("English")
        cur = S.get("lang")
        (self.rb_zh if cur == "zh" else self.rb_en if cur == "en" else self.rb_sys
         ).setChecked(True)
        f.addWidget(self.rb_sys)
        f.addWidget(self.rb_zh)
        f.addWidget(self.rb_en)
        note = QLabel(tr("restart_needed"))
        note.setObjectName("Dim")
        f.addWidget(note)
        f.addStretch(1)
        return w

    def _page_about(self) -> QWidget:
        w = QWidget()
        f = QVBoxLayout(w)
        f.addWidget(_title(tr("about")))
        big = QLabel(f"{APP_NAME}")
        big.setStyleSheet("font-size: 24pt; font-weight: 600;")
        f.addWidget(big)
        ver = QLabel(APP_VERSION)
        ver.setObjectName("Dim")
        f.addWidget(ver)
        f.addSpacing(8)
        f.addWidget(QLabel(tr("app_desc")))
        f.addSpacing(8)
        oss = QLabel(tr("ossl") + ": Qt / Pillow / py7zr / pyzipper / rarfile / "
                     "pillow-heif / pillow-avif / psd-tools")
        oss.setWordWrap(True)
        oss.setObjectName("Dim")
        f.addWidget(oss)
        if CODEC_ERRORS:
            warn = QLabel("; ".join(CODEC_ERRORS))
            warn.setWordWrap(True)
            warn.setObjectName("Faint")
            f.addWidget(warn)
        f.addStretch(1)
        return w

    # ---------- apply ----------
    def _apply_and_close(self):
        S.set("theme", ["system", "light", "dark"][self.theme.currentIndex()])
        S.set("bkcolor", ["auto", "dark", "light", "white", "black", "grid"][
            self.bkcolor.currentIndex()])
        for key, cb in (("confirm_delete", self.chk_del), ("esc_exit", self.chk_esc),
                        ("remember_window", self.chk_win),
                        ("single_instance", self.chk_single),
                        ("side_arrow", self.chk_side), ("bottom_bar", self.chk_bar),
                        ("mini_title", self.chk_mini),
                        ("inter_high", self.chk_inter),
                        ("zoom_lock_save", self.chk_zlock),
                        ("exif_rotate", self.chk_exifrot),
                        ("progressive", self.chk_prog),
                        ("icc_file", self.chk_iccf),
                        ("icc_monitor", self.chk_iccm),
                        ("prefetch_next", self.chk_prefetch),
                        ("webtoon_gap", self.chk_wgap),
                        ("double_gap", self.chk_dgap),
                        ("double_cover", self.chk_cover),
                        ("auto_play_anim", self.chk_anim),
                        ("keep_effects", self.chk_keepfx),
                        ("group_raw_jpg", self.chk_group)):
            S.set(key, cb.isChecked())
        S.set("cache_mb", self.cache_mb.value())
        S.set("webtoon_gap_px", self.wgap_px.value())
        S.set("double_gap_px", self.dgap_px.value())
        S.set("wheel_mode", self.wheel.currentData())
        S.set("dbl_click_max", self.chk_dbl.isChecked())
        S.set("edge_page", self.chk_edge.isChecked())
        S.set("no_save_lastdir", self.chk_nolastdir.isChecked())
        S.set("trans_bg", ["grid", "white", "black"][self.trans.currentIndex()])
        S.set("filmstrip_hide_secs", self.fs_hide.value())
        S.set("group_show_jpg", self.rawjpg.currentData())
        S.set("editor_path", self.editor.text())
        S.set("photo_folder1", self.pf1.text())
        S.set("photo_folder2", self.pf2.text())
        S.set("ss_interval", self.ss_interval.value())
        S.set("ss_loop", self.ss_loop.isChecked())
        S.set("ss_random", self.ss_random.isChecked())
        S.set("ss_effect", ["none", "fade", "slide"][self.ss_effect.currentIndex()])
        if hasattr(self, "_keys_pending"):
            S.set("key_overrides", self._keys_pending)
        old_lang = S.get("lang")
        new_lang = "" if self.rb_sys.isChecked() else ("zh" if self.rb_zh.isChecked()
                                                       else "en")
        S.set("lang", new_lang)
        self.settingsChanged.emit()
        self.accept()
        if new_lang != old_lang:
            self.languageChangeRequested.emit(new_lang or "auto")

    def _reset(self):
        from PySide6.QtWidgets import QMessageBox
        r = QMessageBox.question(self, tr("confirm"), tr("set_confirm_reset"))
        if r == QMessageBox.StandardButton.Yes:
            S.reset_all()
            self.settingsChanged.emit()
            self.accept()


# ---------------------------------------------------------------- effects

class AdjustDialog(QDialog):
    fxChanged = Signal(dict)

    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("effect"))
        self._canvas = canvas
        base = canvas.effects() if canvas else {}
        self._fx = {"gamma": 1.0, "brightness": 1.0, "contrast": 1.0,
                    "saturation": 1.0, "channel": "rgb", "gray": False,
                    "sepia": False, "invert": False, **base}
        f = QFormLayout(self)
        self.sl_b = self._slider(20, 300, int(self._fx["brightness"] * 100))
        self.sl_c = self._slider(20, 300, int(self._fx["contrast"] * 100))
        self.sl_s = self._slider(0, 300, int(self._fx["saturation"] * 100))
        self.sl_g = self._slider(10, 300, int(self._fx["gamma"] * 100))
        f.addRow(tr("brightness"), self.sl_b)
        f.addRow(tr("contrast"), self.sl_c)
        f.addRow(tr("saturation"), self.sl_s)
        f.addRow(tr("eff_gamma"), self.sl_g)
        self.cb_ch = QComboBox()
        self.cb_ch.addItems([tr("channel_rgb"), tr("channel_r"), tr("channel_g"),
                             tr("channel_b")])
        self.cb_ch.setCurrentIndex({"rgb": 0, "r": 1, "g": 2, "b": 3}.get(
            self._fx.get("channel", "rgb"), 0))
        f.addRow(tr("channel_rgb"), self.cb_ch)
        self.cb_gray = QCheckBox(tr("eff_gray"))
        self.cb_gray.setChecked(self._fx["gray"])
        self.cb_sepia = QCheckBox(tr("eff_sepia"))
        self.cb_sepia.setChecked(self._fx["sepia"])
        self.cb_inv = QCheckBox(tr("eff_invert"))
        self.cb_inv.setChecked(self._fx["invert"])
        f.addRow(self.cb_gray)
        f.addRow(self.cb_sepia)
        f.addRow(self.cb_inv)
        btns = QHBoxLayout()
        rst = QPushButton(tr("reset"))
        rst.clicked.connect(self._reset_fx)
        btns.addWidget(rst)
        btns.addStretch(1)
        ok = QPushButton(tr("ok"))
        ok.setObjectName("Accent")
        ok.clicked.connect(self.accept)
        btns.addWidget(ok)
        f.addRow(btns)
        for sl in (self.sl_b, self.sl_c, self.sl_s, self.sl_g):
            sl.valueChanged.connect(self._emit)
        self.cb_ch.currentIndexChanged.connect(self._emit)
        self.cb_gray.toggled.connect(self._emit)
        self.cb_sepia.toggled.connect(self._emit)
        self.cb_inv.toggled.connect(self._emit)

    def _slider(self, lo, hi, val):
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(val)
        return s

    def _reset_fx(self):
        self.sl_b.setValue(100)
        self.sl_c.setValue(100)
        self.sl_s.setValue(100)
        self.sl_g.setValue(100)
        self.cb_ch.setCurrentIndex(0)
        self.cb_gray.setChecked(False)
        self.cb_sepia.setChecked(False)
        self.cb_inv.setChecked(False)

    def _emit(self):
        fx = {"brightness": self.sl_b.value() / 100,
              "contrast": self.sl_c.value() / 100,
              "saturation": self.sl_s.value() / 100,
              "gamma": self.sl_g.value() / 100,
              "channel": ["rgb", "r", "g", "b"][self.cb_ch.currentIndex()],
              "gray": self.cb_gray.isChecked(),
              "sepia": self.cb_sepia.isChecked(),
              "invert": self.cb_inv.isChecked()}
        self._fx = fx
        self.fxChanged.emit(dict(fx))

    def fx(self) -> dict:
        return dict(self._fx)


# ---------------------------------------------------------------- convert

_CONV_FORMATS = [("keep", None), ("jpg", "JPEG"), ("png", "PNG"), ("webp", "WEBP"),
                 ("bmp", "BMP"), ("tif", "TIFF")]


class ConvertWorker(QThread):
    progress = Signal(int, int)      # done, total
    finishedAll = Signal(bool)       # any error?
    requestOpenDir = Signal(str)

    def __init__(self, jobs, parent=None):
        super().__init__(parent)
        self.jobs = jobs             # list of (src_path_or_bytes_loader, out_path, opts)
        self.cancel = False

    def run(self):
        import io
        from PIL import Image
        err = False
        total = len(self.jobs)
        for i, (loader, out_path, opts) in enumerate(self.jobs):
            if self.cancel:
                break
            try:
                src = loader()          # bytes
                pil = Image.open(io.BytesIO(src))
                pil.load()
                rot = opts.get("rotate", 0)
                if rot == 90:
                    pil = pil.transpose(Image.Transpose.ROTATE_270)
                elif rot == 270:
                    pil = pil.transpose(Image.Transpose.ROTATE_90)
                elif rot == 180:
                    pil = pil.transpose(Image.Transpose.ROTATE_180)
                rw, rh = opts.get("resize", (0, 0))
                rmode = opts.get("resize_mode", "none")
                if rmode != "none" and rw > 0 and rh > 0:
                    if rmode == "keep":
                        pil.thumbnail((rw, rh), Image.LANCZOS)
                    else:
                        pil = pil.resize((rw, rh), Image.LANCZOS)
                fmt = opts.get("pil_format")
                kw = {}
                if fmt == "JPEG":
                    if pil.mode != "RGB":
                        pil = pil.convert("RGB")
                    kw["quality"] = opts.get("quality", 90)
                elif fmt == "WEBP":
                    kw["quality"] = opts.get("quality", 90)
                if fmt is not None:
                    pil.save(out_path, fmt, **kw)
                else:
                    pil.save(out_path, quality=opts.get("quality", 90))
            except Exception:
                err = True
            self.progress.emit(i + 1, total)
        self.finishedAll.emit(err)


class ConvertDialog(QDialog):
    def __init__(self, source, entries, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("conv_title"))
        self.resize(720, 560)
        self._source = source
        self._entries = entries
        self._worker: ConvertWorker | None = None
        root = QVBoxLayout(self)
        root.addWidget(_title(tr("conv_filelist")))
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        for e in entries:
            self.list.addItem(e.name)
        self.list.setFixedHeight(150)
        root.addWidget(self.list)
        root.addWidget(_title(tr("conv_settings")))
        form = QFormLayout()
        # format
        rowf = QHBoxLayout()
        self.fmt = QComboBox()
        self.fmt.addItem(tr("keep_original"), 0)
        for key, label in (("jpg", "JPG"), ("png", "PNG"), ("webp", "WebP"),
                           ("bmp", "BMP"), ("tif", "TIFF")):
            self.fmt.addItem(label, key)
        self.fmt.currentIndexChanged.connect(self._refresh)
        rowf.addWidget(self.fmt)
        rowf.addWidget(QLabel(tr("conv_quality")))
        self.quality = QSpinBox()
        self.quality.setRange(30, 100)
        self.quality.setValue(90)
        rowf.addWidget(self.quality)
        rowf.addStretch(1)
        form.addRow(tr("conv_format"), rowf)
        # resize
        rowr = QHBoxLayout()
        self.rmode = QComboBox()
        self.rmode.addItem(tr("conv_resize_none"), "none")
        self.rmode.addItem(tr("conv_resize_keep"), "keep")
        self.rmode.addItem(tr("conv_resize_stretch"), "stretch")
        self.rmode.currentIndexChanged.connect(self._refresh)
        self.rw = QSpinBox()
        self.rw.setRange(1, 30000)
        self.rw.setValue(1920)
        self.rh = QSpinBox()
        self.rh.setRange(1, 30000)
        self.rh.setValue(1080)
        rowr.addWidget(self.rmode)
        rowr.addWidget(QLabel(tr("conv_newsize")))
        rowr.addWidget(self.rw)
        rowr.addWidget(QLabel("×"))
        rowr.addWidget(self.rh)
        rowr.addStretch(1)
        form.addRow(tr("conv_resize"), rowr)
        # rotate
        self.rot = QComboBox()
        self.rot.addItem(tr("rotate_none"), 0)
        self.rot.addItem(tr("rotate_l"), 270)
        self.rot.addItem(tr("rotate_r"), 90)
        self.rot.addItem(tr("rotate_180"), 180)
        form.addRow(tr("conv_rotate"), self.rot)
        # output
        self.out = QComboBox()
        self.out.addItem(tr("conv_same"), "same")
        self.out.addItem(tr("conv_sub"), "sub")
        self.out.addItem(tr("conv_custom"), "custom")
        self.out.currentIndexChanged.connect(self._refresh)
        self.outdir = QLineEdit()
        browse = QPushButton(tr("browse"))
        browse.setObjectName("Card")
        browse.clicked.connect(self._browse_out)
        rowo = QHBoxLayout()
        rowo.addWidget(self.outdir, 1)
        rowo.addWidget(browse)
        self.outrow = rowo
        form.addRow(tr("conv_out"), self.out)
        self.outcustom = QWidget()
        self.outcustom.setLayout(rowo)
        form.addRow("", self.outcustom)
        # prefix
        self.prefix = QLineEdit("")
        self.prefix.textChanged.connect(self._refresh)
        form.addRow(tr("conv_prefix"), self.prefix)
        # overwrite
        self.ow = QComboBox()
        self.ow.addItem(tr("ow_rename"), "rename")
        self.ow.addItem(tr("ow_overwrite"), "overwrite")
        self.ow.addItem(tr("ow_skip"), "skip")
        form.addRow(tr("conv_overwrite"), self.ow)
        root.addLayout(form, 1)
        self.preview = QLabel("")
        self.preview.setObjectName("Dim")
        root.addWidget(self.preview)
        # progress
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        root.addWidget(self.bar)
        btns = QHBoxLayout()
        self.start_btn = QPushButton(tr("start"))
        self.start_btn.setObjectName("Accent")
        self.start_btn.clicked.connect(self._start)
        self.stop_btn = QPushButton(tr("stop"))
        self.stop_btn.clicked.connect(self._stop)
        self.stop_btn.setEnabled(False)
        self.open_btn = QPushButton(tr("conv_open_folder"))
        self.open_btn.clicked.connect(self._open_out)
        self.open_btn.setEnabled(False)
        close = QPushButton(tr("close"))
        close.clicked.connect(self.reject)
        btns.addWidget(self.start_btn)
        btns.addWidget(self.stop_btn)
        btns.addWidget(self.open_btn)
        btns.addStretch(1)
        btns.addWidget(close)
        root.addLayout(btns)
        self._out_dir = ""
        self._refresh()

    def _browse_out(self):
        d = QFileDialog.getExistingDirectory(self, tr("browse"), self.outdir.text())
        if d:
            self.outdir.setText(d)

    def _out_base(self) -> str:
        mode = self.out.currentData()
        base = os.path.dirname(self._source.path)
        if mode == "sub":
            base = os.path.join(base, "PView_Output")
        elif mode == "custom":
            base = self.outdir.text().strip() or base
        return base

    def _fmt_for(self, entry) -> tuple[str | None, str]:
        """returns (pil_format or None, ext)"""
        sel = self.fmt.currentData()
        ext = os.path.splitext(entry.name)[1].lower()
        if sel in (None, 0, "keep"):
            m = {".jpg": "JPEG", ".jpeg": "JPEG", ".jfif": "JPEG",
                 ".png": "PNG", ".apng": "PNG", ".webp": "WEBP", ".bmp": "BMP",
                 ".tif": "TIFF", ".tiff": "TIFF", ".gif": "GIF"}
            fmt = m.get(ext)
            if fmt is None:
                fmt = "PNG"
                ext = ".png"
            return fmt, ext
        ext = {"jpg": ".jpg", "png": ".png", "webp": ".webp", "bmp": ".bmp",
               "tif": ".tif"}[sel]
        fmt = {"jpg": "JPEG", "png": "PNG", "webp": "WEBP", "bmp": "BMP",
               "tif": "TIFF"}[sel]
        return fmt, ext

    def _refresh(self):
        self.outcustom.setVisible(self.out.currentData() == "custom")
        can_resize = self.rmode.currentData() != "none"
        self.rw.setEnabled(can_resize)
        self.rh.setEnabled(can_resize)
        sel = self.fmt.currentData()
        self.quality.setEnabled(sel in ("jpg", "webp", None, 0, "keep"))
        if self._entries:
            e = self._entries[0]
            _fmt, ext = self._fmt_for(e)
            stem = os.path.splitext(e.name)[0]
            self.preview.setText(tr("conv_preview") + ": " +
                                 self.prefix.text() + stem + ext)

    def _unique_path(self, base, stem, ext) -> str:
        p = os.path.join(base, stem + ext)
        if self.ow.currentData() == "overwrite" or not os.path.exists(p):
            return p
        if self.ow.currentData() == "skip":
            return ""
        n = 2
        while True:
            p = os.path.join(base, f"{stem} ({n}){ext}")
            if not os.path.exists(p):
                return p
            n += 1

    def _start(self):
        base = self._out_base()
        os.makedirs(base, exist_ok=True)
        quality = self.quality.value()
        rmode = self.rmode.currentData()
        resize = (self.rw.value(), self.rh.value())
        rot = self.rot.currentData()
        prefix = self.prefix.text()
        sel = self.fmt.currentData()
        jobs = []
        for e in self._entries:
            fmt, ext = self._fmt_for(e)
            stem = prefix + os.path.splitext(e.name)[0]
            out = self._unique_path(base, stem, ext)
            if not out:
                continue
            if os.path.normpath(out) == os.path.normpath(
                    e.key if not self._source.archive else ""):
                continue
            src_path = e.key if not self._source.archive else None
            entry = e
            jobs.append((self._make_loader(entry), out,
                         {"pil_format": fmt, "quality": quality,
                          "resize_mode": rmode, "resize": resize, "rotate": rot}))
        if not jobs:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, tr("conv_title"), tr("conv_no_files"))
            return
        self._worker = ConvertWorker(jobs, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finishedAll.connect(self._on_done)
        self._out_dir = base
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.bar.setValue(0)
        self._worker.start()

    def _make_loader(self, entry):
        source = self._source

        def load():
            return source.read_bytes(entry)
        return load

    def _on_progress(self, done, total):
        self.bar.setMaximum(total)
        self.bar.setValue(done)
        self.setWindowTitle(tr("conv_processing").format(done, total))

    def _on_done(self, err):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.open_btn.setEnabled(True)
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, tr("conv_title"),
                                tr("conv_failed") if err else tr("conv_completed"))

    def _stop(self):
        if self._worker:
            self._worker.cancel = True

    def _open_out(self):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._out_dir))


# ---------------------------------------------------------------- misc small

class WallpaperDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("set_wallpaper"))
        f = QFormLayout(self)
        self.style = QComboBox()
        self.style.addItem(tr("wp_fill"), 10)
        self.style.addItem(tr("wp_fit"), 6)
        self.style.addItem(tr("wp_center"), 0)
        f.addRow(tr("wallpaper_style"), self.style)
        btns = QHBoxLayout()
        ok = QPushButton(tr("wp_apply"))
        ok.setObjectName("Accent")
        ok.clicked.connect(self.accept)
        cancel = QPushButton(tr("cancel"))
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        f.addRow(btns)


class PasswordDialog(QDialog):
    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("password"))
        self.resize(420, 140)
        v = QVBoxLayout(self)
        v.addWidget(QLabel(tr("enter_password")))
        v.addWidget(QLabel(os.path.basename(path)))
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        v.addWidget(self.edit)
        btns = QHBoxLayout()
        btns.addStretch(1)
        ok = QPushButton(tr("ok"))
        ok.setObjectName("Accent")
        ok.clicked.connect(self.accept)
        cancel = QPushButton(tr("cancel"))
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        v.addLayout(btns)
        self.edit.setFocus()

    def password(self) -> str:
        return self.edit.text()


class BookmarkManagerDialog(QDialog):
    openBookmark = Signal(dict)

    def __init__(self, bookmarks: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("bookmark_manager"))
        self.resize(640, 420)
        v = QVBoxLayout(self)
        self.list = QListWidget()
        for b in bookmarks:
            self.list.addItem(b.get("display") or b.get("path", ""))
            it = self.list.item(self.list.count() - 1)
            it.setData(Qt.ItemDataRole.UserRole, b)
        v.addWidget(self.list)
        btns = QHBoxLayout()
        del_btn = QPushButton(tr("bookmark_del"))
        del_btn.clicked.connect(self._del)
        btns.addWidget(del_btn)
        btns.addStretch(1)
        close = QPushButton(tr("close"))
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        v.addLayout(btns)
        self.list.itemDoubleClicked.connect(self._open)

    def _open(self, item):
        b = item.data(Qt.ItemDataRole.UserRole)
        self.openBookmark.emit(b)
        self.accept()

    def _del(self):
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))
