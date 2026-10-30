"""Datos de demostración.

Todos los elementos de ejemplo llevan la marca `demo` y el prefijo «[EJEMPLO]», usan sonidos
generados por el propio programa y se crean DESACTIVADOS: nada suena hasta que el usuario
revise y active cada evento. Se pueden borrar de una vez desde Configuración.
"""
from __future__ import annotations

from datetime import date, time, timedelta
from pathlib import Path

from . import sounds
from .library import normalize, title_for
from .models import (
    CONFLICT_INTERRUPT,
    CONFLICT_WAIT,
    END_AUDIO,
    END_DURATION,
    END_TIME,
    Event,
)

P = "[EJEMPLO] "
WEEKDAYS = frozenset(range(5))


def load_demo(db, sounds_dir: Path) -> None:
    bell = sounds.demo_bell(sounds_dir)
    notice = sounds.demo_notice(sounds_dir)
    music = [sounds.demo_music(sounds_dir, i) for i in (1, 2)]

    def track(p: Path) -> int:
        p = normalize(p)
        t = db.track_by_path(p)
        return t.id if t else db.add_track(p, P + title_for(p).replace("EJEMPLO ", ""), Path(p).stat().st_size, demo=True)

    bell_id, notice_id = track(bell), track(notice)
    music_ids = [track(m) for m in music]
    existing = {pl.name for pl in db.playlists()}
    name = P + "Música ambiental"
    if name in existing:
        pl_id = next(pl.id for pl in db.playlists() if pl.name == name)
    else:
        pl_id = db.add_playlist(name, "secuencial", True, demo=True)
        db.set_playlist_tracks(pl_id, music_ids)
    sid = db.default_schedule_id()

    def ev(**kw) -> None:
        base = dict(schedule_id=sid, days=WEEKDAYS, enabled=False, demo=True)
        base.update(kw)
        db.save_event(Event(**base))

    ev(name=P + "Música de entrada", kind="musica", start=time(8, 20), end_mode=END_TIME, end_time=time(8, 30),
       playlist_id=pl_id, priority=3, conflict=CONFLICT_WAIT, resume=True)
    ev(name=P + "Timbre comienzo de clase", kind="timbre", start=time(8, 30), end_mode=END_AUDIO,
       track_id=bell_id, priority=8, conflict=CONFLICT_INTERRUPT)
    for h, m in ((9, 25), (10, 20), (12, 40), (13, 35)):
        ev(name=P + f"Timbre cambio de clase {h:02d}:{m:02d}", kind="timbre", start=time(h, m),
           end_mode=END_AUDIO, track_id=bell_id, priority=8, conflict=CONFLICT_INTERRUPT)
    ev(name=P + "Timbre inicio del recreo", kind="timbre", start=time(11, 15), end_mode=END_AUDIO,
       track_id=bell_id, priority=8, conflict=CONFLICT_INTERRUPT)
    ev(name=P + "Música durante el recreo", kind="musica", start=time(11, 16), end_mode=END_TIME,
       end_time=time(11, 44), playlist_id=pl_id, volume=70, priority=3, conflict=CONFLICT_WAIT, resume=True)
    ev(name=P + "Timbre fin del recreo", kind="timbre", start=time(11, 45), end_mode=END_AUDIO,
       track_id=bell_id, priority=9, conflict=CONFLICT_INTERRUPT)
    ev(name=P + "Timbre final de clase", kind="timbre", start=time(14, 30), end_mode=END_AUDIO,
       track_id=bell_id, priority=8, conflict=CONFLICT_INTERRUPT)
    ev(name=P + "Música de salida", kind="musica", start=time(14, 31), end_mode=END_DURATION, duration_min=10,
       playlist_id=pl_id, priority=3, conflict=CONFLICT_WAIT, resume=True)
    # aviso puntual: el próximo viernes
    today = date.today()
    friday = today + timedelta(days=(4 - today.weekday()) % 7 or 7)
    db.save_event(Event(name=P + "Aviso: reunión de claustro", kind="aviso", date=friday, start=time(13, 0),
                        end_mode=END_AUDIO, track_id=notice_id, priority=6, conflict=CONFLICT_INTERRUPT,
                        enabled=False, demo=True))
