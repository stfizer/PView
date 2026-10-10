"""P view entry point."""
from __future__ import annotations

import os
import sys


def _main():
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if base not in sys.path:
        sys.path.insert(0, base)

    from PySide6.QtCore import QStandardPaths  # noqa: F401  (plugin env)
    from PySide6.QtWidgets import QApplication

    from pview import APP_NAME, ORG_NAME
    from pview import icons, settings as S
    from pview.i18n import set_language
    from pview.widgets import Toast  # noqa: F401

    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    open_target = args[0] if args else ""

    from pview import get_logger
    log = get_logger()
    log.info("=== P view start ===")
    log.info("frozen=%s argv=%s target=%s", getattr(sys, "frozen", False),
             sys.argv, open_target)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setDesktopFileName("PView")

    # app icon
    from PySide6.QtGui import QIcon
    if getattr(sys, "frozen", False):
        # PyInstaller 6 onedir: datas live under <exe>/_internal (sys._MEIPASS)
        ico_candidates = []
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            ico_candidates.append(os.path.join(meipass, "assets", "pview.ico"))
        exe_dir = os.path.dirname(sys.executable)
        ico_candidates.append(os.path.join(exe_dir, "assets", "pview.ico"))
        ico_candidates.append(os.path.join(exe_dir, "_internal", "assets",
                                           "pview.ico"))
        ico_path = next((p for p in ico_candidates if os.path.exists(p)), "")
    else:
        ico_path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "assets", "pview.ico")
    if ico_path and os.path.exists(ico_path):
        app.setWindowIcon(QIcon(ico_path))

    # icon cache dir for QSS icons
    icon_dir = os.path.join(S.app_data_dir(), "icons")
    icons.init_icon_cache(icon_dir)

    lang = S.get("lang")
    if not lang:
        import locale
        try:
            loc = locale.getlocale()[0] or ""
            lang = "zh" if ("Chinese" in loc or "China" in loc) else "en"
        except Exception:
            lang = "en"
    set_language(lang)

    # ---- single instance ----
    if S.get("single_instance"):
        from PySide6.QtNetwork import QLocalServer, QLocalSocket
        sock = QLocalSocket()
        sock.connectToServer("PViewSingle")
        if sock.waitForConnected(300):
            if open_target:
                sock.write(open_target.encode("utf-8"))
                sock.flush()
                sock.waitForBytesWritten(300)
            sock.disconnectFromServer()
            return 0
        QLocalServer.removeServer("PViewSingle")
        server = QLocalServer()
        server.listen("PViewSingle")
        app._pview_server = server  # keep alive

    from pview.mainwindow import MainWindow
    win = MainWindow(open_target)
    win.show()

    if S.get("single_instance"):
        def _on_conn():
            conn = server.nextPendingConnection()
            if conn:
                conn.readyRead.connect(
                    lambda: _open_from_conn(conn))
        def _open_from_conn(conn):
            data = bytes(conn.readAll()).decode("utf-8", "replace")
            conn.disconnectFromServer()
            if data and win.isVisible():
                win.open_path(data)
                win.showNormal()
                win.raise_()
                win.activateWindow()
        server.newConnection.connect(_on_conn)

    return app.exec()


if __name__ == "__main__":
    sys.exit(_main())
