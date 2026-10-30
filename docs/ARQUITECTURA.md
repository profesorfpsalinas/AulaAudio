# Arquitectura y decisiones técnicas

## 1. Elección de tecnologías

| Necesidad | Elección | Motivo | Alternativas descartadas |
|---|---|---|---|
| Lenguaje | Python 3.12 | Mantenible, multiplataforma, biblioteca estándar amplia (sqlite3, zoneinfo, wave) | — |
| Interfaz | PySide6 6.11.2 (Qt 6, LGPL) | Oficial de Qt, nativa en Windows y Linux, bandeja del sistema, accesibilidad | Tkinter (pobre en bandeja y estética), Electron (pesado, servidor web) |
| Audio | **QtMultimedia** del propio PySide6 (`QMediaPlayer`, `QAudioOutput`, `QMediaDevices`) | Viene en las ruedas oficiales con backend **FFmpeg** en Windows y Linux (MP3, WAV, OGG, Opus, FLAC, AAC/M4A); permite elegir dispositivo y avisa de conexiones/desconexiones; una dependencia menos | python-vlc (requiere VLC instalado aparte), pygame (sin selección de dispositivo fiable), sounddevice+soundfile (sin MP3 sin códecs extra) |
| Datos | SQLite (biblioteca estándar) en modo WAL | Local, transaccional, resistente a cortes de luz | Archivos JSON (sin transacciones) |
| Planificador | **Propio**, lógica pura con reloj inyectable | Reglas de festivos/cambios de horario/prioridades específicas; probable al segundo con reloj simulado | APScheduler (no modela excepciones ni conflictos; persistencia propia innecesaria) |
| Zonas horarias | `zoneinfo` + paquete `tzdata` | Estándar; `tzdata` es imprescindible en Windows | pytz (obsoleto) |
| Empaquetado | PyInstaller 6.22 (modo carpeta) + Inno Setup 6.7 | Herramientas mantenidas y documentadas; instalador por usuario sin administrador | Nuitka (más lento de construir), MSI/WiX (más complejo) |

Versiones verificadas: se consultaron en PyPI (`pip index versions`) y se comprobó en este equipo
que las APIs usadas existen en PySide6 6.11.2 (`QMediaPlayer.errorOccurred`, `mediaStatusChanged`,
`QMediaDevices.audioOutputsChanged`, `QAudioOutput.setDevice`, `QtAudio.convertVolume`, `QLockFile`).

**Compatibilidad Windows/Linux.** QtMultimedia usa el backend FFmpeg en ambos sistemas desde Qt 6.5;
en Linux necesita PulseAudio o PipeWire (con su capa de compatibilidad Pulse), presentes en las
distribuciones de escritorio habituales. La bandeja del sistema en GNOME requiere la extensión
«AppIndicator»; si no hay bandeja, la ventana no se oculta al cerrar (se pide confirmación para salir).
Evitar la suspensión solo está implementado en Windows (`SetThreadExecutionState`, sin administrador);
en Linux se documenta cómo desactivarla desde los ajustes de energía.

## 2. Módulos

```
aulaaudio/
  app.py          Arranque: argumentos, carpetas, registro, instancia única, BD, copias, ventana
  paths.py        Carpetas separadas de configuración, datos, copias y registros
  config.py       Settings + guardado atómico (temporal + fsync + os.replace) con copia .bak
  models.py       Dataclasses (Event, Track, Playlist, Schedule, CalendarException) y validación
  db.py           SQLite: esquema versionado, migraciones, CRUD con consultas parametrizadas
  scheduler.py    Qué suena cada día (excepciones, horarios alternativos, DST, medianoche)
  engine.py       Motor: temporizador, conflictos, cola, reanudación, errores, acciones manuales
  audio.py        AudioBackend (interfaz), QtAudioBackend (real) y FakeAudioBackend (pruebas)
  library.py      Biblioteca: añadir, comprobar, relocalizar, M3U
  backup.py       Copias .zip validadas, restauración con copia previa automática
  simulation.py   Simulación con el motor real, reloj virtual y copia en memoria de la BD
  system.py       Registro rotativo, inicio automático (HKCU / XDG), evitar suspensión
  sounds.py       Sonido de prueba y sonidos de ejemplo sintetizados
  demo.py         Datos de demostración identificados y desactivados
  ui/             Una pestaña por archivo + diálogos + estilo
```

Flujo: `QTimer` (0,5 s) → `PlaybackEngine.tick()` → `Scheduler.occurrences_between(último, ahora]`
→ reglas de conflicto → `AudioBackend.play()`. El backend avisa con señales (`finished`, `failed`,
`devices_changed`) que llevan un número de reproducción para descartar avisos atrasados.
La interfaz nunca accede al audio directamente: siempre pasa por el motor, que garantiza que solo
haya una reproducción a la vez (incluidas «Escuchar» y «Prueba de sonido»).

## 3. Reglas de reproducción

- Un único flujo de audio. Cada evento tiene prioridad (1–10) y comportamiento ante conflicto:
  **interrumpir** (si su prioridad ≥ la de lo que suena; si no, se omite), **esperar** (cola hasta su
  hora de fin o 10 min) u **omitir**.
- **Reanudación** solo si el evento interrumpido la tiene activada, su franja sigue abierta y la
  interrupción duró menos de 15 min. Lo manual y las pruebas nunca se reanudan.
- **Manual**: prioridad configurable (5). Timbres (8) y avisos (6) la interrumpen; la música (3) no.
- **Detener** vacía también la cola y las reanudaciones: tras pulsarlo, solo vuelve a sonar el
  siguiente evento programado.
- **Arranque**: nunca se reproduce nada pasado. Una franja en curso se ofrece con «Iniciar ahora».
- **Retrasos**: si entre dos comprobaciones pasa más del margen (60 s), los eventos del hueco se
  omiten y se avisa (suspensión, hibernación, bloqueo).
- **Reloj que retrocede**: se continúa desde la nueva hora sin repetir eventos ya sonados.
- **Cambio de hora**: horas locales convertidas a UTC con `zoneinfo`; hora inexistente → una hora
  después; hora repetida → una sola vez (la primera); «duración» = tiempo real.
- **Errores de archivo**: se marca la pista, se registra y se pasa a la siguiente; si falla una vuelta
  entera, la sesión se detiene. **Errores de dispositivo**: un único reintento; después, se detiene
  y se avisa. No hay bucles de reintento ni reinicios automáticos.

## 4. Fiabilidad

- SQLite en WAL con `synchronous=FULL`, transacciones en todas las escrituras, `quick_check` al
  arrancar. Si la base está dañada se ofrece restaurar la copia más reciente y se conserva la dañada.
- Configuración con escritura atómica y copia `.bak`; valores fuera de rango se corrigen.
- Instancia única (`QLockFile`): dos copias abiertas harían sonar dos veces los timbres.
- Copia automática diaria al arrancar (se conservan 14) y copia previa a toda restauración o
  migración de esquema.
- Registro rotativo (1 MB × 5) + historial en la base de datos (180 días).
- Errores inesperados de la interfaz se registran sin cerrar la aplicación (`sys.excepthook`).

## 5. Seguridad (mínimo privilegio)

- Sin administrador: instalación y datos en el perfil del usuario; inicio automático en
  `HKCU\...\Run` (Windows) o `~/.config/autostart` (Linux), solo si se activa expresamente.
- Sin red: no abre puertos, no hay servidor, no hay telemetría, no descarga nada. Las listas M3U
  ignoran direcciones `http://`.
- No ejecuta comandos de shell. Las rutas del inicio automático salen de `sys.executable` y se
  formatean con `subprocess.list2cmdline` (solo formatea) o con escape XDG.
- SQL siempre parametrizado (se prueba con nombres maliciosos). Búsquedas `LIKE` escapadas.
- Validación de entradas en los modelos (longitudes, rangos, fechas) y de rutas (extensión de audio,
  archivo existente, sin seguir enlaces simbólicos al explorar carpetas, límite de 20 000 archivos).
- Copias: nunca sobrescribe (apertura exclusiva `'x'`), valida miembros permitidos (impide rutas
  `../`), tamaño, integridad SQLite y versión de esquema antes de restaurar.
- Mensajes al usuario comprensibles; los detalles técnicos van solo al registro local.
- No se añade autenticación: equipo local de un solo uso sin datos personales; añadir contraseñas
  solo dificultaría el uso sin una amenaza concreta que lo justifique.

## 6. Supuestos tomados (decisiones ambiguas)

1. Precisión de minuto en los horarios (HH:MM), como en los horarios escolares.
2. Zona horaria predeterminada `Europe/Madrid`, configurable.
3. El volumen de un evento es **relativo** al general (70 % = 70 % del volumen general).
4. Los eventos extraordinarios suenan aunque el día sea festivo (son una decisión explícita).
5. Si coinciden un festivo y un cambio de horario, gana el festivo.
6. Si falta el dispositivo elegido, por defecto se usa el predeterminado del sistema y se avisa
   (configurable a «no reproducir»).
7. Un archivo suelto con fin por hora o duración se repite hasta el final; con «al terminar el
   audio» suena una vez.
8. Los datos de ejemplo se crean desactivados para que nada suene sin revisión.

## 7. Limitaciones conocidas

- No suena con el equipo apagado, suspendido, hibernando, con la sesión cerrada o sin corriente.
  Recomendación: SAI, desactivar la suspensión, inicio automático y sesión iniciada.
- Windows puede suspender igualmente por decisión del usuario, por batería crítica o por directivas
  del centro. En Linux la inhibición de suspensión no está implementada.
- Si se cambia el dispositivo predeterminado de Windows durante la reproducción, Qt puede tardar
  unos segundos en cambiar de salida. La reconexión de dispositivos USB/Bluetooth depende del sistema.
- No se verifica si un archivo es decodificable hasta reproducirlo (la comprobación masiva verifica
  existencia y lectura). Use «Escuchar» o la prueba de sonido.
- El paquete de Linux no se ha podido construir ni probar en este entorno de desarrollo (Windows sin
  WSL): el script está preparado y debe ejecutarse en Linux. Ver PRUEBAS.md.
- Solo un dispositivo de salida a la vez (no hay zonas de audio independientes).
