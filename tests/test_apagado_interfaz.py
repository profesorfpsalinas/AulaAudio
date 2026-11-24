"""Apagado programado y vacaciones en el motor y en la interfaz (sin apagar nada de verdad)."""
from datetime import date, time

import pytest

from aulaaudio import vacaciones
from aulaaudio.config import ConfigStore
from aulaaudio.engine import PlaybackEngine
from aulaaudio.models import EXC_HOLIDAY, EXC_VACATION, CalendarException
from aulaaudio.ui.common import AppContext
from aulaaudio.ui.main_window import MainWindow
from aulaaudio.ui.shutdown_dialog import ShutdownDialog
from conftest import add_event, local, run_until, start_engine_at


def history(db):
    return [r["message"] for r in db.history()]


@pytest.fixture
def apagado(settings):
    settings.apagado_activo = True
    settings.apagado_hora = "15:30"
    settings.apagado_dias = [0, 1, 2, 3, 4]
    settings.apagado_aviso_minutos = 2
    return settings


def navidad(**kw):
    return CalendarException(name="Navidad", kind=EXC_VACATION, date_from=date(2026, 12, 23),
                             date_to=date(2027, 1, 7), **kw)


# ----------------------------------------------------------------- motor
def test_el_motor_pide_apagar_a_su_hora(engine, clock, db, apagado):
    asked = []
    engine.shutdown_requested.connect(asked.append)
    start_engine_at(engine, clock, local(2026, 12, 21, 15, 29, 50))
    run_until(engine, clock, local(2026, 12, 21, 15, 29, 59))
    assert asked == []
    run_until(engine, clock, local(2026, 12, 21, 15, 31))
    assert asked == ["15:30"]
    assert any("apagado programado" in m for m in history(db))
    assert "Próximo apagado" in engine.next_shutdown_text() and "mañana" in engine.next_shutdown_text()


def test_en_vacaciones_no_se_apaga_ni_suena(engine, clock, db, apagado, track, backend):
    db.save_exception(navidad())
    add_event(db, "Entrada", time(8, 0), track_id=track())
    asked = []
    engine.shutdown_requested.connect(asked.append)
    start_engine_at(engine, clock, local(2026, 12, 23, 7, 59, 50))
    run_until(engine, clock, local(2026, 12, 23, 8, 0, 5))
    assert backend.played == []
    clock.set(local(2026, 12, 23, 15, 29, 50))
    engine.tick()
    run_until(engine, clock, local(2026, 12, 23, 15, 31))
    assert asked == []
    assert any("suspendido" in m and "Navidad" in m for m in history(db))


def test_cambiar_las_vacaciones_sin_reiniciar(engine, clock, db, apagado):
    asked = []
    engine.shutdown_requested.connect(asked.append)
    start_engine_at(engine, clock, local(2026, 12, 9, 15, 0))
    db.save_exception(CalendarException(name="Claustro", kind=EXC_HOLIDAY, date_from=date(2026, 12, 9),
                                        date_to=date(2026, 12, 9)))
    engine.reload()  # lo mismo que hace la interfaz tras guardar
    run_until(engine, clock, local(2026, 12, 9, 15, 31), step=5)
    assert asked == []


def test_parada_manual_tiene_prioridad(engine, clock, db, apagado):
    asked = []
    engine.shutdown_requested.connect(asked.append)
    engine.set_automation(False)
    start_engine_at(engine, clock, local(2026, 12, 21, 15, 29, 50))
    run_until(engine, clock, local(2026, 12, 21, 15, 31))
    assert asked == []


def test_si_falla_la_lectura_no_se_apaga(engine, clock, db, apagado, monkeypatch):
    asked = []
    engine.shutdown_requested.connect(asked.append)
    start_engine_at(engine, clock, local(2026, 12, 21, 15, 29, 50))
    monkeypatch.setattr(db, "events", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disco")))
    engine.reload()
    run_until(engine, clock, local(2026, 12, 21, 15, 31))
    assert asked == [] and not engine.data_ok
    assert any("cancelado por seguridad" in m for m in history(db))


# ----------------------------------------------------------------- ventana de cuenta atrás
def test_cuenta_atras_se_puede_cancelar(qtbot):
    dlg = ShutdownDialog("15:30", 5)
    qtbot.addWidget(dlg)
    got = []
    dlg.confirmed.connect(lambda: got.append("apagar"))
    dlg.cancelled.connect(lambda: got.append("cancelar"))
    assert "5:00" in dlg.counter.text() or "4:59" in dlg.counter.text()
    dlg.btn_cancel.click()
    assert got == ["cancelar"]


def test_cuenta_atras_termina_y_confirma(qtbot, monkeypatch):
    import aulaaudio.ui.shutdown_dialog as sd
    now = [1000.0]
    monkeypatch.setattr(sd.time, "monotonic", lambda: now[0])
    dlg = ShutdownDialog("15:30", 1)
    qtbot.addWidget(dlg)
    got = []
    dlg.confirmed.connect(lambda: got.append("apagar"))
    now[0] += 61
    dlg._tick()
    assert got == ["apagar"]


@pytest.fixture
def window(qtbot, monkeypatch, paths, db, apagado, backend, clock):
    for mod in ("aulaaudio.ui.common", "aulaaudio.ui.main_window", "aulaaudio.ui.calendar_tab",
                "aulaaudio.ui.settings_tab"):
        monkeypatch.setattr(f"{mod}.ask", lambda *a, **k: True, raising=False)
        monkeypatch.setattr(f"{mod}.info", lambda *a, **k: None, raising=False)
        monkeypatch.setattr(f"{mod}.error", lambda *a, **k: None, raising=False)
    apagado.primera_ejecucion_completada = True
    engine = PlaybackEngine(db, apagado, backend, clock)
    ctx = AppContext(paths, db, ConfigStore(paths.config_file), apagado, engine, backend, clock)
    w = MainWindow(ctx)
    qtbot.addWidget(w)
    w.show()
    yield w
    w._really_quit = True
    engine.shutdown()


def test_ventana_apaga_con_la_orden_del_sistema(window, monkeypatch, clock):
    calls = []
    monkeypatch.setattr("aulaaudio.system.shutdown_computer", lambda: (calls.append(1), (False, "prueba"))[1])
    eng = window.ctx.engine
    start_engine_at(eng, clock, local(2026, 12, 21, 15, 29, 55))
    run_until(eng, clock, local(2026, 12, 21, 15, 30, 2))
    dlg = window._shutdown_dialog
    assert dlg is not None and dlg.isVisible()
    dlg.btn_now.click()
    assert calls == [1]  # la orden falló («prueba»): se avisa y el programa sigue abierto
    assert any("prueba" in m for m in history(window.ctx.db))


def test_ventana_cancelar_no_apaga(window, monkeypatch, clock):
    calls = []
    monkeypatch.setattr("aulaaudio.system.shutdown_computer", lambda: (calls.append(1), (True, ""))[1])
    eng = window.ctx.engine
    start_engine_at(eng, clock, local(2026, 12, 21, 15, 29, 55))
    run_until(eng, clock, local(2026, 12, 21, 15, 30, 2))
    window._shutdown_dialog.btn_cancel.click()
    assert calls == [] and any("cancelado por el usuario" in m for m in history(window.ctx.db))


def test_calendario_muestra_lo_que_se_suspende(window, db):
    db.save_exceptions(vacaciones.parse('{"vacaciones": [{"nombre": "Navidad", "fecha_inicio": "2026-12-23", '
                                        '"fecha_fin": "2027-01-07", "desactivar_sonidos": true, '
                                        '"desactivar_apagado": false}]}').items)
    window.ctx.notify_data_changed()
    t = window.calendar.exc_table
    assert t.item(0, 0).text() == "Navidad" and t.item(0, 3).text() == "Sonidos"
    window.calendar.cal.setSelectedDate(window.calendar.cal.selectedDate().fromString("2026-12-28", "yyyy-MM-dd"))
    assert "Navidad" in window.calendar.day_reason.text()
    assert "se apagará" in window.calendar.day_reason.text()


def test_configuracion_guarda_el_apagado(window, paths):
    st = window.settings_tab
    st.load()
    assert st.off_on.isChecked() and st.off_time.time().toString("HH:mm") == "15:30"
    st.off_days[5].setChecked(True)
    st._save()
    assert window.ctx.settings.apagado_dias == [0, 1, 2, 3, 4, 5]
    assert ConfigStore(paths.config_file).load().apagado_dias == [0, 1, 2, 3, 4, 5]
