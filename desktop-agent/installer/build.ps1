# Build the agent executable and the installer (Phase 9).
#
#   cd desktop-agent
#   .\installer\build.ps1
#   .\installer\build.ps1 -SkipInstaller     # exe only, no Inno Setup needed
#
# Windows only. PyInstaller cross-compilation does not exist — a Windows exe must be
# built on Windows — so this is a .ps1 rather than something CI can run on Linux.

[CmdletBinding()]
param(
    [switch]$SkipInstaller,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "== Checking the build environment ==" -ForegroundColor Cyan
& $Python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not installed. Run: $Python -m pip install -r requirements-dev.txt"
}

# A package missing from *this* interpreter is invisible to PyInstaller's own checks: a
# module imported only inside a function body (agent.tray's `import pystray`, done lazily
# so headless mode never pays for it) is not a hard error at build time even when
# unresolvable — PyInstaller logs it to warn-agent.txt and ships an exe that raises
# ModuleNotFoundError the first time a user actually opens the tray. The --version smoke
# test below never reaches that code path, so a build like that still looks green.
# Importing every runtime dependency up front catches it before packaging starts.
Write-Host "== Checking runtime dependencies are installed ==" -ForegroundColor Cyan
$runtimeModules = @("requests", "keyring", "psutil", "pystray", "PIL", "win32api", "uiautomation")
$missing = @()
foreach ($module in $runtimeModules) {
    & $Python -c "import $module" 2>$null
    if ($LASTEXITCODE -ne 0) { $missing += $module }
}
if ($missing.Count -gt 0) {
    throw "The build interpreter is missing: $($missing -join ', '). Run: $Python -m pip install -r requirements-dev.txt (in the same environment $Python resolves to)."
}

$version = (& $Python -c "from agent.version import __version__; print(__version__)").Trim()
Write-Host "Agent version $version"
$env:AGENT_VERSION = $version

# The privacy guard runs against the source before anything is packaged. Shipping a
# binary that was never checked would defeat the point of checking at all (README §31).
Write-Host "== Privacy guard ==" -ForegroundColor Cyan
& $Python (Join-Path (Split-Path -Parent $root) "scripts\check_privacy.py")
if ($LASTEXITCODE -ne 0) { throw "Privacy guard failed. Not building." }

Write-Host "== Tests ==" -ForegroundColor Cyan
& $Python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed. Not building." }

Write-Host "== Version resource ==" -ForegroundColor Cyan
& $Python installer\make_version_info.py

Write-Host "== PyInstaller ==" -ForegroundColor Cyan
& $Python -m PyInstaller installer\agent.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

$exe = Join-Path $root "dist\OfficeTrackerAgent.exe"
if (-not (Test-Path $exe)) { throw "Expected $exe, which is not there." }

# A built exe that cannot answer --version is a broken build, and finding that out on
# the first machine of a rollout is the expensive way to find it out.
Write-Host "== Smoke test ==" -ForegroundColor Cyan
$reported = (& $exe --version 2>&1 | Out-String).Trim()
if ($reported -ne $version) {
    throw "The built exe reports '$reported' but the source says '$version'."
}
Write-Host "  $exe reports $reported" -ForegroundColor Green

if ($SkipInstaller) {
    Write-Host "Done (installer skipped)." -ForegroundColor Green
    exit 0
}

Write-Host "== Inno Setup ==" -ForegroundColor Cyan
$iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
    foreach ($candidate in @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
        # winget installs Inno Setup per-user by default, which is neither of the above.
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $candidate) { $iscc = $candidate; break }
    }
}
if (-not $iscc) {
    throw "Inno Setup 6 (ISCC.exe) was not found. Install it, or pass -SkipInstaller."
}

& $iscc installer\OfficeTracker.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed." }

Write-Host "Built dist\OfficeTrackerSetup-$version.exe" -ForegroundColor Green
Write-Host ""
Write-Host "Unsigned builds trip SmartScreen. Sign before rollout, or use the" -ForegroundColor Yellow
Write-Host "IT-managed silent install documented in docs/deployment-runbook.md." -ForegroundColor Yellow
