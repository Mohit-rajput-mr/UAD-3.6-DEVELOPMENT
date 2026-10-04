# Install the UAD 3.6 WinTOTAL MOD on this device.
#
#   powershell -ExecutionPolicy Bypass -File setup\install.ps1
#
# What it does, and nothing else:
#   1. checks Python 3.11+ is installed (it does NOT install Python -- if it is
#      missing it tells you the one command to run, which needs your consent)
#   2. installs the Python packages in setup\requirements.txt
#   3. seeds the AI agent's memory for this folder (setup\seed_memory.ps1)
#   4. runs setup\check.py --tests and prints what is ready
#
# Nothing in WinTOTAL is modified.  The MOD talks to TOTAL through the
# debugging port a la mode ship enabled in TOTAL's browser component
# (127.0.0.1:8088).  TOTAL must be running with a UAD 3.6 report open for the
# last check to pass.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "Python is not installed (or not on PATH)." -ForegroundColor Yellow
    Write-Host "Install it, then run this script again:" -ForegroundColor Yellow
    Write-Host "    winget install -e --id Python.Python.3.12"
    Write-Host "(or python.org -- tick 'Add python.exe to PATH')"
    exit 1
}
$ver = & python -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ([version]$ver -lt [version]'3.11') {
    Write-Host "Python $ver is too old; 3.11 or newer is needed." -ForegroundColor Yellow
    Write-Host "    winget install -e --id Python.Python.3.12"
    exit 1
}
Write-Host "Python $ver found."

Write-Host "Installing packages ..."
& python -m pip install --upgrade pip | Out-Null
& python -m pip install -r "$root\setup\requirements.txt"
if ($LASTEXITCODE -ne 0) { Write-Host "pip failed -- see the messages above." -ForegroundColor Red; exit 1 }

Write-Host "Seeding the agent's memory for this folder ..."
& powershell -ExecutionPolicy Bypass -File "$root\setup\seed_memory.ps1"

Write-Host ""
Write-Host "Checking the device ..."
& python "$root\setup\check.py" --tests
exit $LASTEXITCODE
