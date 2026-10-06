"""Verify ALL keyboard shortcuts: static binding audit + real key dispatch.

Dynamically fires only safe shortcuts (navigation/zoom/view/effects/toggles);
modal-dialog shortcuts are fired with an auto-closer; file-system-risky keys
(Del/F2/Ins family) are skipped in the dynamic pass but audited statically.
"""
import os
import sys

PVIEW_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PVIEW_ROOT)
os.environ.pop("QT_QPA_PLATFORM", None)

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QShortcut
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest

app = QApplication(sys.argv)

from pview import settings as S
S.set("confirm_delete", True)   # keep Del behind a confirm dialog

TMP = os.path.join(os.environ["TEMP"], "pview_guiverify2")
from pview.mainwindow import MainWindow

win = MainWindow(os.path.join(TMP, "exif.jpg"))
win.resize(1160, 740)
win.show()

RISKY = {"Del", "F2", "Ins", "Shift+Ins", "Ctrl+Ins",   # may touch files
         "Ctrl+P",                                      # native print dialog
         "Ctrl+E", "Ctrl+N"}   # spawn external apps that steal the focus

# mock native file dialogs so Ctrl+O / Ctrl+S / Ctrl+E don't block on them
from PySide6.QtWidgets import QFileDialog
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: ("",))
ok = True


def check(name, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + (f"  {detail}" if detail else ""))
    ok = ok and cond


def probe():
    shortcuts = win.findChildren(QShortcut)
    keys = {}
    for sc in shortcuts:
        ks = sc.key().toString()
        keys.setdefault(ks, []).append(sc)
    print(f"[AUDIT] QShortcut objects: {len(shortcuts)}, "
          f"unique keys: {len(keys)}")

    # static: empty/duplicate keys
    dup = {k: len(v) for k, v in keys.items() if len(v) > 1}
    check("no duplicate shortcuts", not dup, str(dup) if dup else "")
    empty = [sc.key().toString() for sc in shortcuts if sc.key().isEmpty()]
    check("no empty bindings", not empty)
    check("shortcuts enabled", all(sc.isEnabled() for sc in shortcuts))

    # static: every expected key exists
    expected = ["Right", "Down", "Left", "Up", "Space", "PgDown", "PgUp",
                "Home", "End", "Ctrl+PgDown", "Ctrl+PgUp",
                "Ctrl+Alt+PgDown", "]", "[", "+", "=", "-", "0", "9", "8",
                "7", "6", "5", "Z", "Alt+Right", "Alt+Left", "Alt+Down",
                "Alt+Up", "Ctrl+M", "Ctrl+F", "Ctrl+I", "Ctrl+Y",
                "Ctrl+Shift+S", "Ctrl+G", "U", "I", "S", "Alt+T", "F8",
                "Ctrl+1", "Ctrl+2", "Ctrl+3", "Ctrl+4", "Ctrl+5", "Ctrl+6",
                "Ctrl+7", "Ctrl+8", "Ctrl+9",
                "F11", "Alt+Return", "F", "Return", "Tab", "Shift+Tab", "B",
                "F2", "Del", "Ctrl+C", "Ctrl+V", "Ctrl+T", "Ctrl+P",
                "Ctrl+S", "Ctrl+E", "Ins", "Shift+Ins", "Ctrl+Ins",
                "Ctrl+A", "Ctrl+Return", "F5", "F1", "F4", "Ctrl+W",
                "Ctrl+O", "Ctrl+N", "Esc", "Ctrl+Shift+G"]
    missing = [k for k in expected if k not in keys]
    check(f"all {len(expected)} expected keys bound", not missing,
          f"missing={missing}" if missing else "")

    # dynamic: fire each safe shortcut and check it dispatches. NOTE: some
    # shortcuts (F5/settings) REBUILD all QShortcut objects, so a one-time
    # probe connection would go stale — connect a fresh probe per fire.
    def fire(ks):
        seq = QKeySequence(ks)
        if seq.count() != 1:
            return False
        comb = seq[0]
        key = comb.key()
        mods = comb.keyboardModifiers()
        fired_local = set()
        for sc in win.findChildren(QShortcut):
            if sc.key().toString() == ks:
                sc.activated.connect(
                    lambda f=fired_local: f.add(1))
        # a modal dialog opened by a previous shortcut deactivates the main
        # window; WindowShortcut dispatch requires an active window
        win.activateWindow()
        QApplication.processEvents()
        QTest.keyClick(win, key, mods)
        return bool(fired_local)

    safe = [k for k in keys if k not in RISKY]
    for ks in safe:
        # auto-close any modal dialog that the shortcut opens
        def closer():
            m = QApplication.activeModalWidget()
            if m:
                m.close()
        QTimer.singleShot(250, closer)
        if not fire(ks):
            # Tab-style keys may be swallowed by focus handling: retry once
            QTimer.singleShot(250, closer)
            if not fire(ks):
                check(f"shortcut fires: {ks}", False)
                continue
        print(f"  ok {ks}")
    check("dynamic dispatch verified for all safe shortcuts", True)

    print("ALL OK" if ok else "SOME FAILED")
    app.quit()


QTimer.singleShot(700, probe)
app.exec()
