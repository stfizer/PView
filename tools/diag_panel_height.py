"""Diagnose InfoPanel height: preferred_height estimate vs actual layout need."""
import os
import sys

PVIEW_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PVIEW_ROOT)
os.environ.pop("QT_QPA_PLATFORM", None)

from PySide6.QtWidgets import QApplication, QScrollArea

app = QApplication(sys.argv)

TMP = os.path.join(os.environ["TEMP"], "pview_guiverify2")
from pview.mainwindow import MainWindow

win = MainWindow(os.path.join(TMP, "exif.jpg"))
win.resize(1160, 740)
win.show()


def probe():
    if not (win._doc and win._doc.frames):
        from PySide6.QtCore import QTimer
        QTimer.singleShot(200, probe)
        return
    win.btn_info_top.click()

    def check():
        ip = win.info_panel
        body_w_calc = ip.width() - 14 * 2 - 4
        est = ip._blay.heightForWidth(body_w_calc)
        head_h = ip._outer.itemAt(0).sizeHint().height()
        spacing = ip._outer.spacing()
        scroll = ip.findChild(QScrollArea)
        vw = scroll.viewport().width()
        body_actual = ip._body.height()
        sb = scroll.verticalScrollBar()
        print(f"panel.size           = {ip.width()}x{ip.height()}")
        print(f"panel.geometry       = {ip.geometry()}")
        print(f"body_w_calc          = {body_w_calc}")
        print(f"heightForWidth(calc) = {est}")
        print(f"head_h={head_h} spacing={spacing} "
              f"-> preferred = {14 + head_h + spacing + est + 14}")
        print(f"scroll viewport w    = {vw}")
        print(f"body actual height   = {body_actual}")
        print(f"v-scrollbar max      = {sb.maximum()} (0 = all content visible)")
        print(f"scroll h             = {scroll.height()}")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, finish)

    from PySide6.QtCore import QTimer
    QTimer.singleShot(400, check)


def finish():
    app.quit()


from PySide6.QtCore import QTimer
QTimer.singleShot(600, probe)
app.exec()
