# AulaAudio

Programa de escritorio para que un centro educativo reproduzca **automáticamente** la música
ambiental, los timbres y los avisos según un horario semanal, con festivos y cambios de horario.

Pensado para personal sin conocimientos técnicos: todo se hace desde la ventana, en español,
sin servidor, sin cuentas, sin Internet y sin permisos de administrador.

## Funciones principales

- **Inicio**: estado (funcionando / detenido / incidencia), reloj, próximo evento, lo que suena,
  botones grandes de reproducir, pausar, reanudar y detener, volumen y prueba de sonido.
- **Programación**: eventos semanales (música, timbre, aviso) con días, hora, fin (al terminar el
  audio, tras X minutos o a una hora), archivo o lista, volumen propio, prioridad y qué hacer si
  coincide con otro. Crear, editar, duplicar, activar/desactivar, eliminar, copiar un día a otros.
  Varios horarios (ordinario, jornada reducida…). Vista semanal y próximas 24 horas.
- **Biblioteca de audio**: añadir archivos y carpetas (sin copiarlos ni moverlos), buscar,
  escuchar, listas secuenciales o aleatorias con repetición, ordenar, importar/exportar M3U,
  comprobar archivos y localizar de nuevo los que se hayan movido.
- **Calendario y excepciones**: festivos, vacaciones, días no lectivos, cambios de horario y
  eventos extraordinarios de una fecha. Consultar qué sonará cualquier día. **Simulación**: recorre
  virtualmente un día con las reglas reales sin emitir sonido.
- **Configuración**: dispositivo de salida, volumen, fundido, inicio automático, bandeja del
  sistema, evitar suspensión, zona horaria, copias automáticas, datos de ejemplo.
- **Historial e incidencias** y **Copias de seguridad / restauración**.

## Descarga

Descargue la última versión desde la página de
[**Releases**](../../releases/latest):

- **Windows**: descargue y ejecute `AulaAudio-1.0.0-Windows-instalador.exe` (no pide administrador).
  Si Windows SmartScreen avisa de «editor desconocido», pulse *Más información → Ejecutar de todas formas*.

## Inicio rápido

- **Windows**: ejecute `AulaAudio-1.0.0-Windows-instalador.exe` (no pide administrador).
- **Linux**: descomprima `AulaAudio-1.0.0-Linux-x86_64.tar.gz` y ejecute `./instalar.sh`.
- **Desde el código fuente** (Windows o Linux, Python 3.10 o superior; probado con 3.12):

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    ·    Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m aulaaudio
```

## Documentación

| Documento | Contenido |
|---|---|
| [docs/INSTALACION.md](docs/INSTALACION.md) | Instalación, ejecución en desarrollo y construcción de instaladores |
| [docs/CONFIGURACION_INICIAL.md](docs/CONFIGURACION_INICIAL.md) | Conexión al equipo de sonido (minijack/RCA), primera prueba y primer horario |
| [docs/MANUAL_USUARIO.md](docs/MANUAL_USUARIO.md) | Uso diario de cada pestaña y reglas de reproducción |
| [docs/MANUAL_MANTENIMIENTO.md](docs/MANUAL_MANTENIMIENTO.md) | Copias, restauración, actualización, desinstalación, registros y **recuperación ante fallos** |
| [docs/LISTA_PUESTA_EN_MARCHA.md](docs/LISTA_PUESTA_EN_MARCHA.md) | Lista de comprobación para el centro |
| [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md) | Decisiones técnicas, módulos, seguridad y limitaciones |
| [docs/PRUEBAS.md](docs/PRUEBAS.md) | Pruebas automatizadas y resultados reales |
| [LICENCIAS_TERCEROS.md](LICENCIAS_TERCEROS.md) | Licencias y **derechos de reproducción pública de la música** |

## Limitaciones importantes

- AulaAudio **solo puede sonar si el ordenador está encendido, despierto y con la sesión
  iniciada** y el programa abierto. No puede garantizar ningún evento si el equipo está apagado,
  suspendido, hibernando o sin corriente. Los eventos perdidos **no** se reproducen con retraso.
- Si el ordenador se apaga a mitad de jornada, al volver a abrirlo se continúa con los eventos
  siguientes; si en ese momento hay una franja en curso (p. ej. el recreo), se ofrece
  «Iniciar ahora» pero no empieza sola.
- La precisión es de ±1 segundo aproximadamente, y depende de que el reloj del equipo esté en hora
  (Windows y Linux lo sincronizan solos si hay red).

## Datos de demostración

Al abrir por primera vez se puede cargar un horario de ejemplo. Todos sus elementos llevan el
prefijo **[EJEMPLO]**, usan sonidos sintetizados por el propio programa, se crean **desactivados**
y se eliminan de una vez en *Configuración → Eliminar datos de ejemplo*.

## Estructura del proyecto

```
aulaaudio/            código de la aplicación
  ui/                 interfaz gráfica (una pestaña por archivo)
  scheduler.py        cálculo de horarios (lógica pura)
  engine.py           motor de reproducción (prioridades, conflictos, recuperación)
  audio.py            salida de audio (QtMultimedia) y backend simulado
  db.py · models.py   base de datos SQLite y validación
  backup.py · library.py · config.py · simulation.py · system.py · sounds.py · demo.py
tests/                pruebas automatizadas (reloj simulado, sin sonido)
packaging/            PyInstaller, instalador de Windows (Inno Setup) y paquete de Linux
docs/                 manuales
tools/make_icon.py    generación del icono
```

## Licencia

AulaAudio es software libre, distribuido bajo la licencia **GNU GPL v3.0**
(véase [LICENSE](LICENSE)). Puede usarlo, copiarlo, modificarlo y redistribuirlo, siempre que
las versiones modificadas que distribuya mantengan la misma licencia y su código fuente.
Las licencias de los componentes de terceros se detallan en
[LICENCIAS_TERCEROS.md](LICENCIAS_TERCEROS.md).
