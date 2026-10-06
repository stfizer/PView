"""Verify the packaged exe responds to REAL mouse clicks on (i) and (...) buttons.

Uses SetCursorPos + mouse_event (true OS-level input) so the full native
event path is exercised (WM_NCHITTEST routing included).
"""
import ctypes
import os
import subprocess
import sys
import time

import win32api
import win32con
import win32gui
from PIL import Image, ImageDraw

TMP = os.path.join(os.environ["TEMP"], "pview_clicktest")
os.makedirs(TMP, exist_ok=True)
img = Image.new("RGB", (1500, 1000), (90, 110, 150))
d = ImageDraw.Draw(img)
d.text((60, 60), "Click Test", fill=(255, 255, 255))
img.save(os.path.join(TMP, "pic1.jpg"), "JPEG", quality=88)

EXE = r"F:\workbuddy空间任务\图片查看器\PView\dist\Pview\Pview.exe"
OUT = r"F:\workbuddy空间任务\图片查看器\PView\docs\verify_out"
os.makedirs(OUT, exist_ok=True)

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


def grab(hwnd, path):
    rect = win32gui.GetWindowRect(hwnd)
    w, h = rect[2] - rect[0], rect[3] - rect[1]
    hdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(hwnd, mdc, 2)
    buf = ctypes.create_string_buffer(w * h * 4)

    class BMIH(ctypes.Structure):
        _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                    ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                    ("biBitCount", ctypes.c_uint16),
                    ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32),
                    ("biXPelsPerMeter", ctypes.c_int32),
                    ("biYPelsPerMeter", ctypes.c_int32),
                    ("biClrUsed", ctypes.c_uint32),
                    ("biClrImportant", ctypes.c_uint32)]

    class BMI(ctypes.Structure):
        _fields_ = [("bmiHeader", BMIH), ("bmiColors", ctypes.c_uint32 * 3)]

    bmi = BMI()
    bmi.bmiHeader.biSize = ctypes.sizeof(BMIH)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    Image.frombuffer("RGBA", (w, h), buf.raw, "raw", "BGRA", 0, 1) \
        .convert("RGB").save(path)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, hdc)


def real_click(x, y):
    win32api.SetCursorPos((int(x), int(y)))
    time.sleep(0.25)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.08)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.6)


proc = subprocess.Popen([EXE, os.path.join(TMP, "pic1.jpg")])
time.sleep(9)

found = []


def enum_cb(hwnd, _):
    if win32gui.IsWindowVisible(hwnd) and "P view" in win32gui.GetWindowText(hwnd):
        found.append(hwnd)


win32gui.EnumWindows(enum_cb, None)
if not found:
    print("FAIL: no window")
    proc.terminate()
    sys.exit(1)
hwnd = found[0]


def force_foreground(hwnd):
    """Bring the window up reliably: ALT-tap releases the foreground lock
    (SetForegroundWindow alone silently fails when the caller is background)."""
    for attempt in range(3):
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        time.sleep(0.3)
        if win32gui.GetForegroundWindow() == hwnd:
            return True
        try:
            import win32com.client  # noqa
            shell = win32com.client.Dispatch("WScript.Shell")
            shell.SendKeys("%")
            time.sleep(0.2)
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        time.sleep(0.3)
    return win32gui.GetForegroundWindow() == hwnd


if not force_foreground(hwnd):
    print("WARN: could not bring Pview to foreground; clicks may land elsewhere")
time.sleep(0.8)

# real visible bounds (GetWindowRect includes invisible resize borders)
class RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                ("r", ctypes.c_long), ("b", ctypes.c_long)]


dwmapi = ctypes.windll.dwmapi
fx = RECT()
dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(fx), ctypes.sizeof(fx))
left, top, right = fx.l, fx.t, fx.r
W = right - left
y = top + 23
print(f"visible bounds=({left},{top},{right}) W={W}")

grab(hwnd, os.path.join(OUT, "click_0_initial.png"))


def find_button_centers(png_path):
    """Scan the caption band for the 5 bright button icons (right to left).

    Returns (info_x, more_x) in SCREEN coordinates, or (None, None).
    Immune to layout/spacing changes (hardcoded offsets went stale once).
    """
    im = Image.open(png_path).convert("L")
    w, h = im.size
    px = im.load()
    cols = set()
    for yy in range(14, 46, 2):          # caption band rows (PNG coords)
        for x in range(w - 1, w - 500, -1):
            if px[x, yy] > 120:
                cols.add(x)
    xs = sorted(cols, reverse=True)      # right to left
    groups = []                          # [leftmost, rightmost] per icon
    for x in xs:
        if groups and groups[-1][0] - x <= 22:
            groups[-1][0] = x
        else:
            groups.append([x, x])
    centers = [(g[0] + g[1]) / 2 for g in groups]
    print("button icon centers (png):", centers)
    # caption icons right-to-left: close, max, min, more, info — min may be
    # missed by the scan, but more/info are always the two LEFTMOST groups
    # and max is always the 2nd group from the right (close is the rightmost)
    if len(centers) >= 2:
        gx = win32gui.GetWindowRect(hwnd)[0]   # PNG x=0 is this + 8px border
        return (int(gx + centers[-1]), int(gx + centers[-2]),
                int(gx + centers[1]))
    return None, None, None


info_x, more_x, max_x = find_button_centers(
    os.path.join(OUT, "click_0_initial.png"))
if info_x is None:
    print("FAIL: could not locate caption buttons")
    proc.terminate()
    sys.exit(1)
print(f"clicking info=({info_x},{y}) more=({more_x},{y}) max=({max_x},{y})")

# --- maximize button: glyph should be single frame now, stacked when max ---
# NOTE: window geometry changes on maximize/restore, so re-derive DWM bounds
# AND re-scan the caption icons after every state change before clicking.
def rescan(png_name):
    global y, info_x, more_x, max_x
    grab(hwnd, os.path.join(OUT, png_name))
    b = RECT()
    dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(b), ctypes.sizeof(b))
    y = b.t + 23
    info_x, more_x, max_x = find_button_centers(os.path.join(OUT, png_name))
    if info_x is None:
        print(f"FAIL: rescan after {png_name} failed")
        proc.terminate()
        sys.exit(1)
    print(f"  bounds=({b.l},{b.t},{b.r}) y={y} max=({max_x},{y})")


real_click(max_x, y)
time.sleep(1.2)
rescan("click_3_maximized.png")
real_click(max_x, y)   # restore back
time.sleep(1.0)
rescan("click_4_restored.png")
print(f"restored: clicking info=({info_x},{y}) more=({more_x},{y})")

# pre-activate: first click on empty client area only activates the window
real_click(left + W // 2, top + 400)
time.sleep(0.4)

# --- click (i) ---
real_click(info_x, y)
grab(hwnd, os.path.join(OUT, "click_1_info.png"))

# close it again (click (i) again)
real_click(info_x, y)
time.sleep(0.5)

# --- click (...) ---
real_click(more_x, y)
time.sleep(1.0)
grab(hwnd, os.path.join(OUT, "click_2_more.png"))
# also full screen for the modal dialog
try:
    from PIL import ImageGrab
    ImageGrab.grab().save(os.path.join(OUT, "click_2_more_screen.png"))
except Exception:
    pass

# send ESC to close dialog if open
win32api.SetCursorPos((left + W // 2, top + 300))
import win32com.client  # noqa (optional)
try:
    shell = win32com.client.Dispatch("WScript.Shell")
    shell.SendKeys("{ESC}")
except Exception:
    pass
time.sleep(0.6)

proc.terminate()
print("done; screenshots in", OUT)
