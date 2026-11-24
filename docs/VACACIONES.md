# Calendario de vacaciones: `vacaciones.json`

AulaAudio guarda los festivos y vacaciones en su base de datos, así que siguen activos aunque se
reinicie el equipo. El archivo `vacaciones.json` sirve para **intercambiarlos**: prepararlos con
el Bloc de notas, pasarlos a otro centro o guardarlos de un curso a otro.

- **Importar**: *Calendario y excepciones → Importar vacaciones.json…*. Puede **añadir** los
  periodos a los que ya hay (los repetidos no se duplican) o **sustituir** todos los festivos,
  vacaciones y días no lectivos (los cambios de horario se conservan). Antes se hace una copia de
  seguridad automática y los cambios se aplican al momento, sin reiniciar.
- **Exportar**: *Exportar vacaciones.json…*. Si el archivo ya existía, se conserva como
  `vacaciones.json.bak`.

Ejemplo completo: [vacaciones.example.json](../vacaciones.example.json). Las fechas son solo
de ejemplo.

## Formato

```json
{
  "version": 1,
  "vacaciones": [
    {
      "nombre": "Navidad",
      "fecha_inicio": "2026-12-23",
      "fecha_fin": "2027-01-07",
      "tipo": "vacaciones",
      "desactivar_sonidos": true,
      "desactivar_apagado": true
    }
  ],
  "dias_sueltos": [
    "2026-12-08",
    { "fecha": "2027-01-06", "nombre": "Reyes", "desactivar_sonidos": true, "desactivar_apagado": false }
  ]
}
```

| Clave | Obligatoria | Significado |
|---|---|---|
| `nombre` | sí | Nombre del periodo (máx. 100 caracteres) |
| `fecha_inicio`, `fecha_fin` | sí | `AAAA-MM-DD`. Las dos fechas están **incluidas** |
| `tipo` | no | `vacaciones` (por defecto), `no_lectivo` o `festivo` |
| `desactivar_sonidos` | no (`true`) | Esos días no suena la programación semanal |
| `desactivar_apagado` | no (`true`) | Esos días no se apaga el equipo a la hora programada |
| `notas` | no | Texto libre |

En `dias_sueltos` se puede escribir solo la fecha (`"2026-12-08"`: festivo con todo suspendido)
o un bloque con `fecha`, `nombre` y las mismas opciones.

`desactivar_encendido` se acepta como sinónimo de `desactivar_sonidos`. AulaAudio no puede
encender el equipo (eso depende de la BIOS/UEFI); lo que «arranca» cada día es su programación de
sonidos.

## Reglas

- Si coinciden varios periodos, se aplica el **más restrictivo**: basta con que uno suspenda algo.
- Al terminar un periodo vuelve sola la programación habitual. No se ejecuta nada atrasado.
- Los horarios semanales no se borran ni se modifican durante las vacaciones.
- Se avisa de los periodos que se solapan (por ejemplo, dos periodos de varios días, o un festivo
  dentro de unas vacaciones que suspenden otras cosas).

## Si el archivo tiene errores

**No se importa nada** y la programación sigue igual. El aviso indica qué corregir, por ejemplo:

- «línea 7, columna 5: falta una coma o sobra una»
- «Periodo «Navidad»: la fecha de inicio (07/01/2027) es posterior a la de fin (23/12/2026)»
- «la fecha «23/12/2026» no es válida (formato AAAA-MM-DD, por ejemplo 2026-12-23)»
- ««desactivar_apagado» debe ser true o false (sin comillas)»

Consejo: guarde el archivo como UTF-8. Las comillas deben ser rectas (`"`), no tipográficas (`“ ”`).
