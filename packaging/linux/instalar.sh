#!/usr/bin/env bash
# Instala AulaAudio para el usuario actual, sin sudo.
# Programa: ~/.local/opt/aulaaudio   ·   Datos: ~/.config/aulaaudio y ~/.local/share/aulaaudio
# Una actualización sustituye solo el programa; los datos del centro no se tocan.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/opt/aulaaudio"
if [ -d "$DEST" ]; then
  echo "Actualizando la instalación existente (sus datos se conservan)..."
  rm -rf "$DEST/AulaAudio"
fi
mkdir -p "$DEST" "$HOME/.local/share/applications"
cp -r "$SRC/AulaAudio" "$DEST/"
cp "$SRC/aulaaudio.png" "$SRC/desinstalar.sh" "$DEST/"
[ -d "$SRC/documentacion" ] && cp -r "$SRC/documentacion" "$DEST/"
sed "s|@APPDIR@|$DEST|g" "$SRC/aulaaudio.desktop" > "$HOME/.local/share/applications/aulaaudio.desktop"
chmod +x "$DEST/AulaAudio/AulaAudio"
echo "AulaAudio instalado. Ábralo desde el menú de aplicaciones o con: $DEST/AulaAudio/AulaAudio"
