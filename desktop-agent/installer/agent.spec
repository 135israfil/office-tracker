# PyInstaller spec for the Office Tracker agent (Phase 9).
#
#     pyinstaller installer/agent.spec --noconfirm
#
# Produces a single `OfficeTrackerAgent.exe` in `dist/`. One file rather than a folder
# because Inno Setup then has one thing to place and the uninstaller one thing to
# remove; the startup cost of unpacking is paid once, at login.
#
# Windowed, not console: this runs from `HKCU\Run` at every login, and a console build
# would flash a black window in the user's face every morning.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(SPECPATH).parent))

from agent.version import __version__  # noqa: E402

block_cipher = None

# PyInstaller finds imports by walking them, and these are reached dynamically:
# keyring picks its platform backend at runtime, and pystray and PIL load their
# platform implementations the same way. Without them the build succeeds and the
# agent fails on the first machine it touches. On macOS, AppKit/Quartz/Foundation/
# ApplicationServices are also only ever imported inside try/except blocks (see
# collectors/idle.py, application.py, browser.py, system.py) specifically so a
# missing pyobjc degrades instead of crashing — which is exactly the shape PyInstaller's
# static import walk cannot see through, so they have to be named here explicitly too.
if sys.platform == "darwin":
    hiddenimports = [
        "keyring.backends.macOS",
        "pystray._darwin",
        "PIL._tkinter_finder",
        "AppKit",
        "Quartz",
        "Foundation",
        "ApplicationServices",
    ]
else:
    hiddenimports = [
        "keyring.backends.Windows",
        "pystray._win32",
        "PIL._tkinter_finder",
    ]

analysis = Analysis(
    ["entry.py"],
    pathex=[str(Path(SPECPATH).parent)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # §31 is enforced structurally, and that includes the build: nothing capable of
    # screen capture, key hooking or clipboard access may be collected into the binary
    # even transitively. `scripts/check_privacy.py` guards the source; this guards the
    # artefact.
    #
    # tkinter is NOT one of those — it is a GUI toolkit (the enrollment prompt and
    # status/error dialogs in tray.py both need it) with no screen-capture, input-
    # synthesis or clipboard capability of its own. It was excluded here by mistake,
    # grouped in with the genuinely privacy-sensitive libraries above rather than
    # checked against what the codebase actually imports — and every tray dialog
    # (Status, Enrol, Sync now, error reporting) has been silently broken since,
    # failing with "No module named 'tkinter'" the moment any of them was clicked, with
    # nowhere for that error to surface until agent.log existed to catch it.
    excludes=[
        "mss",
        "pyautogui",
        "pynput",
        "keyboard",
        "sounddevice",
        "cv2",
        "win32clipboard",
        "pytest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(analysis.pure, analysis.zipped_data, cipher=block_cipher)

# version_info.txt is a Windows PE version resource (see make_version_info.py) and has
# no meaning to EXE() on macOS, where version info instead goes on BUNDLE()'s
# info_plist below — so it is passed only on the platform that can use it.
exe_kwargs = dict(
    name="OfficeTrackerAgent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX-packed binaries are a reliable way to be flagged by antivirus.
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,  # No Developer ID yet; macOS still ad-hoc-signs arm64.
    entitlements_file=None,
)
if sys.platform == "darwin":
    icns = Path(SPECPATH) / "agent.icns"
    if icns.exists():
        exe_kwargs["icon"] = str(icns)
else:
    ico = Path(SPECPATH) / "agent.ico"
    if ico.exists():
        exe_kwargs["icon"] = str(ico)
    exe_kwargs["version"] = str(Path(SPECPATH) / "version_info.txt")

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.zipfiles,
    analysis.datas,
    [],
    **exe_kwargs,
)

if sys.platform == "darwin":
    # LSUIElement: a menu-bar app with no Dock icon — tray.py's own docstring on why
    # this is a visible tray app and not a hidden service applies equally here; LSUIElement
    # keeps it out of the Dock and Cmd+Tab switcher without making it invisible, the same
    # "people know tracking is on, but it isn't in their way" balance the Windows build
    # strikes by living in the system tray rather than as a window.
    app = BUNDLE(
        exe,
        name="OfficeTrackerAgent.app",
        bundle_identifier="com.officetracker.agent",
        info_plist={
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "LSUIElement": True,
            "NSAppleEventsUsageDescription": (
                "Office Tracker reads the active browser's address bar to record "
                "which website is in use."
            ),
            "NSScreenCaptureUsageDescription": (
                "Office Tracker periodically captures a screenshot as part of "
                "employer-configured activity tracking."
            ),
        },
    )
