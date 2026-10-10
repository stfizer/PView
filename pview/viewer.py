"""Image canvas: zoom/pan/fit modes/rotation/effects/animation/transitions,
plus the webtoon continuous-scroll view."""
from __future__ import annotations

import math
import threading
from collections import OrderedDict

from PySide6.QtCore import (QEasingCurve, QPointF, QRectF, QSize, Qt,
                            QThread, QTimer, QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QWidget

from . import settings as S
from .i18n import tr
from .loader import ImageDoc

FIT_MODES = ("fit", "width", "height", "original")

_GAMMA_LUT_CACHE: dict = {}


def _gamma_lut(g: float):
    lut = _GAMMA_LUT_CACHE.get(g)
    if lut is None:
        lut = []
        for i in range(256):
            v = 255.0 * ((i / 255.0) ** (1.0 / g if g > 0 else 1.0))
            lut.append(max(0, min(255, int(round(v)))))
        _GAMMA_LUT_CACHE[g] = lut
    return lut


def apply_effects(img, fx: dict):
    """fx: gray, sepia, invert, gamma, brightness, contrast, saturation, channel."""
    from PIL import Image, ImageChops, ImageEnhance, ImageOps
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    if fx.get("gray"):
        a = img.getchannel("A")
        img = ImageOps.grayscale(img.convert("RGB")).convert("RGBA")
        img.putalpha(a)
    if fx.get("sepia"):
        a = img.getchannel("A")
        img = ImageOps.colorize(ImageOps.grayscale(img.convert("RGB")),
                                (43, 21, 0), (255, 235, 205)).convert("RGBA")
        img.putalpha(a)
    if fx.get("invert"):
        r, g, b, a = img.split()
        img = Image.merge("RGBA", (ImageChops.invert(r), ImageChops.invert(g),
                                   ImageChops.invert(b), a))
    g_ = fx.get("gamma", 1.0)
    if abs(g_ - 1.0) > 1e-3:
        lut = _gamma_lut(g_)
        img = img.point(lut * 3 + list(range(256)))
    b_ = fx.get("brightness", 1.0)
    if abs(b_ - 1.0) > 1e-3:
        img = ImageEnhance.Brightness(img).enhance(b_)
    c_ = fx.get("contrast", 1.0)
    if abs(c_ - 1.0) > 1e-3:
        img = ImageEnhance.Contrast(img).enhance(c_)
    s_ = fx.get("saturation", 1.0)
    if abs(s_ - 1.0) > 1e-3:
        img = ImageEnhance.Color(img).enhance(s_)
    if fx.get("sharpen"):
        from PIL import ImageFilter
        img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=90,
                                                 threshold=2))
    ch = fx.get("channel", "rgb")
    if ch in ("r", "g", "b"):
        idx = {"r": 0, "g": 1, "b": 2}[ch]
        chans = list(img.split())
        for i in range(3):
            if i != idx:
                chans[i] = chans[i].point(lambda v: 0)
        img = Image.merge("RGBA", chans)
    return img


class _FxWorker(QThread):
    done = Signal(object, object)  # key, QImage

    def __init__(self, parent=None):
        super().__init__(parent)
        self._jobs = OrderedDict()
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._quit = False
        self.start()

    def submit(self, key, pil_img, fx):
        with self._lock:
            self._jobs.pop(key, None)
            self._jobs[key] = (pil_img, dict(fx))
            while len(self._jobs) > 6:
                self._jobs.popitem(last=False)
        self._wake.set()

    def run(self):
        while not self._quit:
            job = None
            with self._lock:
                if self._jobs:
                    key, (img, fx) = self._jobs.popitem(last=True)
                    job = (key, img, fx)
            if job is None:
                self._wake.wait(0.5)
                self._wake.clear()
                continue
            key, img, fx = job
            try:
                out = apply_effects(img, fx)
                from .loader import pil_to_qimage
                qi = pil_to_qimage(out)
            except Exception:
                qi = None
            if not self._quit and qi is not None:
                self.done.emit(key, qi)

    def stop(self):
        self._quit = True
        self._wake.set()


class ImageViewCanvas(QWidget):
    """Displays one (or a pair of) ImageDoc(s) with full viewer semantics."""

    zoomChanged = Signal(float)
    pageRequested = Signal(int)   # +1 = next image, -1 = previous image
    fxChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._doc: ImageDoc | None = None
        self._doc2: ImageDoc | None = None   # second page (double page mode)
        self._key = ""
        self._frame = 0
        self._zoom = 1.0
        self._offset = QPointF(0, 0)         # top-left of content box in widget coords
        self._fit_mode = S.get("view_mode") if S.get("view_mode") in FIT_MODES else "fit"
        self._stretch_small = bool(S.get("stretch_small"))
        self._rot = 0        # 0/90/180/270
        self._flip_h = False
        self._flip_v = False
        self._fx: dict = {}
        self._fx_done = {}   # key -> QImage processed
        self._panning = False
        self._drag_start = None
        self._drag_offset0 = QPointF(0, 0)
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._advance_anim)
        self._anim_playing = False
        self._fx_worker = _FxWorker()
        self._fx_worker.done.connect(self._fx_ready)
        self._bg_color = QColor()
        # transition
        self._snap_prev: QPixmap | None = None
        self._trans_mode = "none"
        self._trans_t = 1.0
        self._trans_anim: QVariantAnimation | None = None
        self._hq_pending = False   # progressive render: rough pass first

    def _hq_ready(self):
        if self._hq_pending:
            self._hq_pending = False
            self.update()

    # ------------- document -------------
    def set_doc(self, doc: ImageDoc | None, key: str = "", transition: str = "none"):
        if transition != "none" and self._doc is not None and self.isVisible():
            self._snap_prev = self._grab_content()
            self._trans_mode = transition
            self._start_transition()
        else:
            self._snap_prev = None
            self._trans_mode = "none"
            self._trans_t = 1.0
        self._doc = doc
        self._doc2 = None
        self._key = key
        self._frame = 0
        self._fx_done.clear()
        self._anim_timer.stop()
        self._anim_playing = False
        if doc and doc.animated and S.get("auto_play_anim"):
            self.play(True)
        if doc and doc.frames:
            self._compute_auto_bg(doc)
            self._reset_for_new_image()
            # progressive render: big images start with a fast rough pass,
            # then a high-quality repaint a tick later (BandiView option)
            self._hq_pending = False
            try:
                if (S.get("progressive") and doc.size.width() * doc.size.height()
                        > 2_000_000):
                    self._hq_pending = True
                    QTimer.singleShot(250, self._hq_ready)
            except Exception:
                self._hq_pending = False
        self.update()
        self._maybe_process_fx()

    def set_pair(self, doc: ImageDoc | None, doc2: ImageDoc | None, key: str = "",
                 transition: str = "none"):
        self.set_doc(doc, key, transition)
        self._doc2 = doc2
        if doc and doc.frames:
            self._reset_for_new_image()
        self.update()
        self._maybe_process_fx()

    def doc(self) -> ImageDoc | None:
        return self._doc

    def doc2(self) -> ImageDoc | None:
        return self._doc2

    def _content_size(self) -> QSize:
        if not self._doc or not self._doc.frames:
            return QSize(0, 0)
        s1 = self._doc.size
        if self._doc2 and self._doc2.frames:
            s2 = self._doc2.size
            try:
                if S.get("double_gap"):
                    g = max(0, int(S.get("double_gap_px") or 10))
                else:
                    g = 12
            except Exception:
                g = 12
            return QSize(s1.width() + s2.width() + g,
                         max(s1.height(), s2.height()))
        return QSize(s1.width(), s1.height())

    def _compute_auto_bg(self, doc: ImageDoc):
        self._bg_color = QColor()
        if S.get("bkcolor") != "auto":
            return
        try:
            fr = doc.frame(0)
            if fr.isNull():
                return
            img = fr.convertToFormat(QImage.Format.Format_RGB32).scaled(
                20, 20, Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            r = g = b = 0
            n = max(1, img.width() * img.height())
            for y in range(img.height()):
                for x in range(img.width()):
                    c = img.pixelColor(x, y)
                    r += c.red()
                    g += c.green()
                    b += c.blue()
            r, g, b = r // n, g // n, b // n
            base = QColor(29, 29, 29) if self._palette_dark() else QColor(240, 240, 240)
            self._bg_color = QColor(int(base.red() * 0.72 + r * 0.28),
                                    int(base.green() * 0.72 + g * 0.28),
                                    int(base.blue() * 0.72 + b * 0.28))
        except Exception:
            self._bg_color = QColor()

    def _palette_dark(self) -> bool:
        from .theme import current_theme
        return current_theme() == "dark"

    # ------------- view state -------------
    def set_fit_mode(self, mode: str):
        if mode in FIT_MODES:
            self._fit_mode = mode
            S.set("view_mode", mode)
            self.recompute_fit()

    def fit_mode(self) -> str:
        return self._fit_mode

    def toggle_stretch_small(self) -> bool:
        self._stretch_small = not self._stretch_small
        S.set("stretch_small", self._stretch_small)
        self.recompute_fit()
        return self._stretch_small

    def set_rotation(self, rot: int, flip_h: bool | None = None,
                     flip_v: bool | None = None):
        self._rot = rot % 360
        if flip_h is not None:
            self._flip_h = flip_h
        if flip_v is not None:
            self._flip_v = flip_v
        self.recompute_fit()
        self.update()

    def rotation(self):
        return self._rot, self._flip_h, self._flip_v

    def reset_rotation(self):
        self._rot = 0
        self._flip_h = False
        self._flip_v = False
        self.recompute_fit()
        self.update()

    def set_effects(self, fx: dict):
        self._fx = dict(fx)
        self._fx_done.clear()
        self._maybe_process_fx()
        self.update()
        self.fxChanged.emit()

    def effects(self) -> dict:
        return dict(self._fx)

    def _fx_signature(self) -> tuple:
        f = self._fx
        return (f.get("gray", False), f.get("sepia", False), f.get("invert", False),
                round(f.get("gamma", 1.0), 3), round(f.get("brightness", 1.0), 3),
                round(f.get("contrast", 1.0), 3), round(f.get("saturation", 1.0), 3),
                f.get("channel", "rgb"), f.get("sharpen", False))

    def _is_fx_neutral(self) -> bool:
        return self._fx_signature() == (False, False, False, 1.0, 1.0, 1.0, 1.0,
                                        "rgb", False)

    def _maybe_process_fx(self):
        if not self._fx or not self._doc or not self._doc.frames or self._is_fx_neutral():
            return
        from .loader import pil_from_qimage
        doc = self._doc
        idx = self._frame if doc.animated else 0
        k = (self._key, idx, self._fx_signature())
        if k not in self._fx_done and doc.frames:
            self._fx_worker.submit(k, pil_from_qimage(doc.frame(idx)), self._fx)
        if self._doc2 and self._doc2.frames:
            k2 = (self._key + "#2", 0, self._fx_signature())
            if k2 not in self._fx_done:
                self._fx_worker.submit(k2, pil_from_qimage(self._doc2.frame(0)), self._fx)

    def _fx_ready(self, key, qi):
        self._fx_done[key] = qi
        self.update()

    # ------------- zoom / fit -------------
    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, z: float, anchor: QPointF | None = None):
        if not self._doc or not self._doc.frames:
            return
        z = max(0.01, min(64.0, z))
        if anchor is None:
            anchor = QPointF(self.width() / 2, self.height() / 2)
        img_pt = self._to_image_pt(anchor)
        self._zoom = z
        if self._fit_mode == "original":
            self._center_offset()
        else:
            self._apply_fit_mode_offset()
        new_anchor = self._from_image_pt(img_pt)
        self._offset += (anchor - new_anchor)
        self._clamp_offset()
        self.update()
        self.zoomChanged.emit(self._zoom)

    def zoom_in(self, anchor=None):
        # guard against clicked(bool)/triggered(bool) passing checked as anchor
        if not isinstance(anchor, QPointF):
            anchor = None
        # step by 5 PERCENTAGE POINTS (50% -> 55% -> 60%); a multiplicative
        # 1.05 step only adds 2.5pp at 50% and reads as "not 5%" to the user
        pct = int(round(self._zoom * 100))
        self.set_zoom((pct + 5) / 100.0, anchor)

    def zoom_out(self, anchor=None):
        if not isinstance(anchor, QPointF):
            anchor = None
        pct = int(round(self._zoom * 100))
        self.set_zoom(max(1, pct - 5) / 100.0, anchor)

    def zoom_100(self):
        self._fit_mode = "original"
        self._zoom = 1.0
        self._center_offset()
        self._clamp_offset()
        self.update()
        self.zoomChanged.emit(self._zoom)

    def fit_best(self):
        self._fit_mode = "fit"
        self.recompute_fit()

    def toggle_zoom_fit_100(self):
        if self._fit_mode == "original":
            self.fit_best()
        else:
            self.zoom_100()

    def recompute_fit(self):
        if not self._doc or not self._doc.frames:
            return
        cs = self._content_size()
        if cs.isEmpty():
            return
        vw, vh = self.width(), self.height()
        iw, ih = cs.width(), cs.height()
        if self._rot in (90, 270):
            iw, ih = ih, iw
        if self._fit_mode == "fit":
            self._zoom = min(vw / iw, vh / ih)
        elif self._fit_mode == "width":
            self._zoom = vw / iw
        elif self._fit_mode == "height":
            self._zoom = vh / ih
        else:
            self._zoom = 1.0
        if (self._stretch_small and self._fit_mode == "original"
                and self._zoom * iw < vw and self._zoom * ih < vh):
            self._zoom = min(vw / iw, vh / ih)
        self._zoom = max(0.01, min(64.0, self._zoom))
        self._apply_fit_mode_offset()
        self.update()
        self.zoomChanged.emit(self._zoom)

    def _apply_fit_mode_offset(self):
        if self._fit_mode == "fit":
            self._center_offset()
        elif self._fit_mode == "width":
            self._offset.setX((self.width() - self._zoomed_w()) / 2)
            self._offset.setY(min(0, (self.height() - self._zoomed_h()) / 2))
        elif self._fit_mode == "height":
            self._offset.setY((self.height() - self._zoomed_h()) / 2)
            self._offset.setX(min(0, (self.width() - self._zoomed_w()) / 2))
        self._clamp_offset()

    def _zoomed_size(self):
        cs = self._content_size()
        z = self._zoom
        if cs.isEmpty():
            return 0.0, 0.0
        if self._rot in (90, 270):
            return z * cs.height(), z * cs.width()
        return z * cs.width(), z * cs.height()

    def _zoomed_w(self):
        return self._zoomed_size()[0]

    def _zoomed_h(self):
        return self._zoomed_size()[1]

    def _center_offset(self):
        self._offset = QPointF((self.width() - self._zoomed_w()) / 2,
                               (self.height() - self._zoomed_h()) / 2)

    def _reset_for_new_image(self):
        if S.get("zoom_lock"):
            self._fit_mode = "original"
            self._zoom = max(0.01, min(64.0, float(S.get("zoom_lock_value")) or 1.0))
            self._center_offset()
            self._clamp_offset()
            self.zoomChanged.emit(self._zoom)
        else:
            if self._fit_mode == "original":
                self._zoom = 1.0
                self._center_offset()
                self._clamp_offset()
            else:
                self.recompute_fit()
        self.update()

    def scroll_center(self):
        self._center_offset()
        self._clamp_offset()
        self.update()

    def scroll_by(self, dx: float, dy: float):
        self._offset += QPointF(dx, dy)
        self._clamp_offset()
        self.update()

    def _clamp_offset(self):
        if not self._doc or self._content_size().isEmpty():
            return
        zw, zh = self._zoomed_w(), self._zoomed_h()
        vw, vh = self.width(), self.height()
        if zw <= vw:
            self._offset.setX((vw - zw) / 2)
        else:
            self._offset.setX(max(vw - zw, min(0.0, self._offset.x())))
        if zh <= vh:
            self._offset.setY((vh - zh) / 2)
        else:
            self._offset.setY(max(vh - zh, min(0.0, self._offset.y())))

    # ------------- geometry mapping -------------
    def _content_transform(self) -> QTransform:
        t = QTransform()
        cs = self._content_size()
        if cs.isEmpty():
            return t
        t.translate(self._offset.x(), self._offset.y())
        if self._rot in (90, 270):
            t.translate(self._zoomed_w() / 2, self._zoomed_h() / 2)
            t.rotate(self._rot)
            t.translate(-self._zoom * cs.width() / 2, -self._zoom * cs.height() / 2)
        elif self._rot == 180:
            t.translate(self._zoomed_w(), self._zoomed_h())
            t.rotate(180)
        t.scale(-1 if self._flip_h else 1, -1 if self._flip_v else 1)
        t.scale(self._zoom, self._zoom)
        return t

    def _to_image_pt(self, widget_pt: QPointF) -> QPointF:
        inv, _ok = self._content_transform().inverted()
        return inv.map(widget_pt)

    def _from_image_pt(self, img_pt: QPointF) -> QPointF:
        return self._content_transform().map(img_pt)

    # ------------- animation -------------
    def play(self, on: bool | None = None):
        if not self._doc or not self._doc.animated:
            return
        if on is None:
            on = not self._anim_playing
        self._anim_playing = on
        if on:
            self._schedule_frame()
        else:
            self._anim_timer.stop()

    def is_playing(self) -> bool:
        return self._anim_playing

    def step_frame(self, delta: int):
        if not self._doc or not self._doc.animated or not self._doc.frames:
            return
        n = len(self._doc.frames)
        self._frame = (self._frame + delta) % n
        self._anim_timer.stop()
        self._anim_playing = False
        self._maybe_process_fx()
        self.update()

    def _schedule_frame(self):
        if not self._anim_playing or not self._doc or not self._doc.durations:
            return
        idx = self._frame % len(self._doc.durations)
        self._anim_timer.start(self._doc.durations[idx])

    def _advance_anim(self):
        if not self._doc or len(self._doc.frames) <= 1:
            return
        n = len(self._doc.frames)
        self._frame = (self._frame + 1) % n
        if not self._doc.loop and self._frame == 0:
            self._anim_timer.stop()
            self._anim_playing = False
        self._maybe_process_fx()
        self._schedule_frame()
        self.update()

    def frame_index(self) -> int:
        return self._frame

    # ------------- transitions -------------
    def _grab_content(self) -> QPixmap | None:
        pm = QPixmap(self.size())
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self._paint_content(p)
        p.end()
        return pm

    def _start_transition(self):
        if self._trans_anim:
            self._trans_anim.stop()
        # start fully on the previous snapshot: leaving _trans_t at 1.0 made
        # the first paint show the NEW image, the next frame (t=0) hid it
        # behind the old snapshot again -> visible flicker on page turns
        self._trans_t = 0.0
        anim = QVariantAnimation(self)
        anim.setDuration(240)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(self._set_trans_t)
        anim.finished.connect(self._trans_done)
        self._trans_anim = anim
        anim.start()

    def _trans_done(self):
        self._snap_prev = None
        self._trans_t = 1.0
        self._trans_mode = "none"
        self.update()

    def _set_trans_t(self, v):
        self._trans_t = float(v)
        self.update()

    # ------------- painting -------------
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,
                        bool(S.get("inter_high")) and not self._hq_pending)
        self._paint_background(p)
        if self._snap_prev is not None and self._trans_t < 1.0:
            if self._trans_mode == "slide":
                dx = self.width() * self._trans_t
                p.setOpacity(1.0)
                p.drawPixmap(QPointF(dx, 0), self._snap_prev)
            else:
                p.setOpacity(max(0.0, 1.0 - self._trans_t))
                p.drawPixmap(0, 0, self._snap_prev)
            p.setOpacity(self._trans_t)
        self._paint_content(p)
        p.end()

    def _paint_background(self, p: QPainter):
        c = self._bg_color
        if c.isValid():
            p.fillRect(self.rect(), c)
            return
        if self._palette_dark():
            p.fillRect(self.rect(), QColor(29, 29, 29))
        else:
            p.fillRect(self.rect(), QColor(245, 245, 245))

    def _paint_content(self, p: QPainter):
        if not self._doc or not self._doc.frames:
            return
        t = self._content_transform()
        gap = 0
        if self._doc2 and self._doc2.frames:
            try:
                if S.get("double_gap"):
                    gap = max(0, int(S.get("double_gap_px") or 10))
                else:
                    gap = 12
            except Exception:
                gap = 12
        # widget-space rects for shadows
        r1 = t.mapRect(QRectF(0, 0, self._doc.size.width(), self._doc.size.height()))
        r2 = None
        if self._doc2 and self._doc2.frames:
            x2 = self._doc.size.width() + gap
            r2 = t.mapRect(QRectF(x2, 0, self._doc2.size.width(), self._doc2.size.height()))
        self._draw_shadow(p, r1)
        if r2:
            self._draw_shadow(p, r2)
        p.save()
        p.setTransform(t, False)
        img1 = self._processed_frame(self._doc, self._frame if self._doc.animated else 0, "")
        self._draw_image(p, img1, self._doc.size)
        if self._doc2 and self._doc2.frames:
            x2 = self._doc.size.width() + gap
            p.save()
            p.translate(x2, 0)
            img2 = self._processed_frame(self._doc2, 0, "#2")
            self._draw_image(p, img2, self._doc2.size)
            p.restore()
        p.restore()

    def _processed_frame(self, doc: ImageDoc, idx: int, suffix: str) -> QImage:
        img = doc.frame(idx)
        if self._fx and not self._is_fx_neutral():
            k = (self._key + suffix, idx, self._fx_signature())
            done = self._fx_done.get(k)
            if done is not None:
                img = done
        return img

    def _draw_image(self, p: QPainter, img: QImage, size: QSize):
        if img.isNull():
            return
        rect = QRectF(0, 0, size.width(), size.height())
        if img.hasAlphaChannel() and S.get("trans_bg") == "grid":
            self._draw_checkerboard(p, rect)
        p.drawImage(rect, img)

    def _draw_shadow(self, p: QPainter, rect: QRectF):
        pad = 12
        alpha0 = 60
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(pad, 0, -2):
            a = int(alpha0 * (1 - i / pad) ** 1.6)
            p.setBrush(QColor(0, 0, 0, a))
            r = QRectF(rect.x() - i, rect.y() - i,
                       rect.width() + 2 * i, rect.height() + 2 * i)
            p.drawRoundedRect(r, 6 + i / 2, 6 + i / 2)

    def _draw_checkerboard(self, p: QPainter, rect: QRectF):
        tile = 12
        c1 = QColor(58, 58, 58) if self._palette_dark() else QColor(255, 255, 255)
        c2 = QColor(44, 44, 44) if self._palette_dark() else QColor(206, 206, 206)
        x0 = math.floor(rect.x() / tile) * tile
        y0 = math.floor(rect.y() / tile) * tile
        y = y0
        row = 0
        p.setPen(Qt.PenStyle.NoPen)
        while y < rect.bottom():
            x = x0
            col = row
            while x < rect.right():
                p.setBrush(c1 if col % 2 == 0 else c2)
                p.drawRect(QRectF(x, y, tile, tile))
                x += tile
                col += 1
            y += tile
            row += 1

    # ------------- events -------------
    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self._doc:
            self.recompute_fit()

    def wheelEvent(self, e):
        d = e.angleDelta().y()
        ctrl = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
        shift = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if ctrl or S.get("wheel_mode") == "zoom":
            # same 5-percentage-point step as the +/- buttons
            pct = int(round(self._zoom * 100))
            new_pct = pct + 5 if d > 0 else max(1, pct - 5)
            self.set_zoom(new_pct / 100.0, e.position())
            e.accept()
            return
        can_v = self._zoomed_h() > self.height() + 1
        can_h = self._zoomed_w() > self.width() + 1
        if can_v or can_h:
            dy = d * 0.6
            old_y = self._offset.y()
            if shift and can_h:
                self.scroll_by(dy, 0)
                e.accept()
                return
            self.scroll_by(0, dy)
            moved = abs(self._offset.y() - old_y) > 0.5
            at_bottom = self._offset.y() <= (self.height() - self._zoomed_h()) + 0.5
            at_top = self._offset.y() >= -0.5
            if not moved or (dy < 0 and at_bottom) or (dy > 0 and at_top):
                # scroll hit an edge (or nothing to scroll): turn the page
                self.pageRequested.emit(1 if d < 0 else -1)
                e.accept()
                return
            e.accept()
            return
        # fit inside window: wheel flips pages directly
        if d:
            self.pageRequested.emit(1 if d < 0 else -1)
            e.accept()
            return
        e.ignore()

    def mousePressEvent(self, e):
        overflow = (self._zoomed_w() > self.width() + 1 or
                    self._zoomed_h() > self.height() + 1)
        if overflow and e.button() in (Qt.MouseButton.LeftButton,
                                       Qt.MouseButton.MiddleButton):
            self._panning = True
            self._drag_start = e.position()
            self._drag_offset0 = QPointF(self._offset)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            e.accept()
            return
        # BandiView-style edge paging: click near the left/right screen edge
        if (S.get("edge_page") and not overflow
                and e.button() == Qt.MouseButton.LeftButton):
            x = e.position().x()
            if x < self.width() * 0.2:
                self.pageRequested.emit(-1)
                e.accept()
                return
            if x > self.width() * 0.8:
                self.pageRequested.emit(1)
                e.accept()
                return
        e.ignore()

    def mouseMoveEvent(self, e):
        if self._panning and self._drag_start is not None:
            d = e.position() - self._drag_start
            self._offset = self._drag_offset0 + d
            self._clamp_offset()
            self.update()
            e.accept()
            return
        e.ignore()

    def mouseReleaseEvent(self, e):
        if self._panning:
            self._panning = False
            self._drag_start = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()
            e.accept()
            return
        e.ignore()

    def mouseDoubleClickEvent(self, e):
        # merged: double-click maximizes (BandiView default) when enabled,
        # otherwise toggles fit/100% zoom
        if e.button() == Qt.MouseButton.LeftButton:
            if S.get("dbl_click_max"):
                w = self.window()
                if hasattr(w, "_toggle_max"):
                    w._toggle_max()
            else:
                self.toggle_zoom_fit_100()
            e.accept()
            return
        e.ignore()

    def closeEvent(self, ev):
        self._fx_worker.stop()
        super().closeEvent(ev)


# ---------------------------------------------------------------- webtoon

def _w_h_estimate(width: int) -> float:
    return width * 1.4


class WebtoonView(QWidget):
    """Continuous vertical strip of all images in the current source."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._provider = None       # callable(index) -> ImageDoc|None
        self._count = 0
        self._heights: list[float] = []
        self._ys: list[float] = []
        self._total_h = 1.0
        self._scroll = 0.0
        self._spacing = 8
        self._images: "OrderedDict[int, QImage]" = OrderedDict()
        self._retry_scheduled = False

    def set_provider(self, count: int, provider):
        self._count = count
        self._provider = provider
        self._heights = [0.0] * count
        self._ys = [0.0] * count
        self._images.clear()
        self._scroll = 0.0
        try:
            self._spacing = (max(0, int(S.get("webtoon_gap_px") or 10))
                             if S.get("webtoon_gap") else 8)
        except Exception:
            self._spacing = 8
        self._recompute_layout()
        self.update()
        self._load_visible()

    def _recompute_layout(self):
        y = 0.0
        w = max(1, self.width() - 24)
        for i in range(self._count):
            self._ys[i] = y
            h = self._heights[i] if self._heights[i] > 0 else w * 1.4
            y += h + self._spacing
        self._total_h = max(y, self.height() + 1)

    def paintEvent(self, ev):
        p = QPainter(self)
        from .theme import current_theme
        p.fillRect(self.rect(), QColor(29, 29, 29) if current_theme() == "dark"
                   else QColor(245, 245, 245))
        w = max(1, self.width() - 24)
        x = 12
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for i in range(self._count):
            y = self._ys[i] - self._scroll
            h = self._heights[i] if self._heights[i] > 0 else w * 1.4
            if y + h < 0 or y > self.height():
                continue
            img = self._images.get(i)
            if img is not None:
                p.drawImage(QRectF(x, y, w, h), img)
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 255, 255, 14))
                p.drawRoundedRect(QRectF(x, y, w, h), 8, 8)
                p.setPen(QPen(QColor(255, 255, 255, 40)))
                p.drawText(QRectF(x, y, w, h), Qt.AlignmentFlag.AlignCenter,
                           tr("loading"))
        p.end()

    def wheelEvent(self, e):
        d = e.angleDelta().y()
        self.scroll_by(-d * 0.6)
        e.accept()

    def scroll_by(self, dy: float):
        self._scroll = max(0.0, min(self._total_h - self.height(), self._scroll + dy))
        self.update()
        self._load_visible()

    def scroll_center_on(self, index: int):
        if 0 <= index < self._count:
            self._scroll = max(0.0, self._ys[index] - 40)
            self.update()
            self._load_visible()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._recompute_layout()
        self._load_visible()

    def _load_visible(self):
        if not self._provider:
            return
        w = max(1, self.width() - 24)
        for i in range(self._count):
            y = self._ys[i] - self._scroll
            h = self._heights[i] if self._heights[i] > 0 else w * 1.4
            if y + h < -500 or y > self.height() + 500:
                continue
            if i not in self._images:
                doc = self._provider(i)
                if doc and doc.frames:
                    img = doc.frame(0)
                    self._images[i] = img
                    self._heights[i] = img.height() * w / max(1, img.width())
                    self._update_ys_from(i)
                    self.update()
                    self._load_visible()
                    return
                if not self._retry_scheduled:
                    self._retry_scheduled = True
                    QTimer.singleShot(300, self._retry)
                return

    def _retry(self):
        self._retry_scheduled = False
        self._load_visible()

    def _update_ys_from(self, index: int):
        y = self._ys[index] + self._heights[index] + self._spacing
        w = max(1, self.width() - 24)
        for i in range(index + 1, self._count):
            self._ys[i] = y
            y += (self._heights[i] if self._heights[i] > 0 else w * 1.4) + self._spacing
        self._total_h = max(y, self.height() + 1)
