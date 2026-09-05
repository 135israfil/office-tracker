#!/usr/bin/env python
"""Fail the build if the codebase gains a capability README.txt §31 prohibits.

§31 forbids keylogging, screen recording, screenshots, webcam, microphone and
clipboard monitoring. Those are enforced structurally rather than by review: the
libraries that make them possible must never appear in an import.

`uiautomation` is the awkward case, and the reason this file has a second half.
The browser collector cannot read an address bar without it, so it cannot be
banned outright - but the same library can also synthesise keystrokes and grab
bitmaps, which are exactly two of the things §31 rules out. Only its tree-reading
APIs are permitted; the call-level check below rejects the rest by name.

This is a blunt instrument on purpose. If a legitimate need collides with it,
that collision deserves a conversation, not a quiet exemption.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Module names that provide a prohibited capability, mapped to why they are banned.
BANNED_MODULES = {
    "keyboard": "key logging",
    "pynput": "key and mouse logging",
    "mss": "screen capture",
    "pyautogui": "screen capture and input synthesis",
    "pyscreenshot": "screen capture",
    "d3dshot": "screen capture",
    "cv2": "camera capture",
    "sounddevice": "microphone capture",
    "pyaudio": "microphone capture",
    "win32clipboard": "clipboard monitoring",
    "pyperclip": "clipboard monitoring",
}

# Fully-qualified attribute paths that are prohibited even though their root
# package is legitimate (Pillow is fine; Pillow's screen grabber is not).
BANNED_ATTRIBUTES = {
    "PIL.ImageGrab": "screen capture",
}

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
    # Screen capture
    "CaptureToImage": "screen capture",
    "BitmapFromWindow": "screen capture",
    "ToBitmap": "screen capture",
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
