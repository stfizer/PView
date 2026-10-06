"""Offscreen smoke test for P view: exercises all core paths."""
import io
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, Qt

TMP = tempfile.mkdtemp(prefix="pview_test_")


def make_fixtures():
    from PIL import Image, ImageDraw
    paths = {}
    for name, color, size in [("a.jpg", (200, 60, 60), (1200, 800)),
                              ("b.png", (60, 200, 60), (800, 1200)),
                              ("c.png", (60, 60, 200), (640, 480))]:
        img = Image.new("RGBA", size, color + (255,))
        d = ImageDraw.Draw(img)
        d.ellipse([size[0]//4, size[1]//4, size[0]*3//4, size[1]*3//4],
                  fill=(255, 255, 255, 160))
        p = os.path.join(TMP, name)
        if name.endswith(".jpg"):
            img.convert("RGB").save(p, "JPEG", quality=90)
        else:
            img.save(p, "PNG")
        paths[name] = p
    # animated gif
    frames = [Image.new("RGB", (200, 200), (i * 40, 100, 150)).quantize(64)
              for i in range(6)]
    frames[0].save(os.path.join(TMP, "anim.gif"), save_all=True,
                   append_images=frames[1:], duration=80, loop=0)
    # webp animated
    rgba_frames = [Image.new("RGBA", (150, 150), (i * 40, 120, 200, 255))
                   for i in range(4)]
    rgba_frames[0].save(os.path.join(TMP, "anim.webp"), save_all=True,
                        append_images=rgba_frames[1:], duration=100, loop=0)
    # transparent png
    t = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(t)
    d.ellipse([50, 50, 250, 250], fill=(255, 0, 0, 128))
    t.save(os.path.join(TMP, "trans.png"))
    # zip
    with zipfile.ZipFile(os.path.join(TMP, "book.zip"), "w",
                         zipfile.ZIP_DEFLATED) as zf:
        for i in range(5):
            buf = io.BytesIO()
            Image.new("RGB", (400, 300), (i * 50, 100, 150)).save(buf, "PNG")
            zf.writestr(f"page{i}.png", buf.getvalue())
        zf.writestr("note.txt", "not an image")
    # encrypted zip (ZipCrypto)
    import pyzipper
    with pyzipper.AESZipFile(os.path.join(TMP, "enc.zip"), "w",
                             compression=pyzipper.ZIP_DEFLATED,
                             encryption=pyzipper.WZ_AES) as zf:
        zf.setpassword(b"1234")
        buf = io.BytesIO()
        Image.new("RGB", (320, 240), (10, 200, 120)).save(buf, "PNG")
        zf.writestr("secret.png", buf.getvalue())
    # 7z
    import py7zr
    with py7zr.SevenZipFile(os.path.join(TMP, "pack.7z"), "w") as z:
        for i in range(3):
            buf = io.BytesIO()
            Image.new("RGB", (500, 400), (180, i * 60, 40)).save(buf, "JPEG")
            z.writestr(buf.getvalue(), f"img{i}.jpg")
    # tar.gz
    import tarfile
    with tarfile.open(os.path.join(TMP, "arch.tar.gz"), "w:gz") as tf:
        for i in range(2):
            buf = io.BytesIO()
            Image.new("RGB", (300, 300), (90, 90, i * 100)).save(buf, "PNG")
            data = buf.getvalue()
            info = tarfile.TarInfo(f"t{i}.png")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    # second folder
    os.makedirs(os.path.join(TMP, "sub2"), exist_ok=True)
    Image.new("RGB", (100, 100), (255, 0, 0)).save(
        os.path.join(TMP, "sub2", "s2.png"))
    return paths


def main():
    app = QApplication(sys.argv)
    from pview import icons, settings as S
    icons.init_icon_cache(os.path.join(S.app_data_dir(), "icons"))

    fixtures = make_fixtures()
    from pview.mainwindow import MainWindow

    win = MainWindow()
    win.resize(1100, 700)
    win.show()
    app.processEvents()

    results = []

    def check(name, cond):
        results.append((name, bool(cond)))
        print(("PASS" if cond else "FAIL"), name, flush=True)

    # --- 1. open folder with images
    win.open_path(fixtures["a.jpg"])
    app.processEvents()
    check("open folder source", win._source is not None and
          len(win._source.entries) >= 6)
    loop = QEventLoopish(app)
    loop.wait_until(lambda: win._doc is not None and win._doc.ok and
                    win._current_key().endswith("a.jpg"), 8000)
    check("doc loaded", win._doc is not None and win._doc.ok)
    check("entry index", win._current_key().endswith("a.jpg"))

    # --- navigation
    win.go_next(); app.processEvents()
    loop.wait_until(lambda: win._doc is not None and win._doc.frames, 8000)
    check("go_next", win._idx >= 0)
    win.go_first(); app.processEvents()
    check("go_first", win._idx == 0)
    win.go_last(); app.processEvents()
    check("go_last", win._idx == len(win._source.entries) - 1)
    win.go_next10(); app.processEvents()
    check("next10 clamp", win._idx == len(win._source.entries) - 1)

    # --- zip archive
    win.open_path(os.path.join(TMP, "book.zip"))
    app.processEvents()
    check("zip entries", win._source is not None and len(win._source.entries) == 5)
    loop.wait_until(lambda: win._doc is not None and win._doc.ok, 8000)
    check("zip doc", win._doc is not None and win._doc.ok)
    win.go_next(); app.processEvents()
    loop.wait_until(lambda: win._idx == 1 and win._doc is not None and
                    win._doc.size.width() == 400, 8000)
    check("zip page2", win._idx == 1)

    # --- encrypted zip
    win.open_path(os.path.join(TMP, "enc.zip"))
    app.processEvents()
    # password dialog will block; bypass: open source directly with password
    from pview.archive import ImageSource
    src = ImageSource(os.path.join(TMP, "enc.zip"), password="1234")
    check("enc zip with pw", len(src.entries) == 1)
    data = src.read_bytes(src.entries[0])
    check("enc zip read", len(data) > 100)
    src_bad = ImageSource(os.path.join(TMP, "enc.zip"), password="wrong")
    ok = True
    try:
        src_bad.read_bytes(src_bad.entries[0])
        ok = False
    except Exception:
        ok = True
    check("enc zip wrong pw raises", ok)

    # --- 7z
    win.open_path(os.path.join(TMP, "pack.7z"))
    app.processEvents()
    check("7z entries", win._source and len(win._source.entries) == 3)
    loop.wait_until(lambda: win._doc is not None and win._doc.ok, 10000)
    check("7z doc", win._doc is not None and win._doc.ok)

    # --- tar.gz
    win.open_path(os.path.join(TMP, "arch.tar.gz"))
    app.processEvents()
    check("tar entries", win._source and len(win._source.entries) == 2)
    loop.wait_until(lambda: win._doc is not None and win._doc.ok, 8000)
    check("tar doc", win._doc is not None and win._doc.ok)

    # --- animated gif
    win.open_path(os.path.join(TMP, "anim.gif"))
    app.processEvents()
    loop.wait_until(lambda: win._current_key().endswith("anim.gif") and
                    win._doc is not None and win._doc.ok and win._doc.animated and
                    len(win._doc.frames) == 6, 8000)
    check("gif animated", win._doc is not None and win._doc.animated and
          len(win._doc.frames) == 6)
    win.anim_step(1)
    app.processEvents()
    check("gif frame step", win.canvas.frame_index() == 1)

    # --- animated webp
    win.open_path(os.path.join(TMP, "anim.webp"))
    app.processEvents()
    loop.wait_until(lambda: win._doc is not None and win._doc.ok, 8000)
    check("webp animated", win._doc is not None and win._doc.animated)

    # --- transparent png + checkerboard
    win.open_path(os.path.join(TMP, "trans.png"))
    app.processEvents()
    loop.wait_until(lambda: win._doc is not None and win._doc.ok, 8000)
    check("transparent png", win._doc is not None and win._doc.ok)

    # --- view modes / zoom / rotation / fx
    win.set_view_mode("original")
    app.processEvents()
    check("vm original", win.canvas.fit_mode() == "original")
    win.canvas.zoom_in()
    check("zoom in", win.canvas.zoom() > 1.0)
    win.set_view_mode("fit")
    win.rotate(90)
    app.processEvents()
    check("rotate", win.canvas.rotation()[0] == 90)
    win.toggle_flip(True)
    check("flip h", win.canvas.rotation()[1])
    win.reset_rotation()
    check("reset rotation", win.canvas.rotation()[0] == 0)
    win.fx_toggle("invert")
    app.processEvents()
    check("fx invert", win.canvas.effects().get("invert"))
    win.fx_toggle("invert")
    win.set_filter("sharpen")
    app.processEvents()
    check("filter sharpen", win.canvas.effects().get("sharpen"))
    win.set_filter("none")

    # --- double page & webtoon
    win.open_path(os.path.join(TMP, "book.zip"))
    app.processEvents()
    loop.wait_until(lambda: win._doc is not None, 8000)
    win.set_view_mode("l2r")
    app.processEvents()
    check("double mode", win._double_mode == "l2r")
    win.set_view_mode("fit")
    win.set_view_mode("webtoon")
    app.processEvents()
    check("webtoon on", win._webtoon_mode and win.stack.currentWidget() is win.webtoon)
    win.set_view_mode("fit")
    check("webtoon off", not win._webtoon_mode)

    # --- slideshow step logic (no start)
    win._ss_effect = "fade"
    win.go_next("fade")
    app.processEvents()

    # --- convert single png->jpg via worker
    from pview.dialogs import ConvertWorker
    outp = os.path.join(TMP, "conv_out.jpg")
    w = ConvertWorker([(lambda: open(fixtures["b.png"], "rb").read(), outp,
                        {"pil_format": "JPEG", "quality": 90, "resize_mode": "none",
                         "resize": (0, 0), "rotate": 90})])
    w.start()
    w.wait(15000)
    check("convert worker", os.path.exists(outp) and os.path.getsize(outp) > 100)

    # --- misc
    win._toast("测试通知")
    app.processEvents()
    check("toast", True)
    win.stop_slideshow()
    win._copy_path()
    from PySide6.QtWidgets import QApplication as QA
    cbtxt = QA.clipboard().text()
    check("copy path", "arch" in cbtxt or len(cbtxt) > 0)

    # --- settings dialog construct
    from pview.dialogs import SettingsDialog, AdjustDialog
    sd = SettingsDialog(win)
    check("settings dialog", sd is not None)
    ad = AdjustDialog(win.canvas, win)
    check("adjust dialog", ad is not None)
    from pview.gallery import NavigatorDialog
    nd = NavigatorDialog(win._source, 0, win)
    check("navigator dialog", nd is not None)

    # --- theme switch live
    S.set("theme", "light")
    win.apply_theme()
    app.processEvents()
    S.set("theme", "dark")
    win.apply_theme()
    app.processEvents()
    check("theme switch", True)

    print()
    fails = [n for n, ok in results if not ok]
    print(f"TOTAL {len(results)}, FAILED {len(fails)}", fails if fails else "")
    return 1 if fails else 0


class QEventLoopish:
    def __init__(self, app):
        self.app = app

    def wait_until(self, cond, timeout_ms=5000):
        waited = 0
        while waited < timeout_ms:
            self.app.processEvents()
            try:
                if cond():
                    return True
            except Exception:
                pass
            self.app.thread().msleep(50)
            waited += 50
        return False


if __name__ == "__main__":
    sys.exit(main())
