"""Verify round 7: app icon, accent title, folder label, zoom input, panel title."""
import os
import sys

PVIEW_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PVIEW_ROOT)
os.environ.pop("QT_QPA_PLATFORM", None)

from PySide6.QtWidgets import QApplication, QLabel, QSpinBox

app = QApplication(sys.argv)

TMP = os.path.join(os.environ["TEMP"], "pview_guiverify2")
from pview.mainwindow import MainWindow, _app_icon

win = MainWindow(os.path.join(TMP, "exif.jpg"))
win.resize(1160, 740)
win.show()

ok = True


def check(name, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + name)
    ok = ok and cond


def probe():
    # --- app icon ---
    check("window icon is the program icon (non-null)",
          not win.windowIcon().isNull())
    check("topbar app_btn shows program icon + static",
          win.app_btn._static_icon and not win.app_btn.icon().isNull())

    # --- accent title ---
    qss = win._palette and None
    check("title label objectName TitleLabel (accent via QSS)",
          win.title_label.objectName() == "TitleLabel")

    # --- folder label bold + clickable + text split ---
    if win._source:
        check("folder label bold weight",
              win.folder_label.font().weight() >= QFont.Weight.DemiBold + 100
              or win.folder_label.font().bold())
        check("folder label caption-block (real clicks reach it)",
              getattr(win.folder_label, "_caption_block", False))
        check("folder label shows folder name",
              win.folder_label.text() != "")
        check("file label starts with ' > '",
              win.file_label.text().startswith(" > "))

    # --- zoom inline edit ---
    check("zoom edit is a hidden QSpinBox", not win.zoom_edit.isVisible())
    win._zoom_edit_start()
    check("zoom edit visible after label click", win.zoom_edit.isVisible())
    check("zoom edit value matches current zoom",
          win.zoom_edit.value() == int(round(win.canvas.zoom() * 100)))
    win.zoom_edit.setValue(200)
    win._zoom_edit_done()
    check("zoom applied from editor (200%)",
          abs(win.canvas.zoom() - 2.0) < 0.01)
    check("label restored after editing", not win.zoom_edit.isVisible())

    # --- info panel: single '文件信息' heading ---
    win.btn_info_top.click()

    def check_panel():
        ip = win.info_panel
        titles = []
        for i in range(ip._blay.count()):
            wdg = ip._blay.itemAt(i).widget()
            if isinstance(wdg, QLabel) and wdg.objectName() == "SectionTitle":
                titles.append(wdg.text())
        check(f"panel body has exactly one section title ({titles})",
              titles == ["EXIF"])
        win.toggle_info()
        print("ALL OK" if ok else "SOME FAILED")
        app.quit()

    from PySide6.QtCore import QTimer
    QTimer.singleShot(400, check_panel)


from PySide6.QtGui import QFont
from PySide6.QtCore import QTimer
QTimer.singleShot(600, probe)
app.exec()
