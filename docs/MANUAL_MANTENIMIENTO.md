# Manual de mantenimiento

## 1. Dónde están los datos

| Contenido | Windows | Linux |
|---|---|---|
| Programa | `%LOCALAPPDATA%\Programs\AulaAudio` | `~/.local/opt/aulaaudio` |
| Configuración (`config.json`, `config.json.bak`) | `%LOCALAPPDATA%\AulaAudio\config` | `~/.config/aulaaudio` |
| Base de datos (`aulaaudio.db`) y sonidos de ejemplo | `%LOCALAPPDATA%\AulaAudio\datos` | `~/.local/share/aulaaudio/datos` |
| Copias de seguridad | `%LOCALAPPDATA%\AulaAudio\copias` | `~/.local/share/aulaaudio/copias` |
| Registros (`aulaaudio.log`, rotativo 1 MB × 5) | `%LOCALAPPDATA%\AulaAudio\registros` | `~/.local/state/aulaaudio/registros` |

Las carpetas se abren desde *Configuración → Datos → Abrir*. La música está donde el centro la
guardó: AulaAudio solo guarda la ruta.

## 2. Copia de seguridad

- **Automática**: una al día al abrir AulaAudio; se conservan las 14 últimas.
- **Manual**: *Copias de seguridad → Crear copia ahora*. Hágala siempre tras cambiar el horario.
- **Fuera del equipo**: *Exportar copia seleccionada…* a un pendrive o carpeta de red, al menos
  al inicio de cada trimestre. Copie también la carpeta de música.
- Una copia (`aulaaudio_copia_FECHA_tipo.zip`) contiene base de datos, configuración y manifiesto;
  nunca sustituye a otra copia existente.

## 3. Restauración

1. *Copias de seguridad* → seleccione la copia → *Restaurar la seleccionada…* (o *desde un archivo…*).
2. Confirme. AulaAudio detiene la reproducción, valida la copia (formato, contenido, integridad y
   versión), guarda el estado actual como copia «Antes de restaurar» y restaura.
3. Si la copia no es válida, se muestra el motivo y **no se modifica nada**.
4. Si los archivos de música están en otra ruta en este equipo: *Biblioteca → Localizar archivos movidos…*.

**Trasladar a otro ordenador**: instale AulaAudio, copie la música, restaure la copia exportada y
use *Localizar archivos movidos…*.

## 4. Actualización

1. Haga una copia manual y expórtela.
2. Ejecute el instalador de la nueva versión (cierra AulaAudio si está abierto). En Linux, `./instalar.sh`
   del paquete nuevo.
3. El instalador sustituye solo el programa. Los datos no se tocan. Si la nueva versión necesita
   actualizar la base de datos, antes crea automáticamente una copia «Antes de actualizar».
4. Abra AulaAudio, revise *Inicio* y haga una *Simulación* del día siguiente.

Para volver a la versión anterior: reinstálela y restaure la copia «Antes de actualizar» (una base
de datos de una versión más moderna no se abre en una anterior, para evitar dañarla).

## 5. Desinstalación

- **Windows**: *Configuración → Aplicaciones → AulaAudio → Desinstalar* (o *Desinstalar AulaAudio*
  en el menú Inicio). El desinstalador **pregunta** si se eliminan también los datos:
  - **No** (predeterminado): se conservan programación, copias y registros para reinstalar.
  - **Sí**: se borra `%LOCALAPPDATA%\AulaAudio`. La música nunca se borra.
  También se elimina el inicio automático si estaba activado.
- **Linux**: `bash ~/.local/opt/aulaaudio/desinstalar.sh`. Para borrar también los datos hay que
  escribir `SI` explícitamente; si no, se conservan.

## 6. Registros e historial

- *Historial e incidencias* muestra los últimos 2 000 registros (se conservan 180 días; ajustable).
- El archivo `aulaaudio.log` guarda los detalles técnicos y rota solo (máximo ~6 MB).
- `AulaAudio.exe --diagnostico` (o `python -m aulaaudio --diagnostico`) prueba el audio en
  silencio y escribe `registros/diagnostico.txt`: adjúntelo al pedir ayuda.

## 7. Recuperación ante fallos

| Síntoma | Qué hacer |
|---|---|
| **No suena nada** | 1) Estado en *Inicio*: si pone *Detenido*, active la automatización. 2) *Prueba de sonido*. 3) Volumen de Windows/Linux, del amplificador y su entrada seleccionada; cable bien insertado. 4) *Configuración → Dispositivo de salida*. 5) Ejecute el diagnóstico. |
| Suena por los altavoces del portátil y no por la megafonía | Elija el dispositivo correcto en *Configuración* o márquelo como predeterminado en Windows. Si el elegido se desconectó, AulaAudio usa el predeterminado y avisa (o no reproduce, según la opción). |
| «No hay ningún dispositivo de salida» | Conecte altavoces/tarjeta; en Windows revise *Configuración → Sistema → Sonido*. AulaAudio se recupera solo cuando el dispositivo vuelve. |
| «No se encuentra el archivo» | *Biblioteca → Comprobar archivos* y *Localizar archivos movidos…*. Si estaban en un pendrive o en red, conéctelo. |
| «El archivo no se puede reproducir» | Archivo dañado o formato no admitido: conviértalo a MP3 o WAV. |
| Un timbre no sonó | *Historial*: busque «Omitido». Motivos: equipo suspendido/apagado, prioridad menor que lo que sonaba, festivo, evento desactivado. Use *Consultar una fecha* y *Simulación*. |
| Aviso «ha estado sin funcionar X min» | El equipo se suspendió o bloqueó. Desactive la suspensión; deje activado *Impedir que el equipo se suspenda*. |
| «AulaAudio ya está abierto» | Ya hay una copia en la bandeja. Si no aparece, reinicie la sesión. |
| La configuración se ha restablecido | El archivo estaba dañado; se recuperó la copia `.bak` o los valores por defecto (queda en el historial). Revise *Configuración*. |
| **Base de datos dañada** al abrir | AulaAudio ofrece restaurar la copia más reciente. El archivo dañado se conserva como `aulaaudio.db.danada_FECHA`. Si no hay copias, exporte el registro y contacte con el responsable TIC. |
| La aplicación se cierra sola | Ábrala de nuevo (no hay reinicios automáticos para evitar sonidos inesperados). Revise `aulaaudio.log` (líneas `CRITICAL`). |
| Hora incorrecta | Sincronice el reloj del sistema y compruebe la zona horaria en *Configuración*. |

**Tras un corte de luz**: al volver la corriente, encienda el equipo (o configure en la BIOS
*Restore on AC power loss: Power On*). Con el inicio automático, AulaAudio vuelve a funcionar al
iniciar sesión; los eventos perdidos no se reproducen tarde.
