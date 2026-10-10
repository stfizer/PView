"""Right-side sliding info panel: file info + EXIF key metadata."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QScrollArea, QToolButton, QVBoxLayout, QWidget)

from .i18n import tr
from .loader import human_size
from .widgets import IconButton

import os


class InfoPanel(QFrame):
    """Floating right drawer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("InfoPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(316)
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(14, 14, 14, 14)

        head = QHBoxLayout()
        self._title = QLabel(tr("file_info"))
        self._title.setObjectName("SectionTitle")
        head.addWidget(self._title)
        head.addStretch(1)
        self._close_btn = IconButton("win-close", tr("close"), 30, 14)
        head.addWidget(self._close_btn)
        self._outer.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._body = QWidget()
        self._blay = QVBoxLayout(self._body)
        self._blay.setContentsMargins(0, 4, 4, 0)
        self._blay.setSpacing(2)
        scroll.setWidget(self._body)
        self._outer.addWidget(scroll)

        self._rows: list[tuple[QLabel, QLabel]] = []
        self._gps_cb = None

    # ---------- population ----------
    def show_entry(self, source, index: int, doc, zoom: float | None = None):
        self._clear_rows()
        self._zoom_lbl = None
        entry = source.entries[index] if source and 0 <= index < len(source.entries) else None
        if entry is None:
            return
        rows: list[tuple[str, str]] = []
        # file info (BandiView layout) — panel header already carries the
        # "文件信息" title, so no extra section heading here
        total = len(source.entries)
        name_txt = entry.name + (f"  [{index + 1}/{total}]" if total > 1 else "")
        rows.append((tr("fi_name"), name_txt))
        rows.append((tr("fi_folder"), os.path.dirname(source.path)))
        size_bytes = entry.size
        rows.append((tr("fi_size"), human_size(size_bytes) if size_bytes else "-"))
        import datetime
        if entry.mtime:
            dt = datetime.datetime.fromtimestamp(entry.mtime)
            rows.append((tr("fi_modified"),
                         dt.strftime("%Y/%m/%d %H:%M:%S")))
        if doc and doc.size.width():
            mode = doc.src_mode or (
                "RGBA" if (doc.frames and doc.frames[0].hasAlphaChannel())
                else "RGB")
            info = f"{doc.size.width()}x{doc.size.height()} " \
                   f"({doc.fmt or 'IMG'}, {mode}(8bit))"
            if doc.animated:
                info += f"   ({len(doc.frames)} {tr('fi_frames')})"
            rows.append((tr("fi_dims"), info))
            if doc.fmt:
                rows.append(("Format", doc.fmt))
        # current zoom (BandiView-style "放大/缩小" row, live-updated)
        if zoom is not None and doc and doc.frames:
            rows.append((tr("zoom"), f"{int(round(zoom * 100))}%"))
            self._zoom_lbl = None
        if not source.archive and os.path.exists(entry.key):
            try:
                ct = os.path.getctime(entry.key)
                rows.append((tr("fi_created"),
                             datetime.datetime.fromtimestamp(ct).strftime("%Y/%m/%d %H:%M:%S")))
            except OSError:
                pass
        for k, v in rows:
            self._add_row(k, v)
        # exif
        self._add_section(tr("exif_info"))
        exif = doc.exif if doc else None
        exif_rows: list[tuple[str, str]] = []
        if exif and exif.fields:
            for k, v in exif.fields.items():
                exif_rows.append((k, str(v)))
        else:
            exif_rows.append(("", tr("no_exif")))
        if exif and exif.gps:
            lat, lon = exif.gps
            exif_rows.append((tr("exif_gps"), f"{lat:.5f}, {lon:.5f}"))
        for k, v in exif_rows:
            self._add_row(k, v)
        if exif and exif.gps:
            lat, lon = exif.gps
            btn = QToolButton()
            btn.setText("🌐 " + tr("gps_open_map"))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("QToolButton{border:none;color:#4cc2ff;padding:2px 0;}"
                              "QToolButton:hover{text-decoration:underline;}")
            btn.clicked.connect(lambda: self._open_map(lat, lon))
            self._blay.addWidget(btn)
        # re-locate the live zoom label (last file-info row when present)
        for k, v in rows:
            if k == tr("zoom"):
                self._zoom_lbl = self._last_value_label
        self._blay.addStretch(1)

    def _open_map(self, lat: float, lon: float):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(
            f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=16/{lat}/{lon}"))

    def _clear_rows(self):
        while self._blay.count():
            item = self._blay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                pass
        self._rows.clear()

    def _add_section(self, text: str):
        lbl = QLabel(text)
        lbl.setObjectName("SectionTitle")
        self._blay.addWidget(lbl)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background: rgba(128,128,128,0.25); border: none;")
        self._blay.addWidget(line)

    def _add_row(self, k: str, v: str) -> QLabel:
        holder = QWidget()
        g = QGridLayout(holder)
        g.setContentsMargins(0, 2, 0, 2)
        g.setHorizontalSpacing(10)
        kl = QLabel(k)
        kl.setObjectName("Dim")
        kl.setStyleSheet("color: rgba(128,128,128,0.9); background: transparent;")
        vl = QLabel(v)
        vl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        vl.setWordWrap(True)
        vl.setStyleSheet("background: transparent;")
        g.addWidget(kl, 0, 0, Qt.AlignmentFlag.AlignTop)
        g.addWidget(vl, 0, 1)
        g.setColumnStretch(0, 0)
        g.setColumnStretch(1, 1)
        self._blay.addWidget(holder)
        self._last_value_label = vl
        return vl

    def update_zoom(self, z: float):
        """Live-update the zoom row while the panel is visible."""
        lbl = getattr(self, "_zoom_lbl", None)
        if lbl is not None:
            lbl.setText(f"{int(round(z * 100))}%")

    def retint(self, p: dict):
        # near-opaque so the panel reads as ONE uniform surface: lower values
        # let bright image areas bleed through and look like a solid lighter
        # block inside the panel (user-visible inconsistency)
        self.setStyleSheet("""
            QFrame#InfoPanel {{
                background: rgba(24,24,24,0.97);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 10px;
            }}
            QLabel {{ color: #ffffff; }}
        """)

    # ---------- height ----------
    def preferred_height(self) -> int:
        """Height needed to show all rows without scrolling."""
        body_w = self.width() - 14 * 2 - 4   # outer margins + body right margin
        body_h = max(0, self._blay.heightForWidth(body_w))
        head_h = self._outer.itemAt(0).sizeHint().height()
        # +10px slack: wrapped labels can render a few px taller than the
        # hfw estimate; if content overflows even 1px a scrollbar appears,
        # shrinking the viewport and locking the scrollbar in (feedback loop)
        return 14 + head_h + self._outer.spacing() + body_h + 14 + 10

    def fit_height(self, max_h: int):
        """Clamp panel height to content, never beyond max_h (scroll if needed)."""
        self.setFixedHeight(max(140, min(self.preferred_height(), max_h)))
        # self-calibrate one tick later: measure the real scrollbar overflow
        # (immune to font-metric / DPI drift between estimate and render)
        QTimer.singleShot(0, lambda: self._calibrate_height(max_h))

    def _calibrate_height(self, max_h: int):
        if not self.isVisible():
            return
        scroll = self.findChild(QScrollArea)
        if scroll is None:
            return
        over = scroll.verticalScrollBar().maximum()
        if over > 0:
            self.setFixedHeight(min(self.height() + over + 4, max_h))

    # ---------- slide in/out ----------
    def slide_in(self):
        parent = self.parentWidget()
        if not parent:
            return
        self.fit_height(parent.height() - 90)
        self.move(parent.width() - self.width() - 16, 64)
        self.show()
        self.raise_()

    def slide_out(self):
        self.hide()
