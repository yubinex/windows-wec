# Builds dist\WindowsWEC.exe, a single file you can hand to people.
# Run from the project root:  powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = if (Test-Path .venv\Scripts\python.exe) { ".venv\Scripts\python.exe" } else { "python" }
& $python -m pip install --quiet -r requirements.txt pyinstaller

# Render the app icon (the same generic badge as the tray) to an .ico.
New-Item -ItemType Directory -Force build | Out-Null
& $python -c "from wec_tray.icon import make_icon; make_icon('WEC', 'idle').save('build/WindowsWEC.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64)])"

& $python -m PyInstaller --noconfirm --clean --onefile --noconsole `
    --name WindowsWEC --icon build\WindowsWEC.ico `
    --add-data "wec_tray\flags;wec_tray\flags" run_wec_tray.py

Write-Host "Built dist\WindowsWEC.exe"
