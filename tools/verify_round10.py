"""Verify round 10: wheel page-turn and file-association page."""
import os
import sys

PVIEW_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PVIEW_ROOT)
os.environ.pop("QT_QPA_PLATFORM", None)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QWheelEvent

app = QApplication(sys.argv)

TMP = os.path.join(os.environ["TEMP"], "pview_guiverify2")
from pview.mainwindow import MainWindow
from pview.dialogs import SettingsDialog, ASSOC_GROUPS

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
    got = []
    c.pageRequested.connect(lambda d: got.append(d))

    def wheel(dy):
        e = QWheelEvent(QPointF(100, 100), QPointF(500, 500),
                        QPoint(0, 0), QPoint(0, dy),
                        Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
        c.wheelEvent(e)

    wheel(120)    # wheel up -> previous
    wheel(-120)   # wheel down -> next
    check(f"wheel up=prev, down=next (got {got})", got == [-1, 1])

    # --- association page ---
    dlg = SettingsDialog(win)
    # nav row for assoc = index 5
    dlg.nav.setCurrentRow(5)
    t = dlg.assoc_table
    total_exts = sum(len(e) for _, e in ASSOC_GROUPS)
    headers = sum(1 for _, e in ASSOC_GROUPS)
    check(f"assoc table rows = {t.rowCount()} (expect {total_exts + headers})",
          t.rowCount() == total_exts + headers)
    # some known system-associated ext should show a non-empty app
    samples = 0
    for r in range(t.rowCount()):
        it0 = t.item(r, 0)
        if it0 and it0.text() == ".png":
            app_txt = t.item(r, 1).text()
            print(f"  .png shows: '{app_txt}'")
            samples += 1
    check("png row present", samples == 1)
    check("_read_assoc returns text for jpg",
          __import__("pview.dialogs", fromlist=["_read_assoc"])
          ._read_assoc("jpg") != "")
    dlg.close()

    print("ALL OK" if ok else "SOME FAILED")
    app.quit()


QTimer.singleShot(700, probe)
app.exec()
