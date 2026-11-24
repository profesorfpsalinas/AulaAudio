"""Apagado programado del equipo (lógica pura, sin Qt; probada con reloj simulado).

Orden de prioridad (de mayor a menor) para decidir si un día se apaga el equipo:
1. El apagado programado está desactivado en Configuración, o la automatización está
   detenida manualmente: no se apaga.
2. Vacaciones, días no lectivos y cambios de horario con «suspender apagado».
3. Festivos y días sueltos con «suspender apagado».
4. Programación semanal habitual (días y hora de Configuración).
Si coinciden varias excepciones se aplica la más restrictiva: basta con que una suspenda
el apagado para que ese día no se apague.

Reglas de seguridad:
* Nunca se apaga con retraso: si el programa no estaba funcionando a la hora del apagado
  (equipo suspendido, programa cerrado), ese apagado se omite.
* Si no se ha podido leer la programación o el calendario, no se apaga (acción peligrosa).
* Antes de apagar se muestra una cuenta atrás que cualquiera puede cancelar.
* El equipo NO se enciende solo: encenderlo depende de la BIOS/UEFI o de una persona.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .models import DAY_NAMES, EXC_HOLIDAY, EXCEPTION_KINDS, CalendarException, parse_hhmm
from .scheduler import local_to_utc

SHUTDOWN, SUSPENDED, MISSED, BLOCKED = "apagar", "suspendido", "omitido", "bloqueado"


@dataclass(frozen=True)
class ShutdownDecision:
    day: date
    scheduled: bool  # la programación semanal prevé apagar ese día
    when_utc: datetime | None
    suspended_by: str = ""  # motivo de la suspensión; vacío si no se suspende

    @property
    def will_shutdown(self) -> bool:
        return self.scheduled and not self.suspended_by

    def text(self, tz: ZoneInfo) -> str:
        if not self.scheduled:
            return self.suspended_by or "Sin apagado programado ese día."
        hhmm = self.when_utc.astimezone(tz).strftime("%H:%M")
        if self.suspended_by:
            return f"Apagado de las {hhmm} suspendido. {self.suspended_by}"
        return f"El equipo se apagará a las {hhmm} (con aviso previo cancelable)."


def _rank(e: CalendarException) -> int:
    # 0 = vacaciones / no lectivo / cambio de horario; 1 = festivo o día suelto
    return 1 if e.kind == EXC_HOLIDAY else 0


def shutdown_decision(d: date, settings, exceptions: list[CalendarException], tz: ZoneInfo) -> ShutdownDecision:
    if not settings.apagado_activo:
        return ShutdownDecision(d, False, None, "El apagado programado está desactivado.")
    if d.weekday() not in set(settings.apagado_dias):
        return ShutdownDecision(d, False, None, f"No hay apagado programado los {DAY_NAMES[d.weekday()]}.")
    when = local_to_utc(d, parse_hhmm(settings.apagado_hora), tz)
    if not settings.automatizacion_activa:
        return ShutdownDecision(d, True, when, "La automatización está detenida manualmente.")
    covering = sorted((e for e in exceptions if e.covers(d) and e.suspend_shutdown), key=_rank)
    if covering:
        e = covering[0]
        return ShutdownDecision(d, True, when, f"{EXCEPTION_KINDS[e.kind].split(' (')[0]}: {e.name}.")
    return ShutdownDecision(d, True, when)


class ShutdownPlanner:
    """Detecta cuándo llega la hora de apagar, una sola vez por día y sin acciones atrasadas."""

    def __init__(self):
        self.handled: dict[date, str] = {}

    def check(self, window_start: datetime, now: datetime, settings, exceptions: list[CalendarException],
              tz: ZoneInfo, data_ok: bool, margin: timedelta) -> tuple[str, ShutdownDecision] | None:
        """Devuelve (acción, decisión) si en (window_start, now] había un apagado previsto."""
        d = window_start.astimezone(tz).date() - timedelta(days=1)
        last = now.astimezone(tz).date()
        result = None
        while d <= last:
            dec = shutdown_decision(d, settings, exceptions, tz)
            if dec.scheduled and d not in self.handled and window_start < dec.when_utc <= now:
                if now - dec.when_utc > margin:
                    action = MISSED
                elif not data_ok:
                    action = BLOCKED
                elif dec.suspended_by:
                    action = SUSPENDED
                else:
                    action = SHUTDOWN
                self.handled[d] = action
                result = (action, dec)
            d += timedelta(days=1)
        cutoff = last - timedelta(days=7)
        self.handled = {k: v for k, v in self.handled.items() if k >= cutoff}
        return result

    def next_shutdown(self, after: datetime, settings, exceptions: list[CalendarException], tz: ZoneInfo,
                      horizon_days: int = 31) -> ShutdownDecision | None:
        """Próximo apagado que sí se va a realizar (para mostrarlo en la interfaz)."""
        d = after.astimezone(tz).date()
        for _ in range(horizon_days + 1):
            dec = shutdown_decision(d, settings, exceptions, tz)
            if dec.will_shutdown and dec.when_utc > after and d not in self.handled:
                return dec
            d += timedelta(days=1)
        return None
