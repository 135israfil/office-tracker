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

analysis = Analysis(
    ["entry.py"],
    pathex=[str(Path(SPECPATH).parent)],
    binaries=[],
    datas=[],
    # PyInstaller finds imports by walking them, and these three are reached
    # dynamically: keyring picks its Windows backend at runtime, and pystray and PIL
    # load their platform implementations the same way. Without them the build succeeds
    # and the agent fails on the first machine it touches.
    hiddenimports=[
        "keyring.backends.Windows",
        "pystray._win32",
        "PIL._tkinter_finder",
    ],
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

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.zipfiles,
    analysis.datas,
    [],
    name="OfficeTrackerAgent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX-packed binaries are a reliable way to be flagged by antivirus.
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(Path(SPECPATH) / "agent.ico") if (Path(SPECPATH) / "agent.ico").exists() else None,
    version=str(Path(SPECPATH) / "version_info.txt"),
)
