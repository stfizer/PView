"""Verify round 9: percentage-point zoom step, Enter override, panel 0.97."""
import os
import sys

PVIEW_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PVIEW_ROOT)
os.environ.pop("QT_QPA_PLATFORM", None)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QKeyEvent

app = QApplication(sys.argv)

TMP = os.path.join(os.environ["TEMP"], "pview_guiverify2")
from pview.mainwindow import MainWindow

win = MainWindow(os.path.join(TMP, "exif.jpg"))
win.resize(1160, 740)
win.show()

ok = True


def check(name, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + name)
    ok = ok and cond


def probe():
    c = win.canvas
    # --- 5 percentage-point steps from an odd starting zoom ---
    c.set_zoom(0.50)
    c.zoom_in()
    check(f"zoom_in 50% -> 55% (got {c.zoom()*100:.1f}%)",
          abs(c.zoom() * 100 - 55) < 0.01)
    c.zoom_in()
    check(f"zoom_in 55% -> 60% (got {c.zoom()*100:.1f}%)",
          abs(c.zoom() * 100 - 60) < 0.01)
    c.zoom_out()
    check(f"zoom_out 60% -> 55% (got {c.zoom()*100:.1f}%)",
          abs(c.zoom() * 100 - 55) < 0.01)
    c.set_zoom(0.03)
    c.zoom_out()
    check(f"zoom_out clamps at low end (got {c.zoom()*100:.1f}%)",
          c.zoom() * 100 >= 1)

    # --- Enter: ShortcutOverride claimed so the shortcut never consumes it ---
    win._zoom_edit_start()
    ev = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_Return,
                   Qt.KeyboardModifier.NoModifier)
    handled = win.eventFilter(win.zoom_edit, ev)
    check("ShortcutOverride claimed by zoom editor", handled is True)
    check("editor accepted the override", ev.isAccepted())
    # apply path still works
    win.zoom_edit.setValue(123)
    win._zoom_edit_done()
    check(f"apply zoom via Enter path -> 123% (got {c.zoom()*100:.1f}%)",
          abs(c.zoom() * 100 - 123) < 0.01)

    # --- panel near-opaque ---
    win.btn_info_top.click()

    def check_bg():
        ss = win.info_panel.styleSheet()
        check("panel background rgba(24,24,24,0.97)",
              "rgba(24,24,24,0.97)" in ss)
        win.toggle_info()
        # --- folder label gap ---
        m = win.folder_label.contentsMargins()
        check(f"folder label left gap 10px (got {m.left()})", m.left() == 10)
        print("ALL OK" if ok else "SOME FAILED")
        app.quit()

    QTimer.singleShot(300, check_bg)


QTimer.singleShot(600, probe)
app.exec()
