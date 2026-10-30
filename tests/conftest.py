"""Utilidades comunes de las pruebas.

Las pruebas no emiten sonido (FakeAudioBackend), usan un reloj simulado, trabajan en
carpetas temporales y no modifican la configuración del sistema operativo.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from aulaaudio.audio import FakeAudioBackend  # noqa: E402
from aulaaudio.clock import SimulatedClock  # noqa: E402
from aulaaudio.config import Settings  # noqa: E402
from aulaaudio.db import Database  # noqa: E402
from aulaaudio.engine import PlaybackEngine  # noqa: E402
from aulaaudio.models import Event  # noqa: E402
from aulaaudio.paths import from_root  # noqa: E402

TZ = ZoneInfo("Europe/Madrid")


def local(y, mo, d, h=0, mi=0, s=0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=TZ)


@pytest.fixture
def paths(tmp_path):
    p = from_root(tmp_path / "aulaaudio")
    p.ensure()
    return p


@pytest.fixture
def db(paths):
    d = Database(paths.db_file)
    yield d
    d.close()


@pytest.fixture
def audio_dir(tmp_path):
    d = tmp_path / "musica"
    d.mkdir()
    return d


def make_file(folder: Path, name: str, size: int = 2048) -> str:
    p = folder / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\0" * size)
    return str(p)


@pytest.fixture
def track(db, audio_dir):
    """Crea pistas (archivos ficticios: el backend simulado no los decodifica)."""
    def _make(name="timbre.mp3", size=2048):
        path = make_file(audio_dir, name, size)
        return db.add_track(path, Path(name).stem, size)
    return _make


@pytest.fixture
def settings():
    s = Settings()
    s.fundido_salida_segundos = 0
    return s


@pytest.fixture
def clock():
    return SimulatedClock(local(2026, 11, 2, 7, 0))  # lunes 2 de noviembre de 2026


@pytest.fixture
def backend(qapp):
    return FakeAudioBackend()


@pytest.fixture
def engine(qapp, db, settings, backend, clock):
    e = PlaybackEngine(db, settings, backend, clock)
    yield e
    e.shutdown()


def add_event(db, name="Evento", start=time(8, 0), days=frozenset(range(5)), **kw) -> int:
    ev = Event(name=name, start=start, days=days, schedule_id=kw.pop("schedule_id", db.default_schedule_id()), **kw)
    return db.save_event(ev)


def run_until(engine, clock, moment: datetime, step: float = 1.0) -> None:
    """Avanza el reloj simulado hasta `moment` llamando a tick() en cada paso."""
    while clock.now() < moment:
        clock.advance(step)
        engine.tick()


def start_engine_at(engine, clock, moment: datetime) -> None:
    clock.set(moment)
    engine.reload()
    engine.tick()  # primera comprobación
