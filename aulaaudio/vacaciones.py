"""Importación y exportación del calendario de vacaciones y festivos (vacaciones.json).

Los periodos se guardan en la base de datos del programa (siguen activos tras reiniciar el
equipo). El archivo vacaciones.json sirve para intercambiarlos: prepararlos a mano,
copiarlos a otro centro o conservarlos de un curso a otro.

Formato (todas las claves en español; las fechas en AAAA-MM-DD, ambas incluidas):

{
  "version": 1,
  "vacaciones": [
    {"nombre": "Navidad", "fecha_inicio": "2026-12-23", "fecha_fin": "2027-01-07",
     "tipo": "vacaciones",               (opcional: vacaciones | no_lectivo | festivo)
     "desactivar_sonidos": true,          (no suena la programación semanal)
     "desactivar_apagado": true}          (no se apaga el equipo)
  ],
  "dias_sueltos": [
    "2026-12-08",                         (forma corta: festivo con todo suspendido)
    {"fecha": "2027-01-06", "nombre": "Reyes", "desactivar_sonidos": true, "desactivar_apagado": true}
  ]
}

Por compatibilidad se acepta "desactivar_encendido" como sinónimo de "desactivar_sonidos"
(AulaAudio no enciende el equipo: lo que «enciende» cada día es su programación de sonidos).
Los cambios de horario no se incluyen: dependen de los horarios de cada centro.

La lectura es «todo o nada»: si el archivo tiene cualquier error no se importa nada y se
explica qué línea o qué periodo hay que corregir.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from .models import (
    EXC_ALT,
    EXC_HOLIDAY,
    EXC_NONSCHOOL,
    EXC_VACATION,
    MAX_NAME,
    CalendarException,
    ValidationError,
    describe_overlap,
    find_overlaps,
)

FILE_NAME = "vacaciones.json"
FORMAT_VERSION = 1
JSON_KINDS = {"vacaciones": EXC_VACATION, "no_lectivo": EXC_NONSCHOOL, "festivo": EXC_HOLIDAY}
MAX_ITEMS = 1000
MAX_BYTES = 2_000_000


class VacationFileError(ValueError):
    """El archivo no se puede leer o tiene datos no válidos (mensaje apto para el usuario)."""


@dataclass
class ImportResult:
    items: list[CalendarException]
    warnings: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ lectura
def _parse_date(value, where: str) -> date:
    if not isinstance(value, str):
        raise VacationFileError(f"{where}: la fecha debe escribirse entre comillas como \"AAAA-MM-DD\".")
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise VacationFileError(f"{where}: la fecha «{value}» no es válida (formato AAAA-MM-DD, "
                                "por ejemplo 2026-12-23).") from None


def _flag(obj: dict, key: str, where: str, default: bool = True) -> bool:
    value = obj.get(key, default)
    if not isinstance(value, bool):
        raise VacationFileError(f"{where}: «{key}» debe ser true o false (sin comillas).")
    return value


def _period(obj, index: int) -> CalendarException:
    where = f"Periodo n.º {index} de «vacaciones»"
    if not isinstance(obj, dict):
        raise VacationFileError(f"{where}: debe ser un bloque {{ ... }} con nombre y fechas.")
    name = obj.get("nombre")
    if not isinstance(name, str) or not name.strip():
        raise VacationFileError(f"{where}: falta el «nombre».")
    where = f"Periodo «{name.strip()[:60]}»"
    for key in ("fecha_inicio", "fecha_fin"):
        if key not in obj:
            raise VacationFileError(f"{where}: falta «{key}».")
    start = _parse_date(obj["fecha_inicio"], where)
    end = _parse_date(obj["fecha_fin"], where)
    if start > end:
        raise VacationFileError(f"{where}: la fecha de inicio ({start:%d/%m/%Y}) es posterior a la de fin "
                                f"({end:%d/%m/%Y}).")
    kind_text = obj.get("tipo", "vacaciones")
    if kind_text not in JSON_KINDS:
        raise VacationFileError(f"{where}: tipo «{kind_text}» desconocido (use vacaciones, no_lectivo o festivo).")
    sounds_key = "desactivar_sonidos" if "desactivar_sonidos" in obj else "desactivar_encendido"
    return _build(name, JSON_KINDS[kind_text], start, end, _flag(obj, sounds_key, where),
                  _flag(obj, "desactivar_apagado", where), obj.get("notas", ""), where)


def _single_day(obj, index: int) -> CalendarException:
    where = f"Día suelto n.º {index}"
    if isinstance(obj, str):
        d = _parse_date(obj, where)
        return _build(f"Festivo {d:%d/%m/%Y}", EXC_HOLIDAY, d, d, True, True, "", where)
    if not isinstance(obj, dict) or "fecha" not in obj:
        raise VacationFileError(f"{where}: escriba la fecha (\"2026-12-08\") o un bloque con «fecha».")
    d = _parse_date(obj["fecha"], where)
    name = obj.get("nombre") or f"Festivo {d:%d/%m/%Y}"
    if not isinstance(name, str):
        raise VacationFileError(f"{where}: el «nombre» debe ir entre comillas.")
    sounds_key = "desactivar_sonidos" if "desactivar_sonidos" in obj else "desactivar_encendido"
    return _build(name, EXC_HOLIDAY, d, d, _flag(obj, sounds_key, where),
                  _flag(obj, "desactivar_apagado", where), obj.get("notas", ""), where)


def _build(name, kind, start, end, sounds, shutdown, notes, where) -> CalendarException:
    if len(name.strip()) > MAX_NAME:
        raise VacationFileError(f"{where}: el nombre supera {MAX_NAME} caracteres.")
    e = CalendarException(name=name, kind=kind, date_from=start, date_to=end,
                          notes=notes if isinstance(notes, str) else "",
                          suspend_sounds=sounds, suspend_shutdown=shutdown)
    try:
        return e.validate()
    except ValidationError as exc:
        raise VacationFileError(f"{where}: {exc}") from None


def parse(text: str) -> ImportResult:
    """Interpreta el contenido de vacaciones.json. Lanza VacationFileError si hay errores."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise VacationFileError(
            f"El archivo está dañado o mal escrito (línea {exc.lineno}, columna {exc.colno}: {_json_hint(exc)}). "
            "No se ha importado nada.") from None
    if not isinstance(raw, dict):
        raise VacationFileError("El archivo debe empezar por { y contener «vacaciones» y/o «dias_sueltos».")
    if "vacaciones" not in raw and "dias_sueltos" not in raw:
        raise VacationFileError("El archivo no contiene «vacaciones» ni «dias_sueltos».")
    version = raw.get("version", FORMAT_VERSION)
    if not isinstance(version, int) or version > FORMAT_VERSION:
        raise VacationFileError("El archivo procede de una versión más moderna de AulaAudio. Actualice el programa.")
    periods, days = raw.get("vacaciones", []), raw.get("dias_sueltos", [])
    if not isinstance(periods, list) or not isinstance(days, list):
        raise VacationFileError("«vacaciones» y «dias_sueltos» deben ser listas entre corchetes [ ... ].")
    if len(periods) + len(days) > MAX_ITEMS:
        raise VacationFileError(f"El archivo tiene demasiados periodos (máximo {MAX_ITEMS}).")
    items = [_period(p, i) for i, p in enumerate(periods, 1)] + [_single_day(d, i) for i, d in enumerate(days, 1)]
    unique: list[CalendarException] = []
    warnings = []
    for e in items:
        if any(e.same_as(u) for u in unique):
            warnings.append(f"«{e.name}» aparece repetido en el archivo; se importa una sola vez.")
        else:
            unique.append(e)
    warnings += overlap_warnings(unique)
    return ImportResult(unique, warnings)


def _json_hint(exc: json.JSONDecodeError) -> str:
    msg = exc.msg.lower()
    if "delimiter" in msg:
        return "falta una coma o sobra una"
    if "property name" in msg:
        return "revise las comillas y que no sobre una coma antes de }"
    if "expecting value" in msg:
        return "falta un valor o sobra una coma"
    return exc.msg


def read_file(path: Path) -> ImportResult:
    path = Path(path)
    try:
        if path.stat().st_size > MAX_BYTES:
            raise VacationFileError("El archivo es demasiado grande para ser un calendario de vacaciones.")
        data = path.read_bytes()
    except OSError as exc:
        raise VacationFileError(f"No se puede leer el archivo: {exc.strerror or exc}") from None
    try:
        text = data.decode("utf-8-sig")  # admite el BOM que añade el Bloc de notas
    except UnicodeDecodeError:
        try:
            text = data.decode("cp1252")
        except UnicodeDecodeError:
            raise VacationFileError("El archivo no es de texto (guárdelo como UTF-8).") from None
    return parse(text)


# ------------------------------------------------------------------ comprobaciones
def overlap_warnings(items: list[CalendarException]) -> list[str]:
    return [f"Se solapan {describe_overlap(a, b)}." for a, b in find_overlaps(items)]


def merge_plan(existing: list[CalendarException], incoming: list[CalendarException], replace: bool
               ) -> tuple[list[CalendarException], list[str]]:
    """Qué se va a añadir y avisos (duplicados omitidos, solapes con los periodos actuales).

    Con replace=True se sustituyen todos los festivos/vacaciones/días no lectivos actuales
    (los cambios de horario se conservan siempre)."""
    kept = [e for e in existing if e.kind == EXC_ALT] if replace else list(existing)
    to_add, warnings = [], []
    for e in incoming:
        if any(e.same_as(k) for k in kept):
            warnings.append(f"«{e.name}» ya existe con las mismas fechas; no se duplica.")
        else:
            to_add.append(e)
    known = {id(e) for e in kept}
    for a, b in find_overlaps(kept + to_add):
        if id(a) in known and id(b) in known:
            continue  # solapes antiguos: ya se avisó al crearlos
        warnings.append(f"Se solapan {describe_overlap(a, b)}.")
    return to_add, warnings


def shift_year(d: date, years: int = 1) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 de febrero en un año no bisiesto
        return d.replace(year=d.year + years, day=28)


def next_year_copies(items: list[CalendarException], existing: list[CalendarException]
                     ) -> tuple[list[CalendarException], list[str]]:
    """Copias de los periodos con las fechas un año después (omite las que ya existen)."""
    copies, warnings = [], []
    for e in items:
        c = CalendarException(name=e.name, kind=e.kind, date_from=shift_year(e.date_from),
                              date_to=shift_year(e.date_to), schedule_id=e.schedule_id, notes=e.notes,
                              suspend_sounds=e.suspend_sounds, suspend_shutdown=e.suspend_shutdown)
        if any(c.same_as(x) for x in existing + copies):
            warnings.append(f"«{c.name}» ya existe en {c.date_from.year}; no se duplica.")
        else:
            copies.append(c)
    return copies, warnings


# ------------------------------------------------------------------ escritura
def to_dict(items: list[CalendarException]) -> dict:
    rev = {v: k for k, v in JSON_KINDS.items()}
    periods, days = [], []
    for e in sorted(items, key=lambda x: (x.date_from, x.date_to, x.name)):
        if e.kind == EXC_ALT:
            continue
        common = {"desactivar_sonidos": e.suspend_sounds, "desactivar_apagado": e.suspend_shutdown}
        if e.notes:
            common["notas"] = e.notes
        if e.kind == EXC_HOLIDAY and e.date_from == e.date_to:
            days.append({"fecha": e.date_from.isoformat(), "nombre": e.name, **common})
        else:
            periods.append({"nombre": e.name, "fecha_inicio": e.date_from.isoformat(),
                            "fecha_fin": e.date_to.isoformat(), "tipo": rev[e.kind], **common})
    return {"version": FORMAT_VERSION, "vacaciones": periods, "dias_sueltos": days}


def write_file(path: Path, items: list[CalendarException]) -> Path | None:
    """Escribe vacaciones.json de forma atómica. Si ya existía, conserva antes una copia
    (vacaciones.json.bak) y devuelve su ruta."""
    path = Path(path)
    text = json.dumps(to_dict(items), ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if path.exists():
        backup = path.with_name(path.name + ".bak")
        shutil.copy2(path, backup)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return backup
