"""Image loading: PIL pipeline -> QImage frames, EXIF, caching, prefetch."""
from __future__ import annotations

import io
import os
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from PySide6.QtCore import QBuffer, QIODevice, QObject, QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication, QImage, QPixmap

from .archive import Entry, ImageSource, ext_of

# ---------------- optional codecs ----------------

CODEC_ERRORS: list[str] = []

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception as e:  # pragma: no cover
    CODEC_ERRORS.append(f"HEIF: {e}")

try:
    import pillow_avif  # noqa: F401
except Exception as e:
    CODEC_ERRORS.append(f"AVIF: {e}")

try:
    from PIL import Image, ImageOps, ImageFile
    Image.MAX_IMAGE_PIXELS = None  # allow huge images (viewer use-case)
    ImageFile.LOAD_TRUNCATED_IMAGES = True
except Exception as e:  # pragma: no cover
    raise RuntimeError("Pillow is required") from e


def _open_psd(data: bytes):
    from psd_tools import PSDImage
    psd = PSDImage.open(io.BytesIO(data))
    try:
        return psd.composite()
    except Exception:
        return psd.topil()


# ---------------- exif ----------------

@dataclass
class ExifInfo:
    fields: "OrderedDict[str, str]" = field(default_factory=OrderedDict)
    gps: tuple[float, float] | None = None
    orientation: int = 1


_METERING = {0: "Unknown", 1: "Average", 2: "CenterWeightedAverage", 3: "Spot",
             4: "MultiSpot", 5: "Pattern", 6: "Partial"}
_EXPPROG = {0: "N/A", 1: "Manual", 2: "Auto", 3: "Aperture-priority",
            4: "Shutter-priority", 5: "Creative", 6: "Action", 7: "Portrait",
            8: "Landscape"}


def _flash_str(v):
    try:
        return "Fired" if int(v) & 1 else "Did not fire"
    except Exception:
        return str(v)


def _metering_str(v):
    return _METERING.get(int(v), str(v))


def _expprog_str(v):
    return _EXPPROG.get(int(v), str(v))


def _rational_str(v):
    try:
        if isinstance(v, tuple):
            num, den = v
        else:
            num, den = v.numerator, v.denominator
        den = den or 1
        val = num / den
        if val == 0:
            return "0"
        if val >= 1:
            return f"{val:g}"
        inv = den / num if num else 0
        return f"1/{inv:g}"
    except Exception:
        return str(v)


def _bias_str(v):
    try:
        if isinstance(v, tuple):
            num, den = v
            val = num / (den or 1)
        elif hasattr(v, "numerator"):
            val = v.numerator / (v.denominator or 1)
        else:
            val = float(v)
        return f"{val:+.2f} EV"
    except Exception:
        return str(v)


def _wb_str(v):
    try:
        return "Manual" if int(v) else "Auto"
    except Exception:
        return str(v)


_ORIENTS = {1: "Normal", 2: "Flip H", 3: "Rotate 180", 4: "Flip V",
            5: "Transpose", 6: "Rotate 90 CW", 7: "Transverse",
            8: "Rotate 90 CCW"}


def _orient_str(v):
    try:
        return _ORIENTS.get(int(v), str(v))
    except Exception:
        return str(v)


# ordered to match the BandiView EXIF panel layout
_FMTS = {
    271: ("exif_make", str),
    272: ("exif_model", str),
    305: ("exif_software", str),
    36867: ("exif_datetime", str),
    37385: ("exif_flash", _flash_str),
    37386: ("exif_focal", lambda v: _rational_str(v) + " mm"),
    41989: ("exif_focal35", str),
    33434: ("exif_exposure", lambda v: _rational_str(v) + " sec."),
    37380: ("exif_bias", _bias_str),
    33437: ("exif_fnumber", lambda v: "f/" + _rational_str(v)),
    34855: ("exif_iso", lambda v: str(v)),
    41987: ("exif_wb", _wb_str),
    37383: ("exif_metering", _metering_str),
    34850: ("exif_expprog", _expprog_str),
    274: ("exif_orientation", _orient_str),
    42036: ("exif_lens", str),
}


def _dms_to_deg(dms) -> float:
    try:
        d, m, s = dms
        return float(d) + float(m) / 60.0 + float(s) / 3600.0
    except Exception:
        return 0.0


def parse_exif(pil_img) -> ExifInfo:
    info = ExifInfo()
    try:
        exif = pil_img.getexif()
    except Exception:
        return info
    try:
        info.orientation = exif.get(274, 1) or 1
    except Exception:
        pass
    from .i18n import tr
    try:
        exif_ifd = exif.get_ifd(0x8769)
    except Exception:
        exif_ifd = {}
    for tag, (key, fmt) in _FMTS.items():
        val = exif_ifd.get(tag, exif.get(tag))
        if val is None:
            continue
        try:
            s = fmt(val)
        except Exception:
            s = str(val)
        if s and s != "None":
            info.fields[tr(key)] = str(s)
    try:
        gps = exif.get_ifd(0x8825)
        if gps.get(2) and gps.get(4):
            lat = _dms_to_deg(gps.get(2))
            lon = _dms_to_deg(gps.get(4))
            if str(gps.get(1, "N")).upper() in ("S", "W"):
                lat, lon = -lat, -lon
            if lat or lon:
                info.gps = (lat, lon)
    except Exception:
        pass
    return info


# ---------------- document ----------------

@dataclass
class ImageDoc:
    frames: list[QImage] = field(default_factory=list)
    durations: list[int] = field(default_factory=list)   # ms per frame
    loop: bool = True
    animated: bool = False
    exif: ExifInfo | None = None
    size: QSize = QSize(0, 0)
    fmt: str = ""
    src_mode: str = ""       # original PIL mode, e.g. RGB / RGBA / CMYK
    mem: int = 0
    ok: bool = True
    error: str = ""

    def frame(self, i: int) -> QImage:
        return self.frames[i % len(self.frames)] if self.frames else QImage()


def pil_to_qimage(img) -> QImage:
    if img.mode in ("CMYK", "I;16", "I"):
        img = img.convert("RGB")
    if img.mode == "P":
        img = img.convert("RGBA" if "transparency" in img.info else "RGB")
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    if img.mode == "RGB":
        fmt = QImage.Format.Format_RGB888
        bpl = img.width * 3
    else:
        fmt = QImage.Format.Format_RGBA8888
        bpl = img.width * 4
    data = img.tobytes("raw", img.mode)
    qi = QImage(data, img.width, img.height, bpl, fmt)
    return qi.copy()  # detach from python buffer


def load_doc(data: bytes, ext: str, name: str = "") -> ImageDoc:
    doc = ImageDoc()
    try:
        if ext == ".psd" or ext == ".psb":
            pil = _open_psd(data)
        else:
            pil = Image.open(io.BytesIO(data))
            pil.load()
    except Exception as e:
        doc.ok = False
        doc.error = str(e)
        return doc

    doc.fmt = (pil.format or ext.strip(".")).upper()
    doc.exif = parse_exif(pil)
    try:
        doc.src_mode = pil.mode or ""
    except Exception:
        doc.src_mode = ""

    # honour embedded ICC / monitor profile (BandiView-style options)
    try:
        from . import settings as _S
        pil = _apply_icc(pil, bool(_S.get("icc_file")),
                         bool(_S.get("icc_monitor")))
    except Exception:
        pass

    # animated?
    animated = getattr(pil, "is_animated", False)
    try:
        n_frames = int(getattr(pil, "n_frames", 1))
    except Exception:
        n_frames = 1
    n_frames = max(1, min(n_frames, 4096))

    orient = doc.exif.orientation if doc.exif else 1

    def fix(im):
        if 2 <= orient <= 8:
            im = ImageOps.exif_transpose(im)
        return im

    try:
        if animated and n_frames > 1:
            doc.animated = True
            loop = pil.info.get("loop", 0)
            doc.loop = (loop == 0)
            for i in range(n_frames):
                pil.seek(i)
                dur = int(pil.info.get("duration", 100) or 100)
                doc.durations.append(max(20, dur))
                fr = fix(pil.copy().convert("RGBA"))
                doc.frames.append(pil_to_qimage(fr))
        else:
            fr = fix(pil.convert("RGBA"))
            doc.frames.append(pil_to_qimage(fr))
            doc.durations = [0]
    except Exception as e:
        doc.ok = False
        doc.error = str(e)

    if doc.frames:
        doc.size = doc.frames[0].size()
        doc.mem = sum(f.size().width() * f.size().height() * 4 for f in doc.frames)
    return doc


# ---------------- ICC colour management ----------------

_monitor_profile_cache: str = ""


def _monitor_profile_path() -> str:
    """Path of the primary monitor's ICC profile (Windows)."""
    global _monitor_profile_cache
    if _monitor_profile_cache:
        return _monitor_profile_cache
    try:
        import ctypes
        gdi32 = ctypes.windll.gdi32
        user32 = ctypes.windll.user32
        dc = user32.GetDC(0)
        try:
            buf = ctypes.create_unicode_buffer(260)
            size = ctypes.c_uint32(260)
            if gdi32.GetICMProfileW(dc, ctypes.byref(size), buf):
                _monitor_profile_cache = buf.value
        finally:
            user32.ReleaseDC(0, dc)
    except Exception:
        pass
    return _monitor_profile_cache


def _apply_icc(im, use_file: bool, use_monitor: bool):
    """Convert an image from its embedded ICC profile to sRGB/monitor."""
    if not (use_file or use_monitor):
        return im
    src_prof = im.info.get("icc_profile")
    if not src_prof:
        return im
    try:
        from PIL import ImageCms
        src = ImageCms.ImageCmsProfile(io.BytesIO(src_prof))
        if use_monitor:
            mpath = _monitor_profile_path()
            if mpath and os.path.exists(mpath):
                dst = ImageCms.ImageCmsProfile(mpath)
            else:
                dst = ImageCms.createProfile("sRGB")
        else:
            dst = ImageCms.createProfile("sRGB")
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        out_mode = "RGBA" if im.mode == "RGBA" else "RGB"
        out = ImageCms.profileToProfile(im, src, dst, outputMode=out_mode)
        return out if out is not None else im
    except Exception:
        return im


# ---------------- caches & pools ----------------

MEM_BUDGET = 384 * 1024 * 1024   # decoded frame budget
_prefetch_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pview-pre")
_thumb_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pview-th")


class DocCache(QObject):
    """LRU cache of ImageDoc keyed by (source_path, entry_key)."""

    def __init__(self):
        super().__init__()
        self._d: "OrderedDict[tuple, ImageDoc]" = OrderedDict()
        self._mem = 0
        self._lock = threading.Lock()

    def get(self, key) -> ImageDoc | None:
        with self._lock:
            doc = self._d.get(key)
            if doc is not None:
                self._d.move_to_end(key)
            return doc

    def put(self, key, doc: ImageDoc):
        with self._lock:
            old = self._d.pop(key, None)
            if old is not None:
                self._mem -= old.mem
            self._d[key] = doc
            self._mem += doc.mem
            try:
                from . import settings as _S
                budget = max(64, int(_S.get("cache_mb") or 384)) * 1024 * 1024
            except Exception:
                budget = MEM_BUDGET
            while self._mem > budget and len(self._d) > 2:
                _k, v = self._d.popitem(last=False)
                self._mem -= v.mem

    def clear(self):
        with self._lock:
            self._d.clear()
            self._mem = 0


DOC_CACHE = DocCache()


class ThumbCache(QObject):
    """Thumbnail store keyed by (source_path, entry_key, theme-bucket)."""
    ready = Signal(object)  # key

    THUMB = 256

    def __init__(self):
        super().__init__()
        self._m: "OrderedDict[tuple, QPixmap]" = OrderedDict()
        self._pending: set = set()
        self._lock = threading.Lock()

    def get(self, key) -> QPixmap | None:
        with self._lock:
            pm = self._m.get(key)
            if pm is not None:
                self._m.move_to_end(key)
            return pm

    def request(self, key, source: ImageSource, entry: Entry):
        if self.get(key) is not None:
            return
        with self._lock:
            if key in self._pending:
                return
            self._pending.add(key)
        _thumb_pool.submit(self._job, key, source, entry)

    def _job(self, key, source, entry):
        try:
            data = source.read_bytes(entry)
            pil = Image.open(io.BytesIO(data))
            pil.load()
            if getattr(pil, "is_animated", False):
                pil.seek(0)
            pil = pil.convert("RGB")
            w, h = pil.size
            scale = self.THUMB / max(w, h, 1)
            if scale < 1.0:
                pil = pil.resize((max(1, int(w * scale)), max(1, int(h * scale))),
                                 Image.BILINEAR)
            buf = QBuffer()
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            pil.save(buf, "PNG")
            img = QImage.fromData(buf.data(), "PNG")
            pm = QPixmap.fromImage(img)
        except Exception:
            pm = QPixmap()
        with self._lock:
            self._pending.discard(key)
            if pm.isNull():
                return
            self._m[key] = pm
            while len(self._m) > 1200:
                self._m.popitem(last=False)
        self.ready.emit(key)


THUMBS = ThumbCache()


def pil_from_qimage(qimg: QImage):
    """QImage (RGBA8888) -> PIL RGBA Image."""
    q = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = q.width(), q.height()
    buf = bytes(q.constBits())  # sized w*h*4
    return Image.frombytes("RGBA", (w, h), buf, "raw", "RGBA", 0, 1)


def human_size(n: int) -> str:
    f = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if f < 1024 or unit == "GB":
            return f"{f:.0f} {unit}" if unit == "B" else f"{f:.1f} {unit}"
        f /= 1024.0
    return f"{f:.1f} GB"
