"""14. Interacción de la interfaz con el motor de reproducción (sin sonido real)."""
from datetime import time

import pytest
from PySide6.QtCore import Qt

from aulaaudio.config import ConfigStore
from aulaaudio.engine import PlaybackEngine
from aulaaudio.models import END_TIME
from aulaaudio.ui import common
from aulaaudio.ui.common import AppContext
from aulaaudio.ui.main_window import MainWindow
from conftest import add_event, local, run_until, start_engine_at


@pytest.fixture
def window(qtbot, monkeypatch, paths, db, settings, backend, clock):
    # Confirmaciones automáticas: las pruebas no deben quedarse esperando diálogos.
    for mod in ("aulaaudio.ui.common", "aulaaudio.ui.home", "aulaaudio.ui.schedule_tab",
                "aulaaudio.ui.main_window", "aulaaudio.ui.library_tab", "aulaaudio.ui.settings_tab"):
        monkeypatch.setattr(f"{mod}.ask", lambda *a, **k: True, raising=False)
    for mod in ("aulaaudio.ui.common", "aulaaudio.ui.home", "aulaaudio.ui.schedule_tab",
                "aulaaudio.ui.library_tab", "aulaaudio.ui.settings_tab"):
        monkeypatch.setattr(f"{mod}.info", lambda *a, **k: None, raising=False)
        monkeypatch.setattr(f"{mod}.error", lambda *a, **k: None, raising=False)
    settings.primera_ejecucion_completada = True
    store = ConfigStore(paths.config_file)
    engine = PlaybackEngine(db, settings, backend, clock)
    ctx = AppContext(paths, db, store, settings, engine, backend, clock)
    w = MainWindow(ctx)
    qtbot.addWidget(w)
    w.show()
    yield w
    w._really_quit = True
    engine.shutdown()


def test_estado_inicial(window):
    assert "Funcionando" in window.home.status.text()
    assert not window.home.btn_stop.isEnabled()


def test_evento_programado_se_ve_en_inicio_y_se_detiene_con_el_boton(window, qtbot, db, clock, backend, track):
    add_event(db, "Recreo", time(11, 0), track_id=track(), end_mode=END_TIME, end_time=time(11, 30))
    window.ctx.notify_data_changed()
    eng = window.ctx.engine
    start_engine_at(eng, clock, local(2026, 11, 2, 10, 59, 58))
    assert "Recreo" in window.home.next_lbl.text()
    run_until(eng, clock, local(2026, 11, 2, 11, 0, 1))
    assert "Recreo" in window.home.now_lbl.text()
    assert window.home.btn_stop.isEnabled() and window.home.btn_pause.isEnabled()
    qtbot.mouseClick(window.home.btn_pause, Qt.MouseButton.LeftButton)
    assert backend.paused and window.home.btn_resume.isEnabled()
    qtbot.mouseClick(window.home.btn_resume, Qt.MouseButton.LeftButton)
    assert not backend.paused
    qtbot.mouseClick(window.home.btn_stop, Qt.MouseButton.LeftButton)
    assert eng.current is None and backend.playing is None
    assert window.home.now_lbl.text() == "Nada."


def test_boton_automatizacion(window, qtbot, paths):
    qtbot.mouseClick(window.home.btn_auto, Qt.MouseButton.LeftButton)
    assert "Detenido" in window.home.status.text()
    assert ConfigStore(paths.config_file).load().automatizacion_activa is False  # se guarda
    qtbot.mouseClick(window.home.btn_auto, Qt.MouseButton.LeftButton)
    assert "Funcionando" in window.home.status.text()


def test_prueba_de_sonido_usa_el_motor(window, qtbot, backend):
    qtbot.mouseClick(window.home.btn_test, Qt.MouseButton.LeftButton)
    assert backend.playing and backend.playing.endswith("prueba_de_sonido.wav")
    assert window.ctx.engine.current.kind == "prueba"


def test_incidencia_visible_y_reconocible(window, qtbot, db, clock, backend, track):
    backend.problem = "No hay ningún dispositivo de salida de audio disponible."
    add_event(db, "Timbre", time(9, 0), track_id=track())
    window.ctx.notify_data_changed()
    eng = window.ctx.engine
    start_engine_at(eng, clock, local(2026, 11, 2, 8, 59, 59))
    run_until(eng, clock, local(2026, 11, 2, 9, 0, 1))
    assert "Incidencia" in window.home.status.text()
    assert window.home.btn_ack.isVisible()
    backend.problem = None
    qtbot.mouseClick(window.home.btn_ack, Qt.MouseButton.LeftButton)
    assert "Funcionando" in window.home.status.text()


def test_evento_en_curso_al_abrir(window, qtbot, db, clock, backend, track):
    add_event(db, "Recreo", time(11, 0), track_id=track(), end_mode=END_TIME, end_time=time(11, 30))
    window.ctx.notify_data_changed()
    start_engine_at(window.ctx.engine, clock, local(2026, 11, 2, 11, 10))
    assert window.home.missed_box.isVisibleTo(window) and backend.played == []
    qtbot.mouseClick(window.home.btn_missed, Qt.MouseButton.LeftButton)
    assert backend.played and window.ctx.engine.current.title == "Recreo"


def test_tabla_de_programacion_y_desactivar(window, qtbot, db, track):
    add_event(db, "Timbre 1", time(8, 30), track_id=track())
    window.ctx.notify_data_changed()
    table = window.schedule.table
    assert table.rowCount() == 1 and table.item(0, 3).text() == "Timbre 1"
    table.selectRow(0)
    window.schedule._toggle()
    assert db.events()[0].enabled is False
    assert window.schedule.table.item(0, 0).text() == "No"
    assert window.ctx.engine.next_occurrence() is None  # el motor recargó la programación


def _save_with_dialog(monkeypatch, fill):
    """Sustituye exec() del diálogo: rellena los campos y pulsa «Guardar» como haría el usuario."""
    from aulaaudio.ui.event_dialog import EventDialog

    def fake_exec(dlg):
        fill(dlg)
        dlg._accept()
        return dlg.result()
    monkeypatch.setattr(EventDialog, "exec", fake_exec)


def test_nuevo_evento_desde_la_ventana(window, monkeypatch, db, track):
    tid = track("timbre.mp3")
    window.ctx.notify_data_changed()

    def fill(dlg):
        dlg.name.setText("Timbre de entrada")
        dlg.kind.setCurrentIndex(1)  # Timbre
        dlg.cb_track.setCurrentIndex(dlg.cb_track.findData(tid))
    _save_with_dialog(monkeypatch, fill)
    window.schedule._new()
    evs = db.events()
    assert [e.name for e in evs] == ["Timbre de entrada"] and evs[0].track_id == tid
    assert window.schedule.table.rowCount() == 1


def test_evento_de_musica_sin_listas_usa_un_archivo(window, monkeypatch, db, track):
    tid = track("cancion.mp3")
    window.ctx.notify_data_changed()
    _save_with_dialog(monkeypatch, lambda dlg: dlg.name.setText("Recreo"))
    window.schedule._new()
    assert [(e.name, e.track_id) for e in db.events()] == [("Recreo", tid)]


def test_editar_evento_desde_la_ventana(window, monkeypatch, db, track):
    add_event(db, "Viejo", time(8, 0), track_id=track())
    window.ctx.notify_data_changed()
    _save_with_dialog(monkeypatch, lambda dlg: dlg.name.setText("Nuevo nombre"))
    window.schedule.table.selectRow(0)
    window.schedule._edit()
    assert [e.name for e in db.events()] == ["Nuevo nombre"]


def test_evento_extraordinario_desde_calendario(window, monkeypatch, db, track):
    track()
    window.ctx.notify_data_changed()
    _save_with_dialog(monkeypatch, lambda dlg: dlg.name.setText("Simulacro"))
    window.calendar._new_oneoff()
    assert [(e.name, e.is_one_off) for e in db.events()] == [("Simulacro", True)]


def test_volumen_desde_la_interfaz(window, backend):
    window.home.slider.setValue(50)
    assert window.ctx.settings.volumen_general == 50
    assert window.ctx.engine.settings.volumen_general == 50


def test_cerrar_ventana_no_detiene_la_programacion(window):
    window.ctx.settings.minimizar_a_bandeja = True
    if window.tray is None:
        pytest.skip("Bandeja del sistema no disponible en esta plataforma de pruebas")
    window.ctx.settings.aviso_bandeja_mostrado = True
    window.close()
    assert not window.isVisible() and window.ctx.engine is not None
