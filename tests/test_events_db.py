"""1. Creación, edición y eliminación de eventos · 13. Errores de base de datos."""
from datetime import date, time

import pytest

from aulaaudio.db import SCHEMA_VERSION, Database, DatabaseError
from aulaaudio.models import END_DURATION, END_TIME, Event, ValidationError
from conftest import add_event


def test_crear_editar_eliminar(db, track):
    tid = track()
    eid = add_event(db, "Timbre 1", time(8, 30), track_id=tid, kind="timbre", priority=8)
    ev = db.event(eid)
    assert ev.name == "Timbre 1" and ev.start == time(8, 30) and ev.days == frozenset(range(5))
    ev.name, ev.start, ev.days = "Timbre primera hora", time(8, 25), frozenset({0, 2})
    db.save_event(ev)
    ev2 = db.event(eid)
    assert (ev2.name, ev2.start, ev2.days) == ("Timbre primera hora", time(8, 25), frozenset({0, 2}))
    db.delete_event(eid)
    assert db.event(eid) is None


def test_duplicar_y_desactivar(db, track):
    eid = add_event(db, "Recreo", track_id=track())
    dup = db.duplicate_event(eid)
    assert dup != eid and db.event(dup).name == "Recreo (copia)"
    db.set_event_enabled(eid, False)
    assert db.event(eid).enabled is False and db.event(dup).enabled is True


@pytest.mark.parametrize("changes, msg", [
    (dict(name="  "), "nombre"),
    (dict(days=frozenset()), "día"),
    (dict(track_id=None), "archivo"),
    (dict(end_mode=END_DURATION, duration_min=0), "duración"),
    (dict(end_mode=END_TIME, end_time=time(8, 0)), "coincidir"),
    (dict(priority=11), "prioridad"),
    (dict(volume=150), "volumen"),
])
def test_validacion(db, track, changes, msg):
    base = dict(name="X", days=frozenset({0}), start=time(8, 0), track_id=track(), schedule_id=db.default_schedule_id())
    base.update(changes)
    with pytest.raises(ValidationError, match=msg):
        db.save_event(Event(**base))


def test_evento_extraordinario_sin_horario(db, track):
    eid = db.save_event(Event(name="Simulacro", date=date(2026, 11, 5), start=time(12, 0), track_id=track()))
    ev = db.event(eid)
    assert ev.is_one_off and ev.schedule_id is None and ev.days == frozenset()
    assert [e.id for e in db.events(one_off=True)] == [eid]


def test_copiar_dia(db, track):
    tid = track()
    a = add_event(db, "A", time(8, 0), days=frozenset({0}), track_id=tid)
    b = add_event(db, "B", time(9, 0), days=frozenset({2}), track_id=tid)
    n = db.copy_day(db.default_schedule_id(), 0, [1, 2], replace=True)
    assert n == 2
    assert db.event(a).days == frozenset({0, 1, 2})
    assert db.event(b) is None  # se quedó sin días al sustituir el miércoles


def test_borrar_pista_deja_evento_sin_audio(db, track):
    tid = track()
    eid = add_event(db, "A", track_id=tid)
    db.delete_track(tid)
    assert db.event(eid).track_id is None


def test_nombres_unicos_de_listas(db):
    db.add_playlist("Recreo")
    with pytest.raises(ValidationError):
        db.add_playlist("Recreo")


def test_inyeccion_sql_tratada_como_texto(db, track):
    nasty = "x'); DROP TABLE events; --"
    eid = add_event(db, nasty, track_id=track())
    assert db.event(eid).name == nasty
    assert db.tracks(search="%' OR 1=1 --") == []


# ----------------------------------------------------------------- errores de base de datos
def test_base_de_datos_corrupta(tmp_path):
    f = tmp_path / "rota.db"
    f.write_bytes(b"esto no es sqlite" * 200)
    with pytest.raises(DatabaseError, match="dañada"):
        Database(f)


def test_esquema_mas_moderno(tmp_path):
    import sqlite3

    f = tmp_path / "futura.db"
    con = sqlite3.connect(f)
    con.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 5}")
    con.close()
    with pytest.raises(DatabaseError, match="más moderna"):
        Database(f)


def test_base_cerrada(db):
    db.close()
    with pytest.raises(DatabaseError):
        db.events()


def test_transaccion_se_deshace(db, track):
    tid = track()
    with pytest.raises(RuntimeError):
        with db.tx() as c:
            c.execute("INSERT INTO playlists(name) VALUES (?)", ("temporal",))
            raise RuntimeError("fallo a mitad")
    assert db.playlists() == []
    assert db.integrity_ok()
