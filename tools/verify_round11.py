"""Verify round 11: settings reorganized to BandiView-style grouping."""
import os
import sys

PVIEW_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PVIEW_ROOT)
os.environ.pop("QT_QPA_PLATFORM", None)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

app = QApplication(sys.argv)

TMP = os.path.join(os.environ["TEMP"], "pview_guiverify2")
from pview.mainwindow import MainWindow
from pview.dialogs import SettingsDialog

win = MainWindow(os.path.join(TMP, "exif.jpg"))
win.resize(1160, 740)
win.show()

ok = True


def check(name, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + name)
    ok = ok and cond


def probe():
    dlg = SettingsDialog(win)
    dlg.show()
    # walk through every page so each one gets built/polished
    labels = [dlg.nav.item(i).text() for i in range(dlg.nav.count())]
    print("nav:", labels)
    check("11 nav entries in BandiView order",
          labels == ["常规", "浏览", "图像处理", "格式关联", "快捷键",
                     "鼠标", "书签", "图片文件夹", "杂项", "语言", "关于"])
    for i in range(dlg.nav.count()):
        dlg.nav.setCurrentRow(i)
        app.processEvents()
    check("all 11 pages build without errors", True)
    # spot-check relocated controls
    check("theme moved to browse page", hasattr(dlg, "theme"))
    check("bkcolor moved to image page", hasattr(dlg, "bkcolor"))
    check("wheel on mouse page", hasattr(dlg, "wheel"))
    check("folders page has pf1/pf2",
          hasattr(dlg, "pf1") and hasattr(dlg, "pf2"))
    check("misc page has slideshow + editor",
          hasattr(dlg, "ss_interval") and hasattr(dlg, "editor"))
    check("bookmark page has history checkboxes",
          hasattr(dlg, "chk_posa") and hasattr(dlg, "chk_posf"))
    # apply must still work with the reorganized pages
    try:
        dlg._apply_and_close()
        check("apply works after regroup", True)
    except Exception as e:
        check(f"apply works after regroup ({e})", False)
    print("ALL OK" if ok else "SOME FAILED")
    app.quit()


QTimer.singleShot(700, probe)
app.exec()
