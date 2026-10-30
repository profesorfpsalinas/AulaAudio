"""Relojes intercambiables.

El motor nunca llama directamente a datetime.now(): recibe un reloj. En producción se usa
SystemClock; en las pruebas y en el modo de simulación se usa SimulatedClock, que permite
avanzar el tiempo virtualmente sin esperar a la hora real.
Todos los instantes se manejan en UTC con zona horaria; la conversión a hora local se hace
en el planificador con zoneinfo.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    @property
    def simulated(self) -> bool:
        return False


class SimulatedClock:
    """Reloj virtual. `speed` > 0 hace que avance solo, multiplicando el tiempo real."""

    def __init__(self, start: datetime, speed: float = 0.0):
        if start.tzinfo is None:
            raise ValueError("El reloj simulado necesita una fecha con zona horaria")
        self._base = start.astimezone(timezone.utc)
        self._speed = speed
        self._real_base = time.monotonic()

    def now(self) -> datetime:
        if self._speed:
            elapsed = (time.monotonic() - self._real_base) * self._speed
            return self._base + timedelta(seconds=elapsed)
        return self._base

    def set(self, moment: datetime) -> None:
        self._base = moment.astimezone(timezone.utc)
        self._real_base = time.monotonic()

    def advance(self, seconds: float = 0, **kwargs) -> datetime:
        self.set(self.now() + timedelta(seconds=seconds, **kwargs))
        return self.now()

    @property
    def simulated(self) -> bool:
        return True
