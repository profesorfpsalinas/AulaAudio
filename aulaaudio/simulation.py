"""Modo de simulación: recorre virtualmente un periodo y cuenta qué sonaría.

Usa el motor de reproducción REAL con un reloj simulado y un backend silencioso, de modo que
las reglas de prioridad, conflictos y reanudación son exactamente las mismas que en la
jornada real. Trabaja sobre una copia en memoria de la base de datos: no modifica nada.

Si no se conoce la duración de un archivo (aún no se ha reproducido nunca), se supone:
10 s para los timbres y avisos y 3 min para la música (los WAV se miden directamente).
"""
from __future__ import annotations

import os
import sqlite3
import wave
from dataclasses import dataclass
from datetime import datetime, timedelta

from .audio import FakeAudioBackend
from .clock import SimulatedClock
from .config import Settings
from .db import Database
from .models import KIND_MUSIC

MUSIC_SECONDS = 180
SHORT_SECONDS = 10


@dataclass
class SimEntry:
    when: datetime  # hora local
    level: str
    message: str


class _MemoryDb(Database):
    """Copia en memoria de la base de datos real."""

    def __init__(self, source: Database):
        self.path = ":memory:"
        self.conn = sqlite3.connect(":memory:", isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        source.conn.backup(self.conn)
        self.conn.execute("PRAGMA foreign_keys = ON")


class _TimedBackend(FakeAudioBackend):
    """Backend silencioso que «termina» cada pista cuando pasa su duración."""

    def __init__(self, clock, durations_ms: dict[str, int]):
        super().__init__()
        self.clock = clock
        self.durations_ms = durations_ms
        self.started: datetime | None = None

    def play(self, path, volume):
        tok = super().play(path, volume)
        self.started = self.clock.now()
        return tok

    def poll(self):
        if self.playing and self.started and not self.paused:
            ms = self.durations_ms.get(self.playing, MUSIC_SECONDS * 1000)
            if (self.clock.now() - self.started).total_seconds() * 1000 >= ms:
                self.finish()


def _wav_ms(path: str) -> int | None:
    try:
        with wave.open(path) as w:
            return int(w.getnframes() * 1000 / w.getframerate())
    except Exception:
        return None


def _durations(db: Database) -> dict[str, int]:
    short_ids = {e.track_id for e in db.events() if e.track_id and e.kind != KIND_MUSIC}
    result = {}
    for t in db.tracks():
        ms = t.duration_ms or (_wav_ms(t.path) if t.path.lower().endswith(".wav") else None)
        result[t.path] = ms or (SHORT_SECONDS if t.id in short_ids else MUSIC_SECONDS) * 1000
    return result


def simulate(db: Database, settings: Settings, start_local: datetime, end_local: datetime,
             step_seconds: int = 5, assume_files_exist: bool = True) -> list[SimEntry]:
    from .engine import PlaybackEngine

    mem = _MemoryDb(db)
    s = Settings(**settings.__dict__)
    s.automatizacion_activa = True
    s.fundido_salida_segundos = 0
    clock = SimulatedClock(start_local - timedelta(seconds=step_seconds))  # el primer paso cae en start
    backend = _TimedBackend(clock, _durations(mem))
    entries: list[SimEntry] = []
    tz = start_local.tzinfo

    def record(level, category, message):
        entries.append(SimEntry(clock.now().astimezone(tz), level, message))

    mem.add_history = record  # la simulación no escribe en el historial real
    engine = PlaybackEngine(mem, s, backend, clock)
    engine.file_exists = (lambda p: True) if assume_files_exist else os.path.isfile
    engine.tick()  # primera comprobación: fija el punto de partida
    for o in engine.missed_in_progress:
        record("aviso", "reproduccion", f"«{o.event.name}» ya estaba en curso al empezar la simulación: en uso "
               "real no se inicia solo, se ofrece el botón «Iniciar ahora».")
    end_utc = end_local.astimezone(clock.now().tzinfo)
    try:
        while clock.now() < end_utc:
            clock.advance(step_seconds)
            backend.poll()
            engine.tick()
    finally:
        engine.shutdown()
        mem.close()
    return entries
