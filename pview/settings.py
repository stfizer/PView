"""Persistent settings for P view (INI file under %APPDATA%/PView)."""
from __future__ import annotations

import os
from PySide6.QtCore import QSettings, QStandardPaths

from . import APP_NAME, ORG_NAME

DEFAULTS = {
    "lang": "",                  # "" = system default, "zh", "en"
    "theme": "system",           # system / light / dark
    "bkcolor": "auto",           # auto / dark / light / white / black / grid
    "confirm_delete": True,
    "esc_exit": False,           # ESC exits program when not fullscreen
    "remember_window": True,
    "remember_pos_archive": True,
    "remember_pos_folder": True,
    "single_instance": False,
    "side_arrow": True,
    "bottom_bar": True,
    "mini_title": False,         # persist filename overlay on the canvas
    "filmstrip_hide_secs": 5,    # auto-hide filmstrip 3-10 s after pointer leaves
    "exif_rotate": True,
    "auto_play_anim": True,
    "zoom_lock_save": False,
    "keep_effects": False,
    "group_raw_jpg": False,
    "group_show_jpg": True,      # True = show JPG side of RAW+JPG group
    "trans_bg": "grid",          # grid / white / black
    "view_mode": "fit",          # fit / width / height / original
    "stretch_small": False,
    "zoom_lock": False,
    "zoom_lock_value": 1.0,
    "inter_high": True,          # high quality interpolation
    "wheel_mode": "page",        # page / zoom
    "last_action": "loop",       # loop / nothing / next_folder
    "ss_interval": 3,
    "ss_loop": False,
    "ss_random": False,
    "ss_effect": "fade",         # none / fade / slide
    "editor_path": "",           # image editor executable
    "photo_folder1": "",
    "photo_folder2": "",
    "sort_key": "name",          # name / date / size / type / created
    "sort_desc": False,
    "geometry": "",
    "last_dir": "",
    # --- BandiView-style image processing options ---
    "prefetch_next": True,       # cache next/prev image while viewing
    "cache_mb": 600,             # doc cache budget in MB
    "progressive": True,         # show low-quality pass of big images first
    "icc_file": True,            # honour embedded ICC profile of the file
    "icc_monitor": False,        # convert to the monitor's ICC profile
    "webtoon_gap": False,        # insert spacing between webtoon pages
    "webtoon_gap_px": 10,
    "double_gap": False,         # spacing between the two pages of a spread
    "double_gap_px": 10,
    "double_cover": False,       # first image of a spread shown alone
    # --- mouse ---
    "dbl_click_max": True,       # double-click toggles maximize
    "edge_page": False,          # click near left/right edge to flip page
    # --- misc ---
    "no_save_lastdir": False,    # do not remember the browsed folder
    "ctx_menu": True,            # explorer context menu integration
    "key_overrides": {},         # {command_id: [key sequences]}
}

_settings: QSettings | None = None


def qsettings() -> QSettings:
    global _settings
    if _settings is None:
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        os.makedirs(base, exist_ok=True)
        _settings = QSettings(os.path.join(base, "pview.ini"), QSettings.Format.IniFormat)
    return _settings


def get(key: str):
    v = qsettings().value(key, None)
    d = DEFAULTS.get(key)
    if v is None:
        return d
    if isinstance(d, bool):
        if isinstance(v, bool):
            return v
        return str(v).lower() in ("true", "1", "yes")
    if isinstance(d, int):
        try:
            return int(v)
        except (TypeError, ValueError):
            return d
    if isinstance(d, float):
        try:
            return float(v)
        except (TypeError, ValueError):
            return d
    return v


def set(key: str, value):
    qsettings().setValue(key, value)
    qsettings().sync()


def reset_all():
    qsettings().clear()
    qsettings().sync()


def app_data_dir() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    os.makedirs(base, exist_ok=True)
    return base
