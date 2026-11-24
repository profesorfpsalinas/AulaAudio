# Manual de usuario

## Inicio

- **Estado** (franja de color):
  - Verde **Funcionando**: los eventos sonarán a su hora.
  - Naranja **Detenido**: la automatización está desactivada; no sonará nada programado.
  - Rojo **Incidencia**: hay un problema (falta un archivo, no hay altavoces…). Lea el mensaje,
    resuélvalo y pulse **Entendido**. Queda anotado en *Historial*.
- **Próximo evento**, **Sonando ahora** y **Próximas 24 horas**.
- **Reproducir…**: suena una lista o un archivo a mano. Si ya suena algo, se le pedirá confirmación.
- **Pausar / Reanudar / Detener**. *Detener* también cancela lo que estuviera esperando; después
  solo sonará el siguiente evento programado.
- **Volumen general** y **Prueba de sonido**.
- **Activar / Desactivar automatización**: sin borrar nada de la programación.
- Si abre AulaAudio en mitad de una franja (por ejemplo, durante el recreo), aparece un aviso con
  **Iniciar ahora**. Por seguridad, nunca empieza sola.

Al cerrar la ventana, AulaAudio **sigue funcionando** en la bandeja del sistema (junto al reloj).
Para salir de verdad: clic derecho en el icono → *Salir de AulaAudio…*.

## Programación

- **Horario**: el *Horario ordinario* se usa todos los días salvo excepciones. Puede crear otros
  (*Nuevo horario…*, *Duplicar…*) para jornada reducida, día del centro, etc.
- **Nuevo evento / Editar** (doble clic) / **Duplicar** / **Activar/desactivar** / **Eliminar**.
- **Copiar un día a otros…**: hace que los días elegidos tengan los mismos eventos que el día de
  origen. Con *Sustituir*, los eventos que ya tuvieran esos días dejan de sonar en ellos.
- **Vista semanal** (con flechas para otras semanas) y **Próximas 24 horas** muestran lo que sonará
  realmente, con festivos y cambios de horario aplicados.

### Campos de un evento

| Campo | Significado |
|---|---|
| Tipo | Música, Timbre o Aviso (ajusta valores recomendados) |
| Cuándo | Cada semana (días marcados) o una fecha concreta (evento extraordinario) |
| Hora de inicio | HH:MM |
| Finaliza | *Al terminar el audio* (una vez), *Tras una duración* o *A una hora* (si es anterior al inicio, termina al día siguiente) |
| Audio | Un archivo o una lista |
| Volumen propio | % del volumen general (opcional) |
| Prioridad | 1–10. Recomendado: música 3, avisos 6, timbres 8 |
| Si ya suena algo | *Interrumpir* (solo si su prioridad es igual o mayor), *Esperar* o *No reproducirse* |
| Reanudar | Si lo interrumpe otro evento, continúa después, dentro de su franja |

### Reglas de reproducción

1. Nunca suenan dos cosas a la vez.
2. Un timbre (8) que llega durante la música del recreo (3) la interrumpe; al acabar el timbre la
   música continúa por donde iba si tiene *Reanudar* y aún está en su franja (máx. 15 min de corte).
3. Un evento de menor prioridad con *Interrumpir* no corta a uno de mayor prioridad: se omite.
4. La reproducción manual tiene prioridad 5 (configurable): la cortan timbres y avisos, no la música
   programada, y no se reanuda sola.
5. Si el equipo estuvo suspendido o apagado, lo que no sonó **no** se reproduce tarde.
6. Cambio de hora: los eventos suenan a la hora del reloj. Un evento a las 02:30 la noche del
   adelanto suena a las 03:30; la noche del retraso suena una sola vez.

## Biblioteca de audio

- *Añadir archivos…* / *Añadir carpeta…*: AulaAudio no copia ni mueve sus archivos.
  Formatos: MP3, WAV, OGG, Opus, FLAC, M4A/AAC (y WMA en Windows).
- *Buscar*, *Escuchar* (doble clic), *Parar*.
- *Comprobar archivos*: marca los que faltan. *Localizar archivos movidos…*: si movió la carpeta de
  música (o cambió la letra del pendrive/disco), elija la nueva ubicación y se encuentran por nombre
  y tamaño.
- *Quitar de la biblioteca*: no borra el archivo del disco (avisa si lo usa algún evento).
- Listas: *Nueva*, *Renombrar*, *Duplicar*, *Eliminar*, orden *Secuencial/Aleatorio*, *Repetir*,
  *Subir/Bajar*, *Importar/Exportar M3U*.

### Música libre para recreos

El botón **🎵 Añadir música libre para recreos** añade 8 piezas instrumentales originales
(unos 19 minutos) y crea la lista **«Recreo — música libre»**, aleatoria y con repetición. Para
usarla, cree en *Programación* un evento de tipo Música a la hora del recreo, elija esa lista y el
fin «A una hora concreta». Las piezas se copian a la carpeta de datos del centro, así que no se
pierden al actualizar el programa. Pulsar el botón otra vez no duplica nada (y recupera las piezas
que se hubieran borrado).

| Pieza | Estilo | Duración |
|---|---|---|
| Patio soleado | Pop alegre | 2:12 |
| Bocadillo a la carrera | Videojuego clásico | 2:33 |
| Siesta de nubes | Lo-fi tranquilo | 2:46 |
| Rayuela | Funky | 2:19 |
| Brisa en el pasillo | Ambiente suave | 2:28 |
| Vuelta a clase | Pop con marimba | 2:11 |
| Canicas | Pop enérgico | 2:19 |
| Merienda tranquila | Lo-fi cálido | 2:34 |

Son obras originales en **dominio público (CC0)**: se pueden reproducir en público sin licencias.
El justificante (`LEEME.txt`) se guarda junto a las piezas.

## Calendario y excepciones

- **Festivos, vacaciones y cambios**: *Festivo*, *Vacaciones* y *Día no lectivo*; *Cambio de
  horario* usa otro horario esos días. En cada periodo se elige **qué se suspende**:
  - *Silenciar la programación de sonidos*: no suena ningún evento semanal.
  - *No apagar el equipo*: ese día no se hace el apagado programado (ver Configuración).
  Las fechas «desde» y «hasta» están incluidas. Las excepciones prevalecen siempre sobre el horario
  ordinario y, si coinciden varias, se aplica la **más restrictiva**. Al terminar el periodo vuelve
  sola la programación habitual (no se ejecuta nada atrasado). Los horarios semanales no se borran.
  - **Duplicar para el año siguiente**: seleccione uno o varios periodos (Ctrl o Mayús) y se crean
    con las mismas fechas un año después. Revise las fechas que cambian (Semana Santa, Carnaval).
  - **Importar / Exportar vacaciones.json**: ver [VACACIONES.md](VACACIONES.md). Antes de importar
    se hace una copia de seguridad; si el archivo tiene errores no se importa nada.
  - Si dos periodos se solapan, el programa lo avisa al guardarlos y bajo la lista.
- **Eventos extraordinarios**: suenan solo en su fecha (también en festivos).
- **Consultar una fecha**: elija un día en el calendario y verá qué sonará y por qué.
  En rojo, días sin sonido; en naranja, días con otro horario; en azul, días en los que solo se
  suspende el apagado. Si el apagado programado está activo, también indica si ese día se apagará.
- **Simulación**: avanza virtualmente por un periodo aplicando todas las reglas, sin sonido.

## Configuración

Dispositivo de salida y qué hacer si se desconecta, volumen general, fundido final, automatización,
retraso máximo admitido, prioridad manual, zona horaria, inicio automático, bandeja, evitar la
suspensión (Windows), **apagado programado**, conservación del historial, copias automáticas y datos
de ejemplo. Pulse **Guardar cambios** para aplicar.

### Apagado programado del equipo

Desactivado por defecto. Al activarlo se elige la hora, los días y los minutos de aviso. A esa hora
aparece una ventana con una cuenta atrás y los botones **Cancelar el apagado de hoy** y **Apagar
ahora**; si nadie la cancela, AulaAudio detiene el sonido y apaga el equipo. En *Inicio* se muestra
el próximo apagado previsto.

Orden de prioridad: 1) automatización desactivada manualmente (no se apaga); 2) vacaciones, días no
lectivos y cambios de horario con «No apagar el equipo»; 3) festivos y días sueltos con esa opción;
4) días y hora de Configuración. Si el programa no estaba funcionando a la hora del apagado, ese día
no se apaga (nunca se apaga con retraso). Si no se puede leer la programación, tampoco se apaga.

**Encendido:** AulaAudio no puede encender un equipo apagado. Para que se encienda solo, configure
el encendido programado en la BIOS/UEFI del equipo («Power On by RTC», «Wake on RTC» o similar) o
en el propio aula; en vacaciones el equipo se encenderá igualmente, pero no sonará nada si el
periodo silencia los sonidos.

## Historial e incidencias

Todo lo que ha sonado, lo omitido y los problemas, con filtro por tipo y exportación a CSV.

## Copias de seguridad

*Crear copia ahora*, *Exportar…* (a un pendrive), *Restaurar la seleccionada…* o *desde un
archivo…*. Antes de restaurar se guarda automáticamente el estado actual. Ver Manual de mantenimiento.
