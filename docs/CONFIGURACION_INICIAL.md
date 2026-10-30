# Guía de configuración inicial

## 1. Conectar el ordenador al equipo de sonido

**Material habitual**

| Salida del ordenador | Entrada del amplificador / mesa | Cable |
|---|---|---|
| Minijack 3,5 mm (verde, auriculares) | 2 × RCA (rojo/blanco, «AUX», «LINE IN», «CD») | Minijack estéreo → 2 RCA macho |
| Minijack 3,5 mm | Minijack «AUX IN» | Minijack ↔ minijack estéreo |
| Minijack 3,5 mm | Jack 6,3 mm o XLR (mesa de mezclas) | Minijack → 2 jack 6,3 mm (o caja DI) |
| USB (tarjeta de sonido externa) | Según la tarjeta | El de la tarjeta |

**Pasos**

1. Con el amplificador **apagado o con su volumen al mínimo**, conecte el cable a la salida de
   auriculares del ordenador y a una entrada de **línea** (AUX/LINE/CD) del amplificador. No use la
   entrada de micrófono: distorsiona.
2. Encienda el amplificador y seleccione esa entrada.
3. En Windows, ponga el volumen del sistema en torno al 80 % (icono del altavoz). En Linux, en los
   ajustes de sonido. AulaAudio no cambia el volumen del sistema.
4. Desactive en el sistema los sonidos de notificaciones para que no salgan por la megafonía
   (Windows: *Configuración → Sistema → Sonido → Más opciones de sonido → Sonidos → Combinación:
   Sin sonidos*).
5. Si hay zumbido: use un cable corto y apantallado, conecte el portátil a la corriente con un
   enchufe de la misma regleta que el amplificador o use un aislador de masa (*ground loop isolator*).

## 2. Primera prueba de sonido

1. Abra AulaAudio. En **Configuración → Audio**, elija el dispositivo de salida (si duda, deje
   «Predeterminado del sistema») y pulse **Guardar cambios**.
2. En **Inicio**, pulse **Prueba de sonido**: debe oír tres notas ascendentes.
3. Suba poco a poco el volumen del amplificador hasta un nivel adecuado. Ajuste después el
   **Volumen general** de AulaAudio (recomendado 70–90 %) y el **Volumen propio** de cada evento.
4. Si no se oye nada, consulte *Recuperación ante fallos* en el Manual de mantenimiento.

## 3. Primer horario

1. **Biblioteca de audio** → *Añadir carpeta…* con la música y *Añadir archivos…* con el timbre.
2. Cree una lista (*Nueva…*), por ejemplo «Recreo»; seleccione pistas a la izquierda y pulse
   *Añadir pistas seleccionadas*. Elija *Secuencial* o *Aleatorio* y deje *Repetir* marcado.
3. **Programación** → *Nuevo evento*:
   - Timbre de entrada: tipo *Timbre*, L-V, 08:30, *Al terminar el audio*, archivo del timbre,
     prioridad 8, *Interrumpir lo que suena*.
   - Música del recreo: tipo *Música*, L-V, 11:16, *A una hora concreta* 11:44, lista «Recreo»,
     prioridad 3, *Esperar a que termine lo que suena*, *Reanudar* marcado.
4. Repita para el resto de timbres (puede usar *Duplicar* y cambiar la hora).
5. **Calendario y excepciones** → añada festivos y vacaciones del curso.
6. **Calendario → Simulación**: elija un día lectivo y pulse *Simular*. Revise que todo ocurre a
   la hora prevista. Use también *Consultar una fecha* para un festivo.
7. **Configuración → Inicio y funcionamiento**: marque *Abrir AulaAudio al iniciar sesión* y
   *Arrancar minimizado*, y pulse *Guardar cambios*.
8. **Copias de seguridad** → *Crear copia ahora* y *Exportar copia seleccionada…* a un pendrive.

Si cargó el horario de ejemplo, sus eventos están **desactivados**: edítelos o actívelos con
*Activar / desactivar*. Puede borrarlos todos en *Configuración → Eliminar datos de ejemplo*.

## 4. Ajustes del equipo recomendados

- Energía: *Suspender: nunca* mientras esté enchufado, y que la pantalla se apague si se quiere.
- Inicio de sesión automático en un usuario dedicado (lo configura el responsable TIC).
- Hora sincronizada automáticamente (*Configuración → Hora e idioma → Establecer hora
  automáticamente*).
- Actualizaciones de Windows fuera del horario lectivo (*Horas activas*).
