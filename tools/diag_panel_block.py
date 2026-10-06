"""Diagnose InfoPanel 'bright block': is it a solid widget or image bleed-through?"""
import os
import sys

PVIEW_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PVIEW_ROOT)
os.environ.pop("QT_QPA_PLATFORM", None)

from PySide6.QtWidgets import QApplication, QScrollArea
from PySide6.QtGui import QImage, QColor
from PySide6.QtCore import QTimer

app = QApplication(sys.argv)

TMP = os.path.join(os.environ["TEMP"], "pview_guiverify2")
from PIL import Image
# a half-black half-white image so bleed-through is obvious
img = Image.new("RGB", (1200, 800), (255, 255, 255))
d = ImageDraw = None
from PIL import ImageDraw
dr = ImageDraw.Draw(img)
dr.rectangle([0, 0, 600, 800], fill=(0, 0, 0))
dr.rectangle([600, 0, 1200, 800], fill=(255, 255, 255))
img.save(os.path.join(TMP, "bw.jpg"), "JPEG", quality=95)

from pview.mainwindow import MainWindow

win = MainWindow(os.path.join(TMP, "bw.jpg"))
win.resize(1160, 740)
win.show()


def probe():
    win.btn_info_top.click()

    def check():
        ip = win.info_panel
        pm = win.grab()
        img = pm.toImage()
        # panel geometry; row area vs EXIF area
        g = ip.geometry()
        # sample a horizontal line inside the row area (middle of panel body)
        # and one in the EXIF tail
        def avg_row(y):
            r = g_ = b = n = 0
            for x in range(g.x() + 20, g.x() + g.width() - 20, 4):
                c = img.pixelColor(x, y)
                r += c.red(); g_ += c.green(); b += c.blue(); n += 1
            return (r // n, g_ // n, b // n)
        head_y = g.y() + 20
        rows_y = g.y() + int(g.height() * 0.35)
        exif_y = g.y() + g.height() - 30
        print("panel geom:", g)
        print("avg RGB head:", avg_row(head_y))
        print("avg RGB rows:", avg_row(rows_y))
        print("avg RGB exif:", avg_row(exif_y))
        # widget audit
        scroll = ip.findChild(QScrollArea)
        vp = scroll.viewport()
        print("scroll bg:", scroll.palette().color(vp.backgroundRole()).name(),
              "viewport autofill:", vp.autoFillBackground(),
              "body autofill:", ip._body.autoFillBackground())
        print("body size:", ip._body.size(), "viewport size:", vp.size())
        app.quit()

    QTimer.singleShot(400, check)


QTimer.singleShot(600, probe)
app.exec()
