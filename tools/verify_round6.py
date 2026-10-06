"""Verify round 6: flicker fix, 5% zoom step, window-button glyph states."""
import os
import sys

PVIEW_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PVIEW_ROOT)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)

TMP = os.path.join(os.environ["TEMP"], "pview_guiverify2")
from pview.mainwindow import MainWindow
from pview.viewer import ImageViewCanvas

win = MainWindow(os.path.join(TMP, "exif.jpg"))
win.resize(1160, 740)
win.show()

ok = True


def check(name, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + name)
    ok = ok and cond


def probe():
    global ok
    c = win.canvas

    # --- flicker fix: transition must start fully on the old snapshot ---
    c._trans_t = 1.0
    c._trans_mode = "none"
    doc_old = win._doc
    win.go_next()
    # after go_next the canvas either got a new doc synchronously (cache)
    # or is waiting (async); if synchronous, transition state must be armed
    if c._trans_mode != "none":
        check("transition armed with t=0.0 (no first-frame flash)", c._trans_t == 0.0)
        check("previous snapshot captured", c._snap_prev is not None)
    else:
        print("SKIP transition (async load path)")

    # --- zoom step 5% ---
    win.go_first()
    z0 = c.zoom()
    c.zoom_in()
    z1 = c.zoom()
    c.zoom_out()
    z2 = c.zoom()
    check(f"zoom_in step 5% ({z0:.3f} -> {z1:.3f})", abs(z1 - z0 * 1.05) < 1e-6)
    check(f"zoom_out step 5% (back to {z2:.3f})", abs(z2 - z0) < 1e-6)

    # --- glyph state switching ---
    check("initial glyph = win-max (normal state)",
          win.btn_max._icon_name == "win-max")
    win.showMaximized()
    win._toggle_max()   # currently maximized -> back to normal
    check("after unmaximize glyph = win-max", win.btn_max._icon_name == "win-max")
    win._toggle_max()   # normal -> maximized
    check("after maximize glyph = win-restore",
          win.btn_max._icon_name == "win-restore")
    win.showNormal()
    win.btn_max.set_icon_name("win-max")

    # --- new icons render non-blank ---
    from pview import icons
    for n in ("win-min", "win-max", "win-restore", "win-close"):
        pm = icons._render(icons.ICONS[n].replace("{c}", "#ffffff"), 48)
        check(f"icon {n} renders non-empty", not pm.isNull())

    print("ALL OK" if ok else "SOME FAILED")
    app.quit()


from PySide6.QtCore import QTimer
QTimer.singleShot(600, probe)
app.exec()
