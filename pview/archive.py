"""Unified sources of image sequences: plain folders and archives (zip/cbz,
tar, 7z, rar/cbr). Handles passwords and natural sorting."""
from __future__ import annotations

import os
import re
import tarfile
import zipfile
from dataclasses import dataclass, field

from . import settings as S

IMG_EXTS = {
    ".jpg", ".jpeg", ".jfif", ".jpe", ".png", ".apng", ".gif", ".bmp", ".dib",
    ".webp", ".tif", ".tiff", ".ico", ".tga", ".ppm", ".pgm", ".pbm", ".pnm",
    ".heic", ".heif", ".hif", ".avif", ".psd", ".psb", ".dds", ".exr", ".hdr",
    ".svg", ".jp2", ".j2k", ".jxl", ".pfm",
}
RAW_EXTS = {
    ".crw", ".cr2", ".cr3", ".nef", ".nrw", ".arw", ".srf", ".sr2", ".dng",
    ".raf", ".orf", ".rw2", ".pef", ".ptx", ".srw", ".x3f", ".erf", ".mef",
    ".mos", ".iiq", ".kdc", ".dcr", ".rwl", ".3fr", ".fff", ".gpr",
}
ARCHIVE_EXTS = {".zip", ".cbz", ".7z", ".rar", ".cbr", ".tar", ".gz", ".tgz",
                ".bz2", ".xz", ".zst", ".lz4"}
ZIP_EXTS = {".zip", ".cbz"}
SEVENZ_EXTS = {".7z"}
RAR_EXTS = {".rar", ".cbr"}
TAR_EXTS = {".tar", ".gz", ".tgz", ".bz2", ".xz", ".zst", ".lz4"}
GROUPABLE_EXTS = {".jpg", ".jpeg", ".jpe", ".hif", ".heif"}  # raw+jpg pairing

ALL_FILE_EXTS = IMG_EXTS | RAW_EXTS | ARCHIVE_EXTS


def ext_of(name: str) -> str:
    return os.path.splitext(name)[1].lower()


def is_image_name(name: str) -> bool:
    return ext_of(name) in IMG_EXTS or ext_of(name) in RAW_EXTS


def is_archive_path(path: str) -> bool:
    return ext_of(path) in ARCHIVE_EXTS


_nat_re = re.compile(r"(\d+)")


def natural_key(s: str):
    parts = _nat_re.split(s.lower())
    return tuple(int(p) if p.isdigit() else p for p in parts)


@dataclass
class Entry:
    """One viewable item inside a source."""
    key: str            # archive member name or absolute file path
    name: str           # display name (file name only)
    size: int = 0
    mtime: float = 0.0
    group: str = ""     # grouping key (RAW+JPG pair stem)

    def sort_tuple(self, key: str, desc: bool):
        if key == "date":
            v = self.mtime
        elif key == "size":
            v = self.size
        elif key == "type":
            v = ext_of(self.name)
        else:  # name
            v = natural_key(self.name)
        return (v, natural_key(self.name)) if not desc else _RevKey(v)


class _RevKey:
    __slots__ = ("v",)

    def __init__(self, v):
        self.v = v

    def __lt__(self, other):
        return other.v < self.v

    def __eq__(self, other):
        return self.v == other.v


class SourceError(Exception):
    pass


class WrongPasswordError(SourceError):
    pass


class PasswordNeededError(SourceError):
    pass


# ------------------------------------------------------------------ backends

class _ZipBackend:
    def __init__(self, path: str, password: str = ""):
        import pyzipper
        self.pw = password.encode("utf-8") if password else None
        try:
            self.zf = pyzipper.AESZipFile(path, "r")
        except Exception as e:
            raise SourceError(str(e))
        self.infos = [i for i in self.zf.infolist() if not i.is_dir()]

    def names(self):
        return self.infos

    def read(self, name: str) -> bytes:
        try:
            return self.zf.read(name, pwd=self.pw)
        except RuntimeError as e:
            raise WrongPasswordError(str(e))
        except zipfile.BadZipFile as e:
            raise SourceError(str(e))

    def encrypted(self) -> bool:
        return any(i.flag_bits & 0x1 for i in self.infos)

    def close(self):
        self.zf.close()


class _TarBackend:
    def __init__(self, path: str, password: str = ""):
        try:
            self.tf = tarfile.open(path, "r:*")
        except Exception as e:
            raise SourceError(str(e))
        self.infos = [m for m in self.tf.getmembers() if m.isfile()]

    def names(self):
        return self.infos

    def read(self, name: str) -> bytes:
        f = self.tf.extractfile(name)
        if f is None:
            raise SourceError("missing member")
        return f.read()

    def encrypted(self) -> bool:
        return False

    def close(self):
        self.tf.close()


class _SevenZipBackend:
    def __init__(self, path: str, password: str = ""):
        import py7zr
        self.path = path
        self.pw = password or None
        try:
            self.zf = py7zr.SevenZipFile(path, "r", password=self.pw)
        except py7zr.exceptions.PasswordRequired:
            raise PasswordNeededError()
        except py7zr.Bad7zLib as e:
            raise SourceError(str(e))
        except Exception as e:
            raise SourceError(str(e))
        self.infos = [f for f in self.zf.list() if not f.is_directory]
        self._needs_pw = self.zf.needs_password() and not self.pw

    def names(self):
        return self.infos

    def read(self, name: str) -> bytes:
        import tempfile
        if self._needs_pw:
            raise PasswordNeededError()
        with tempfile.TemporaryDirectory(prefix="pview7z") as td:
            try:
                with py7zr.SevenZipFile(self.path, "r", password=self.pw) as z:
                    z.extract(targets=[name], path=td)
            except py7zr.exceptions.PasswordRequired:
                raise WrongPasswordError("bad password")
            except Exception as e:
                raise SourceError(str(e))
            out = os.path.join(td, name.replace("\\", "/"))
            if not os.path.exists(out):
                # py7zre stores with internal dirs; try suffix match
                for root, _dirs, files in os.walk(td):
                    for fn in files:
                        if fn == os.path.basename(name):
                            out = os.path.join(root, fn)
                            break
            with open(out, "rb") as f:
                return f.read()

    def encrypted(self) -> bool:
        return self.zf.needs_password()

    def close(self):
        try:
            self.zf.close()
        except Exception:
            pass


class _RarBackend:
    def __init__(self, path: str, password: str = ""):
        import rarfile
        rarfile.UNRAR_TOOL = _find_unrar() or "unrar"
        rarfile.BSDTAR_TOOL = os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                                           "System32", "tar.exe")
        try:
            self.rf = rarfile.RarFile(path)
        except rarfile.BadRarFile as e:
            raise SourceError(str(e))
        except FileNotFoundError as e:
            raise SourceError(str(e))
        except Exception as e:
            raise SourceError(str(e))
        self.pw = password
        if self.pw:
            self.rf.setpassword(self.pw)
        self.infos = [i for i in self.rf.infolist() if i.is_file()]
        self._needs_pw = self.rf.needs_password() and not self.pw

    def names(self):
        return self.infos

    def read(self, name: str) -> bytes:
        if self._needs_pw:
            raise PasswordNeededError()
        try:
            return self.rf.read(name)
        except rarfile.PasswordRequired:
            raise PasswordNeededError()
        except rarfile.RarWrongPassword:
            raise WrongPasswordError("bad password")
        except Exception as e:
            raise SourceError(str(e))

    def encrypted(self) -> bool:
        return self.rf.needs_password()

    def close(self):
        self.rf.close()


def _find_unrar() -> str:
    for p in (r"C:\Program Files\WinRAR\UnRAR.exe",
              r"C:\Program Files (x86)\WinRAR\UnRAR.exe",
              os.path.join(os.path.dirname(os.path.dirname(__file__)), "unrar.exe")):
        if os.path.exists(p):
            return p
    return ""


_BACKENDS = (
    (ZIP_EXTS, _ZipBackend),
    (TAR_EXTS, _TarBackend),
    (SEVENZ_EXTS, _SevenZipBackend),
    (RAR_EXTS, _RarBackend),
)


# ------------------------------------------------------------------ source

class ImageSource:
    """An ordered, sorted list of image entries from a folder or an archive."""

    def __init__(self, path: str, password: str = "", sort_key: str = "",
                 sort_desc: bool | None = None):
        self.path = os.path.normpath(os.path.abspath(path))
        self.password = password
        self.archive = is_archive_path(path)
        self.backend = None
        self.need_password = False
        self.error: str = ""
        key = sort_key or S.get("sort_key")
        desc = S.get("sort_desc") if sort_desc is None else sort_desc
        self.entries: list[Entry] = self._load(key, desc)

    # ---- construction ----
    def _load(self, key: str, desc: bool) -> list[Entry]:
        if not self.archive:
            return self._load_folder(key, desc)
        from . import log_exception
        for exts, cls in _BACKENDS:
            if ext_of(self.path) in exts:
                try:
                    self.backend = cls(self.path, self.password)
                except (PasswordNeededError, WrongPasswordError):
                    self.need_password = True
                    return []
                except Exception as e:
                    log_exception(f"backend {cls.__name__} failed for {self.path}", e)
                    self.error = str(e)
                    return []
                break
        if self.backend is None:
            self.error = "unsupported archive"
            return []
        entries = []
        for info in self.backend.names():
            name = getattr(info, "filename", None) or getattr(info, "name", "")
            base = os.path.basename(name.replace("\\", "/"))
            if not is_image_name(base):
                continue
            size = int(getattr(info, "file_size", 0) or 0)
            mtime = 0.0
            dt = getattr(info, "date_time", None)
            try:
                if dt and dt[0] >= 1980:
                    import calendar
                    mtime = calendar.timegm(dt)
            except Exception:
                pass
            entries.append(Entry(key=name, name=base, size=size, mtime=mtime))
        entries.sort(key=lambda e: e.sort_tuple(key, desc))
        return entries

    def _load_folder(self, key: str, desc: bool) -> list[Entry]:
        if not os.path.isdir(self.path):
            self.error = "not a folder"
            return []
        raw: list[Entry] = []
        try:
            with os.scandir(self.path) as it:
                for de in it:
                    if not de.is_file():
                        continue
                    e = ext_of(de.name)
                    if e not in IMG_EXTS and e not in RAW_EXTS:
                        continue
                    try:
                        st = de.stat()
                    except OSError:
                        continue
                    raw.append(Entry(key=de.path, name=de.name,
                                     size=st.st_size, mtime=st.st_mtime))
        except OSError as e:
            self.error = str(e)
            return []
        if S.get("group_raw_jpg"):
            raw = _group_raw_jpg(raw)
        raw.sort(key=lambda e: e.sort_tuple(key, desc))
        return raw

    # ---- reading ----
    def read_bytes(self, entry: Entry) -> bytes:
        if self.backend is not None:
            return self.backend.read(entry.key)
        with open(entry.key, "rb") as f:
            return f.read()

    def close(self):
        if self.backend is not None:
            self.backend.close()
            self.backend = None

    # ---- sibling navigation ----
    def sibling_archives(self) -> list[str]:
        """Archives in the same directory, sorted by current sort settings."""
        parent = os.path.dirname(self.path) if self.archive else self.path
        out = []
        try:
            for de in os.scandir(parent):
                if de.is_file() and is_archive_path(de.name):
                    out.append(de.path)
        except OSError:
            return []
        k = S.get("sort_key")
        d = S.get("sort_desc")

        def sk(p):
            st = os.stat(p)
            if k == "date":
                v = st.st_mtime
            elif k == "size":
                v = st.st_size
            elif k == "type":
                v = ext_of(p)
            else:
                v = natural_key(os.path.basename(p))
            return v

        out.sort(key=sk, reverse=d)
        return out

    def sibling_folders(self) -> list[str]:
        """Parent-sibling folders (of the current folder) that contain images."""
        base = os.path.dirname(self.path) if self.archive else self.path
        parent = os.path.dirname(base)
        cur = base
        out = []
        try:
            for de in os.scandir(parent):
                if de.is_dir():
                    out.append(de.path)
        except OSError:
            return []
        out.sort(key=lambda p: natural_key(os.path.basename(p)),
                 reverse=S.get("sort_desc"))
        # rotate so current folder is first
        if cur in out:
            i = out.index(cur)
            out = out[i:] + out[:i]
        return out


def _group_raw_jpg(entries: list[Entry]) -> list[Entry]:
    """Collapse RAW+JPG(HIF) same-stem pairs into one entry (prefer JPG)."""
    by_stem: dict[str, dict[str, Entry]] = {}
    for e in entries:
        ext = ext_of(e.name)
        stem = e.name[: len(e.name) - len(ext)]
        by_stem.setdefault(stem.lower(), {})[ext] = e
    out = []
    show_jpg = S.get("group_show_jpg")
    for stem, exts in by_stem.items():
        has_raw = any(ext in RAW_EXTS for ext in exts)
        has_jpg = any(ext in GROUPABLE_EXTS for ext in exts)
        if has_raw and has_jpg and len(exts) == 2:
            pick_ext = ".jpg" if show_jpg else next(iter(RAW_EXTS & set(exts)))
            pick = exts.get(pick_ext) or next(iter(exts.values()))
            pick.group = stem
            out.append(pick)
        else:
            out.extend(exts.values())
    return out
