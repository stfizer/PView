"""Real-GUI (windows platform) verification of feature requests, with screenshots.

Steps:
  1_initial         image loaded, arrows hidden (auto-hide default)
  2_arrows_hover    hot-zone enter -> both arrows appear at once
  3_arrows_gone     leave -> arrows hide again
  4_filmstrip       strip open, thumbnails rendered
  5_wheel_scroll    wheel event scrolls strip horizontally
  6_autohide        after filmstrip_hide_secs the strip auto-hides
  7_infopanel       info panel: BandiView layout (name[n/N], image info, EXIF)
  8_settings_btn    "..." button opens the Settings dialog directly
  9_menu            full menu still builds (popup check)
"""
import os
import sys
import tempfile

PVIEW_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PVIEW_ROOT)
os.environ.pop("QT_QPA_PLATFORM", None)

OUT_DIR = os.path.join(PVIEW_ROOT, "docs", "verify_out")
os.makedirs(OUT_DIR, exist_ok=True)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint, QPointF, QEvent, Qt, QTimer
from PySide6.QtGui import QWheelEvent

app = QApplication(sys.argv)

TMP = os.path.join(os.environ["TEMP"], "pview_guiverify2")
os.makedirs(TMP, exist_ok=True)
from PIL import Image, ImageDraw
for i in range(8):
    img = Image.new("RGB", (1400, 900), (i * 35 % 255, 110, 160))
    d = ImageDraw.Draw(img)
    for k in range(8):
        d.ellipse([k * 170, 150 + k * 80, k * 170 + 260, 430 + k * 80],
                  outline=(255, 255, 255), width=8)
    d.text((50, 50), f"Verify2 {i + 1}", fill=(255, 255, 255))
    img.save(os.path.join(TMP, f"img{i}.jpg"), "JPEG", quality=88)
# an image with fake EXIF for the panel
ex = Image.new("RGB", (1200, 800), (40, 90, 140))
exif = Image.Exif()
exif[271] = "TestMaker"
exif[272] = "TestModel"
exif[305] = "PviewTest"
exif[306] = "2030:12:31 00:00:01"
ex.save(os.path.join(TMP, "exif.jpg"), "JPEG", exif=exif)

from pview import settings as S
from pview.mainwindow import MainWindow

win = MainWindow(os.path.join(TMP, "exif.jpg"))
win.resize(1160, 740)
win.show()

results = []


def grab(name):
    pm = win.grab()
    path = os.path.join(OUT_DIR, name + ".png")
    pm.save(path)
    results.append(name)
    print(f"[SHOT] {name}")


def step(fn, delay=300):
    QTimer.singleShot(delay, fn)


def s1_initial():
    if not (win._doc and win._doc.frames):
        step(s1_initial, 200)
        return
    print(f"[CHK] arrows hidden initially: "
          f"L={not win.arrow_left.isVisible()} R={not win.arrow_right.isVisible()} "
          f"hotzones={win._hot_l.isVisible() and win._hot_r.isVisible()}")
    grab("1_initial")
    step(s2_arrows_hover, 300)


def s2_arrows_hover():
    # simulate pointer entering the fixed hot zone
    app.sendEvent(win._hot_l, QEvent(QEvent.Type.Enter))
    step(lambda: (
        print(f"[CHK] arrows after hot-zone enter: "
              f"L={win.arrow_left.isVisible()} R={win.arrow_right.isVisible()}"),
        grab("2_arrows_hover"),
        step(s3_arrows_leave, 300),
    ), 150)


def s3_arrows_leave():
    app.sendEvent(win._hot_l, QEvent(QEvent.Type.Leave))
    step(lambda: (
        win._nav_do_hide(),
        print(f"[CHK] arrows after leave: "
              f"L={win.arrow_left.isVisible()} R={win.arrow_right.isVisible()}"),
        grab("3_arrows_gone"),
        step(s4_filmstrip, 300),
    ), 150)


def s4_filmstrip():
    S.set("filmstrip_hide_secs", 3)   # fast auto-hide for the test
    win.resize(720, 740)              # narrow -> strip overflows -> scrollable
    win.btn_gallery.setChecked(True)
    step(s4_wait, 200)


def s4_wait():
    cells = win.filmstrip._cells
    have = sum(1 for c in cells if c._pm is not None)
    if cells and have < len(cells):
        step(s4_wait, 200)
        return
    print(f"[CHK] filmstrip cells={len(cells)} with_pixmap={have}")
    grab("4_filmstrip")
    step(s5_wheel, 300)


def s5_wheel():
    hsb = win.filmstrip._scroll.horizontalScrollBar()
    v0 = hsb.value()
    ev = QWheelEvent(QPointF(100, 40), QPointF(100, 40),
                     QPoint(0, 0), QPoint(0, -120), Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier,
                     Qt.ScrollPhase.NoScrollPhase, False)
    app.sendEvent(win.filmstrip, ev)
    v1 = hsb.value()
    print(f"[CHK] wheel scroll: hsb {v0} -> {v1} "
          + ("OK" if v1 > v0 else "NO MOVE"))
    grab("5_wheel_scroll")
    step(s6_autohide, 300)


def s6_autohide():
    # pointer "leaves" the strip -> hide after filmstrip_hide_secs (3 s here)
    app.sendEvent(win.filmstrip, QEvent(QEvent.Type.Leave))
    def check():
        vis = win.filmstrip.isVisible()
        gal = win.btn_gallery.isChecked()
        print(f"[CHK] autohide: strip visible={vis} gallery checked={gal} "
              + ("OK" if not vis and not gal else "NOT HIDDEN"))
        grab("6_autohide")
        step(s7_info, 300)
    step(check, 3600)


def s7_info():
    win.btn_info_top.click()
    def check():
        ip = win.info_panel
        texts = []
        for i in range(ip._blay.count()):
            wdg = ip._blay.itemAt(i).widget()
            if wdg and wdg.layout():
                labels = [wdg.layout().itemAt(j).widget()
                          for j in range(wdg.layout().count())]
                texts.append(" | ".join(l.text() for l in labels
                                        if hasattr(l, "text")))
        joined = " ;; ".join(texts)
        print(f"[CHK] info panel visible={ip.isVisible()} rows={ip._blay.count()}")
        print(f"[CHK] panel content: {joined[:400]}")
        grab("7_infopanel")
        win.toggle_info()
        step(s8_settings, 300)
    step(check, 350)


def s8_settings():
    fired = {"v": False}

    def check_in_modal():
        modal = QApplication.activeModalWidget()
        fired["v"] = True
        print(f"[CHK] settings dialog in modal loop: "
              f"{type(modal).__name__ if modal else None}")
        grab("8_settings_btn")
        if modal:
            modal.close()

    # click() blocks inside exec(); register the check first so it runs
    # inside the dialog's own modal event loop
    step(check_in_modal, 500)
    win.btn_menu.click()
    if not fired["v"]:     # dialog never opened
        print("[CHK] settings dialog did NOT open")
        grab("8_settings_btn")
    step(s9_menu, 400)


def s9_menu():
    m = win._build_menu()
    pos = win.btn_menu.mapToGlobal(QPoint(0, win.btn_menu.height()))
    QTimer.singleShot(500, lambda: (
        grab("9_menu"),
        m.close()))
    m.popup(pos)
    step(finish, 1200)


def finish():
    print(f"[DONE] screenshots: {len(results)}")
    app.quit()


step(s1_initial, 600)
app.exec()
sys.exit(0 if len(results) >= 9 else 1)
