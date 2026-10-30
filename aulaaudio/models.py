"""Modelos de datos y validación de entradas del usuario."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time

DAY_NAMES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
DAY_SHORT = ["L", "M", "X", "J", "V", "S", "D"]
MONTH_NAMES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
               "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

KIND_MUSIC, KIND_BELL, KIND_NOTICE = "musica", "timbre", "aviso"
KINDS = {KIND_MUSIC: "Música", KIND_BELL: "Timbre", KIND_NOTICE: "Aviso"}

END_AUDIO, END_DURATION, END_TIME = "fin_audio", "duracion", "hora_fin"
END_MODES = {
    END_AUDIO: "Al terminar el audio",
    END_DURATION: "Tras una duración",
    END_TIME: "A una hora concreta",
}

CONFLICT_INTERRUPT, CONFLICT_WAIT, CONFLICT_SKIP = "interrumpir", "esperar", "omitir"
CONFLICTS = {
    CONFLICT_INTERRUPT: "Interrumpir lo que suena (si tiene igual o menor prioridad)",
    CONFLICT_WAIT: "Esperar a que termine lo que suena",
    CONFLICT_SKIP: "No reproducirse si ya suena algo",
}

EXC_HOLIDAY, EXC_VACATION, EXC_NONSCHOOL, EXC_ALT = "festivo", "vacaciones", "no_lectivo", "horario_alternativo"
EXCEPTION_KINDS = {
    EXC_HOLIDAY: "Festivo (sin sonido)",
    EXC_VACATION: "Vacaciones (sin sonido)",
    EXC_NONSCHOOL: "Día no lectivo (sin sonido)",
    EXC_ALT: "Cambio de horario (usar otro horario)",
}
SILENT_EXCEPTIONS = (EXC_HOLIDAY, EXC_VACATION, EXC_NONSCHOOL)

DEFAULT_PRIORITY = {KIND_MUSIC: 3, KIND_BELL: 8, KIND_NOTICE: 6}
MAX_NAME = 100


class ValidationError(ValueError):
    """Error de validación con un mensaje apto para mostrar al usuario."""


def parse_hhmm(text: str) -> time:
    try:
        hh, mm = str(text).strip().split(":")[:2]
        return time(int(hh), int(mm))
    except (ValueError, AttributeError) as exc:
        raise ValidationError(f"Hora no válida: {text!r}. Use el formato HH:MM.") from exc


def fmt_hhmm(t: time) -> str:
    return f"{t.hour:02d}:{t.minute:02d}"


def days_to_text(days: frozenset[int] | set[int]) -> str:
    if set(days) == {0, 1, 2, 3, 4}:
        return "Lunes a viernes"
    if set(days) == set(range(7)):
        return "Todos los días"
    return ", ".join(DAY_SHORT[d] for d in sorted(days))


@dataclass
class Event:
    id: int | None = None
    name: str = ""
    kind: str = KIND_MUSIC
    schedule_id: int | None = None  # None en eventos extraordinarios (fecha concreta)
    days: frozenset[int] = field(default_factory=frozenset)
    date: date | None = None  # si tiene fecha es un evento extraordinario/puntual
    start: time = time(8, 0)
    end_mode: str = END_AUDIO
    duration_min: int | None = None
    end_time: time | None = None
    track_id: int | None = None
    playlist_id: int | None = None
    volume: int | None = None  # % relativo al volumen general; None = 100 %
    enabled: bool = True
    priority: int = 3
    conflict: str = CONFLICT_INTERRUPT
    resume: bool = False  # reanudar tras ser interrumpido si aún está en su franja
    demo: bool = False

    @property
    def is_one_off(self) -> bool:
        return self.date is not None

    def validate(self) -> "Event":
        self.name = (self.name or "").strip()
        if not self.name:
            raise ValidationError("El evento necesita un nombre.")
        if len(self.name) > MAX_NAME:
            raise ValidationError(f"El nombre no puede superar {MAX_NAME} caracteres.")
        if self.kind not in KINDS:
            raise ValidationError("Tipo de evento no válido.")
        if self.date is None:
            if not self.days:
                raise ValidationError("Seleccione al menos un día de la semana.")
            if not all(isinstance(d, int) and 0 <= d <= 6 for d in self.days):
                raise ValidationError("Días de la semana no válidos.")
            if self.schedule_id is None:
                raise ValidationError("El evento semanal debe pertenecer a un horario.")
        if self.end_mode not in END_MODES:
            raise ValidationError("Condición de finalización no válida.")
        if self.end_mode == END_DURATION:
            if not self.duration_min or not 1 <= int(self.duration_min) <= 720:
                raise ValidationError("La duración debe estar entre 1 y 720 minutos.")
        if self.end_mode == END_TIME:
            if self.end_time is None:
                raise ValidationError("Indique la hora de finalización.")
            if self.end_time == self.start:
                raise ValidationError("La hora de finalización no puede coincidir con la de inicio.")
        if (self.track_id is None) == (self.playlist_id is None):
            raise ValidationError("Elija un archivo de audio o una lista de reproducción.")
        if self.volume is not None and not 0 <= int(self.volume) <= 100:
            raise ValidationError("El volumen debe estar entre 0 y 100.")
        if not 1 <= int(self.priority) <= 10:
            raise ValidationError("La prioridad debe estar entre 1 y 10.")
        if self.conflict not in CONFLICTS:
            raise ValidationError("Comportamiento ante conflictos no válido.")
        return self


@dataclass
class Track:
    id: int | None
    path: str
    title: str
    size: int | None = None
    duration_ms: int | None = None
    status: str = "ok"  # ok | falta | error
    status_msg: str = ""
    demo: bool = False


@dataclass
class Playlist:
    id: int | None
    name: str
    mode: str = "secuencial"  # secuencial | aleatorio
    repeat: bool = True
    demo: bool = False


@dataclass
class Schedule:
    id: int | None
    name: str
    is_default: bool = False
    demo: bool = False


@dataclass
class CalendarException:
    id: int | None = None
    name: str = ""
    kind: str = EXC_HOLIDAY
    date_from: date = field(default_factory=date.today)
    date_to: date = field(default_factory=date.today)
    schedule_id: int | None = None
    notes: str = ""

    def validate(self) -> "CalendarException":
        self.name = (self.name or "").strip()
        if not self.name:
            raise ValidationError("La excepción necesita un nombre (por ejemplo, «Navidad»).")
        if len(self.name) > MAX_NAME:
            raise ValidationError(f"El nombre no puede superar {MAX_NAME} caracteres.")
        if self.kind not in EXCEPTION_KINDS:
            raise ValidationError("Tipo de excepción no válido.")
        if self.date_to < self.date_from:
            raise ValidationError("La fecha final no puede ser anterior a la inicial.")
        if (self.date_to - self.date_from).days > 400:
            raise ValidationError("Una excepción no puede abarcar más de 400 días.")
        if self.kind == EXC_ALT and self.schedule_id is None:
            raise ValidationError("Elija el horario que se usará esos días.")
        if self.kind != EXC_ALT:
            self.schedule_id = None
        self.notes = (self.notes or "").strip()[:500]
        return self

    def covers(self, d: date) -> bool:
        return self.date_from <= d <= self.date_to
