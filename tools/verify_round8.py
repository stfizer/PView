"""Verify round 8: navigator thumbs, Enter separation, uniform panel bg."""
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
    # --- Enter separation: editor swallows Enter; shortcut handler guards ---
    win._zoom_edit_start()
    check("zoom editor open", win.zoom_edit.isVisible())
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return,
                   Qt.KeyboardModifier.NoModifier)
    handled = win.eventFilter(win.zoom_edit, ev)
    check("zoom_edit swallows Enter via eventFilter", handled is True)
    win._zoom_edit_done()
    check("editor closed", not win.zoom_edit.isVisible())

    # --- navigator thumbnails (non-modal probe) ---
    from pview.gallery import NavigatorDialog
    dlg = NavigatorDialog(win._source, 0, win)
    dlg.show()

    def check_cells():
        items = dlg._items
        with_icon = sum(1 for it in items if not it.icon().isNull())
        check(f"navigator cells with thumbnails ({with_icon}/{len(items)})",
              with_icon == len(items) and len(items) > 0)
        check("navigator cells show file names",
              all(it.text() for it in items))
        dlg.close()
        # --- info panel uniform background ---
        win.btn_info_top.click()

        def check_bg():
            ss = win.info_panel.styleSheet()
            check("panel background uniform rgba(28,28,28,0.88)",
                  "rgba(28,28,28,0.88)" in ss)
            win.toggle_info()
            print("ALL OK" if ok else "SOME FAILED")
            app.quit()

        QTimer.singleShot(300, check_bg)

    QTimer.singleShot(900, check_cells)   # let async thumbs land


QTimer.singleShot(600, probe)
app.exec()
