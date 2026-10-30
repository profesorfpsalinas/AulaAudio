# Pruebas y resultados

Todas las pruebas usan un **reloj simulado** (no esperan a la hora real), un **backend de audio
silencioso** (no emiten sonido), carpetas temporales y no modifican la configuración del sistema
operativo (el inicio automático se prueba en una carpeta XDG temporal; el Registro de Windows no se
escribe en las pruebas).

```bash
python -m pytest                 # todas (plataforma Qt «offscreen»)
python -m pytest -o addopts="" -v
```

## Resultados reales (26/10/2026 · Windows 11 Pro 10.0.26300 · Python 3.12.10 · PySide6 6.11.2)

**110 superadas, 1 omitida, 0 fallidas** (≈7 s).

Corrección posterior a la entrega 1.0.0: la ventana «Evento» no se podía usar porque un atributo
llamado `event` tapaba el método `QWidget.event()` de Qt. Corregido y cubierto con 4 pruebas nuevas
que abren la ventana y guardan eventos (nuevo, música sin listas, edición, evento extraordinario).

La prueba omitida (`test_cerrar_ventana_no_detiene_la_programacion`) necesita bandeja del sistema,
que no existe en la plataforma *offscreen*. Se ejecutó aparte con la plataforma gráfica real de
Windows (`QT_QPA_PLATFORM=windows python -m pytest tests/test_ui.py`): **13 de 13 superadas**.

## Cobertura de los requisitos

| # | Requisito | Archivo · pruebas principales |
|---|---|---|
| 1 | Crear, editar y eliminar eventos | `test_events_db.py`: crear/editar/eliminar, duplicar, desactivar, 7 validaciones, copiar día |
| 2 | Cálculo del siguiente evento | `test_scheduler.py`: siguiente evento (mismo día y fin de semana), sin eventos, desactivados |
| 3 | Recurrencia semanal | `test_recurrencia_semanal`, `test_orden_por_hora_y_prioridad` |
| 4 | Excepciones y festivos | festivo, vacaciones de varios días, cambio de horario, festivo prevalece, evento extraordinario en festivo, simulación con festivo |
| 5 | Conflictos | interrumpe y reanuda, sin reanudar, fuera de franja, menor prioridad, esperar/omitir, espera caducada, nunca dos a la vez, manual vs timbre/música, detener vacía la cola |
| 6 | Medianoche | `test_evento_que_cruza_la_medianoche`, `test_evento_a_medianoche`, `test_motor_cruza_la_medianoche` |
| 7 | Cambio de hora | hora inexistente (29/03/2026), hora repetida (25/10/2026), duración real, 08:00 antes/después, motor en ambos cambios |
| 8 | Reinicio | eventos pasados no suenan, franja en curso ofrecida sin arrancar, reinicio completo con BD en disco, suspensión, reloj que retrocede |
| 9 | Archivos inexistentes | se salta, todos faltan (se detiene sin bucle), archivo dañado, evento sin audio |
| 10 | Dispositivos no disponibles | sin dispositivo no se reproduce, un único reintento, dispositivo que vuelve |
| 11 | Copias y restauración | crear/restaurar (+copia previa), no sobrescribe, poda automática, zip inválido, rutas `../`, versión futura, BD dañada |
| 12 | Persistencia de configuración | persistencia, recuperación desde `.bak`, valores por defecto, rangos, escritura atómica |
| 13 | Errores de base de datos | BD corrupta, esquema futuro, BD cerrada, transacción deshecha, inyección SQL tratada como texto |
| 14 | Interfaz ↔ motor | crear/editar eventos con la ventana «Evento» (semanal, música sin listas, extraordinario), estado inicial, evento visible y botones pausa/reanudar/detener, botón de automatización (se guarda), prueba de sonido, incidencia visible y «Entendido», «Iniciar ahora», tabla y desactivar, volumen, cierre a bandeja |

## Verificaciones manuales realizadas en este equipo

| Verificación | Resultado |
|---|---|
| Backend real QtMultimedia a volumen 0: WAV hasta el final, archivo inexistente, MP3 dañado | Fin detectado; «No se ha podido abrir el archivo»; «Formato de audio no compatible» |
| Detección de dispositivos | Se detectaron unos auriculares Bluetooth conectándose y desconectándose entre ejecuciones |
| Arranque completo de la interfaz y capturas de las 7 pestañas | Correcto, sin errores en el registro |
| Prueba de extremo a extremo con reloj acelerado ×30 (`--modo-simulacion`) | El timbre de las 08:30 se inició a su hora virtual; la música en curso no arrancó sola |
| Simulación por línea de comandos (`--simular`) | Correcta |
| Ejecutable PyInstaller: `--diagnostico` | «Reproducción de prueba (silenciosa): correcto» |
| Ejecutable: instancia única y cierre forzado del proceso | La 2.ª instancia se rechaza; la BD queda íntegra tras matar el proceso |
| Instalador: instalación silenciosa en carpeta temporal, diagnóstico del programa instalado, desinstalación silenciosa | Correcto; el programa y los accesos se eliminan; los datos no se tocan |
| `packaging/windows/build_windows.ps1` completo | Pruebas → PyInstaller → diagnóstico → instalador: correcto |

## Pendiente de verificar

- **Paquete de Linux**: no se ha podido construir ni probar (el entorno es Windows sin WSL). Ejecute
  `bash packaging/linux/build_linux.sh` en Linux x86_64: el script ejecuta las mismas pruebas y el
  diagnóstico antes de empaquetar.
- Desinstalación interactiva de Windows respondiendo «Sí» a borrar datos (la ruta silenciosa, que
  conserva los datos, sí se ha probado).
- Escritura real en `HKCU\...\Run` del inicio automático (no se ha modificado el Registro del equipo
  de desarrollo; se ha comprobado la orden generada).
- Prueba de una jornada completa en tiempo real con el equipo de sonido del centro.
