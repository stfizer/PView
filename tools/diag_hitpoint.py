"""What window/control actually sits at the caption button point?"""
import ctypes
import os
import subprocess
import sys
import time

import win32api
import win32con
import win32gui

TMP = os.path.join(os.environ["TEMP"], "pview_clicktest")
EXE = r"F:\workbuddy空间任务\图片查看器\PView\dist\Pview\Pview.exe"

user32 = ctypes.windll.user32

proc = subprocess.Popen([EXE, os.path.join(TMP, "pic1.jpg")])
time.sleep(9)

found = []


def enum_cb(hwnd, _):
    if win32gui.IsWindowVisible(hwnd) and "P view" in win32gui.GetWindowText(hwnd):
        found.append(hwnd)


win32gui.EnumWindows(enum_cb, None)
print("Pview windows:", [(h, win32gui.GetWindowText(h),
                          win32gui.GetWindowRect(h)) for h in found])
hwnd = found[0]
try:
    win32gui.SetForegroundWindow(hwnd)
except Exception:
    pass
time.sleep(1.0)

rect = win32gui.GetWindowRect(hwnd)
print("GetWindowRect:", rect)
l, t, r, b = rect
y = t + 23
for label, x in (("info", r - 208), ("more", r - 168), ("max", r - 92 - 23),
                 ("close", r - 23)):
    win32api.SetCursorPos((int(x), y))
    time.sleep(0.15)
    pt = win32api.GetCursorPos()
    h = win32gui.WindowFromPoint(pt)
    cls = win32gui.GetClassName(h) if h else "?"
    txt = win32gui.GetWindowText(h) if h else "?"
    root = user32.GetAncestor(h, 2)  # GA_ROOT
    root_txt = win32gui.GetWindowText(root) if root else "?"
    print(f"{label} click-point ({pt[0]},{pt[1]}) -> hwnd={h} class={cls} "
          f"text='{txt[:30]}' root='{root_txt[:30]}' same_root={root == hwnd}")

# real click on (i) -> does the panel appear?
win32api.SetCursorPos((r - 208, y))
time.sleep(0.3)
win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
time.sleep(0.08)
win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
time.sleep(1.0)
try:
    from PIL import ImageGrab
    img = ImageGrab.grab()
    # sample where the panel should be (right edge inside window)
    px = img.getpixel((r - 160, t + 200))
    print("pixel at panel area (screen):", px)
except Exception as e:
    print("grab err", e)
proc.terminate()
