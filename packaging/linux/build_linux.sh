#!/usr/bin/env bash
# Construye el paquete de AulaAudio para Linux (x86_64). DEBE ejecutarse EN LINUX:
# un ejecutable construido en Windows no funciona en Linux ni a la inversa.
# Requisitos: Python 3.10+ con venv, y las bibliotecas de sistema que necesita Qt
# (en Debian/Ubuntu: sudo apt install python3-venv libxcb-cursor0 libpulse0 libegl1).
# Uso:  bash packaging/linux/build_linux.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

python3 -m venv .venv-linux
PY=.venv-linux/bin/python
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r requirements-dev.txt

echo "Ejecutando pruebas..."
QT_QPA_PLATFORM=offscreen "$PY" -m pytest -q -p no:cacheprovider

echo "Generando iconos..."
QT_QPA_PLATFORM=offscreen "$PY" tools/make_icon.py

echo "Construyendo con PyInstaller..."
"$PY" -m PyInstaller packaging/aulaaudio.spec --noconfirm --distpath dist-linux --workpath build-linux

echo "Diagnóstico silencioso del ejecutable..."
TMPD="$(mktemp -d)"
./dist-linux/AulaAudio/AulaAudio --datos "$TMPD" --diagnostico || echo "AVISO: el diagnóstico de audio no fue correcto"

VERSION="$("$PY" -c 'import aulaaudio; print(aulaaudio.__version__)')"
PKG="AulaAudio-${VERSION}-Linux-x86_64"
rm -rf "dist-linux/$PKG"
mkdir -p "dist-linux/$PKG"
cp -r dist-linux/AulaAudio "dist-linux/$PKG/AulaAudio"
cp packaging/aulaaudio.png packaging/linux/aulaaudio.desktop packaging/linux/instalar.sh \
   packaging/linux/desinstalar.sh README.md LICENCIAS_TERCEROS.md "dist-linux/$PKG/"
cp -r docs "dist-linux/$PKG/documentacion"
chmod +x "dist-linux/$PKG/instalar.sh" "dist-linux/$PKG/desinstalar.sh"
tar -C dist-linux -czf "dist-linux/$PKG.tar.gz" "$PKG"
echo "Paquete generado: dist-linux/$PKG.tar.gz"
