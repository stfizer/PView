"""Verify archive viewing in packaged exe: create a real zip, open, screenshot."""
import ctypes
import io
import os
import subprocess
import sys
import time
import zipfile

import win32gui
from PIL import Image, ImageDraw

TMP = os.path.join(os.environ["TEMP"], "pview_verify")
os.makedirs(TMP, exist_ok=True)

zp = os.path.join(TMP, "comic.zip")
with zipfile.ZipFile(zp, "w") as zf:
    for i in range(4):
        img = Image.new("RGB", (1200, 1600), (30 + i * 40, 60, 120 - i * 20))
        d = ImageDraw.Draw(img)
        d.rectangle([100, 100, 1100, 1500], outline=(255, 255, 255), width=8)
        d.text((500, 750), f"Archive Page {i + 1}", fill=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        zf.writestr(f"page{i + 1}.png", buf.getvalue())
print("zip ok:", zp, os.path.getsize(zp), "bytes")

EXE = r"F:\workbuddy空间任务\图片查看器\dist\Pview\Pview.exe"
OUT = r"F:\workbuddy空间任务\图片查看器\verify_zip.png"

proc = subprocess.Popen([EXE, zp])
time.sleep(9)

found = []


def enum_cb(hwnd, _):
    if not win32gui.IsWindowVisible(hwnd):
        return
    if "P view" in win32gui.GetWindowText(hwnd):
        found.append(hwnd)


win32gui.EnumWindows(enum_cb, None)
print("windows:", found)
if not found:
    print("FAIL")
    proc.terminate()
    sys.exit(1)
hwnd = found[0]
win32gui.SetForegroundWindow(hwnd)
time.sleep(1.2)
rect = win32gui.GetWindowRect(hwnd)
w, h = rect[2] - rect[0], rect[3] - rect[1]

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
hdc_window = user32.GetWindowDC(hwnd)
hdc_mem = gdi32.CreateCompatibleDC(hdc_window)
hbmp = gdi32.CreateCompatibleBitmap(hdc_window, w, h)
gdi32.SelectObject(hdc_mem, hbmp)
res = user32.PrintWindow(hwnd, hdc_mem, 2)


class BMIH(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)]


class BMI(ctypes.Structure):
    _fields_ = [("bmiHeader", BMIH), ("bmiColors", ctypes.c_uint32 * 3)]


bmi = BMI()
bmi.bmiHeader.biSize = ctypes.sizeof(BMIH)
bmi.bmiHeader.biWidth = w
bmi.bmiHeader.biHeight = -h
bmi.bmiHeader.biPlanes = 1
bmi.bmiHeader.biBitCount = 32
bmi.bmiHeader.biCompression = 0
buf = ctypes.create_string_buffer(w * h * 4)
gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)
img = Image.frombuffer("RGBA", (w, h), buf.raw, "raw", "BGRA", 0, 1)
img.convert("RGB").save(OUT)
print("saved:", OUT, "PrintWindow:", res)
gdi32.DeleteObject(hbmp)
gdi32.DeleteDC(hdc_mem)
user32.ReleaseDC(hwnd, hdc_window)
proc.terminate()
print("done")
