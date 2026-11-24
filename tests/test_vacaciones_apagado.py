"""Vacaciones, festivos, vacaciones.json y apagado programado (apartado 9 del encargo).

Estas pruebas no necesitan Qt: usan la lógica pura (scheduler, power, vacaciones), la base
de datos SQLite en una carpeta temporal y fechas fijas.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from aulaaudio import vacaciones as vac
from aulaaudio.config import ConfigStore, Settings
from aulaaudio.db import SCHEMA_V1, Database
from aulaaudio.models import (
    EXC_ALT,
    EXC_HOLIDAY,
    EXC_VACATION,
    CalendarException,
    Event,
    ValidationError,
)
from aulaaudio.power import BLOCKED, MISSED, SHUTDOWN, SUSPENDED, ShutdownPlanner, shutdown_decision
from aulaaudio.scheduler import ScheduleData, Scheduler

TZ = ZoneInfo("Europe/Madrid")

EJEMPLO = """{
  "vacaciones": [
    {"nombre": "Navidad", "fecha_inicio": "2026-12-23", "fecha_fin": "2027-01-07",
     "desactivar_encendido": true, "desactivar_apagado": true},
    {"nombre": "Semana Santa", "fecha_inicio": "2027-03-22", "fecha_fin": "2027-03-29",
     "desactivar_encendido": true, "desactivar_apagado": true},
    {"nombre": "Vacaciones de verano", "fecha_inicio": "2027-07-01", "fecha_fin": "2027-08-31",
     "desactivar_encendido": true, "desactivar_apagado": true}
  ],
  "dias_sueltos": ["2026-12-08", "2027-01-06"]
}"""


def at(y, mo, d, h=0, mi=0, s=0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=TZ)


def exc(name, d1, d2=None, kind=EXC_VACATION, sounds=True, shutdown=True, **kw) -> CalendarException:
    return CalendarException(name=name, kind=kind, date_from=d1, date_to=d2 or d1,
                             suspend_sounds=sounds, suspend_shutdown=shutdown, **kw).validate()


def shutdown_settings(**kw) -> Settings:
    s = Settings(apagado_activo=True, apagado_hora="15:30", apagado_dias=[0, 1, 2, 3, 4])
    for k, v in kw.items():
        setattr(s, k, v)
    return s.validated()


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "aulaaudio.db")
    yield d
    d.close()


def weekly_scheduler(db, exceptions) -> Scheduler:
    tid = db.add_track("/tmp/timbre.mp3", "timbre", 10)
    db.save_event(Event(name="Entrada", kind="timbre", start=time(8, 0), days=frozenset(range(5)),
                        schedule_id=db.default_schedule_id(), track_id=tid, priority=8))
    data = ScheduleData(db.events(), exceptions, db.default_schedule_id(), {s.id: s.name for s in db.schedules()})
    return Scheduler(data, "Europe/Madrid")


# ================================================================== vacaciones.json
def test_lee_el_ejemplo_del_encargo():
    res = vac.parse(EJEMPLO)
    assert [e.name for e in res.items] == ["Navidad", "Semana Santa", "Vacaciones de verano",
                                           "Festivo 08/12/2026", "Festivo 06/01/2027"]
    navidad = res.items[0]
    assert (navidad.kind, navidad.date_from, navidad.date_to) == (EXC_VACATION, date(2026, 12, 23), date(2027, 1, 7))
    assert navidad.suspend_sounds and navidad.suspend_shutdown  # «desactivar_encendido» = sonidos
    dia = res.items[3]
    assert (dia.kind, dia.date_from, dia.date_to) == (EXC_HOLIDAY, date(2026, 12, 8), date(2026, 12, 8))
    assert res.warnings == []


def test_cada_periodo_decide_que_suspende():
    res = vac.parse(json.dumps({"vacaciones": [
        {"nombre": "Julio", "fecha_inicio": "2027-07-01", "fecha_fin": "2027-07-31",
         "desactivar_sonidos": True, "desactivar_apagado": False}],
        "dias_sueltos": [{"fecha": "2026-11-02", "nombre": "Puente", "desactivar_sonidos": False,
                          "desactivar_apagado": True}]}))
    julio, puente = res.items
    assert julio.suspend_sounds and not julio.suspend_shutdown
    assert not puente.suspend_sounds and puente.suspend_shutdown and puente.name == "Puente"


@pytest.mark.parametrize("texto, mensaje", [
    ('{"vacaciones": [ {"nombre": "Navidad" "fecha_inicio": "2026-12-23"} ]}', "línea 1"),
    ("no es json", "dañado"),
    ('{"vacaciones": [{"nombre": "X", "fecha_inicio": "2026-12-23", "fecha_fin": "2026-12-01"}]}',
     "posterior"),
    ('{"vacaciones": [{"nombre": "X", "fecha_inicio": "2026-02-30", "fecha_fin": "2026-03-01"}]}', "no es válida"),
    ('{"vacaciones": [{"nombre": "X", "fecha_inicio": "23/12/2026", "fecha_fin": "2027-01-07"}]}', "AAAA-MM-DD"),
    ('{"vacaciones": [{"nombre": "X", "fecha_inicio": "2026-12-23", "fecha_fin": "2027-01-07", '
     '"desactivar_apagado": "si"}]}', "true o false"),
    ('{"vacaciones": [{"fecha_inicio": "2026-12-23", "fecha_fin": "2027-01-07"}]}', "nombre"),
    ('{"vacaciones": [{"nombre": "X", "fecha_inicio": "2026-12-23"}]}', "fecha_fin"),
    ('{"otra_cosa": []}', "no contiene"),
    ('[1, 2]', "empezar por {"),
    ('{"version": 99, "vacaciones": []}', "más moderna"),
])
def test_archivo_danado_o_incorrecto_no_importa_nada(texto, mensaje):
    with pytest.raises(vac.VacationFileError) as info:
        vac.parse(texto)
    assert mensaje in str(info.value)


def test_archivo_ilegible_avisa_y_la_base_de_datos_no_cambia(db, tmp_path):
    db.save_exception(exc("Navidad", date(2026, 12, 23), date(2027, 1, 7)))
    f = tmp_path / "vacaciones.json"
    f.write_text('{"vacaciones": [', encoding="utf-8")
    with pytest.raises(vac.VacationFileError):
        vac.read_file(f)
    with pytest.raises(vac.VacationFileError):
        vac.read_file(tmp_path / "no_existe.json")
    assert [e.name for e in db.exceptions()] == ["Navidad"]


def test_acepta_bom_del_bloc_de_notas(tmp_path):
    f = tmp_path / "vacaciones.json"
    f.write_bytes(b"\xef\xbb\xbf" + EJEMPLO.encode("utf-8"))
    assert len(vac.read_file(f).items) == 5


def test_detecta_solapes_y_duplicados():
    res = vac.parse(json.dumps({"vacaciones": [
        {"nombre": "Navidad", "fecha_inicio": "2026-12-20", "fecha_fin": "2027-01-07"},
        {"nombre": "Fin de trimestre", "fecha_inicio": "2026-12-18", "fecha_fin": "2026-12-22"},
        {"nombre": "Navidad", "fecha_inicio": "2026-12-20", "fecha_fin": "2027-01-07"}]}))
    assert len(res.items) == 2
    assert any("repetido" in w for w in res.warnings)
    assert any("Se solapan" in w and "Fin de trimestre" in w for w in res.warnings)


def test_exportar_e_importar_conserva_todo(tmp_path):
    items = [exc("Navidad", date(2026, 12, 23), date(2027, 1, 7), shutdown=False, notes="Consejería"),
             exc("Inmaculada", date(2026, 12, 8), kind=EXC_HOLIDAY),
             exc("Jornada reducida", date(2027, 6, 1), date(2027, 6, 20), kind=EXC_ALT, schedule_id=1)]
    f = tmp_path / "vacaciones.json"
    assert vac.write_file(f, items) is None
    data = json.loads(f.read_text(encoding="utf-8"))
    assert data["dias_sueltos"][0]["fecha"] == "2026-12-08"
    assert "Jornada reducida" not in f.read_text(encoding="utf-8")  # los cambios de horario no se exportan
    back = vac.read_file(f).items
    assert [(e.name, e.kind, e.date_from, e.date_to, e.suspend_sounds, e.suspend_shutdown, e.notes) for e in back] == \
           [(e.name, e.kind, e.date_from, e.date_to, e.suspend_sounds, e.suspend_shutdown, e.notes) for e in items[:2]]


def test_copia_de_seguridad_del_fichero_antes_de_sobrescribirlo(tmp_path):
    f = tmp_path / "vacaciones.json"
    f.write_text(EJEMPLO, encoding="utf-8")
    bak = vac.write_file(f, [exc("Navidad", date(2027, 12, 23), date(2028, 1, 7))])
    assert bak is not None and bak.read_text(encoding="utf-8") == EJEMPLO
    assert "2027-12-23" in f.read_text(encoding="utf-8")


def test_importar_anade_sin_duplicar_y_sustituir_conserva_cambios_de_horario():
    existing = [exc("Navidad", date(2026, 12, 23), date(2027, 1, 7)),
                exc("Reducida", date(2027, 6, 1), date(2027, 6, 20), kind=EXC_ALT, schedule_id=1)]
    incoming = vac.parse(EJEMPLO).items
    add, warnings = vac.merge_plan(existing, incoming, replace=False)
    assert "Navidad" not in [e.name for e in add] and len(add) == 4
    assert any("ya existe" in w for w in warnings)
    add, _ = vac.merge_plan(existing, incoming, replace=True)
    assert len(add) == 5  # al sustituir, Navidad se vuelve a crear desde el archivo


def test_duplicar_periodos_para_el_curso_siguiente():
    items = [exc("Navidad", date(2026, 12, 23), date(2027, 1, 7), shutdown=False),
             exc("Bisiesto", date(2028, 2, 29), kind=EXC_HOLIDAY)]
    existing = [exc("Navidad", date(2027, 12, 23), date(2028, 1, 7))]
    copies, warnings = vac.next_year_copies(items, existing)
    assert [(c.name, c.date_from, c.date_to) for c in copies] == [("Bisiesto", date(2029, 2, 28), date(2029, 2, 28))]
    assert "ya existe" in warnings[0]
    copies, _ = vac.next_year_copies(items[:1], [])
    assert copies[0].date_from == date(2027, 12, 23) and not copies[0].suspend_shutdown


# ================================================================== validaciones del modelo
def test_validaciones_de_fechas():
    with pytest.raises(ValidationError):
        exc("Al revés", date(2027, 1, 7), date(2026, 12, 23))
    e = exc("Cambio", date(2027, 6, 1), kind=EXC_ALT, schedule_id=1, sounds=True)
    assert e.suspend_sounds is False  # un cambio de horario no silencia


# ================================================================== reglas de sonido
def test_durante_navidad_no_suena_y_al_terminar_se_recupera(db):
    navidad = exc("Navidad", date(2026, 12, 23), date(2027, 1, 7))
    sch = weekly_scheduler(db, [navidad])
    assert sch.day_plan(date(2026, 12, 22)).occurrences  # martes lectivo
    for d in (date(2026, 12, 23), date(2026, 12, 28), date(2027, 1, 7)):  # fechas inclusivas
        plan = sch.day_plan(d)
        assert plan.silent and not plan.occurrences and "Navidad" in plan.reason
    assert sch.day_plan(date(2027, 1, 8)).occurrences  # viernes: vuelve la programación
    assert db.events()[0].enabled  # el horario semanal sigue guardado


def test_festivo_suelto_y_periodo_que_no_silencia(db):
    sch = weekly_scheduler(db, [exc("Inmaculada", date(2026, 12, 8), kind=EXC_HOLIDAY),
                                exc("Evaluación", date(2026, 12, 9), sounds=False)])
    assert not sch.day_plan(date(2026, 12, 8)).occurrences
    assert sch.day_plan(date(2026, 12, 9)).occurrences  # el usuario eligió no suspender los sonidos


def test_regla_mas_restrictiva_para_los_sonidos(db):
    sch = weekly_scheduler(db, [exc("Puente", date(2026, 12, 7), date(2026, 12, 9), sounds=False),
                                exc("Inmaculada", date(2026, 12, 8), kind=EXC_HOLIDAY)])
    assert sch.day_plan(date(2026, 12, 7)).occurrences
    assert not sch.day_plan(date(2026, 12, 8)).occurrences


# ================================================================== apagado programado
def test_decision_de_apagado_y_prioridades():
    s = shutdown_settings()
    navidad = exc("Navidad", date(2026, 12, 23), date(2027, 1, 7))
    reyes = exc("Reyes", date(2027, 1, 6), kind=EXC_HOLIDAY, shutdown=False)
    claustro = exc("Claustro", date(2026, 12, 9), kind=EXC_HOLIDAY, shutdown=False)
    items = [navidad, reyes, claustro]
    normal = shutdown_decision(date(2026, 12, 22), s, items, TZ)
    assert normal.will_shutdown and normal.when_utc == at(2026, 12, 22, 15, 30)
    dec = shutdown_decision(date(2027, 1, 6), s, items, TZ)
    assert dec.scheduled and not dec.will_shutdown and "Navidad" in dec.suspended_by  # la más restrictiva
    assert shutdown_decision(date(2026, 12, 9), s, items, TZ).will_shutdown  # festivo que no suspende el apagado
    assert not shutdown_decision(date(2026, 12, 26), s, items, TZ).scheduled  # sábado
    assert "detenida" in shutdown_decision(date(2026, 12, 22), shutdown_settings(automatizacion_activa=False),
                                           items, TZ).suspended_by  # parada manual: máxima prioridad
    assert not shutdown_decision(date(2026, 12, 22), shutdown_settings(apagado_activo=False), items, TZ).scheduled


def run_planner(planner, settings, items, start, end, step=timedelta(seconds=30), data_ok=True):
    events = []
    t = start
    while t < end:
        nxt = t + step
        found = planner.check(t, nxt, settings, items, TZ, data_ok, timedelta(seconds=60))
        if found:
            events.append((found[0], found[1].day))
        t = nxt
    return events


def test_apagado_una_vez_al_dia_y_suspendido_en_vacaciones():
    s = shutdown_settings()
    items = [exc("Navidad", date(2026, 12, 23), date(2027, 1, 7))]
    p = ShutdownPlanner()
    ev = run_planner(p, s, items, at(2026, 12, 21, 15, 0), at(2026, 12, 24, 16, 0), step=timedelta(minutes=1))
    assert ev == [(SHUTDOWN, date(2026, 12, 21)), (SHUTDOWN, date(2026, 12, 22)),
                  (SUSPENDED, date(2026, 12, 23)), (SUSPENDED, date(2026, 12, 24))]
    # después de las vacaciones se recupera la programación habitual
    ev = run_planner(p, s, items, at(2027, 1, 7, 15, 0), at(2027, 1, 8, 16, 0), step=timedelta(minutes=1))
    assert ev == [(SUSPENDED, date(2027, 1, 7)), (SHUTDOWN, date(2027, 1, 8))]


def test_no_se_apaga_con_retraso():
    s = shutdown_settings()
    p = ShutdownPlanner()
    # el programa estuvo sin funcionar de 15:00 a 17:00 (equipo suspendido)
    found = p.check(at(2026, 12, 21, 15, 0), at(2026, 12, 21, 17, 0), s, [], TZ, True, timedelta(seconds=60))
    assert found[0] == MISSED
    assert p.check(at(2026, 12, 21, 17, 0), at(2026, 12, 21, 17, 1), s, [], TZ, True, timedelta(seconds=60)) is None
    # al terminar unas vacaciones tampoco se ejecutan apagados atrasados
    items = [exc("Navidad", date(2026, 12, 23), date(2027, 1, 7))]
    p2 = ShutdownPlanner()
    assert p2.check(at(2027, 1, 8, 9, 0), at(2027, 1, 8, 9, 0, 1), s, items, TZ, True, timedelta(seconds=60)) is None


def test_si_no_se_puede_leer_el_calendario_no_se_apaga():
    p = ShutdownPlanner()
    found = p.check(at(2026, 12, 21, 15, 29, 59), at(2026, 12, 21, 15, 30, 1), shutdown_settings(), [], TZ,
                    False, timedelta(seconds=60))
    assert found[0] == BLOCKED


def test_proximo_apagado_salta_las_vacaciones():
    items = [exc("Navidad", date(2026, 12, 23), date(2027, 1, 7))]
    dec = ShutdownPlanner().next_shutdown(at(2026, 12, 22, 16, 0), shutdown_settings(), items, TZ)
    assert dec.day == date(2027, 1, 8)


def test_cambio_de_hora_no_duplica_el_apagado():
    s = shutdown_settings(apagado_hora="02:30", apagado_dias=list(range(7)))
    ev = run_planner(ShutdownPlanner(), s, [], at(2026, 10, 24, 0, 0), at(2026, 10, 26, 12, 0),
                     step=timedelta(minutes=5))
    # el 25/10/2026 las 02:30 existen dos veces (retraso de la hora): se apaga una sola vez
    assert ev == [(SHUTDOWN, date(2026, 10, 24)), (SHUTDOWN, date(2026, 10, 25)), (SHUTDOWN, date(2026, 10, 26))]


# ================================================================== persistencia
def test_los_periodos_siguen_tras_reiniciar(tmp_path):
    path = tmp_path / "aulaaudio.db"
    d1 = Database(path)
    d1.save_exceptions(vac.parse(EJEMPLO).items)
    d1.save_exception(exc("Claustro", date(2027, 2, 2), kind=EXC_HOLIDAY, sounds=False, shutdown=True))
    d1.close()
    d2 = Database(path)  # como al reiniciar Windows
    got = {e.name: e for e in d2.exceptions()}
    assert len(got) == 6 and got["Navidad"].date_to == date(2027, 1, 7)
    assert not got["Claustro"].suspend_sounds and got["Claustro"].suspend_shutdown
    d2.close()


def test_migracion_desde_la_version_1_conserva_los_festivos(tmp_path):
    path = tmp_path / "antigua.db"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA_V1)
    con.execute("INSERT INTO schedules(name, is_default) VALUES ('Horario ordinario', 1)")
    con.execute("INSERT INTO calendar_exceptions(name, kind, date_from, date_to, notes) "
                "VALUES ('Navidad', 'vacaciones', '2026-12-23', '2027-01-07', '')")
    con.execute("PRAGMA user_version = 1")
    con.commit()
    con.close()
    d = Database(path)
    (e,) = d.exceptions()
    assert d.schema_version() == 2 and e.name == "Navidad" and e.suspend_sounds and e.suspend_shutdown
    d.close()


def test_guardar_varios_es_todo_o_nada(db):
    good = exc("Navidad", date(2026, 12, 23), date(2027, 1, 7))
    bad = CalendarException(name="", kind=EXC_VACATION, date_from=date(2027, 1, 1), date_to=date(2027, 1, 2))
    with pytest.raises(ValidationError):
        db.save_exceptions([good, bad])
    assert db.exceptions() == []
    db.save_exception(exc("Reducida", date(2027, 6, 1), kind=EXC_ALT, schedule_id=db.default_schedule_id()))
    db.save_exceptions([good], replace_kinds=("vacaciones", "festivo", "no_lectivo"))
    assert sorted(e.name for e in db.exceptions()) == ["Navidad", "Reducida"]


def test_configuracion_del_apagado_se_valida_y_se_guarda(tmp_path):
    s = Settings(apagado_activo=True, apagado_hora="25:99", apagado_dias=[9, 1, 1, 0], apagado_aviso_minutos=0)
    v = s.validated()
    assert (v.apagado_hora, v.apagado_dias, v.apagado_aviso_minutos) == ("15:30", [0, 1], 1)
    store = ConfigStore(tmp_path / "config.json")
    store.save(Settings(apagado_activo=True, apagado_hora="14:45", apagado_dias=[0, 2, 4]))
    loaded = store.load()
    assert (loaded.apagado_activo, loaded.apagado_hora, loaded.apagado_dias) == (True, "14:45", [0, 2, 4])
