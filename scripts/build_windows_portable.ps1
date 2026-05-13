$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir

Set-Location $repoRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python is not available in PATH"
}

python -m pip install -r "$repoRoot\requirements-windows.txt"
python -m PyInstaller --noconfirm --clean "$repoRoot\packaging\windows\move-reminder.spec"

Write-Host "Portable build created at: $repoRoot\dist\move-reminder-portable.exe"
