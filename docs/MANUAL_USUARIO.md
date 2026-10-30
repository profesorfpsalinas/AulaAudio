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

## Calendario y excepciones

- **Festivos, vacaciones y cambios**: *Festivo*, *Vacaciones* y *Día no lectivo* silencian la
  programación semanal; *Cambio de horario* usa otro horario esos días. Las excepciones prevalecen
  siempre sobre el horario ordinario; si coinciden, gana la que silencia.
- **Eventos extraordinarios**: suenan solo en su fecha (también en festivos).
- **Consultar una fecha**: elija un día en el calendario y verá qué sonará y por qué.
  En rojo, días sin sonido; en naranja, días con otro horario.
- **Simulación**: avanza virtualmente por un periodo aplicando todas las reglas, sin sonido.

## Configuración

Dispositivo de salida y qué hacer si se desconecta, volumen general, fundido final, automatización,
retraso máximo admitido, prioridad manual, zona horaria, inicio automático, bandeja, evitar la
suspensión (Windows), conservación del historial, copias automáticas y datos de ejemplo.
Pulse **Guardar cambios** para aplicar.

## Historial e incidencias

Todo lo que ha sonado, lo omitido y los problemas, con filtro por tipo y exportación a CSV.

## Copias de seguridad

*Crear copia ahora*, *Exportar…* (a un pendrive), *Restaurar la seleccionada…* o *desde un
archivo…*. Antes de restaurar se guarda automáticamente el estado actual. Ver Manual de mantenimiento.
