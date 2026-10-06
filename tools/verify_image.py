"""Launch Pview.exe with a test image, screenshot, then verify zoom/toolbar."""
import ctypes
import os
import subprocess
import sys
import time

import win32gui
from PIL import Image, ImageDraw

TMP = os.path.join(os.environ["TEMP"], "pview_verify")
os.makedirs(TMP, exist_ok=True)

# make a few colorful test images
for i, (name, color) in enumerate([("photo1.jpg", (200, 80, 60)),
                                   ("photo2.png", (60, 140, 220)),
                                   ("photo3.jpg", (90, 180, 90))]):
    img = Image.new("RGB", (1600, 1000), color)
    d = ImageDraw.Draw(img)
    for k in range(10):
        d.ellipse([k * 160, 200 + k * 60, k * 160 + 220, 420 + k * 60],
                  outline=(255, 255, 255), width=6)
    d.text((40, 40), f"Test Image {i + 1}: {name}", fill=(255, 255, 255))
    img.save(os.path.join(TMP, name),
             "JPEG" if name.endswith(".jpg") else "PNG")

EXE = r"F:\workbuddy空间任务\图片查看器\PView\dist\Pview\Pview.exe"
OUT = r"F:\workbuddy空间任务\图片查看器\PView\docs\verify_out\verify_exe.png"

proc = subprocess.Popen([EXE, os.path.join(TMP, "photo1.jpg")])
time.sleep(9)

found = []


def enum_cb(hwnd, _):
    if not win32gui.IsWindowVisible(hwnd):
        return
    title = win32gui.GetWindowText(hwnd)
    if "P view" in title:
        found.append((hwnd, title))


win32gui.EnumWindows(enum_cb, None)
print("windows found:", found)
if not found:
    print("FAIL: no window")
    proc.terminate()
    sys.exit(1)

hwnd, title = found[0]
try:
    win32gui.SetForegroundWindow(hwnd)
except Exception:
    pass   # foreground lock can refuse; PrintWindow works regardless
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

bmpinfo = win32gui.GetObject(hbmp)
buf = ctypes.create_string_buffer(w * h * 4)


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
gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)
img = Image.frombuffer("RGBA", (w, h), buf.raw, "raw", "BGRA", 0, 1)
img.convert("RGB").save(OUT)
print("saved:", OUT, "PrintWindow:", res)

gdi32.DeleteObject(hbmp)
gdi32.DeleteDC(hdc_mem)
user32.ReleaseDC(hwnd, hdc_window)
proc.terminate()
print("terminated")
