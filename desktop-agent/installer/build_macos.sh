#!/usr/bin/env bash
# Build the agent .app and wrap it in a .dmg (macOS port of build.ps1's pipeline).
#
#   cd desktop-agent
#   ./installer/build_macos.sh
#   ./installer/build_macos.sh --skip-dmg     # .app only, no hdiutil needed
#
# macOS only. PyInstaller cross-compilation does not exist — a macOS build must be
# built on macOS — so this runs on a GitHub Actions macos-latest runner, not from the
# Windows side of this repo.
set -euo pipefail

PYTHON="${PYTHON:-python3}"
SKIP_DMG=0
for arg in "$@"; do
  case "$arg" in
    --skip-dmg) SKIP_DMG=1 ;;
    *) echo "Unknown argument: $arg" >&2; exit 1 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== Checking the build environment =="
if ! "$PYTHON" -c "import PyInstaller" >/dev/null 2>&1; then
  echo "PyInstaller is not installed. Run: $PYTHON -m pip install -r requirements-dev.txt" >&2
  exit 1
fi

# Same reasoning as build.ps1: a module imported lazily inside a function (agent.tray's
# `import pystray`, agent.collectors.*'s `import AppKit`/`import Quartz`) is invisible to
# PyInstaller's own static checks even when unresolvable, and ships a .app that fails the
# first time a user actually triggers that code path. Importing every runtime dependency
# up front catches it before packaging starts.
echo "== Checking runtime dependencies are installed =="
missing=()
for module in requests keyring psutil pystray PIL AppKit Quartz ApplicationServices Foundation; do
  if ! "$PYTHON" -c "import $module" >/dev/null 2>&1; then
    missing+=("$module")
  fi
done
if [ "${#missing[@]}" -gt 0 ]; then
  echo "The build interpreter is missing: ${missing[*]}. Run: $PYTHON -m pip install -r requirements-dev.txt (in the same environment $PYTHON resolves to)." >&2
  exit 1
fi

version=$("$PYTHON" -c "from agent.version import __version__; print(__version__)")
echo "Agent version $version"
export AGENT_VERSION="$version"

echo "== Privacy guard =="
"$PYTHON" "$(dirname "$ROOT")/scripts/check_privacy.py"

echo "== Tests =="
"$PYTHON" -m pytest -q

echo "== PyInstaller =="
"$PYTHON" -m PyInstaller installer/agent.spec --noconfirm --clean

app="dist/OfficeTrackerAgent.app"
if [ ! -d "$app" ]; then
  echo "Expected $app, which is not there." >&2
  exit 1
fi

# A built .app that cannot answer --version is a broken build, and finding that out on
# the first machine of a rollout is the expensive way to find it out.
echo "== Smoke test =="
reported=$("$app/Contents/MacOS/OfficeTrackerAgent" --version)
if [ "$reported" != "$version" ]; then
  echo "The built app reports '$reported' but the source says '$version'." >&2
  exit 1
fi
echo "  $app reports $reported"

if [ "$SKIP_DMG" -eq 1 ]; then
  echo "Done (dmg skipped)."
  exit 0
fi

echo "== Packaging the .dmg =="
dmg="dist/OfficeTrackerSetup-$version.dmg"
rm -f "$dmg"
staging=$(mktemp -d)
trap 'rm -rf "$staging"' EXIT
cp -R "$app" "$staging/"
ln -s /Applications "$staging/Applications"
hdiutil create -volname "Office Tracker" -srcfolder "$staging" -ov -format UDZO "$dmg"

echo "Built $dmg"
echo
echo "Unsigned build: no Apple Developer ID yet, so this is not notarized."
echo "Gatekeeper will block the first launch - right-click the app and choose Open"
echo "to run it anyway, instead of double-clicking."
