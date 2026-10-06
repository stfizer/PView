"""Diagnose the 4 reported issues offscreen (v2)."""
import os
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

app = QApplication(sys.argv)

TMP = tempfile.mkdtemp(prefix="pview_diag2_")
from PIL import Image, ImageDraw
for i in range(6):
    img = Image.new("RGB", (900, 600), (i * 40, 100, 150))
    d = ImageDraw.Draw(img)
    d.ellipse([200, 150, 700, 450], fill=(255, 255, 255))
    img.save(os.path.join(TMP, f"pic{i}.jpg"), "JPEG", quality=88)

from pview.mainwindow import MainWindow

win = MainWindow(os.path.join(TMP, "pic0.jpg"))
win.resize(1100, 720)
win.show()

def pump(ms):
    """Process events for ~ms milliseconds."""
    t0 = QTimer()
    done = {"v": False}
    def stop():
        done["v"] = True
    t0.timeout.connect(stop)
    t0.start(ms)
    while not done["v"]:
        app.processEvents()
    t0.stop()

pump(600)   # let open_path fire + doc load

print("doc:", "loaded" if (win._doc and win._doc.frames) else "NOT loaded",
      "| source entries:", len(win._source.entries) if win._source else 0)

# ---- Issue 2: zoom via clicked(bool) ----
z0 = win.canvas.zoom()
win.btn_zoom_in.click()
pump(120)
z1 = win.canvas.zoom()
print(f"[ISSUE2] btn_zoom_in.click(): {z0:.4f} -> {z1:.4f} "
      + ("OK" if z1 > z0 else "NO CHANGE (bug confirmed)"))
win.btn_zoom_out.click()
pump(120)
z2 = win.canvas.zoom()
print(f"[ISSUE2] btn_zoom_out.click(): {z1:.4f} -> {z2:.4f} "
      + ("OK" if z2 < z1 else "NO CHANGE (bug confirmed)"))

# ---- Issue 1: filmstrip thumbnails ----
win.toggle_filmstrip(True)
pump(2500)   # wait for thumbnail jobs (2 workers)
cells = win.filmstrip._cells
have_pm = sum(1 for c in cells if c._pm is not None)
print(f"[ISSUE1] cells={len(cells)} with_pixmap={have_pm} "
      f"strip_visible={win.filmstrip.isVisible()}")
if cells:
    try:
        cells[0].grab()   # forces real paintEvent
        print("[OK]   ThumbCell.paintEvent executed without exception")
    except Exception as e:
        traceback.print_exc()
        print(f"[FAIL] ThumbCell.paintEvent raised: {type(e).__name__}: {e}")

# ---- Issue 3: info panel ----
win.toggle_info()
pump(120)
ip = win.info_panel
print(f"[ISSUE3] toggle_info -> visible={ip.isVisible()} geo={ip.geometry()} "
      f"rows={ip._blay.count()}")

# ---- Issue 4: menu build ----
try:
    m = win._build_menu()
    n = len(m.actions())
    print(f"[ISSUE4] _build_menu OK: {n} top-level actions")
    m.deleteLater()
except Exception as e:
    traceback.print_exc()
    print(f"[FAIL] _build_menu raised: {type(e).__name__}: {e}")

print("done")
