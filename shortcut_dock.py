"""
Shortcut Dock (Windows)
=======================
An auto-hide panel that slides out from any screen edge and holds desktop shortcuts,
plus system icons such as the Recycle Bin.

Start it        : just double-click this file (needs Python installed). The first start installs
                  what it needs automatically (internet needed once) and then runs without a console.
Build one .exe  : Settings > Behavior > "Create ShortcutDock.exe", or:  python shortcut_dock.py --build
                  (this single file does everything: installs the build tools, draws its own icon and
                   writes ShortcutDock.exe next to itself - nothing else is needed)
Flags           : --console keeps the console window open (shows errors); --build makes the .exe

Mouse / keys
  Drag a desktop icon to the screen edge ...... moves it into the dock
  Drag empty space in the dock ................ selection box (select several icons)
  Ctrl+click .................................. add / remove one icon from the selection
  Drag selected icons ......................... rearrange (the whole selection moves)
  Drag selected icons out of the dock ......... send them back to the desktop
  Ctrl + mouse wheel .......................... icon size
  Drag the BLUE line .......................... move the dock along its edge (drag to another edge to switch)
  Shift + drag the BLUE line .................. panel depth
  Drag the GREY bar ........................... panel length
  Ctrl+Alt+D .................................. emergency: show + pin / unpin the dock
  Ctrl+Alt+S .................................. emergency: open the settings
  Tray icon ................................... show/hide, settings, quit
"""
import os
import re
import sys
import json
import time
import queue
import ctypes
import struct
import shutil
import winreg
import configparser
import tkinter as tk
from ctypes import wintypes


# ======================================================================================
# 0. Self-contained helpers and build mode  (python shortcut_dock.py --build)
# ======================================================================================
def valid_hex(s):
    """True for colours like '#4a78d0'."""
    return bool(re.fullmatch(r"#[0-9a-fA-F]{6}", s or ""))


def make_app_icon(size=64, accent="#4a78d0"):
    """The program's own icon (tray, settings window, .exe): a tile with four app squares."""
    from PIL import Image, ImageDraw
    s = size * 4                                     # draw big, then shrink = smooth edges
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((s * .04, s * .04, s * .96, s * .96), radius=s * .22, fill=accent)
    cell, gap = s * .26, s * .08
    start = (s - (2 * cell + gap)) / 2
    for r in range(2):
        for c in range(2):
            x, y = start + c * (cell + gap), start + r * (cell + gap)
            d.rounded_rectangle((x, y, x + cell, y + cell), radius=s * .06,
                                fill=(255, 255, 255, 215 if (r, c) == (0, 1) else 255))
    return img.resize((size, size), getattr(Image, "Resampling", Image).LANCZOS)


def _pythons():
    """(python.exe with console, pythonw.exe without) next to the running interpreter."""
    d = os.path.dirname(sys.executable)
    con, win = os.path.join(d, "python.exe"), os.path.join(d, "pythonw.exe")
    return (con if os.path.exists(con) else sys.executable,
            win if os.path.exists(win) else sys.executable)


def build_exe():
    """Turn this one .py file into ONE .exe (no console window, own icon) next to it."""
    import subprocess
    import tempfile
    here = os.path.dirname(os.path.abspath(__file__))
    work = tempfile.mkdtemp(prefix="dockbuild_")
    try:
        print("1/3  Installing build tools (one time, needs internet)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller",
                               "tkinterdnd2", "pywin32", "pillow", "pystray"])
        print("2/3  Drawing the program icon...")
        ico = os.path.join(work, "dock.ico")
        make_app_icon(256).save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                                            (64, 64), (128, 128), (256, 256)])
        print("3/3  Building ShortcutDock.exe (takes a few minutes)...")
        subprocess.check_call([
            sys.executable, "-m", "PyInstaller", "--onefile", "--noconsole", "--clean",
            "--noconfirm", "--name", "ShortcutDock", "--icon", ico,
            "--collect-all", "tkinterdnd2",          # bundles the native drag-and-drop files
            "--hidden-import", "pystray._win32",     # tray icon backend
            "--distpath", here, "--workpath", os.path.join(work, "build"),
            "--specpath", work, os.path.abspath(__file__)])
        print("\nDone!  Your program is the single file:", os.path.join(here, "ShortcutDock.exe"))
        print("Quit the running dock (tray icon > Quit) before starting the new .exe.")
    except Exception as e:
        print("\nBuild failed:", e)
    finally:
        shutil.rmtree(work, ignore_errors=True)       # leave no build clutter behind
    if "--wait" in sys.argv:                          # started from the settings button
        try:
            input("\nPress Enter to close this window...")
        except Exception:
            pass


def bootstrap():
    """Makes the plain .py double-click friendly (the built .exe skips this):
      1. installs any missing package automatically (internet needed once);
      2. restarts itself without the black console window (use --console to keep it)."""
    if getattr(sys, "frozen", False):
        return
    import subprocess
    console, windowless = _pythons()
    missing = []
    for mod, pkg in (("tkinterdnd2", "tkinterdnd2"), ("PIL", "pillow"),
                     ("win32api", "pywin32"), ("pystray", "pystray")):
        try:
            __import__(mod)
        except Exception:
            missing.append(pkg)
    if missing:
        print("First start: installing", ", ".join(missing), "- this can take a minute...")
        for pkg in missing:                           # one by one: the optional tray package may fail
            try:
                subprocess.check_call([console, "-m", "pip", "install", pkg])
            except Exception as e:
                print("Could not install", pkg, "-", e)
        # check the essentials in a fresh process (new packages are not visible to this one)
        if subprocess.call([console, "-c", "import tkinterdnd2, PIL, win32api"]) != 0:
            print("\nThe required packages could not be installed. Check your internet connection,")
            print("then run again.  (Manual way:  pip install tkinterdnd2 pywin32 pillow pystray)")
            try:
                input("\nPress Enter to close...")
            except Exception:
                pass
            sys.exit(1)
    target = console if "--console" in sys.argv else windowless
    if missing or os.path.basename(sys.executable).lower() != os.path.basename(target).lower():
        subprocess.Popen([target, os.path.abspath(__file__), *sys.argv[1:]], close_fds=True,
                         creationflags=0x00000008 | 0x00000200)     # detached: console can close
        sys.exit(0)


if "--build" in sys.argv:
    build_exe()
    sys.exit(0)
bootstrap()

from tkinterdnd2 import TkinterDnD, DND_FILES
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageTk
import win32api, win32con, win32gui, win32ui, win32event, winerror
from win32com.shell import shell, shellcon

# ======================================================================================
# 1. Start-up: DPI awareness, single instance
# ======================================================================================
# Must happen before Tk creates its first window, otherwise Windows scales (blurs) us
# and pixel coordinates no longer match the real screen.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# A named mutex stops a second copy from starting (two docks would fight each other).
_mutex = win32event.CreateMutex(None, False, "ShortcutDock_SingleInstance")
if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
    sys.exit(0)

# ======================================================================================
# 2. Constants, colour themes, system icons
# ======================================================================================
STRIP = 6              # px of the blue line that stays visible while the dock is hidden
DRAG_TRIGGER = 24      # wider "open" zone at the edge while a mouse button is held (file drag)
CLOSE_DELAY = 0.4      # seconds the mouse may be away before the dock hides
SNAP = 60              # px from a screen edge where a dragged dock jumps to that edge
SPEED_MIN = 14         # minimum slide speed (px per frame)
FRAME_MS = 10          # loop period while animating / interacting
IDLE_MS = 30           # loop period while hidden and nothing happens (saves CPU)
ACCENT, ACCENT_DARK = "#4a78d0", "#3b63ad"

# Windows whose focus counts as "the desktop is in front" (used by "Desktop only" mode)
DESKTOP_CLASSES = {"Progman", "WorkerW", "TkTopLevel", "#32768"}

THEMES = {
    "dark": dict(bg="#1e1e1e", fg="#ffffff", sel="#3a4f7a", sel_line="#6d8bd1",
                 btn="#9aa0a6", btn_active="#333333", grip="#555555",
                 dlg_bg="#17181a", card="#232428", text="#e8eaed", muted="#9aa0a6",
                 track="#3a3c42"),
    "light": dict(bg="#f3f3f3", fg="#1b1b1b", sel="#c9dafb", sel_line="#4a78d0",
                  btn="#5f6368", btn_active="#dcdcdc", grip="#c3c3c3",
                  dlg_bg="#eceef2", card="#ffffff", text="#1f2328", muted="#6b7280",
                  track="#d8dbe2"),
}

# Desktop "system" icons that are not files. Each can live in the dock; while it does, the
# real desktop icon is hidden (HideDesktopIcons registry flag) and it returns afterwards.
VIRTUAL = {
    "recycle": dict(title="Recycle Bin", clsid="{645FF040-5081-101B-9F08-00AA002F954E}",
                    emoji="🗑", open="shell:RecycleBinFolder",
                    desc="Open the Recycle Bin straight from the dock."),
    "thispc": dict(title="This PC", clsid="{20D04FE0-3AEA-1069-A2D8-08002B30309D}",
                   emoji="💻", open="shell:MyComputerFolder",
                   desc="Open This PC (your drives)."),
    "spotlight": dict(title="Learn about this picture", clsid="{2cc5ca98-6485-489a-920e-b3e88a6ccce3}",
                      emoji="🖼", open="shell:::{2cc5ca98-6485-489a-920e-b3e88a6ccce3}",
                      desc="The Windows Spotlight icon (only exists if Spotlight is on)."),
}
HIDE_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\HideDesktopIcons\NewStartPanel"

# ======================================================================================
# 3. Paths, logging
# ======================================================================================
DESKTOP = shell.SHGetFolderPath(0, shellcon.CSIDL_DESKTOPDIRECTORY, 0, 0)
try:
    COMMON_DESKTOP = shell.SHGetFolderPath(0, shellcon.CSIDL_COMMON_DESKTOPDIRECTORY, 0, 0)
except Exception:
    COMMON_DESKTOP = DESKTOP

# Everything the app stores lives in one folder: the shortcuts themselves plus a few
# small hidden json files (layout, settings, original desktop positions).
STORE = os.path.join(os.path.expanduser("~"), "ShortcutDock")
os.makedirs(STORE, exist_ok=True)
LAYOUT_FILE = os.path.join(STORE, ".dock_layout.json")
SETTINGS_FILE = os.path.join(STORE, ".dock_settings.json")
ORIGINS_FILE = os.path.join(STORE, ".dock_origins.json")
LOG_FILE = os.path.join(STORE, "dock.log")
IGNORE = {".dock_layout.json", ".dock_settings.json", ".dock_origins.json",
          "dock.log", "desktop.ini"}


def log(*args):
    """Append to dock.log (a windowed .exe has no console, so errors go here)."""
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 200_000:
            os.remove(LOG_FILE)                       # keep the log small
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(map(str, args)) + "\n")
    except Exception:
        pass


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        log("write failed:", path, e)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ======================================================================================
# 4. User settings (saved to disk)
# ======================================================================================
S = {
    "edge": "left",            # left / right / top / bottom
    "offset": 0.5,             # position along that edge: 0 = start, 0.5 = centred, 1 = end
    "w": 0.5,                  # panel width  as a fraction of the screen width
    "h": 0.5,                  # panel height as a fraction of the screen height
    "opacity": 0.5,            # 1.0 = solid
    "icon": 1.0,               # icon size multiplier
    "theme": "dark",           # dark / light
    "desktop_only": False,     # only show while the desktop is in front
    "restore_pos": True,       # sent-back icons return to their original desktop spot
    "return_on_exit": True,    # closing the dock puts every icon back on the desktop
    "line_color": "#4a78d0",   # colour of the edge line (the sliver that stays visible)
    "line_opacity": 0.8,       # how visible that line is while the dock is hidden
}
DEFAULTS = dict(S)
_loaded = read_json(SETTINGS_FILE, {})
if "offset" not in _loaded and "align" in _loaded:    # settings written by an older version
    _loaded["offset"] = {"start": 0.0, "center": 0.5, "end": 1.0}.get(_loaded["align"], 0.5)
S.update({k: v for k, v in _loaded.items() if k in S})
if S["theme"] not in THEMES:
    S["theme"] = "dark"
if not valid_hex(str(S["line_color"])):
    S["line_color"] = DEFAULTS["line_color"]
try:
    S["line_opacity"] = clamp(float(S["line_opacity"]), 0.0, 1.0)    # 0 = invisible line is allowed
except (TypeError, ValueError):
    S["line_opacity"] = DEFAULTS["line_opacity"]
try:                                                                  # the dock itself must stay visible
    S["opacity"] = clamp(float(S["opacity"]), 0.2, 1.0)
except (TypeError, ValueError):
    S["opacity"] = DEFAULTS["opacity"]


def save_settings():
    write_json(SETTINGS_FILE, S)


# Current theme colours as module globals (refreshed by load_theme_globals)
BG = FG = SEL = SEL_LINE = BTN_FG = GRIP_COLOR = "#000000"


def load_theme_globals():
    global BG, FG, SEL, SEL_LINE, BTN_FG, GRIP_COLOR
    t = THEMES[S["theme"]]
    BG, FG, SEL, SEL_LINE = t["bg"], t["fg"], t["sel"], t["sel_line"]
    BTN_FG, GRIP_COLOR = t["btn"], t["grip"]


load_theme_globals()

# ======================================================================================
# 5. Main window and geometry
# ======================================================================================
root = TkinterDnD.Tk()
root.overrideredirect(True)            # no title bar / border: looks like part of the desktop
root.attributes("-topmost", True)
root.configure(bg=BG)

SW, SH = win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1)    # primary screen, pixels
scale = root.winfo_fpixels("1i") / 96                                  # display scaling factor
HEADER = int(28 * scale)
GRIP = max(4, int(5 * scale))
PAD = 4
ICON = win32api.GetSystemMetrics(win32con.SM_CXICON)                   # native icon size
RESAMPLE = getattr(Image, "Resampling", Image).LANCZOS


def dp(n):
    """Scale a design pixel size to the current display scaling."""
    return max(1, int(n * scale))


# Layout numbers; (re)computed from the settings by compute_geometry()
WIDTH = HEIGHT = CANVAS_W = CANVAS_H = COLS = ROWS = 1
AXIS, VIS, HID, FIX = "x", 0, 0, 0     # slide axis, visible/hidden coordinate, fixed coordinate
ICON_PX, TILE_W, TILE_H, IW, IH, FONT_SZ = ICON, 96, 96, 96, 96, 8

# Everything that changes at run time lives in a few small dicts.
state = {"pos": 0, "open": False, "menu": False, "dialog": False, "drag": False,
         "moving": False, "pinned": False, "leave": None, "shown": True,
         "hot": False, "stale": None, "raised": 0.0, "picking": False, "hot_s": False}
drag = {"id": None, "moved": False, "sx": 0, "sy": 0, "lx": 0, "ly": 0, "orig": {}}
band = {"on": False, "id": None, "x0": 0, "y0": 0, "base": set()}   # selection rectangle
mv = {"on": False, "mode": "move", "off": 0, "kind": "strip"}         # moving/resizing the panel
items = {}                 # id -> dict(name, path, virtual, col, row, pil, img, rect, tag)
sel = set()                # ids of the selected icons
next_id = [0]
dialog_win = [None]        # the settings window, while open
dialog_sync = [None]       # callback that refreshes the settings controls
last_icon = [S["icon"]]    # remember what changed so we only redo work when needed
last_cols = [0]
applied_theme = [S["theme"]]
store_mtime = [None]
ui_queue = queue.Queue()   # commands from the tray icon thread (handled on the Tk thread)
quitting = [False]
tray = [None]


def compute_geometry():
    """Derive every size and position from the settings."""
    global WIDTH, HEIGHT, CANVAS_W, CANVAS_H, COLS, ROWS, AXIS, VIS, HID, FIX
    global ICON_PX, TILE_W, TILE_H, IW, IH, FONT_SZ
    ICON_PX = max(16, int(ICON * S["icon"]))
    TILE_W = TILE_H = ICON_PX + int(64 * scale)           # icon + room for the label
    IW, IH = TILE_W - 4, TILE_H - 4
    FONT_SZ = int(clamp(round(8 + (S["icon"] - 1) * 3), 7, 12))

    WIDTH = min(SW, max(TILE_W * 2, int(SW * S["w"])))
    HEIGHT = min(SH, max(TILE_H * 2 + HEADER, int(SH * S["h"])))
    CANVAS_W, CANVAS_H = WIDTH, HEIGHT - HEADER
    COLS = max(1, CANVAS_W // TILE_W)
    ROWS = max(1, CANVAS_H // TILE_H)

    # The panel slides along one axis; on the other axis it sits at FIX.
    e = S["edge"]
    span = (SH - HEIGHT) if e in ("left", "right") else (SW - WIDTH)
    AXIS = "x" if e in ("left", "right") else "y"
    FIX = int(span * clamp(S["offset"], 0.0, 1.0))
    if e == "left":
        VIS, HID = 0, -WIDTH + STRIP                       # hidden = off-screen except the strip
    elif e == "right":
        VIS, HID = SW - WIDTH, SW - STRIP
    elif e == "top":
        VIS, HID = 0, -HEIGHT + STRIP
    else:
        VIS, HID = SH - HEIGHT, SH - STRIP


def pos_xy():
    return (state["pos"], FIX) if AXIS == "x" else (FIX, state["pos"])


alpha_cache = [None]


def update_alpha(force=False):
    """Window opacity: the line's opacity while hidden, the dock's when open, fading between.

    (Tk can only make a whole window transparent, so the line gets its own opacity by
    changing the window's opacity as the panel slides in and out.)
    """
    span = VIS - HID
    prog = clamp((state["pos"] - HID) / span, 0.0, 1.0) if span else 1.0
    dock = max(S["opacity"], 0.15)            # safety floor: an open dock is never invisible
    a = round(S["line_opacity"] + (dock - S["line_opacity"]) * prog, 3)
    if force or a != alpha_cache[0]:
        alpha_cache[0] = a
        root.attributes("-alpha", a)


def apply_geometry():
    x, y = pos_xy()
    root.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")
    update_alpha()


def inside_window(px, py):
    x, y = pos_xy()
    return x <= px < x + WIDTH and y <= py < y + HEIGHT


def at_edge(px, py, zone):
    """Is the pointer touching the dock's screen edge (within the dock's length)?"""
    e = S["edge"]
    if AXIS == "x":
        if not (FIX <= py <= FIX + HEIGHT):
            return False
        return px <= zone if e == "left" else px >= SW - 1 - zone
    if not (FIX <= px <= FIX + WIDTH):
        return False
    return py <= zone if e == "top" else py >= SH - 1 - zone


# ======================================================================================
# 6. Small Windows helpers
# ======================================================================================
def key_down(vk):
    return bool(win32api.GetAsyncKeyState(vk) & 0x8000)


def on_desktop():
    """True when nothing but the desktop (or this app) has the keyboard focus."""
    try:
        h = win32gui.GetForegroundWindow()
        return (not h) or win32gui.GetClassName(h) in DESKTOP_CLASSES
    except Exception:
        return True


def raise_window(win):
    """Put a Tk window at the top of the always-on-top stack without stealing focus."""
    try:
        hwnd = win32gui.GetParent(win.winfo_id()) or win.winfo_id()   # Tk's real top-level handle
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
    except Exception:
        pass


def keep_on_top():
    """Windows can bury 'always on top' windows; re-assert, then lift settings above the dock."""
    if state["picking"]:                      # a colour chooser is open: do not cover it
        return
    raise_window(root)
    if dialog_win[0] is not None:
        raise_window(dialog_win[0])


def pointer_in_dialog(px, py):
    d = dialog_win[0]
    if d is None:
        return False
    try:
        x, y, w, h = d.winfo_rootx(), d.winfo_rooty(), d.winfo_width(), d.winfo_height()
        return x - 8 <= px < x + w + 8 and y - dp(48) <= py < y + h + 8   # includes title bar
    except tk.TclError:
        return False


# --- start with Windows (HKCU Run key, no admin needed) ---
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_command():
    if getattr(sys, "frozen", False):                         # running as the built .exe
        return f'"{sys.executable}"'
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")   # no console window
    return f'"{pyw if os.path.exists(pyw) else sys.executable}" "{os.path.abspath(__file__)}"'


def autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, "ShortcutDock")
            return True
    except OSError:
        return False


def set_autostart(on):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, "ShortcutDock", 0, winreg.REG_SZ, autostart_command())
            else:
                try:
                    winreg.DeleteValue(k, "ShortcutDock")
                except FileNotFoundError:
                    pass
    except OSError as e:
        log("autostart failed:", e)
    return autostart_enabled()


# ======================================================================================
# 7. Talking to Explorer's desktop list view (icon positions, refresh)
# ======================================================================================
# The desktop is a "SysListView32" owned by explorer.exe. Messages that pass pointers
# (read position / read name) need memory INSIDE explorer.exe, hence RemoteMemory.
_u32, _k32 = ctypes.windll.user32, ctypes.windll.kernel32
_u32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                     wintypes.LPARAM, wintypes.UINT, wintypes.UINT,
                                     ctypes.POINTER(ctypes.c_size_t)]
_u32.SendMessageTimeoutW.restype = ctypes.c_ssize_t
_u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_u32.GetWindowThreadProcessId.restype = wintypes.DWORD
_k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.VirtualAllocEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t,
                                wintypes.DWORD, wintypes.DWORD]
_k32.VirtualAllocEx.restype = ctypes.c_void_p
_k32.VirtualFreeEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD]
_k32.VirtualFreeEx.restype = wintypes.BOOL
_k32.WriteProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
_k32.WriteProcessMemory.restype = wintypes.BOOL
_k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                   ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
_k32.ReadProcessMemory.restype = wintypes.BOOL
_k32.CloseHandle.argtypes = [wintypes.HANDLE]

LVM_GETITEMCOUNT, LVM_SETITEMPOSITION = 0x1004, 0x100F
LVM_GETITEMPOSITION, LVM_GETITEMTEXTW = 0x1010, 0x1073


class LVITEMW(ctypes.Structure):
    """Windows LVITEMW structure (list view item), 64-bit layout handled by ctypes."""
    _fields_ = [("mask", wintypes.UINT), ("iItem", ctypes.c_int), ("iSubItem", ctypes.c_int),
                ("state", wintypes.UINT), ("stateMask", wintypes.UINT),
                ("pszText", ctypes.c_void_p), ("cchTextMax", ctypes.c_int),
                ("iImage", ctypes.c_int), ("lParam", ctypes.c_ssize_t),
                ("iIndent", ctypes.c_int), ("iGroupId", ctypes.c_int),
                ("cColumns", wintypes.UINT), ("puColumns", ctypes.c_void_p),
                ("piColFmt", ctypes.c_void_p), ("iGroup", ctypes.c_int)]


class RemoteMemory:
    """A scratch block of memory inside another process (explorer.exe)."""

    def __init__(self, hwnd, size):
        pid = wintypes.DWORD(0)
        _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        # access rights: VM_OPERATION | VM_READ | VM_WRITE
        self.h = _k32.OpenProcess(0x0008 | 0x0010 | 0x0020, False, pid.value)
        if not self.h:
            raise OSError("cannot open Explorer process")
        self.addr = _k32.VirtualAllocEx(self.h, None, size, 0x3000, 0x04)
        if not self.addr:
            _k32.CloseHandle(self.h)
            raise OSError("cannot allocate memory in Explorer")

    def write(self, off, data):
        buf = ctypes.create_string_buffer(data, len(data))
        _k32.WriteProcessMemory(self.h, self.addr + off, buf, len(data), ctypes.byref(ctypes.c_size_t(0)))

    def read(self, off, size):
        buf = ctypes.create_string_buffer(size)
        _k32.ReadProcessMemory(self.h, self.addr + off, buf, size, ctypes.byref(ctypes.c_size_t(0)))
        return buf.raw

    def close(self):
        try:
            _k32.VirtualFreeEx(self.h, self.addr, 0, 0x8000)
        finally:
            _k32.CloseHandle(self.h)


def _lv_send(lv, msg, wparam, lparam):
    """SendMessage with a 400 ms timeout, so a busy Explorer can never freeze the dock."""
    res = ctypes.c_size_t(0)
    ok = _u32.SendMessageTimeoutW(lv, msg, wparam, lparam, 0x2, 400, ctypes.byref(res))
    return res.value if ok else None


def _desktop_listview():
    """Find the window that draws the desktop icons (its location depends on Windows version)."""
    progman = win32gui.FindWindow("Progman", None)
    defview = win32gui.FindWindowEx(progman, 0, "SHELLDLL_DefView", None) if progman else 0
    if not defview:                       # when a wallpaper slideshow is active it lives under WorkerW
        found = []

        def cb(h, _):
            if win32gui.GetClassName(h) == "WorkerW":
                d = win32gui.FindWindowEx(h, 0, "SHELLDLL_DefView", None)
                if d:
                    found.append(d)
            return True
        win32gui.EnumWindows(cb, None)
        defview = found[0] if found else 0
    return win32gui.FindWindowEx(defview, 0, "SysListView32", None) if defview else 0


def _find_index(lv, rem, name):
    """Index of the desktop icon with this name (shortcuts are shown without '.lnk')."""
    count = _lv_send(lv, LVM_GETITEMCOUNT, 0, 0)
    if not count:
        return None
    targets = {name.lower(), os.path.splitext(name)[0].lower()}
    size = ctypes.sizeof(LVITEMW)
    for i in range(count):
        it = LVITEMW()
        it.mask, it.iItem = 0x1, i                      # LVIF_TEXT
        it.pszText, it.cchTextMax = rem.addr + size, 260   # text buffer right after the struct
        rem.write(0, bytes(it))
        if _lv_send(lv, LVM_GETITEMTEXTW, i, rem.addr) is None:
            continue
        text = rem.read(size, 520).decode("utf-16-le", "ignore").split("\x00")[0]
        if text.lower() in targets:
            return i
    return None


def desktop_get_pos(name):
    """Current [x, y] of a desktop icon, or None."""
    try:
        lv = _desktop_listview()
        if not lv:
            return None
        rem = RemoteMemory(lv, 4096)
        try:
            idx = _find_index(lv, rem, name)
            if idx is None:
                return None
            rem.write(0, bytes(8))                              # room for a POINT
            if _lv_send(lv, LVM_GETITEMPOSITION, idx, rem.addr) is None:
                return None
            return list(struct.unpack("ii", rem.read(0, 8)))
        finally:
            rem.close()
    except Exception as e:
        log("get desktop position failed:", e)
        return None


def desktop_set_pos(name, x, y):
    """Move a desktop icon. True = done, False = icon not listed yet, None = give up."""
    try:
        lv = _desktop_listview()
        if not lv:
            return None
        rem = RemoteMemory(lv, 4096)
        try:
            idx = _find_index(lv, rem, name)
            if idx is None:
                return False
            # position travels inside lParam (MAKELPARAM), no remote memory needed
            return _lv_send(lv, LVM_SETITEMPOSITION, idx, ((y & 0xFFFF) << 16) | (x & 0xFFFF)) is not None
        finally:
            rem.close()
    except Exception as e:
        log("set desktop position failed:", e)
        return None


def refresh_desktop():
    """Ask Explorer to redraw the desktop (needed after hiding / showing system icons)."""
    try:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)   # SHCNE_ASSOCCHANGED
        lv = _desktop_listview()
        if lv:                                                            # same as pressing F5
            win32gui.PostMessage(lv, win32con.WM_KEYDOWN, win32con.VK_F5, 0)
            win32gui.PostMessage(lv, win32con.WM_KEYUP, win32con.VK_F5, 0)
    except Exception as e:
        log("desktop refresh failed:", e)


# --- system icons (Recycle Bin, This PC, ...): show / hide on the real desktop ---
def desktop_icon_hidden(clsid):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, HIDE_KEY) as k:
            return winreg.QueryValueEx(k, clsid)[0] == 1
    except OSError:
        return False


def set_desktop_icon_hidden(clsid, hidden, refresh=True):
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, HIDE_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, clsid, 0, winreg.REG_DWORD, 1 if hidden else 0)
    except OSError as e:
        log("hide/show desktop icon failed:", e)
    if refresh:
        refresh_desktop()


origins = read_json(ORIGINS_FILE, {})     # dock file name -> [x, y] it had on the desktop


def schedule_restore(name, pos, tries=12):
    """Explorer needs a moment to list a returned icon, so retry for a few seconds."""
    def attempt(n):
        if desktop_set_pos(name, pos[0], pos[1]) is False and n > 0:
            root.after(300, lambda: attempt(n - 1))
    root.after(350, lambda: attempt(tries))


def restore_blocking(pending, timeout=4.0):
    """Same as schedule_restore, but waits (used while the program is closing)."""
    end = time.time() + timeout
    while pending and time.time() < end:
        pending = [(n, p) for n, p in pending if desktop_set_pos(n, p[0], p[1]) is False]
        if pending:
            time.sleep(0.25)


# ======================================================================================
# 8. Icons: shell icons, Steam / .url icons, system icons, app icon
# ======================================================================================
def hicon_to_image(hicon):
    """Windows icon handle -> RGBA image (and frees the handle).

    DrawIcon has no alpha output, so the icon is drawn twice (on black and on white);
    the difference between the two pictures gives the alpha channel.
    """
    try:
        screen_dc = win32gui.GetDC(0)
        shots = []
        try:
            dc = win32ui.CreateDCFromHandle(screen_dc)
            for rgb in ((0, 0, 0), (255, 255, 255)):
                bmp = win32ui.CreateBitmap()
                bmp.CreateCompatibleBitmap(dc, ICON, ICON)
                mem = dc.CreateCompatibleDC()
                mem.SelectObject(bmp)
                mem.FillSolidRect((0, 0, ICON, ICON), win32api.RGB(*rgb))
                mem.DrawIcon((0, 0), hicon)
                shots.append(Image.frombuffer("RGB", (ICON, ICON), bmp.GetBitmapBits(True),
                                              "raw", "BGRX", 0, 1))
                mem.DeleteDC()
                win32gui.DeleteObject(bmp.GetHandle())
            dc.DeleteDC()
        finally:
            win32gui.ReleaseDC(0, screen_dc)
        black, white = shots
        out = black.convert("RGBA")
        out.putalpha(ImageChops.invert(ImageChops.subtract(white, black).convert("L")))
        return out
    except Exception as e:
        log("icon conversion failed:", e)
        return None
    finally:
        win32gui.DestroyIcon(hicon)


def usable(img):
    """False for None or a completely transparent (blank) icon."""
    return img is not None and img.getchannel("A").getextrema()[1] > 0


def shell_icon(path):
    """The icon Explorer would show for a file."""
    try:
        _, info = shell.SHGetFileInfo(path, 0, shellcon.SHGFI_ICON | shellcon.SHGFI_LARGEICON)
        return hicon_to_image(info[0]) if info[0] else None
    except Exception as e:
        log("shell icon failed:", path, e)
        return None


def load_icon_file(path, index=0):
    """Icon from an .ico/.png/.jpg (full resolution) or from an .exe/.dll resource."""
    if not path or not os.path.isfile(path):
        return None
    if os.path.splitext(path)[1].lower() in (".ico", ".png", ".jpg", ".jpeg", ".bmp"):
        try:
            im = Image.open(path)
            ico = getattr(im, "ico", None)              # .ico files hold several sizes: take the biggest
            if ico is not None:
                im = ico.getimage(max(ico.sizes(), key=lambda s: s[0]))
            return im.convert("RGBA")
        except Exception as e:
            log("image icon failed:", path, e)
    try:
        large, small = win32gui.ExtractIconEx(path, index, 1)
        for h in small:
            win32gui.DestroyIcon(h)
        for h in large[1:]:
            win32gui.DestroyIcon(h)
        return hicon_to_image(large[0]) if large else None
    except Exception as e:
        log("extract icon failed:", path, e)
        return None


def steam_dir():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            return winreg.QueryValueEx(k, "SteamPath")[0].replace("/", "\\")
    except OSError:
        return None


def url_icon(path):
    """Icon of an Internet Shortcut (.url), e.g. Steam games.

    Steam writes the game's icon file into the shortcut ('IconFile='). We read that
    file directly instead of asking Explorer, which can return nothing for it. If the
    file is gone we try Steam's own icon cache, then the Steam logo.
    """
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    for enc in ("utf-8-sig", "mbcs"):
        try:
            with open(path, encoding=enc) as f:
                cp.read_file(f)
            break
        except Exception:
            continue
    d = dict(cp["InternetShortcut"]) if cp.has_section("InternetShortcut") else {}
    icon_file = os.path.expandvars((d.get("iconfile") or "").strip().strip('"'))
    try:
        index = int((d.get("iconindex") or "0").strip())
    except ValueError:
        index = 0
    img = load_icon_file(icon_file, index)
    if usable(img):
        return img
    url = (d.get("url") or "").lower()
    if url.startswith("steam://"):
        steam = steam_dir()
        if steam:
            m = re.search(r"rungameid/(\d+)", url)
            if m:
                img = load_icon_file(os.path.join(steam, "appcache", "librarycache",
                                                  f"{m.group(1)}_icon.jpg"))
                if usable(img):
                    return img
            img = load_icon_file(os.path.join(steam, "steam.exe"), 0)
            if usable(img):
                return img
    return None


def get_icon_image(path):
    """Best available icon for a file, or None."""
    if path.lower().endswith(".url"):
        img = url_icon(path)
        if usable(img):
            return img
    img = shell_icon(path)
    return img if usable(img) else None


def emoji_icon(ch, size=256):
    """Fallback picture: a colour emoji (Segoe UI Emoji ships with Windows)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    try:
        font = ImageFont.truetype("seguiemj.ttf", int(size * 0.75))
        ImageDraw.Draw(img).text((size // 2, size // 2), ch, font=font, anchor="mm",
                                 embedded_color=True)
    except Exception:
        ImageDraw.Draw(img).ellipse((size * .1, size * .1, size * .9, size * .9), fill=ACCENT)
    return img


def virtual_icon(key):
    """Real shell icon of a system item (found through its CLSID), else an emoji."""
    v = VIRTUAL[key]
    try:
        pidl, _ = shell.SHParseDisplayName("::" + v["clsid"], 0)
        _, info = shell.SHGetFileInfo(pidl, 0, shellcon.SHGFI_PIDL | shellcon.SHGFI_ICON
                                      | shellcon.SHGFI_LARGEICON)
        img = hicon_to_image(info[0]) if info[0] else None
        if usable(img):
            return img
    except Exception as e:
        log("system icon failed:", key, e)
    return emoji_icon(v["emoji"])


# ======================================================================================
# 9. Layout helpers
# ======================================================================================
def unique(folder, name):
    """A file name that does not exist yet in folder ('a.lnk' -> 'a (2).lnk')."""
    base, ext = os.path.splitext(name)
    dest, n = os.path.join(folder, name), 2
    while os.path.exists(dest):
        dest = os.path.join(folder, f"{base} ({n}){ext}")
        n += 1
    return dest


layout = read_json(LAYOUT_FILE, {})       # file name -> [col, row] (remembered grid cell)


def save_layout():
    write_json(LAYOUT_FILE, {it["name"]: [it["col"], it["row"]] for it in items.values()})


def cell_xy(col, row):
    return col * TILE_W + PAD, row * TILE_H + PAD


def xy_cell(x, y):
    return max(0, min(COLS - 1, int(x // TILE_W))), max(0, int(y // TILE_H))


def find_free(col, row, ignore=None):
    """Nearest empty grid cell to (col, row). `ignore` = item id(s) that do not block."""
    ignore = set() if ignore is None else ({ignore} if isinstance(ignore, int) else ignore)
    taken = {(it["col"], it["row"]) for i, it in items.items() if i not in ignore}
    col, row = max(0, min(col, COLS - 1)), max(0, row)
    if (col, row) not in taken:
        return col, row
    cells = sorted(((c, r) for r in range(ROWS + 60) for c in range(COLS)),
                   key=lambda p: abs(p[0] - col) + abs(p[1] - row))
    return next((c for c in cells if c not in taken), (col, row))


# ======================================================================================
# 10. Main UI: header, canvas, blue line, grey bar, drag ghost, theme
# ======================================================================================
compute_geometry()

header = tk.Frame(root, bg=BG, height=HEADER)
header.pack(side="top", fill="x")
header.pack_propagate(False)
status = tk.Label(header, text="", fg="#ffb454", bg=BG, font=("Segoe UI", 9))   # short warnings
status.pack(side="left", padx=10)


def flash(msg):
    status.config(text=msg)
    root.after(3000, lambda: status.config(text=""))


def set_pin(value):
    """Pinned = never auto-hides (and ignores 'Desktop only')."""
    state["pinned"] = value
    pin_btn.config(fg=ACCENT if value else BTN_FG)
    if value:
        state["open"] = True


def header_button(text, cmd, **kw):
    b = tk.Button(header, text=text, command=cmd, bg=BG, fg=BTN_FG, relief="flat", bd=0, **kw)
    b.pack(side="right", padx=6 if text == "✕" else 0)
    return b


close_btn = header_button("✕", lambda: quit_app(), activebackground="#c42b1c",
                          activeforeground="white")
pin_btn = header_button("📌", lambda: set_pin(not state["pinned"]))
gear_btn = header_button("⚙", lambda: open_settings())
header_btns = [close_btn, pin_btn, gear_btn]

canvas = tk.Canvas(root, bg=BG, width=CANVAS_W, height=CANVAS_H, highlightthickness=0,
                   yscrollincrement=max(1, TILE_H // 3))
canvas.pack(side="top", fill="both", expand=True)

strip = tk.Frame(root, bg=S["line_color"], cursor="fleur")    # edge line: stays visible when hidden
grip = tk.Frame(root, bg=GRIP_COLOR)                 # grey bar: drag to change the length


def place_strip():
    """Put the blue line on the inner side of the panel and the grey bar at its end."""
    e = S["edge"]
    if e == "left":
        strip.place(x=WIDTH - STRIP, y=0, width=STRIP, height=HEIGHT)
    elif e == "right":
        strip.place(x=0, y=0, width=STRIP, height=HEIGHT)
    elif e == "top":
        strip.place(x=0, y=HEIGHT - STRIP, width=WIDTH, height=STRIP)
    else:
        strip.place(x=0, y=0, width=WIDTH, height=STRIP)
    if AXIS == "x":
        grip.place(x=0, y=HEIGHT - GRIP, width=WIDTH, height=GRIP)
        grip.config(cursor="sb_v_double_arrow")
    else:
        grip.place(x=WIDTH - GRIP, y=0, width=GRIP, height=HEIGHT)
        grip.config(cursor="sb_h_double_arrow")
    grip.lift()
    strip.lift()


def make_menu(parent=None):
    t = THEMES[S["theme"]]
    return tk.Menu(parent or root, tearoff=0, bg=t["card"], fg=t["text"], activebackground=ACCENT,
                   activeforeground="#ffffff", bd=0, relief="flat")


def apply_theme():
    """Recolour the whole dock for the current theme."""
    load_theme_globals()
    t = THEMES[S["theme"]]
    for w in (root, header, status, canvas):
        w.configure(bg=BG)
    grip.configure(bg=GRIP_COLOR)
    for b in header_btns:
        is_close = b is close_btn
        b.configure(bg=BG, fg=BTN_FG, activebackground="#c42b1c" if is_close else t["btn_active"],
                    activeforeground="white" if is_close else FG)
    pin_btn.config(fg=ACCENT if state["pinned"] else BTN_FG)
    relayout_icons()


# Ghost icon that follows the cursor while icons are dragged OUT of the dock.
# "-transparentcolor" makes the ghost's background invisible.
ghost = tk.Toplevel(root)
ghost.withdraw()
ghost.overrideredirect(True)
ghost.attributes("-topmost", True, "-transparentcolor", "#010101")
ghost.configure(bg="#010101")
ghost_lbl = tk.Label(ghost, bg="#010101", bd=0)
ghost_lbl.pack()
ghost_on = [False]


def show_ghost(it, px, py):
    if not ghost_on[0]:
        ghost_lbl.config(image=it["img"])
        ghost_on[0] = True
    ghost.geometry(f"+{px + 10}+{py + 10}")
    ghost.deiconify()
    ghost.lift()


def hide_ghost():
    if ghost_on[0]:
        ghost.withdraw()
        ghost_on[0] = False


# ======================================================================================
# 11. Icon items on the canvas
# ======================================================================================
def draw_item(iid):
    """(Re)create the canvas objects of one icon: background, picture, label."""
    it = items[iid]
    pil = it["pil"]
    if pil.size[0] != ICON_PX:
        pil = pil.resize((ICON_PX, ICON_PX), RESAMPLE)
    it["img"] = ImageTk.PhotoImage(pil)       # keep a reference or Tk drops the picture
    x, y = cell_xy(it["col"], it["row"])
    tag = it["tag"]                           # one tag groups all parts so they move together
    label = os.path.splitext(it["name"])[0]
    if len(label) > 30:
        label = label[:27] + "…"
    it["rect"] = canvas.create_rectangle(x, y, x + IW, y + IH, fill=BG, outline="", tags=(tag,))
    canvas.create_image(x + IW // 2, y + 6, image=it["img"], anchor="n", tags=(tag,))
    canvas.create_text(x + IW // 2, y + 6 + ICON_PX + 4, text=label, fill=FG, width=IW - 8,
                       anchor="n", justify="center", font=("Segoe UI", FONT_SZ), tags=(tag,))


def add_item(name, cell=None):
    path = os.path.join(STORE, name)
    virtual = None
    if name.lower().endswith(".dockitem"):    # marker file of a system icon (Recycle Bin, ...)
        key = read_json(path, {}).get("virtual")
        virtual = key if key in VIRTUAL else None
    if virtual:
        pil = virtual_icon(virtual)
    else:
        pil = get_icon_image(path) or Image.new("RGBA", (ICON, ICON), (90, 90, 90, 255))
    col, row = find_free(*(cell or tuple(layout.get(name, (0, 0)))))
    iid = next_id[0]
    next_id[0] += 1
    items[iid] = {"name": name, "path": path, "virtual": virtual, "col": col, "row": row,
                  "pil": pil, "img": None, "rect": None, "tag": f"i{iid}"}
    draw_item(iid)
    return iid


def relayout_icons():
    """Redraw every icon (icon size or theme changed)."""
    canvas.delete("all")
    for iid in items:
        draw_item(iid)
    paint_selection()


def place(it, col, row):
    """Move an icon to a grid cell (moves its canvas objects relative to where they are)."""
    it["col"], it["row"] = col, row
    px, py = cell_xy(col, row)
    x1, y1 = canvas.coords(it["rect"])[:2]
    canvas.move(it["tag"], px - x1, py - y1)


def update_scroll():
    maxrow = max([it["row"] for it in items.values()] + [ROWS - 1])
    canvas.configure(scrollregion=(0, 0, CANVAS_W, max(CANVAS_H, (maxrow + 1) * TILE_H + PAD)))


def sync(force=False):
    """Make the canvas match the dock folder (files added/removed outside the app)."""
    try:
        m = os.stat(STORE).st_mtime_ns        # folder timestamp: skip the work when unchanged
    except OSError:
        return
    if not force and m == store_mtime[0]:
        return
    store_mtime[0] = m
    try:
        names = {n for n in os.listdir(STORE) if n not in IGNORE}
    except OSError:
        return
    changed = False
    for iid, it in list(items.items()):
        if it["name"] not in names:
            canvas.delete(it["tag"])
            del items[iid]
            sel.discard(iid)
            changed = True
    have = {it["name"] for it in items.values()}
    for n in sorted(names - have):
        add_item(n)
        changed = True
    if changed:
        update_scroll()
        save_layout()


def paint_selection():
    for iid, it in items.items():
        on = iid in sel
        canvas.itemconfig(it["rect"], fill=SEL if on else BG, outline=SEL_LINE if on else "")


def ids_in_rect(x1, y1, x2, y2):
    """Item ids whose canvas objects overlap a rectangle (ids are encoded in the tags 'i<N>')."""
    found = set()
    for obj in canvas.find_overlapping(x1, y1, x2, y2):
        for t in canvas.gettags(obj):
            if t.startswith("i") and t[1:].isdigit():
                found.add(int(t[1:]))
    return found


def hit(cx, cy):
    """Id of the icon under a canvas point, or None."""
    found = ids_in_rect(cx, cy, cx, cy)
    return max(found) if found else None


# ======================================================================================
# 12. System icons (Recycle Bin, This PC, ...) and actions
# ======================================================================================
def virtual_present(key):
    return any(it["virtual"] == key for it in items.values())


def add_virtual(key):
    """Put a system icon into the dock and hide the real one on the desktop."""
    if virtual_present(key):
        return
    v = VIRTUAL[key]
    was_hidden = desktop_icon_hidden(v["clsid"])
    if not was_hidden:
        set_desktop_icon_hidden(v["clsid"], True)
    # a small marker file in the dock folder represents the icon (so layout etc. just work)
    write_json(unique(STORE, v["title"] + ".dockitem"), {"virtual": key, "we_hid": not was_hidden})
    sync(force=True)


def remove_virtual(iid):
    """Take a system icon out of the dock and show it on the desktop again."""
    it = items.get(iid)
    if not it:
        return
    meta = read_json(it["path"], {})
    if meta.get("we_hid") and it["virtual"] in VIRTUAL:          # only undo what we did
        set_desktop_icon_hidden(VIRTUAL[it["virtual"]]["clsid"], False)
    try:
        os.remove(it["path"])
    except OSError as e:
        log("remove marker failed:", e)
    canvas.delete(it["tag"])
    del items[iid]
    sel.discard(iid)
    save_layout()
    update_scroll()
    if dialog_sync[0]:
        dialog_sync[0]()


def launch(iid):
    it = items.get(iid)
    if not it:
        return
    try:
        os.startfile(VIRTUAL[it["virtual"]]["open"] if it["virtual"] else it["path"])
    except Exception as e:
        flash("Could not open")
        log("open failed:", e)


def send_back(iid):
    """Return an icon to the desktop (and to its old spot if enabled)."""
    it = items.get(iid)
    if not it:
        return
    if it["virtual"]:
        remove_virtual(iid)
        return
    dest = unique(DESKTOP, it["name"])
    try:
        shutil.move(it["path"], dest)
    except Exception as e:
        flash("Could not move (permission?)")
        log("move to desktop failed:", e)
        return
    pos = origins.pop(it["name"], None)
    write_json(ORIGINS_FILE, origins)
    if S["restore_pos"] and pos:
        schedule_restore(os.path.basename(dest), pos)
    canvas.delete(it["tag"])
    del items[iid]
    sel.discard(iid)
    save_layout()
    update_scroll()


def arrange_by_name():
    for idx, it in enumerate(sorted(items.values(), key=lambda i: i["name"].lower())):
        place(it, idx // ROWS, idx % ROWS)    # fill downwards, then across (like the desktop)
    save_layout()
    update_scroll()


def select_all():
    sel.clear()
    sel.update(items)
    paint_selection()


def popup(menu, e):
    """Show a context menu; the flag keeps the dock open while the menu is showing."""
    state["menu"] = True
    try:
        menu.tk_popup(e.x_root, e.y_root)
    finally:
        menu.grab_release()
        state["menu"] = False


def apply_settings(save=True):
    """Push the current settings S into the window and the icon grid."""
    compute_geometry()
    strip.configure(bg=S["line_color"])
    canvas.configure(width=CANVAS_W, height=CANVAS_H, yscrollincrement=max(1, TILE_H // 3))
    place_strip()
    if S["icon"] != last_icon[0]:
        last_icon[0] = S["icon"]
        relayout_icons()
    if COLS != last_cols[0]:                  # re-fit icons only when the column count changed
        last_cols[0] = COLS
        for iid, it in sorted(items.items(), key=lambda kv: (kv[1]["row"], kv[1]["col"])):
            place(it, *find_free(it["col"], it["row"], ignore=iid))
    update_scroll()
    state["pos"] = VIS if state["open"] else HID
    apply_geometry()
    if save:
        save_layout()
        save_settings()


# ======================================================================================
# 13. Closing the program
# ======================================================================================
def return_all_icons():
    """Put every dock icon back on the real desktop (files at their original spot)."""
    pending, hid_changed = [], False
    for it in list(items.values()):
        try:
            if it["virtual"]:
                meta = read_json(it["path"], {})
                if meta.get("we_hid") and it["virtual"] in VIRTUAL:
                    set_desktop_icon_hidden(VIRTUAL[it["virtual"]]["clsid"], False, refresh=False)
                    hid_changed = True
                os.remove(it["path"])
            else:
                dest = unique(DESKTOP, it["name"])
                shutil.move(it["path"], dest)
                pos = origins.pop(it["name"], None)
                if S["restore_pos"] and pos:
                    pending.append((os.path.basename(dest), pos))
        except Exception as e:
            log("return icon failed:", it["name"], e)
    write_json(ORIGINS_FILE, origins)
    if hid_changed:
        refresh_desktop()
    restore_blocking(pending)


def quit_app():
    if quitting[0]:
        return
    quitting[0] = True
    try:
        if S["return_on_exit"]:
            return_all_icons()
    except Exception as e:
        log("return on exit failed:", e)
    try:
        if tray[0]:
            tray[0].stop()
    except Exception:
        pass
    root.destroy()


root.protocol("WM_DELETE_WINDOW", quit_app)


def launch_build():
    """Open a console window that builds ShortcutDock.exe from this script (source runs only)."""
    import subprocess
    console, _ = _pythons()
    try:
        subprocess.Popen([console, os.path.abspath(__file__), "--build", "--wait"],
                         creationflags=subprocess.CREATE_NEW_CONSOLE)
        flash("Building - watch the new window")
    except Exception as e:
        flash("Could not start the build")
        log("build launch failed:", e)


def start_tray():
    """System-tray icon (needs the optional 'pystray' package; skipped if it is missing)."""
    try:
        import pystray
    except Exception as e:
        log("no tray icon (pip install pystray):", e)
        return None
    # The tray runs in its own thread, so its menu only posts commands to ui_queue.
    menu = pystray.Menu(
        pystray.MenuItem("Show / hide dock", lambda icon, item: ui_queue.put("toggle"), default=True),
        pystray.MenuItem("Settings", lambda icon, item: ui_queue.put("settings")),
        pystray.MenuItem("Quit", lambda icon, item: ui_queue.put("quit")))
    icon = pystray.Icon("ShortcutDock", make_app_icon(64), "Shortcut Dock", menu)
    icon.run_detached()
    return icon


# ======================================================================================
# 14. Settings window: custom widgets
# ======================================================================================
def set_titlebar(win, dark):
    """Dark / light window title bar (Windows 10 20H1+ and 11)."""
    try:
        win.update_idletasks()
        hwnd = win32gui.GetParent(win.winfo_id()) or win.winfo_id()
        val = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):                 # attribute id differs between Windows builds
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val),
                                                       ctypes.sizeof(val))
    except Exception:
        pass


class Watcher:
    """Mixin: call fn() when a Tk variable changes, and unhook when the widget dies."""

    def watch(self, var, fn):
        tid = var.trace_add("write", lambda *a: fn())

        def cleanup(e):
            if e.widget is self:
                try:
                    var.trace_remove("write", tid)
                except Exception:
                    pass
        self.bind("<Destroy>", cleanup, add="+")


class Segmented(tk.Frame, Watcher):
    """A row of choices; the selected one is highlighted."""

    def __init__(self, parent, options, var, t, pad=10):
        super().__init__(parent, bg=t["track"], padx=dp(2), pady=dp(2))
        self.var, self.t, self.labels = var, t, {}
        for text, val in options:
            lb = tk.Label(self, text=text, font=("Segoe UI", 9, "bold"), padx=dp(pad),
                          pady=dp(5), cursor="hand2", bg=t["track"], fg=t["muted"])
            lb.pack(side="left", expand=True, fill="x")
            lb.bind("<Button-1>", lambda e, v=val: var.set(v))
            self.labels[val] = lb
        self.watch(var, self.refresh)
        self.refresh()

    def refresh(self):
        try:
            cur = self.var.get()
            for val, lb in self.labels.items():
                on = cur == val
                lb.config(bg=ACCENT if on else self.t["track"],
                          fg="#ffffff" if on else self.t["muted"])
        except tk.TclError:
            pass


class SliderRow(tk.Frame, Watcher):
    """Label + current value + a smooth, themed slider."""

    def __init__(self, parent, label, var, lo, hi, t, unit="%"):
        super().__init__(parent, bg=t["card"])
        self.var, self.lo, self.hi, self.t, self.unit = var, lo, hi, t, unit
        top = tk.Frame(self, bg=t["card"])
        top.pack(fill="x")
        tk.Label(top, text=label, bg=t["card"], fg=t["text"], font=("Segoe UI", 10)).pack(side="left")
        self.val = tk.Label(top, bg=t["card"], fg=ACCENT, font=("Segoe UI", 10, "bold"))
        self.val.pack(side="right")
        self.cv = tk.Canvas(self, height=dp(26), bg=t["card"], highlightthickness=0, cursor="hand2")
        self.cv.pack(fill="x")
        self.cv.bind("<Configure>", lambda e: self.draw())
        self.cv.bind("<Button-1>", self.on_mouse)
        self.cv.bind("<B1-Motion>", self.on_mouse)
        self.watch(var, self.draw)

    def draw(self):
        try:
            w, h = self.cv.winfo_width(), self.cv.winfo_height()
            if w < 20:
                return
            v = clamp(self.var.get(), self.lo, self.hi)
            pad, y = dp(10), h // 2
            x0, x1 = pad, w - pad
            xk = x0 + (x1 - x0) * (v - self.lo) / (self.hi - self.lo)
            c, r = self.cv, dp(8)
            c.delete("all")
            c.create_line(x0, y, x1, y, width=dp(4), fill=self.t["track"], capstyle="round")
            c.create_line(x0, y, xk, y, width=dp(4), fill=ACCENT, capstyle="round")
            c.create_oval(xk - r, y - r, xk + r, y + r, fill="#ffffff", outline=ACCENT, width=2)
            self.val.config(text=f"{int(v)}{self.unit}")
        except tk.TclError:
            pass

    def on_mouse(self, e):
        w, pad = self.cv.winfo_width(), dp(10)
        frac = clamp((e.x - pad) / max(1, w - 2 * pad), 0.0, 1.0)
        self.var.set(int(round(self.lo + frac * (self.hi - self.lo))))


class ToggleRow(tk.Frame, Watcher):
    """Title + description on the left, an on/off switch on the right."""

    def __init__(self, parent, title, desc, var, t):
        super().__init__(parent, bg=t["card"])
        self.var, self.t = var, t
        text = tk.Frame(self, bg=t["card"])
        text.pack(side="left", fill="x", expand=True)
        tk.Label(text, text=title, bg=t["card"], fg=t["text"], font=("Segoe UI", 10)).pack(anchor="w")
        tk.Label(text, text=desc, bg=t["card"], fg=t["muted"], font=("Segoe UI", 8),
                 wraplength=dp(270), justify="left").pack(anchor="w")
        self.w, self.h = dp(44), dp(24)
        self.cv = tk.Canvas(self, width=self.w, height=self.h, bg=t["card"],
                            highlightthickness=0, cursor="hand2")
        self.cv.pack(side="right", padx=(dp(10), 0))
        self.cv.bind("<Button-1>", lambda e: var.set(0 if var.get() else 1))
        self.watch(var, self.draw)
        self.draw()

    def draw(self):
        try:
            on, w, h = bool(self.var.get()), self.w, self.h
            col, c = (ACCENT if on else self.t["track"]), self.cv
            c.delete("all")
            c.create_oval(1, 1, h - 1, h - 1, fill=col, outline="")            # pill = 2 ovals + bar
            c.create_oval(w - h + 1, 1, w - 1, h - 1, fill=col, outline="")
            c.create_rectangle(h // 2, 1, w - h // 2, h - 1, fill=col, outline="")
            kx = w - h + 4 if on else 4                                         # knob
            c.create_oval(kx, 4, kx + h - 8, h - 4, fill="#ffffff", outline="")
        except tk.TclError:
            pass


def flat_button(parent, text, command, t, primary=False):
    colors = (dict(bg=ACCENT, fg="#ffffff", activebackground=ACCENT_DARK, activeforeground="#ffffff",
                   font=("Segoe UI", 10, "bold"), padx=dp(20)) if primary else
              dict(bg=t["track"], fg=t["text"], activebackground=t["btn_active"],
                   activeforeground=t["text"], font=("Segoe UI", 10), padx=dp(14)))
    return tk.Button(parent, text=text, command=command, relief="flat", bd=0, pady=dp(7),
                     cursor="hand2", **colors)


LINE_PRESETS = ["#4a78d0", "#2ecc71", "#e74c3c", "#f1c40f", "#9b59b6", "#e67e22",
                "#1abc9c", "#ff4fa3", "#ffffff", "#9aa0a6", "#000000"]


class ColorRow(tk.Frame, Watcher):
    """Colour swatches + a hex field + a Pick button, all editing one string variable."""

    def __init__(self, parent, var, t, pick):
        super().__init__(parent, bg=t["card"])
        self.var, self.t, self.cells = var, t, {}
        swatches = tk.Frame(self, bg=t["card"])
        swatches.pack(fill="x")
        self.sz = dp(22)
        for c in LINE_PRESETS:
            cv = tk.Canvas(swatches, width=self.sz, height=self.sz, bg=t["card"],
                           highlightthickness=0, cursor="hand2")
            cv.pack(side="left", padx=(0, dp(5)))
            cv.bind("<Button-1>", lambda e, c=c: var.set(c))
            self.cells[c] = cv
        row = tk.Frame(self, bg=t["card"])
        row.pack(fill="x", pady=(dp(8), 0))
        self.chip = tk.Canvas(row, width=dp(26), height=dp(26), bg=t["card"], highlightthickness=0)
        self.chip.pack(side="left")
        tk.Entry(row, textvariable=var, width=9, font=("Consolas", 10), bg=t["track"], fg=t["text"],
                 insertbackground=t["text"], relief="flat", highlightthickness=1,
                 highlightbackground=t["track"], highlightcolor=ACCENT).pack(
            side="left", padx=dp(8), ipady=dp(3))
        flat_button(row, "Pick…", pick, t).pack(side="left")
        self.watch(var, self.draw)
        self.draw()

    def draw(self):
        try:
            cur = self.var.get().strip().lower()
            for c, cv in self.cells.items():
                on = c == cur
                cv.delete("all")
                cv.create_oval(2, 2, self.sz - 2, self.sz - 2, fill=c, width=2 if on else 1,
                               outline=ACCENT if on else self.t["track"])
            self.chip.delete("all")
            if valid_hex(cur):                       # preview of whatever is typed
                self.chip.create_rectangle(2, 2, dp(26) - 2, dp(26) - 2, fill=cur,
                                           outline=self.t["track"])
        except tk.TclError:
            pass


# ======================================================================================
# 15. Settings window
# ======================================================================================
def open_settings():
    if state["dialog"]:
        keep_on_top()
        return
    state["dialog"], state["open"] = True, True
    dlg = tk.Toplevel(root)
    dlg.title("Dock settings")
    dlg.attributes("-topmost", True)
    dlg.resizable(False, False)
    dlg._icon = ImageTk.PhotoImage(make_app_icon(32))      # keep a reference
    dlg.iconphoto(False, dlg._icon)
    DW, DH = dp(430), min(dp(670), SH - 60)
    dlg.geometry(f"{DW}x{DH}+{max(0, SW // 2 - DW // 2)}+{max(10, SH // 2 - DH // 2)}")
    dialog_win[0] = dlg

    # one Tk variable per setting; changing any of them applies the settings (debounced)
    v_tab = tk.StringVar(value="0")
    v = dict(theme=tk.StringVar(), edge=tk.StringVar(), off=tk.IntVar(), w=tk.IntVar(),
             h=tk.IntVar(), op=tk.IntVar(), icon=tk.IntVar(), desk=tk.IntVar(),
             rest=tk.IntVar(), auto=tk.IntVar(), ret=tk.IntVar(),
             lcol=tk.StringVar(), lop=tk.IntVar())
    vv = {key: tk.IntVar() for key in VIRTUAL}              # one switch per system icon
    auto_state = [autostart_enabled()]
    body, job = [None], [None]

    def sync_vars():
        """Copy S (and what is in the dock) -> controls."""
        v["theme"].set(S["theme"]); v["edge"].set(S["edge"])
        v["off"].set(round(S["offset"] * 100)); v["w"].set(round(S["w"] * 100))
        v["h"].set(round(S["h"] * 100)); v["op"].set(round(S["opacity"] * 100))
        v["icon"].set(round(S["icon"] * 100)); v["desk"].set(int(S["desktop_only"]))
        v["rest"].set(int(S["restore_pos"])); v["ret"].set(int(S["return_on_exit"]))
        v["auto"].set(int(auto_state[0]))
        v["lcol"].set(S["line_color"]); v["lop"].set(round(S["line_opacity"] * 100))
        for key, var in vv.items():
            var.set(int(virtual_present(key)))

    def push():
        """Copy controls -> S and apply."""
        job[0] = None
        S.update(theme=v["theme"].get(), edge=v["edge"].get(), offset=v["off"].get() / 100,
                 w=v["w"].get() / 100, h=v["h"].get() / 100, opacity=max(0.2, v["op"].get() / 100),
                 icon=v["icon"].get() / 100, desktop_only=bool(v["desk"].get()),
                 restore_pos=bool(v["rest"].get()), return_on_exit=bool(v["ret"].get()),
                 line_opacity=v["lop"].get() / 100)
        col = v["lcol"].get().strip()
        if valid_hex(col):                    # ignore half-typed values like '#4a7'
            S["line_color"] = col.lower()
        if bool(v["auto"].get()) != auto_state[0]:
            auto_state[0] = set_autostart(bool(v["auto"].get()))
        for key, var in vv.items():                          # add / remove system icons
            want = bool(var.get())
            if want and not virtual_present(key):
                add_virtual(key)
            elif not want and virtual_present(key):
                remove_virtual(next(i for i, it in items.items() if it["virtual"] == key))
        if S["theme"] != applied_theme[0]:    # theme change also restyles this window
            applied_theme[0] = S["theme"]
            apply_theme()
            build()
        apply_settings()

    def changed(*_):
        if job[0]:
            try:
                dlg.after_cancel(job[0])
            except tk.TclError:
                pass
        try:
            job[0] = dlg.after(100, push)     # debounce: sliders fire many events per second
        except tk.TclError:
            pass

    sync_vars()
    for var in list(v.values()) + list(vv.values()):
        var.trace_add("write", changed)

    def section(parent, text, t, first=False):
        tk.Label(parent, text=text.upper(), bg=t["card"], fg=t["muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0 if first else dp(14), dp(5)))

    def show_tab(*_):
        """Fill the card with the controls of the selected tab."""
        card = body[0]
        if card is None:
            return
        try:
            for w in card.winfo_children():
                w.destroy()
        except tk.TclError:
            return
        t, tab = THEMES[S["theme"]], v_tab.get()
        if tab == "0":                                         # Appearance
            section(card, "Theme", t, True)
            Segmented(card, [("Dark", "dark"), ("Light", "light")], v["theme"], t).pack(fill="x")
            section(card, "Dock", t)
            SliderRow(card, "Opacity", v["op"], 20, 100, t).pack(fill="x")
            SliderRow(card, "Icon size", v["icon"], 50, 300, t).pack(fill="x", pady=(dp(8), 0))
            section(card, "Edge line", t)
            ColorRow(card, v["lcol"], t, pick_color).pack(fill="x")
            SliderRow(card, "Line opacity", v["lop"], 0, 100, t).pack(fill="x", pady=(dp(10), 0))
            tk.Label(card, bg=t["card"], fg=t["muted"], font=("Segoe UI", 8), justify="left",
                     text="Line opacity = how visible the line is while the dock is hidden.").pack(
                anchor="w", pady=(dp(4), 0))
        elif tab == "1":                                       # Layout
            section(card, "Slides in from", t, True)
            Segmented(card, [("Left", "left"), ("Right", "right"), ("Top", "top"),
                             ("Bottom", "bottom")], v["edge"], t).pack(fill="x")
            section(card, "Position and size", t)
            SliderRow(card, "Position along edge", v["off"], 0, 100, t).pack(fill="x")
            SliderRow(card, "Width", v["w"], 5, 100, t).pack(fill="x", pady=(dp(8), 0))
            SliderRow(card, "Height", v["h"], 5, 100, t).pack(fill="x", pady=(dp(8), 0))
            section(card, "Handy to know", t)
            tk.Label(card, bg=t["card"], fg=t["muted"], font=("Segoe UI", 8), justify="left",
                     text="Drag the blue line to move the dock, or onto another screen edge\n"
                          "to switch edge. Shift+drag = depth. Grey bar = length.\n"
                          "Ctrl + wheel = icon size.  Ctrl+Alt+D = show / pin.").pack(anchor="w")
        elif tab == "2":                                       # Behavior
            section(card, "Behavior", t, True)
            ToggleRow(card, "Return all icons when the dock closes",
                      "Quitting the dock puts every icon back on the desktop.",
                      v["ret"], t).pack(fill="x")
            ToggleRow(card, "Return icons to original spot", "Icons sent back go to the exact "
                      "place they were dragged from (desktop 'Auto arrange' must be off).",
                      v["rest"], t).pack(fill="x", pady=(dp(12), 0))
            ToggleRow(card, "Desktop only", "Hide the dock completely while another window "
                      "is in front.", v["desk"], t).pack(fill="x", pady=(dp(12), 0))
            ToggleRow(card, "Start with Windows", "Launch the dock automatically when you "
                      "sign in.", v["auto"], t).pack(fill="x", pady=(dp(12), 0))
            if not getattr(sys, "frozen", False):          # only when running from the .py file
                section(card, "Single-file program", t)
                flat_button(card, "Create ShortcutDock.exe…", launch_build, t).pack(anchor="w")
                tk.Label(card, bg=t["card"], fg=t["muted"], font=("Segoe UI", 8), justify="left",
                         wraplength=dp(340),
                         text="Opens a window that builds one .exe next to this script "
                              "(a few minutes, internet needed once).").pack(
                    anchor="w", pady=(dp(4), 0))
        else:                                                  # System icons
            section(card, "Desktop system icons", t, True)
            tk.Label(card, bg=t["card"], fg=t["muted"], font=("Segoe UI", 8), justify="left",
                     wraplength=dp(340),
                     text="Switching one on adds it to the dock and hides it on the desktop. "
                          "It returns to the desktop when you switch it off, drag it out of "
                          "the dock, or close the dock (if that option is on).").pack(anchor="w")
            for key, vdef in VIRTUAL.items():
                ToggleRow(card, vdef["title"], vdef["desc"], vv[key], t).pack(
                    fill="x", pady=(dp(14), 0))

    def pick_color():
        """Windows colour chooser. The 'picking' flag stops the dock / settings from being
        raised on top of it while it is open."""
        from tkinter import colorchooser
        cur = v["lcol"].get().strip()
        state["picking"] = True
        try:
            _, hexv = colorchooser.askcolor(color=cur if valid_hex(cur) else S["line_color"],
                                            parent=dlg, title="Edge line colour")
        except Exception as e:
            log("colour chooser failed:", e)
            hexv = None
        finally:
            state["picking"] = False
        if hexv:
            v["lcol"].set(hexv)

    v_tab.trace_add("write", show_tab)

    def close():
        if job[0]:                            # apply anything still waiting in the debounce
            try:
                dlg.after_cancel(job[0])
            except tk.TclError:
                pass
            push()
        dlg.destroy()

    def reset():
        S.update(DEFAULTS)
        sync_vars()
        push()

    def build():
        """(Re)build the whole window; called again when the theme changes."""
        t = THEMES[S["theme"]]
        for w in dlg.winfo_children():
            w.destroy()
        dlg.configure(bg=t["dlg_bg"])
        set_titlebar(dlg, S["theme"] == "dark")
        outer = tk.Frame(dlg, bg=t["dlg_bg"])
        outer.pack(fill="both", expand=True, padx=dp(20), pady=dp(16))
        tk.Label(outer, text="Dock settings", bg=t["dlg_bg"], fg=t["text"],
                 font=("Segoe UI", 15, "bold")).pack(anchor="w")
        tk.Label(outer, text="Changes apply instantly and are saved automatically.",
                 bg=t["dlg_bg"], fg=t["muted"], font=("Segoe UI", 9)).pack(anchor="w", pady=(0, dp(12)))
        footer = tk.Frame(outer, bg=t["dlg_bg"])
        footer.pack(side="bottom", fill="x", pady=(dp(14), 0))
        flat_button(footer, "Done", close, t, primary=True).pack(side="right")
        flat_button(footer, "Reset to defaults", reset, t).pack(side="right", padx=(0, dp(8)))
        Segmented(outer, [("Appearance", "0"), ("Layout", "1"), ("Behavior", "2"),
                          ("System", "3")], v_tab, t, pad=5).pack(fill="x")
        card = tk.Frame(outer, bg=t["card"], padx=dp(18), pady=dp(16))
        card.pack(fill="both", expand=True, pady=(dp(12), 0))
        body[0] = card
        show_tab()

    def on_destroy(ev):
        if ev.widget is dlg:
            state["dialog"] = False
            dialog_win[0] = dialog_sync[0] = None

    dlg.bind("<Destroy>", on_destroy)
    dlg.protocol("WM_DELETE_WINDOW", close)
    dialog_sync[0] = sync_vars
    build()
    keep_on_top()


# ======================================================================================
# 16. Moving / resizing the panel (blue line and grey bar)
# ======================================================================================
def strip_press(e):
    # plain drag = move; Shift+drag = change the depth
    mv.update(on=True, kind="strip", mode="resize" if (e.state & 0x1) else "move")
    state.update(moving=True, open=True, pos=VIS)
    mv["off"] = (e.y_root if AXIS == "x" else e.x_root) - FIX     # where on the panel we grabbed it


def grip_press(e):
    mv.update(on=True, kind="grip")
    state.update(moving=True, open=True, pos=VIS)


def move_panel(px, py):
    """Follow the pointer: slide along the edge, or jump to the edge the pointer reaches."""
    cur, cands = S["edge"], []
    if cur != "left" and px <= SNAP:
        cands.append((px, "left"))
    if cur != "right" and px >= SW - 1 - SNAP:
        cands.append((SW - 1 - px, "right"))
    if cur != "top" and py <= SNAP:
        cands.append((py, "top"))
    if cur != "bottom" and py >= SH - 1 - SNAP:
        cands.append((SH - 1 - py, "bottom"))
    if cands:                                         # snap to the nearest new edge, centred on pointer
        S["edge"] = min(cands)[1]
        compute_geometry()
        mv["off"] = (HEIGHT if S["edge"] in ("left", "right") else WIDTH) // 2
    compute_geometry()
    span, along = ((SH - HEIGHT, py) if S["edge"] in ("left", "right") else (SW - WIDTH, px))
    S["offset"] = clamp((along - mv["off"]) / span, 0.0, 1.0) if span > 0 else 0.0


def resize_depth(px, py):
    e = S["edge"]
    if e in ("left", "right"):
        S["w"] = clamp((px if e == "left" else SW - px) / SW, 0.05, 1.0)
    else:
        S["h"] = clamp((py if e == "top" else SH - py) / SH, 0.05, 1.0)


def resize_length(px, py):
    """Resize along the edge while keeping the panel's start fixed."""
    old_fix = FIX
    if AXIS == "x":
        S["h"] = clamp((py - old_fix) / SH, 0.05, (SH - old_fix) / SH)
    else:
        S["w"] = clamp((px - old_fix) / SW, 0.05, (SW - old_fix) / SW)
    compute_geometry()
    span = (SH - HEIGHT) if AXIS == "x" else (SW - WIDTH)
    S["offset"] = clamp(old_fix / span, 0.0, 1.0) if span > 0 else 0.0


def mv_motion(e):
    if not mv["on"]:
        return
    if mv["kind"] == "grip":
        resize_length(e.x_root, e.y_root)
    elif mv["mode"] == "resize":
        resize_depth(e.x_root, e.y_root)
    else:
        move_panel(e.x_root, e.y_root)
    apply_settings(save=False)                        # live preview, saved on release


def mv_release(e=None):
    if not mv["on"]:
        return
    mv["on"] = False
    state["moving"] = False
    apply_settings(save=True)
    if dialog_sync[0]:
        dialog_sync[0]()


for w, press in ((strip, strip_press), (grip, grip_press)):
    w.bind("<ButtonPress-1>", press)
    w.bind("<B1-Motion>", mv_motion)
    w.bind("<ButtonRelease-1>", mv_release)


# ======================================================================================
# 17. Mouse handling for icons: select, drag, rearrange, send back
# ======================================================================================
def on_press(e):
    canvas.focus_force()                              # lets Ctrl+wheel / keyboard shortcuts work
    cx, cy = canvas.canvasx(e.x), canvas.canvasy(e.y)
    iid, ctrl = hit(cx, cy), bool(e.state & 0x4)
    drag.update(id=None, moved=False, sx=e.x_root, sy=e.y_root, lx=cx, ly=cy, orig={})
    if band["id"] is not None:
        canvas.delete(band["id"])
    band.update(on=False, id=None)

    if iid is None:                                   # empty space: start a selection rectangle
        base = set(sel) if ctrl else set()
        sel.clear()
        sel.update(base)
        band.update(on=True, x0=cx, y0=cy, base=base,
                    id=canvas.create_rectangle(cx, cy, cx, cy, outline=SEL_LINE, dash=(3, 3)))
        paint_selection()
        return
    if ctrl:                                          # Ctrl+click toggles one icon
        sel.symmetric_difference_update({iid})
        paint_selection()
        if iid not in sel:
            return
    elif iid not in sel:                              # click outside the selection selects just it
        sel.clear()
        sel.add(iid)
    paint_selection()
    drag["id"] = iid                                  # a drag of the (whole) selection may follow


def on_motion(e):
    cx, cy = canvas.canvasx(e.x), canvas.canvasy(e.y)
    if band["on"]:                                    # growing the selection rectangle
        canvas.coords(band["id"], band["x0"], band["y0"], cx, cy)
        x1, x2 = sorted((band["x0"], cx))
        y1, y2 = sorted((band["y0"], cy))
        new = band["base"] | ids_in_rect(x1, y1, x2, y2)
        if new != sel:
            sel.clear()
            sel.update(new)
            paint_selection()
        return
    iid = drag["id"]
    if iid is None or iid not in items:
        return
    if not drag["moved"]:                             # ignore tiny jitters, then start the drag
        if abs(e.x_root - drag["sx"]) < 6 and abs(e.y_root - drag["sy"]) < 6:
            return
        drag["moved"] = state["drag"] = True
        drag["orig"] = {i: (items[i]["col"], items[i]["row"]) for i in sel if i in items}
        for i in drag["orig"]:
            canvas.tag_raise(items[i]["tag"])
    dx, dy = cx - drag["lx"], cy - drag["ly"]
    for i in drag["orig"]:
        canvas.move(items[i]["tag"], dx, dy)
    drag["lx"], drag["ly"] = cx, cy
    if inside_window(e.x_root, e.y_root):             # ghost icon only once we leave the panel
        hide_ghost()
    else:
        show_ghost(items[iid], e.x_root, e.y_root)


def on_release(e):
    if band["on"]:
        canvas.delete(band["id"])
        band.update(on=False, id=None)
        return
    iid, moved = drag["id"], drag["moved"]
    drag["id"], drag["moved"] = None, False
    hide_ghost()
    state["drag"] = False
    if iid is None or iid not in items:
        return
    if not moved:                                     # plain click on one icon of a group
        if not (e.state & 0x4) and len(sel) > 1 and iid in sel:
            sel.clear()
            sel.add(iid)
            paint_selection()
        return
    group = [i for i in drag["orig"] if i in items]
    if not inside_window(e.x_root, e.y_root):         # released outside the panel -> desktop
        for i in group:
            send_back(i)
        return
    # released inside: snap the whole group to the grid, keeping its shape
    it = items[iid]
    x1, y1 = canvas.coords(it["rect"])[:2]
    col, row = xy_cell(x1 + IW / 2, y1 + IH / 2)
    oc, orow = drag["orig"][iid]
    dc, dr = col - oc, row - orow
    pending = set(group)                              # not yet placed: do not block free cells
    for i in sorted(group, key=lambda k: (drag["orig"][k][1], drag["orig"][k][0])):
        c0, r0 = drag["orig"][i]
        place(items[i], *find_free(c0 + dc, r0 + dr, ignore=pending))
        pending.discard(i)
    save_layout()
    update_scroll()


def on_double(e):
    iid = hit(canvas.canvasx(e.x), canvas.canvasy(e.y))
    if iid is not None:
        launch(iid)


def on_right(e):
    iid = hit(canvas.canvasx(e.x), canvas.canvasy(e.y))
    if iid is not None and iid not in sel:
        sel.clear()
        sel.add(iid)
    elif iid is None:
        sel.clear()
    paint_selection()
    menu, chosen = make_menu(), [i for i in sel if i in items]
    if iid is not None and chosen:
        n = len(chosen)
        menu.add_command(label="Open" if n == 1 else f"Open {n} items",
                         command=lambda: [launch(i) for i in chosen])
        menu.add_command(label="Send back to desktop" if n == 1 else f"Send {n} items back to desktop",
                         command=lambda: [send_back(i) for i in chosen])
    else:
        menu.add_command(label="Select all", command=select_all)
        menu.add_command(label="Arrange by name", command=arrange_by_name)
        missing = [k for k in VIRTUAL if not virtual_present(k)]
        if missing:                                   # add Recycle Bin / This PC / ...
            sub = make_menu(menu)
            for k in missing:
                sub.add_command(label=VIRTUAL[k]["title"], command=lambda k=k: add_virtual(k))
            menu.add_cascade(label="Add system icon", menu=sub)
        menu.add_command(label="Open dock folder", command=lambda: os.startfile(STORE))
        menu.add_separator()
        menu.add_command(label="Settings…", command=open_settings)
    popup(menu, e)


zoom_job = [None]


def on_wheel(e):
    if e.state & 0x4:                                 # Ctrl + wheel = icon size (debounced)
        S["icon"] = clamp(round(S["icon"] + (0.1 if e.delta > 0 else -0.1), 2), 0.5, 3.0)
        if zoom_job[0]:
            root.after_cancel(zoom_job[0])

        def apply_zoom():
            apply_settings()
            if dialog_sync[0]:
                dialog_sync[0]()
        zoom_job[0] = root.after(80, apply_zoom)
        return
    canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")


for seq, fn in (("<ButtonPress-1>", on_press), ("<B1-Motion>", on_motion),
                ("<ButtonRelease-1>", on_release), ("<Double-Button-1>", on_double),
                ("<Button-3>", on_right), ("<MouseWheel>", on_wheel),
                ("<Control-a>", lambda e: select_all()),
                ("<Escape>", lambda e: (sel.clear(), paint_selection())),
                ("<Return>", lambda e: [launch(i) for i in list(sel) if i in items])):
    canvas.bind(seq, fn)


# ======================================================================================
# 18. Dropping files from the desktop / Explorer onto the dock
# ======================================================================================
def on_drop(event):
    px, py = root.winfo_pointerx(), root.winfo_pointery()
    cx = canvas.canvasx(px - canvas.winfo_rootx())
    cy = canvas.canvasy(py - canvas.winfo_rooty())
    cell = xy_cell(cx, cy)                            # land where the mouse was released
    for p in root.tk.splitlist(event.data):           # splitlist handles paths with spaces
        p = os.path.normpath(p)
        if not os.path.exists(p):
            continue
        parent = os.path.normcase(os.path.dirname(p))
        if parent == os.path.normcase(STORE):
            continue
        # remember where the icon sits on the real desktop BEFORE moving it away
        desk_pos = None
        if parent in (os.path.normcase(DESKTOP), os.path.normcase(COMMON_DESKTOP)):
            desk_pos = desktop_get_pos(os.path.basename(p))
        dest = unique(STORE, os.path.basename(p))
        try:
            shutil.move(p, dest)
        except Exception as e:
            flash("Could not move (permission?)")
            log("move into dock failed:", e)
            continue
        if desk_pos:
            origins[os.path.basename(dest)] = desk_pos
            write_json(ORIGINS_FILE, origins)
        add_item(os.path.basename(dest), cell)
    update_scroll()
    save_layout()


for w in (root, canvas):
    w.drop_target_register(DND_FILES)
    w.dnd_bind("<<Drop>>", on_drop)


# ======================================================================================
# 19. Robustness: nothing may leave the dock stuck
# ======================================================================================
def reset_stuck():
    """Clear every 'busy' flag so the dock can never stay open / unusable."""
    hide_ghost()
    state.update(drag=False, moving=False, menu=False, stale=None)
    drag.update(id=None, moved=False, orig={})
    mv["on"] = False
    if band["id"] is not None:
        try:
            canvas.delete(band["id"])
        except tk.TclError:
            pass
    band.update(on=False, id=None)


def report_error(exc, val, tb):
    """Any error inside a Tk callback: log it and clear stuck flags (Tk would only print it)."""
    log("callback error:", repr(val))
    reset_stuck()


root.report_callback_exception = report_error


def handle_tray_commands():
    """Run commands posted by the tray icon thread."""
    while True:
        try:
            cmd = ui_queue.get_nowait()
        except queue.Empty:
            return
        if cmd == "toggle":                           # show (pinned) / hide
            if state["pinned"] or state["open"]:
                set_pin(False)
                state["open"] = False
            else:
                set_pin(True)
        elif cmd == "settings":
            open_settings()
        elif cmd == "quit":
            quit_app()
            return


# ======================================================================================
# 20. The slide logic (runs every few milliseconds)
# ======================================================================================
def step():
    """One tick: decide open / closed, animate, handle hotkey and watchdog. Returns next delay."""
    handle_tray_commands()
    if quitting[0]:
        return FRAME_MS
    px, py = win32api.GetCursorPos()                  # physical pixels, same units as SW/SH
    btn_down, now = key_down(win32con.VK_LBUTTON), time.time()

    # Emergency hotkeys: Ctrl+Alt+D = show + pin / unpin, Ctrl+Alt+S = open the settings.
    ctrl_alt = key_down(win32con.VK_CONTROL) and key_down(win32con.VK_MENU)
    hot = ctrl_alt and key_down(0x44)                 # D
    if hot and not state["hot"]:
        set_pin(not state["pinned"])
    state["hot"] = hot
    hot_s = ctrl_alt and key_down(0x53)               # S: open the settings even if the dock is invisible
    if hot_s and not state["hot_s"]:
        open_settings()
    state["hot_s"] = hot_s

    # The settings window must always stay above the dock.
    if dialog_win[0] is not None and not state["picking"] and now - state["raised"] > 0.3:
        state["raised"] = now
        raise_window(dialog_win[0])

    # Watchdog: a drag flag that outlives the mouse button is stale -> clear it. The 0.6 s
    # grace avoids racing the normal button-release event.
    flagged = state["drag"] or state["moving"] or drag["id"] is not None or band["on"]
    if flagged and not btn_down:
        state["stale"] = state["stale"] or now
        if now - state["stale"] > 0.6:
            reset_stuck()
    else:
        state["stale"] = None

    busy = (state["menu"] or state["drag"] or state["moving"]
            or drag["id"] is not None or band["on"])
    in_dialog = pointer_in_dialog(px, py)             # using the settings keeps the dock visible

    # "Desktop only": hide the window completely while another program is in front.
    if (S["desktop_only"] and not busy and not state["pinned"] and not in_dialog
            and not on_desktop()):
        if state["shown"]:
            root.withdraw()
            state.update(shown=False, open=False, pos=HID, leave=None)
        return 100
    if not state["shown"]:
        state["shown"] = True
        apply_geometry()
        root.deiconify()
        root.attributes("-topmost", True)
        update_alpha(force=True)
        keep_on_top()

    if in_dialog:
        state["open"] = True

    if state["open"]:
        # stay open while the pointer is on the panel (10 px margin) or something is going on
        x, y = pos_xy()
        inside = x - 10 <= px <= x + WIDTH + 10 and y - 10 <= py <= y + HEIGHT + 10
        if inside or in_dialog or busy or state["pinned"]:
            state["leave"] = None
        elif state["leave"] is None:
            state["leave"] = now                      # pointer just left: start the hide timer
        elif now - state["leave"] > CLOSE_DELAY:
            state.update(open=False, leave=None)
    elif at_edge(px, py, DRAG_TRIGGER if btn_down else STRIP):
        state["open"] = True                          # bigger zone while dragging a file

    # Slide: ease out (step = 1/4 of the remaining distance, but never slower than SPEED_MIN).
    target, cur = (VIS if state["open"] else HID), state["pos"]
    if cur != target:
        diff = target - cur
        move = min(max(SPEED_MIN, abs(diff) // 4), abs(diff))
        state["pos"] = cur + (move if diff > 0 else -move)
        apply_geometry()
        return FRAME_MS
    return FRAME_MS if (state["open"] or busy) else IDLE_MS


def tick():
    """Never let the loop die: an error is logged, flags are cleared, the loop continues."""
    if quitting[0]:
        return
    delay = FRAME_MS
    try:
        delay = step()
    except Exception as e:
        log("tick error:", repr(e))
        try:
            reset_stuck()
        except Exception:
            pass
    if not quitting[0]:
        try:
            root.after(delay, tick)
        except tk.TclError:
            pass


def poll():
    """Slow housekeeping every 1.5 s."""
    global SW, SH
    if quitting[0]:
        return
    try:
        if not state["drag"] and drag["id"] is None:
            sync()                                    # files added / removed outside the app
        cw, ch = win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1)
        if (cw, ch) != (SW, SH):                      # resolution / monitor layout changed
            SW, SH = cw, ch
            apply_settings(save=False)
        if state["shown"]:
            keep_on_top()
    except Exception as e:
        log("poll error:", repr(e))
    if not quitting[0]:
        try:
            root.after(1500, poll)
        except tk.TclError:
            pass


# ======================================================================================
# 21. Go
# ======================================================================================
place_strip()
state["pos"] = HID                                    # start hidden
sync(force=True)
update_scroll()
apply_geometry()
tray[0] = start_tray()
tick()
poll()
root.mainloop()

# ======================================================================================
# MAKE THE ONE-FILE PROGRAM (once, on Windows): start this file, open Settings > Behavior and
# press "Create ShortcutDock.exe"  (or run:  python shortcut_dock.py --build).
# ShortcutDock.exe appears next to this file and is then the only file you need.
# ======================================================================================