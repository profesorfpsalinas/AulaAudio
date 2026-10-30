#!/usr/bin/env bash
# Desinstala AulaAudio del usuario actual. Pregunta explícitamente si se borran los datos.
set -euo pipefail
rm -rf "$HOME/.local/opt/aulaaudio"
rm -f "$HOME/.local/share/applications/aulaaudio.desktop" "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/aulaaudio.desktop"
echo "Programa desinstalado."
CONF="${XDG_CONFIG_HOME:-$HOME/.config}/aulaaudio"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/aulaaudio"
STATE="${XDG_STATE_HOME:-$HOME/.local/state}/aulaaudio"
echo
echo "Los datos (programación, calendario, copias de seguridad y registros) están en:"
echo "  $CONF"; echo "  $DATA"; echo "  $STATE"
read -r -p "¿Desea ELIMINAR también los datos? Escriba SI para borrarlos [no]: " answer
if [ "$answer" = "SI" ]; then
  rm -rf "$CONF" "$DATA" "$STATE"
  echo "Datos eliminados. Sus archivos de música no se han tocado."
else
  echo "Datos conservados."
fi
