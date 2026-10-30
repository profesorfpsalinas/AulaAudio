# Construye AulaAudio para Windows: pruebas -> PyInstaller -> instalador Inno Setup.
# Uso (desde la raíz del proyecto, en PowerShell):
#   powershell -ExecutionPolicy Bypass -File packaging\windows\build_windows.ps1
$ErrorActionPreference = "Stop"
$root = Resolve-Path "$PSScriptRoot\..\.."
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creando entorno virtual..."
    python -m venv .venv
}
$py = ".venv\Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements-dev.txt

Write-Host "Ejecutando pruebas..."
& $py -m pytest -q -p no:cacheprovider
if ($LASTEXITCODE -ne 0) { throw "Las pruebas han fallado: no se construye el paquete." }

Write-Host "Generando iconos..."
& $py tools\make_icon.py

Write-Host "Construyendo con PyInstaller..."
& $py -m PyInstaller packaging\aulaaudio.spec --noconfirm --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { throw "PyInstaller ha fallado." }

Write-Host "Comprobando el ejecutable (diagnóstico silencioso)..."
$tmp = Join-Path $env:TEMP "aulaaudio_build_check"
$p = Start-Process "dist\AulaAudio\AulaAudio.exe" -ArgumentList "--datos", "`"$tmp`"", "--diagnostico" -Wait -PassThru
Get-Content (Join-Path $tmp "registros\diagnostico.txt") -Encoding utf8
if ($p.ExitCode -ne 0) { Write-Warning "El diagnóstico de audio no fue correcto (¿hay dispositivo de salida?)." }

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    Write-Warning "No se encuentra Inno Setup 6. Instálelo (winget install JRSoftware.InnoSetup --scope user) y repita."
    Write-Host "La versión portable está en dist\AulaAudio."
    exit 0
}
& $iscc "packaging\windows\AulaAudio.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup ha fallado." }
Write-Host "Instalador generado en dist\instalador"
