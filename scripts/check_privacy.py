#!/usr/bin/env python
"""Fail the build if the codebase gains a capability README.txt §31 prohibits.

§31 forbids keylogging, webcam, microphone and clipboard monitoring. Those are
enforced structurally rather than by review: the libraries that make them
possible must never appear in an import.

Screenshot/screen-recording capture is deliberately NOT banned as of
2026-11-22 (see README.txt §31's own note on this date, and
docs/designs/screenshot-based-activity-tracking.md) - a conscious policy
change by the project owner, made the way this file's own docstring always
said a legitimate need should be handled: a documented, deliberate edit here,
not a quiet workaround elsewhere. Input synthesis, key/mouse logging, and
clipboard access remain fully banned; only the screen-capture capability
itself was lifted. `pyautogui` stays banned outright even though it can also
capture the screen, because it bundles that with input synthesis, which this
change does not permit.

`uiautomation` is the awkward case, and the reason this file has a second half.
The browser collector cannot read an address bar without it, so it cannot be
banned outright - but the same library can also synthesise keystrokes, which
is still prohibited. Only its tree-reading and (as of the policy change above)
bitmap-capture APIs are permitted; the call-level check below rejects the
keystroke/mouse/clipboard half by name.

This is a blunt instrument on purpose. If a legitimate need collides with it,
that collision deserves a conversation, not a quiet exemption.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Module names that provide a prohibited capability, mapped to why they are banned.
# mss/pyscreenshot/d3dshot (pure screen-capture libraries) are deliberately NOT
# listed here as of 2026-11-22 - see this file's module docstring. pyautogui
# stays banned: it bundles screen capture with input synthesis, and only the
# capture half of this policy was lifted.
BANNED_MODULES = {
    "keyboard": "key logging",
    "pynput": "key and mouse logging",
    "pyautogui": "input synthesis (bundled with screen capture, which is why this stays banned)",
    "cv2": "camera capture",
    "sounddevice": "microphone capture",
    "pyaudio": "microphone capture",
    "win32clipboard": "clipboard monitoring",
    "pyperclip": "clipboard monitoring",
}

# Fully-qualified attribute paths that are prohibited even though their root
# package is legitimate. Pillow's ImageGrab (screen capture) was removed from
# this list on 2026-11-22, the same deliberate policy change noted above.
BANNED_ATTRIBUTES = {}

# Method and function names that are prohibited anywhere they are called, because
# they are the dual-use half of a library that is otherwise needed. `uiautomation`
# reads the UI tree (permitted, and required by §16) but can also drive the mouse
# and keyboard and capture bitmaps (prohibited by §31).
#
# Matched on the attribute name alone rather than a full path, because the calls
# arrive on control objects whose type is not knowable from the source. That makes
# the check blunt: a method of your own called `Click` will trip it. Rename it.
BANNED_CALL_NAMES = {
    # Input synthesis
    "SendKeys": "keystroke synthesis",
    "SendKey": "keystroke synthesis",
    "PressKey": "keystroke synthesis",
    "ReleaseKey": "keystroke synthesis",
    "Click": "mouse synthesis",
    "DoubleClick": "mouse synthesis",
    "RightClick": "mouse synthesis",
    "MiddleClick": "mouse synthesis",
    "DragDrop": "mouse synthesis",
    "WheelUp": "mouse synthesis",
    "WheelDown": "mouse synthesis",
    # Screen capture (CaptureToImage/BitmapFromWindow/ToBitmap) was removed from
    # this list on 2026-11-22 - screen capture is no longer prohibited, see the
    # module docstring.
    # Clipboard
    "GetClipboardText": "clipboard monitoring",
    "SetClipboardText": "clipboard access",
}

SKIP_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "staticfiles",
    "dist",
    "build",
    "migrations",
}


def iter_python_files(root: Path):
    for path in root.rglob("*.py"):
        if SKIP_DIRECTORIES & set(path.parts):
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        yield path


def imported_names(tree: ast.AST):
    """Yield (name, lineno) for every module reachable through an import."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module:
                yield module, node.lineno
            for alias in node.names:
                yield f"{module}.{alias.name}" if module else alias.name, node.lineno


def called_attributes(tree: ast.AST):
    """Yield (attribute_name, lineno) for every attribute call in the file."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            yield node.func.attr, node.lineno


def check_file(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [f"{path}: could not parse ({exc})"]

    violations = []
    for name, lineno in called_attributes(tree):
        if name in BANNED_CALL_NAMES:
            reason = BANNED_CALL_NAMES[name]
            violations.append(
                f"{path}:{lineno}: calls '{name}()' ({reason}) - prohibited by §31"
            )

    for name, lineno in imported_names(tree):
        root = name.split(".")[0]
        if root in BANNED_MODULES:
            reason = BANNED_MODULES[root]
            violations.append(f"{path}:{lineno}: imports '{name}' ({reason}) - prohibited by §31")
        for banned, reason in BANNED_ATTRIBUTES.items():
            if name == banned or name.startswith(f"{banned}."):
                violations.append(
                    f"{path}:{lineno}: imports '{name}' ({reason}) - prohibited by §31"
                )
    return violations


def main() -> int:
    violations = []
    scanned = 0
    for path in iter_python_files(REPO_ROOT):
        scanned += 1
        violations.extend(check_file(path))

    if violations:
        print("Privacy guard FAILED - README.txt §31 prohibits these capabilities:\n")
        for violation in violations:
            print(f"  {violation}")
        print(
            "\nIf this is a false positive, change the guard deliberately in "
            "scripts/check_privacy.py rather than working around it."
        )
        return 1

    print(f"Privacy guard passed ({scanned} Python files scanned).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
