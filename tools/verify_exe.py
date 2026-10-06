"""Launch Pview.exe, find its window, screenshot it via PrintWindow, kill it."""
import ctypes
import os
import subprocess
import sys
import time

import win32con
import win32gui
from PIL import Image

EXE = r"F:\workbuddy空间任务\图片查看器\dist\Pview\Pview.exe"
OUT = r"F:\workbuddy空间任务\图片查看器\verify_shot.png"

proc = subprocess.Popen([EXE])
time.sleep(8)

found = []


def enum_cb(hwnd, _):
    if not win32gui.IsWindowVisible(hwnd):
        return
    title = win32gui.GetWindowText(hwnd)
    if "P view" in title or title == "Pview":
        found.append((hwnd, title))


win32gui.EnumWindows(enum_cb, None)
print("windows found:", found)

if not found:
    print("FAIL: no window")
    sys.exit(1)

hwnd, title = found[0]
win32gui.SetForegroundWindow(hwnd)
time.sleep(1.0)

# GetWindowRect
rect = win32gui.GetWindowRect(hwnd)
w, h = rect[2] - rect[0], rect[3] - rect[1]
print("rect:", rect, "size:", w, "x", h)

PW_RENDERFULLCONTENT = 2
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

hdc_window = user32.GetWindowDC(hwnd)
hdc_mem = gdi32.CreateCompatibleDC(hdc_window)
hbmp = gdi32.CreateCompatibleBitmap(hdc_window, w, h)
gdi32.SelectObject(hdc_mem, hbmp)
# PrintWindow with RENDERFULLCONTENT
res = user32.PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)
print("PrintWindow returned:", res)

bmpinfo = win32gui.GetObject(hbmp)
data = gdi32.GetDIBits  # not used; use PIL via buffer below
# Read pixels via GetDIBits
class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32),
                ("biClrUsed", ctypes.c_uint32), ("biClrImportant", ctypes.c_uint32)]

class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 3)]

bmi = BITMAPINFO()
bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
bmi.bmiHeader.biWidth = w
bmi.bmiHeader.biHeight = -h
bmi.bmiHeader.biPlanes = 1
bmi.bmiHeader.biBitCount = 32
bmi.bmiHeader.biCompression = 0
buf = ctypes.create_string_buffer(w * h * 4)
gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)
img = Image.frombuffer("RGBA", (w, h), buf.raw, "raw", "BGRA", 0, 1)
img.convert("RGB").save(OUT)
print("saved:", OUT)

gdi32.DeleteObject(hbmp)
gdi32.DeleteDC(hdc_mem)
user32.ReleaseDC(hwnd, hdc_window)

# inspect: is it all black?
small = img.convert("L").resize((16, 16))
px = list(small.getdata())
avg = sum(px) / len(px)
print("avg luminance:", round(avg, 1))

proc.terminate()
print("terminated")
