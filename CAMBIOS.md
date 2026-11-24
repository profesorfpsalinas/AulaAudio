# Novedades

## 1.2.0

- **Música libre para recreos**: 8 piezas instrumentales originales (unos 19 minutos; pop, lo-fi,
  funky, estilo videojuego y ambiente) en dominio público (CC0). Se pueden reproducir en el centro
  sin licencias. Botón en *Biblioteca de audio* que crea la lista «Recreo — música libre».
- `tools/componer_musica.py`: el compositor que las genera, para regenerarlas o crear más.

## 1.1.0

- **Vacaciones y festivos mejorados.** En cada periodo se elige qué se suspende: la programación
  de sonidos, el apagado del equipo, o ambos. Si coinciden varios, se aplica el más restrictivo.
- **`vacaciones.json`**: importar (añadir o sustituir, con copia de seguridad previa y validación
  «todo o nada») y exportar (conserva el archivo anterior como `.bak`). Ver
  [docs/VACACIONES.md](docs/VACACIONES.md).
- **Duplicar para el año siguiente** los periodos seleccionados.
- **Avisos de periodos solapados**, al guardarlos y en la lista.
- **Apagado programado del equipo** (opcional, desactivado por defecto): hora, días y aviso previo
  con cuenta atrás cancelable. Se suspende en vacaciones y festivos, si la automatización está
  detenida y si no se puede leer la programación. Nunca apaga con retraso.
- El calendario muestra en azul los días en los que solo se suspende el apagado, y al consultar un
  día indica si el equipo se apagará.
- La base de datos se actualiza sola desde la 1.0 (con copia «Antes de actualizar»).

## 1.0.0

Primera versión publicada.
