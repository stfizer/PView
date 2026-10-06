# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for P view
import os
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
root = os.path.abspath(SPECPATH)

hidden = (
    collect_submodules("py7zr")
    + collect_submodules("pyzipper")
    + [
        "rarfile",
        "pillow_heif",
        "pillow_avif",
        "psd_tools",
        "PIL.Image",
        "PIL.ImageOps",
        "PIL.ImageEnhance",
        "PIL.ImageChops",
        "PIL.ImageFilter",
        "PIL.GifImagePlugin",
        "PIL.WebPImagePlugin",
        "PIL.TiffImagePlugin",
    ]
)

a = Analysis(
    [os.path.join(root, "main.py")],
    pathex=[root],
    binaries=[],
    datas=[(os.path.join(root, "assets", "pview.ico"), "assets")],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "PySide6.QtQml",
              "PySide6.QtQuick", "PySide6.Qt3D", "PySide6.QtCharts",
              "PySide6.QtDataVisualization", "PySide6.QtNetworkAuth"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Pview",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=os.path.join(root, "assets", "pview.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="Pview",
)
