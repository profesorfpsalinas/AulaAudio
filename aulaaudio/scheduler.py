"""Cálculo de qué debe sonar y cuándo.

Módulo de lógica pura (sin Qt ni sonido), probado con reloj simulado.

Reglas:
1. Cada día local se decide qué horario se aplica:
   - Si alguna excepción de tipo festivo/vacaciones/no lectivo cubre la fecha: no suena
     ningún evento semanal ese día.
   - Si no, si una excepción «cambio de horario» cubre la fecha: se usa ese horario.
   - Si no, el horario ordinario.
   Las excepciones siempre prevalecen sobre la programación ordinaria.
2. Los eventos extraordinarios (con fecha concreta) suenan su día, aunque sea festivo:
   son una decisión explícita del usuario para esa fecha.
3. Las horas se interpretan en hora local (zona horaria configurada) y se convierten a UTC
   para comparar instantes. Así el cambio de hora no duplica ni pierde eventos:
   - Hora inexistente (adelanto de primavera, p. ej. 02:30): el evento suena una hora
     después (03:30), que es el mismo instante físico.
   - Hora repetida (retraso de otoño): el evento suena una sola vez, en la primera.
   - «Tras una duración» mide tiempo real transcurrido; «a una hora» usa la hora del reloj.
4. Si la hora de fin es anterior o igual a la de inicio, el evento termina al día siguiente
   (cruza la medianoche).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .models import (
    END_DURATION,
    END_TIME,
    EXC_ALT,
    EXCEPTION_KINDS,
    SILENT_EXCEPTIONS,
    CalendarException,
    Event,
)

UTC = timezone.utc


@dataclass(frozen=True)
class Occurrence:
    event: Event
    local_date: date
    start_utc: datetime
    end_utc: datetime | None  # None = termina cuando acaba el audio

    @property
    def key(self) -> tuple:
        return (self.event.id, self.local_date.isoformat(), self.event.start.isoformat())

    @property
    def priority(self) -> int:
        return int(self.event.priority)


@dataclass
class DayPlan:
    day: date
    schedule_id: int | None
    schedule_name: str
    reason: str  # explicación legible de por qué se aplica este plan
    silent: bool
    occurrences: list[Occurrence] = field(default_factory=list)


@dataclass
class ScheduleData:
    """Instantánea de la programación (se recarga cuando el usuario la modifica)."""
    events: list[Event]
    exceptions: list[CalendarException]
    default_schedule_id: int
    schedule_names: dict[int, str]

    @classmethod
    def from_db(cls, db) -> "ScheduleData":
        return cls(db.events(), db.exceptions(), db.default_schedule_id(),
                   {s.id: s.name for s in db.schedules()})


def local_to_utc(d: date, t, tz: ZoneInfo) -> datetime:
    # fold=0: en horas repetidas se toma la primera; en horas inexistentes se aplica el
    # desfase anterior al cambio, lo que equivale a desplazar el evento una hora más tarde.
    return datetime.combine(d, t, tzinfo=tz).astimezone(UTC)


class Scheduler:
    def __init__(self, data: ScheduleData, tz_name: str = "Europe/Madrid"):
        self.data = data
        self.tz = ZoneInfo(tz_name)
        self._plans: dict[date, DayPlan] = {}  # la instantánea no cambia: se puede cachear

    # ------------------------------------------------------------------ días
    def day_plan(self, d: date) -> DayPlan:
        plan = self._plans.get(d)
        if plan is None:
            if len(self._plans) > 400:
                self._plans.clear()
            plan = self._plans[d] = self._compute_day_plan(d)
        return plan

    def _compute_day_plan(self, d: date) -> DayPlan:
        exc = [e for e in self.data.exceptions if e.covers(d)]
        silent = [e for e in exc if e.kind in SILENT_EXCEPTIONS]
        alt = [e for e in exc if e.kind == EXC_ALT and e.schedule_id is not None]
        sched_id: int | None
        if silent:
            e = silent[0]
            sched_id, silent_day = None, True
            reason = f"{EXCEPTION_KINDS[e.kind].split(' (')[0]}: {e.name}. No suena la programación semanal."
        elif alt:
            e = alt[-1]  # la excepción más reciente de las que coinciden
            sched_id, silent_day = e.schedule_id, False
            reason = f"Cambio de horario «{e.name}»: se usa «{self.data.schedule_names.get(sched_id, '?')}»."
        else:
            sched_id, silent_day = self.data.default_schedule_id, False
            reason = "Horario ordinario."
        occs = []
        for ev in self.data.events:
            if not ev.enabled:
                continue
            if ev.date is not None:
                if ev.date == d:
                    occs.append(self._occurrence(ev, d))
            elif not silent_day and ev.schedule_id == sched_id and d.weekday() in ev.days:
                occs.append(self._occurrence(ev, d))
        occs.sort(key=lambda o: (o.start_utc, -o.priority, o.event.name))
        name = self.data.schedule_names.get(sched_id, "") if sched_id else ""
        return DayPlan(d, sched_id, name, reason, silent_day, occs)

    def _occurrence(self, ev: Event, d: date) -> Occurrence:
        start = local_to_utc(d, ev.start, self.tz)
        end = None
        if ev.end_mode == END_DURATION and ev.duration_min:
            end = start + timedelta(minutes=int(ev.duration_min))
        elif ev.end_mode == END_TIME and ev.end_time is not None:
            end_day = d if ev.end_time > ev.start else d + timedelta(days=1)
            end = local_to_utc(end_day, ev.end_time, self.tz)
            if end <= start:  # caso límite en un cambio de hora
                end = start + timedelta(minutes=1)
        return Occurrence(ev, d, start, end)

    # ------------------------------------------------------------------ intervalos
    def local_date(self, moment: datetime) -> date:
        return moment.astimezone(self.tz).date()

    def occurrences_between(self, start: datetime, end: datetime, include_start: bool = True) -> list[Occurrence]:
        """Ocurrencias cuyo inicio está en [start, end] (o (start, end] si include_start=False)."""
        result = []
        d = self.local_date(start) - timedelta(days=1)
        last = self.local_date(end) + timedelta(days=1)
        while d <= last:
            for o in self.day_plan(d).occurrences:
                after_start = o.start_utc >= start if include_start else o.start_utc > start
                if after_start and o.start_utc <= end:
                    result.append(o)
            d += timedelta(days=1)
        result.sort(key=lambda o: (o.start_utc, -o.priority, o.event.name))
        return result

    def next_occurrence(self, after: datetime, horizon_days: int = 31) -> Occurrence | None:
        d = self.local_date(after)
        for _ in range(horizon_days + 1):
            for o in self.day_plan(d).occurrences:
                if o.start_utc > after:
                    return o
            d += timedelta(days=1)
        return None

    def in_progress(self, moment: datetime) -> list[Occurrence]:
        """Eventos con hora de fin cuya franja incluye `moment` (ya empezados)."""
        found = []
        for o in self.occurrences_between(moment - timedelta(hours=24), moment):
            if o.end_utc is not None and o.start_utc < moment < o.end_utc:
                found.append(o)
        return found

    def local(self, moment: datetime) -> datetime:
        return moment.astimezone(self.tz)
