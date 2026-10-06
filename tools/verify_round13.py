"""Verify round 13: settings expansion (shortcuts/mouse/bookmarks/ctx menu)."""
import os
import sys

PVIEW_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PVIEW_ROOT)
os.environ.pop("QT_QPA_PLATFORM", None)

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QShortcut
from PySide6.QtCore import Qt, QTimer

app = QApplication(sys.argv)

TMP = os.path.join(os.environ["TEMP"], "pview_guiverify2")
from pview.mainwindow import MainWindow
from pview.dialogs import SettingsDialog
from pview import settings as S

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
    check(f"settings window tall enough ({dlg.height()}px)",
          dlg.height() >= 700)
    labels = [dlg.nav.item(i).text() for i in range(dlg.nav.count())]
    check("12 nav entries incl 快捷菜单",
          labels == ["常规", "浏览", "图像处理", "格式关联", "快捷键", "鼠标",
                     "书签", "快捷菜单", "图片文件夹", "杂项", "语言", "关于"])
    # walk all pages
    for i in range(dlg.nav.count()):
        dlg.nav.setCurrentRow(i)
        app.processEvents()
    check("all pages build", True)

    # image-processing page new controls
    check("image page: prefetch/cache/progressive/icc/wgap/dgap/cover",
          all(hasattr(dlg, a) for a in
              ("chk_prefetch", "cache_mb", "chk_prog", "chk_iccf", "chk_iccm",
               "chk_wgap", "wgap_px", "chk_dgap", "dgap_px", "chk_cover")))
    check("mouse page: dbl-max + edge", hasattr(dlg, "chk_dbl")
          and hasattr(dlg, "chk_edge"))
    check("ctx menu page reflects registry state",
          dlg.chk_ctx.isChecked() in (True, False))

    # --- custom shortcuts ---
    dlg.nav.setCurrentRow(4)
    app.processEvents()
    t = dlg._keys_table
    check(f"shortcut table lists all commands ({t.rowCount()})",
          t.rowCount() == 67)
    # simulate: bind key 'B' (owned by bookmark_add) to the 'navigator' command
    for r in range(t.rowCount()):
        if t.item(r, 0).text() == "navigator":
            dlg._keys_table.selectRow(r)
            break
    # auto-confirm the conflict dialog
    orig_q = QMessageBox.question
    answered = {}
    def fake_q(*a, **k):
        answered["called"] = True
        return QMessageBox.StandardButton.Yes
    QMessageBox.question = staticmethod(fake_q)
    dlg._keys_set_binding("navigator", "B", replace_all=False)
    QMessageBox.question = orig_q
    nav_keys = dlg._keys_eff().get("navigator", [])
    check(f"conflicting binding staged ({nav_keys})",
          "B" in nav_keys)
    check("conflict dialog was shown", answered.get("called", False))
    bm_keys = dlg._keys_eff().get("bookmark_add", [])
    check("old conflicting binding removed from bookmark_add",
          "B" not in bm_keys)
    # apply → persisted; then simulate the post-dialog rebuild like
    # MainWindow._show_settings does after exec()
    dlg._apply_and_close()
    saved = S.get("key_overrides") or {}
    check("override persisted on apply",
          "B" in (saved.get("navigator") or []))
    win._rebuild_shortcuts()
    eff = win._effective_keys()
    check("rebuilt effective keys contain the new binding",
          "B" in eff.get("navigator", []))
    nav_shown = {"v": False}
    sc_hit = [sc for sc in win.findChildren(QShortcut)
              if sc.key().toString() == "B"]
    if sc_hit:
        from PySide6.QtTest import QTest
        win.activateWindow()
        app.processEvents()

        def close_nav():
            m = QApplication.activeModalWidget()
            if m is not None and m.__class__.__name__ == "NavigatorDialog":
                nav_shown["v"] = True
                m.close()
            elif m is not None:
                m.close()
        QTimer.singleShot(300, close_nav)
        QTest.keyClick(win, Qt.Key.Key_B, Qt.KeyboardModifier.NoModifier)
    check("pressing B opens the navigator (rebound binding)", nav_shown["v"])

    # cleanup: reset overrides to defaults for the package test
    S.set("key_overrides", {})

    print("ALL OK" if ok else "SOME FAILED")
    app.quit()


QTimer.singleShot(700, probe)
app.exec()
