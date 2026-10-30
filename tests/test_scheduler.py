"""2. Siguiente evento · 3. Recurrencia semanal · 4. Excepciones · 6. Medianoche · 7. Cambio de hora."""
from datetime import date, time, timedelta, timezone

from aulaaudio.models import END_DURATION, END_TIME, CalendarException, Event
from aulaaudio.scheduler import ScheduleData, Scheduler
from conftest import TZ, add_event, local

UTC = timezone.utc


def sched(db, tz="Europe/Madrid") -> Scheduler:
    return Scheduler(ScheduleData.from_db(db), tz)


# ----------------------------------------------------------------- siguiente evento
def test_siguiente_evento(db, track):
    tid = track()
    add_event(db, "Entrada", time(8, 30), track_id=tid)
    add_event(db, "Salida", time(14, 30), track_id=tid)
    s = sched(db)
    nxt = s.next_occurrence(local(2026, 11, 2, 9, 0))  # lunes 9:00
    assert nxt.event.name == "Salida" and s.local(nxt.start_utc) == local(2026, 11, 2, 14, 30)
    nxt = s.next_occurrence(local(2026, 11, 6, 15, 0))  # viernes por la tarde -> lunes
    assert nxt.event.name == "Entrada" and s.local(nxt.start_utc).date() == date(2026, 11, 9)


def test_sin_eventos(db):
    assert sched(db).next_occurrence(local(2026, 11, 2)) is None


def test_eventos_desactivados_no_cuentan(db, track):
    eid = add_event(db, "A", time(8, 30), track_id=track())
    db.set_event_enabled(eid, False)
    assert sched(db).next_occurrence(local(2026, 11, 2)) is None


# ----------------------------------------------------------------- recurrencia semanal
def test_recurrencia_semanal(db, track):
    tid = track()
    add_event(db, "LMX", time(10, 0), days=frozenset({0, 1, 2}), track_id=tid)
    add_event(db, "Sabado", time(11, 0), days=frozenset({5}), track_id=tid)
    s = sched(db)
    week = [len(s.day_plan(date(2026, 11, 2) + timedelta(days=i)).occurrences) for i in range(7)]
    assert week == [1, 1, 1, 0, 0, 1, 0]
    nxt_week = s.day_plan(date(2026, 11, 9)).occurrences
    assert [o.event.name for o in nxt_week] == ["LMX"]


def test_orden_por_hora_y_prioridad(db, track):
    tid = track()
    add_event(db, "Musica", time(10, 0), track_id=tid, priority=3)
    add_event(db, "Timbre", time(10, 0), track_id=tid, priority=8)
    add_event(db, "Antes", time(9, 0), track_id=tid)
    names = [o.event.name for o in sched(db).day_plan(date(2026, 11, 2)).occurrences]
    assert names == ["Antes", "Timbre", "Musica"]


# ----------------------------------------------------------------- excepciones
def test_festivo_silencia_la_programacion(db, track):
    tid = track()
    add_event(db, "Timbre", time(8, 30), track_id=tid)
    db.save_exception(CalendarException(name="Fiesta local", kind="festivo",
                                        date_from=date(2026, 11, 3), date_to=date(2026, 11, 3)))
    s = sched(db)
    assert s.day_plan(date(2026, 11, 3)).occurrences == []
    assert s.day_plan(date(2026, 11, 3)).silent
    assert "Fiesta local" in s.day_plan(date(2026, 11, 3)).reason
    assert len(s.day_plan(date(2026, 11, 4)).occurrences) == 1
    # el siguiente evento salta el festivo
    nxt = s.next_occurrence(local(2026, 11, 2, 9, 0))
    assert s.local(nxt.start_utc).date() == date(2026, 11, 4)


def test_vacaciones_rango(db, track):
    add_event(db, "Timbre", time(8, 30), track_id=track())
    db.save_exception(CalendarException(name="Navidad", kind="vacaciones",
                                        date_from=date(2026, 12, 21), date_to=date(2027, 1, 7)))
    s = sched(db)
    assert all(not s.day_plan(date(2026, 12, 21) + timedelta(days=i)).occurrences for i in range(18))
    assert s.day_plan(date(2027, 1, 8)).occurrences


def test_horario_alternativo(db, track):
    tid = track()
    add_event(db, "Normal", time(14, 30), track_id=tid)
    reducida = db.add_schedule("Jornada reducida")
    add_event(db, "Reducida", time(13, 0), track_id=tid, schedule_id=reducida)
    db.save_exception(CalendarException(name="Junio", kind="horario_alternativo", schedule_id=reducida,
                                        date_from=date(2027, 6, 1), date_to=date(2027, 6, 22)))
    s = sched(db)
    assert [o.event.name for o in s.day_plan(date(2027, 6, 2)).occurrences] == ["Reducida"]
    assert [o.event.name for o in s.day_plan(date(2027, 5, 31)).occurrences] == ["Normal"]


def test_festivo_prevalece_sobre_cambio_de_horario(db, track):
    tid = track()
    alt = db.add_schedule("Otro")
    add_event(db, "Alt", time(9, 0), track_id=tid, schedule_id=alt)
    for kind, sid in (("horario_alternativo", alt), ("festivo", None)):
        db.save_exception(CalendarException(name=kind, kind=kind, schedule_id=sid,
                                            date_from=date(2026, 11, 3), date_to=date(2026, 11, 3)))
    assert sched(db).day_plan(date(2026, 11, 3)).occurrences == []


def test_evento_extraordinario_suena_en_festivo(db, track):
    tid = track()
    add_event(db, "Semanal", time(8, 30), track_id=tid)
    db.save_event(Event(name="Festival", date=date(2026, 11, 3), start=time(12, 0), track_id=tid))
    db.save_exception(CalendarException(name="Fiesta", kind="festivo",
                                        date_from=date(2026, 11, 3), date_to=date(2026, 11, 3)))
    assert [o.event.name for o in sched(db).day_plan(date(2026, 11, 3)).occurrences] == ["Festival"]


def test_excepcion_invalida():
    import pytest

    from aulaaudio.models import ValidationError

    with pytest.raises(ValidationError):
        CalendarException(name="X", kind="festivo", date_from=date(2026, 5, 2), date_to=date(2026, 5, 1)).validate()
    with pytest.raises(ValidationError):
        CalendarException(name="X", kind="horario_alternativo", schedule_id=None).validate()


# ----------------------------------------------------------------- medianoche
def test_evento_que_cruza_la_medianoche(db, track):
    add_event(db, "Nocturno", time(23, 50), days=frozenset({4}), track_id=track(),
              end_mode=END_TIME, end_time=time(0, 10))
    s = sched(db)
    o = s.day_plan(date(2026, 11, 6)).occurrences[0]
    assert s.local(o.end_utc) == local(2026, 11, 7, 0, 10)
    # el sábado a las 00:05 sigue «en curso» aunque el sábado no tenga eventos
    assert [x.event.name for x in s.in_progress(local(2026, 11, 7, 0, 5))] == ["Nocturno"]
    assert s.day_plan(date(2026, 11, 7)).occurrences == []


def test_evento_a_medianoche(db, track):
    add_event(db, "Cero", time(0, 0), days=frozenset({1}), track_id=track())
    s = sched(db)
    found = s.occurrences_between(local(2026, 11, 2, 23, 59), local(2026, 11, 3, 0, 1))
    assert len(found) == 1 and s.local(found[0].start_utc) == local(2026, 11, 3, 0, 0)


# ----------------------------------------------------------------- cambio de hora
def test_hora_de_verano_hora_inexistente(db, track):
    # 29/03/2026: en Madrid se pasa de 02:00 a 03:00. Las 02:30 no existen.
    add_event(db, "Raro", time(2, 30), days=frozenset({6}), track_id=track())
    add_event(db, "Normal", time(8, 0), days=frozenset({6}), track_id=track("b.mp3"))
    s = sched(db)
    occ = {o.event.name: o for o in s.day_plan(date(2026, 3, 29)).occurrences}
    assert s.local(occ["Raro"].start_utc).strftime("%H:%M") == "03:30"
    assert occ["Normal"].start_utc == local(2026, 3, 29, 8, 0).astimezone(UTC)
    assert occ["Normal"].start_utc.hour == 6  # 08:00 CEST = 06:00 UTC


def test_hora_de_invierno_hora_repetida(db, track):
    # 25/10/2026: de 03:00 se vuelve a 02:00. Las 02:30 ocurren dos veces: suena una sola.
    add_event(db, "Doble", time(2, 30), days=frozenset({6}), track_id=track())
    s = sched(db)
    found = s.occurrences_between(local(2026, 10, 25, 0, 0), local(2026, 10, 25, 5, 0))
    assert len(found) == 1
    assert found[0].start_utc == datetime_utc(2026, 10, 25, 0, 30)  # primera vez (CEST)


def test_duracion_en_tiempo_real_durante_cambio_de_hora(db, track):
    add_event(db, "Larga", time(1, 30), days=frozenset({6}), track_id=track(),
              end_mode=END_DURATION, duration_min=120)
    o = sched(db).day_plan(date(2026, 10, 25)).occurrences[0]
    assert o.end_utc - o.start_utc == timedelta(minutes=120)


def test_ocho_de_la_manana_tras_cambio_de_hora(db, track):
    add_event(db, "Entrada", time(8, 0), days=frozenset(range(7)), track_id=track())
    s = sched(db)
    before = s.day_plan(date(2026, 10, 24)).occurrences[0].start_utc
    after = s.day_plan(date(2026, 10, 26)).occurrences[0].start_utc
    assert before.hour == 6 and after.hour == 7  # 08:00 local en ambos casos
    assert s.local(after).strftime("%H:%M") == "08:00"


def datetime_utc(*a):
    from datetime import datetime

    return datetime(*a, tzinfo=UTC)


def test_zona_horaria_configurable(db, track):
    add_event(db, "Entrada", time(8, 0), track_id=track())
    canarias = sched(db, "Atlantic/Canary").day_plan(date(2026, 11, 2)).occurrences[0]
    madrid = sched(db).day_plan(date(2026, 11, 2)).occurrences[0]
    assert canarias.start_utc - madrid.start_utc == timedelta(hours=1)
    assert TZ.key == "Europe/Madrid"
