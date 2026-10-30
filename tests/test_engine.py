"""5. Conflictos · 6/7. Medianoche y cambio de hora en el motor · 8. Reinicio ·
9. Archivos inexistentes · 10. Dispositivos no disponibles."""
import os
from datetime import time, timedelta

from aulaaudio.audio import FAIL_DEVICE
from aulaaudio.engine import PlaybackEngine
from aulaaudio.models import END_AUDIO, END_DURATION, END_TIME
from conftest import add_event, local, make_file, run_until, start_engine_at


def history(db, level=None):
    return [r["message"] for r in db.history(level)]


# ----------------------------------------------------------------- funcionamiento básico
def test_evento_suena_a_su_hora_y_termina_a_su_hora(engine, clock, db, backend, track):
    add_event(db, "Recreo", time(11, 15), playlist_id=None, track_id=track("m.mp3"),
              end_mode=END_TIME, end_time=time(11, 45), kind="musica")
    start_engine_at(engine, clock, local(2026, 11, 2, 11, 14, 50))
    run_until(engine, clock, local(2026, 11, 2, 11, 14, 59))
    assert backend.playing is None
    run_until(engine, clock, local(2026, 11, 2, 11, 15, 1))
    assert engine.current.title == "Recreo" and backend.playing.endswith("m.mp3")
    run_until(engine, clock, local(2026, 11, 2, 11, 45, 1), step=5)
    assert engine.current is None and backend.playing is None


def test_lista_repite_hasta_la_hora_de_fin(engine, clock, db, backend, track):
    pid = db.add_playlist("Recreo", repeat=True)
    db.set_playlist_tracks(pid, [track("a.mp3"), track("b.mp3")])
    add_event(db, "Recreo", time(11, 0), playlist_id=pid, end_mode=END_DURATION, duration_min=30, kind="musica")
    start_engine_at(engine, clock, local(2026, 11, 2, 10, 59, 59))
    run_until(engine, clock, local(2026, 11, 2, 11, 0, 1))
    for _ in range(5):
        backend.finish()
    assert [os.path.basename(p) for p in backend.played] == ["a.mp3", "b.mp3", "a.mp3", "b.mp3", "a.mp3", "b.mp3"]
    assert engine.current is not None


def test_fin_audio_no_repite(engine, clock, db, backend, track):
    pid = db.add_playlist("Una vez", repeat=True)
    db.set_playlist_tracks(pid, [track("a.mp3"), track("b.mp3")])
    add_event(db, "Entrada", time(8, 0), playlist_id=pid, end_mode=END_AUDIO)
    start_engine_at(engine, clock, local(2026, 11, 2, 7, 59, 59))
    run_until(engine, clock, local(2026, 11, 2, 8, 0, 1))
    backend.finish()
    backend.finish()
    assert engine.current is None and len(backend.played) == 2


def test_volumen_por_evento(engine, clock, db, backend, track, settings):
    settings.volumen_general = 80
    add_event(db, "Suave", time(8, 0), track_id=track(), volume=50)
    start_engine_at(engine, clock, local(2026, 11, 2, 7, 59, 59))
    run_until(engine, clock, local(2026, 11, 2, 8, 0, 1))
    assert abs(backend.volume - 0.40) < 1e-9
    engine.set_master_volume(100)
    assert abs(backend.volume - 0.50) < 1e-9


# ----------------------------------------------------------------- conflictos
def test_timbre_interrumpe_musica_y_esta_se_reanuda(engine, clock, db, backend, track):
    music, bell = track("musica.mp3"), track("timbre.mp3")
    add_event(db, "Recreo", time(11, 0), track_id=music, kind="musica", priority=3, conflict="esperar",
              end_mode=END_TIME, end_time=time(11, 30), resume=True)
    add_event(db, "Timbre", time(11, 10), track_id=bell, kind="timbre", priority=8, conflict="interrumpir")
    start_engine_at(engine, clock, local(2026, 11, 2, 10, 59, 59))
    run_until(engine, clock, local(2026, 11, 2, 11, 0, 1))
    backend.position = 42_000
    run_until(engine, clock, local(2026, 11, 2, 11, 10, 1), step=5)
    assert engine.current.title == "Timbre" and backend.playing.endswith("timbre.mp3")
    backend.finish()  # termina el timbre
    assert engine.current.title == "Recreo" and backend.playing.endswith("musica.mp3")
    assert backend.position == 42_000  # continúa donde se quedó
    assert any("reanuda" in m for m in history(db))


def test_sin_reanudar_si_no_esta_activado(engine, clock, db, backend, track):
    add_event(db, "Musica", time(11, 0), track_id=track("m.mp3"), priority=3, end_mode=END_TIME,
              end_time=time(11, 30), resume=False)
    add_event(db, "Timbre", time(11, 10), track_id=track("t.mp3"), priority=8)
    start_engine_at(engine, clock, local(2026, 11, 2, 10, 59, 59))
    run_until(engine, clock, local(2026, 11, 2, 11, 10, 1), step=5)
    backend.finish()
    assert engine.current is None and backend.playing is None


def test_no_se_reanuda_fuera_de_su_franja(engine, clock, db, backend, track):
    add_event(db, "Musica", time(11, 0), track_id=track("m.mp3"), priority=3, end_mode=END_TIME,
              end_time=time(11, 20), resume=True)
    add_event(db, "Aviso largo", time(11, 15), track_id=track("t.mp3"), priority=8)
    start_engine_at(engine, clock, local(2026, 11, 2, 10, 59, 59))
    run_until(engine, clock, local(2026, 11, 2, 11, 25), step=5)  # el aviso dura más que la franja
    backend.finish()
    assert engine.current is None


def test_menor_prioridad_no_interrumpe(engine, clock, db, backend, track):
    add_event(db, "Timbre", time(9, 0), track_id=track("t.mp3"), priority=8)
    add_event(db, "Musica", time(9, 0), track_id=track("m.mp3"), priority=3, conflict="interrumpir")
    start_engine_at(engine, clock, local(2026, 11, 2, 8, 59, 59))
    run_until(engine, clock, local(2026, 11, 2, 9, 0, 1))
    assert engine.current.title == "Timbre"
    assert len(backend.played) == 1
    assert any("menor prioridad" in m for m in history(db, "aviso"))


def test_esperar_y_omitir(engine, clock, db, backend, track):
    add_event(db, "Aviso", time(9, 0), track_id=track("a.mp3"), priority=6)
    add_event(db, "Espera", time(9, 1), track_id=track("e.mp3"), priority=3, conflict="esperar")
    add_event(db, "Omite", time(9, 2), track_id=track("o.mp3"), priority=3, conflict="omitir")
    start_engine_at(engine, clock, local(2026, 11, 2, 8, 59, 59))
    run_until(engine, clock, local(2026, 11, 2, 9, 2, 5))
    assert engine.current.title == "Aviso" and len(engine.waiting) == 1
    backend.finish()
    assert engine.current.title == "Espera"
    assert not any(p.endswith("o.mp3") for p in backend.played)
    assert any("Omitido «Omite»" in m for m in history(db))


def test_la_espera_caduca(engine, clock, db, backend, track):
    add_event(db, "Largo", time(9, 0), track_id=track("a.mp3"), priority=6)
    add_event(db, "Espera", time(9, 1), track_id=track("e.mp3"), priority=3, conflict="esperar")
    start_engine_at(engine, clock, local(2026, 11, 2, 8, 59, 59))
    run_until(engine, clock, local(2026, 11, 2, 9, 20), step=10)  # más de 10 min esperando
    backend.finish()
    assert engine.current is None
    assert any("se pasó su hora" in m for m in history(db))


def test_nunca_dos_reproducciones_a_la_vez(engine, clock, db, backend, track):
    for i in range(4):
        add_event(db, f"E{i}", time(10, 0), track_id=track(f"{i}.mp3"), priority=5, conflict="interrumpir")
    start_engine_at(engine, clock, local(2026, 11, 2, 9, 59, 59))
    run_until(engine, clock, local(2026, 11, 2, 10, 0, 1))
    assert engine.current is not None
    assert backend.playing == backend.played[-1]  # solo una pista activa en el backend


def test_timbre_interrumpe_manual_y_manual_no_se_reanuda(engine, clock, db, backend, track):
    pid = db.add_playlist("Fiesta")
    db.set_playlist_tracks(pid, [track("f.mp3")])
    add_event(db, "Timbre", time(10, 0), track_id=track("t.mp3"), priority=8)
    start_engine_at(engine, clock, local(2026, 11, 2, 9, 55))
    assert engine.play_manual("Fiesta", playlist_id=pid)
    run_until(engine, clock, local(2026, 11, 2, 10, 0, 1), step=5)
    assert engine.current.title == "Timbre"
    backend.finish()
    assert engine.current is None  # la reproducción manual no vuelve sola


def test_archivo_suelto_se_repite_hasta_la_hora_de_fin(engine, clock, db, backend, track):
    add_event(db, "Recreo", time(11, 0), track_id=track("m.mp3"), end_mode=END_TIME, end_time=time(11, 30))
    start_engine_at(engine, clock, local(2026, 11, 2, 10, 59, 59))
    run_until(engine, clock, local(2026, 11, 2, 11, 0, 1))
    backend.finish()
    backend.finish()
    assert len(backend.played) == 3 and engine.current is not None


def test_manual_de_un_archivo_suena_una_vez(engine, clock, backend, track):
    start_engine_at(engine, clock, local(2026, 11, 2, 9, 0))
    engine.play_manual("Uno", track_id=track())
    backend.finish()
    assert engine.current is None and len(backend.played) == 1


def test_musica_programada_no_interrumpe_manual(engine, clock, db, backend, track):
    add_event(db, "Musica", time(10, 0), track_id=track("m.mp3"), priority=3, conflict="interrumpir")
    start_engine_at(engine, clock, local(2026, 11, 2, 9, 55))
    engine.play_manual("Prueba", track_id=track("p.mp3"))
    run_until(engine, clock, local(2026, 11, 2, 10, 0, 5), step=5)
    assert engine.current.title == "Prueba"


def test_detener_vacia_cola_y_reanudaciones(engine, clock, db, backend, track):
    add_event(db, "Musica", time(11, 0), track_id=track("m.mp3"), priority=3, end_mode=END_TIME,
              end_time=time(11, 30), resume=True)
    add_event(db, "Timbre", time(11, 10), track_id=track("t.mp3"), priority=8)
    start_engine_at(engine, clock, local(2026, 11, 2, 10, 59, 59))
    run_until(engine, clock, local(2026, 11, 2, 11, 10, 1), step=5)
    engine.stop()
    run_until(engine, clock, local(2026, 11, 2, 11, 12), step=5)
    assert engine.current is None and backend.playing is None  # no reaparece la música


def test_automatizacion_desactivada(engine, clock, db, backend, track, settings):
    add_event(db, "Timbre", time(9, 0), track_id=track())
    start_engine_at(engine, clock, local(2026, 11, 2, 8, 59))
    engine.set_automation(False)
    run_until(engine, clock, local(2026, 11, 2, 9, 1))
    assert backend.played == []
    assert engine.status()[0] == "detenido"
    engine.set_automation(True)  # al reactivar no suena lo que pasó mientras estaba desactivada
    run_until(engine, clock, local(2026, 11, 2, 9, 2))
    assert backend.played == []


def test_pausa_y_reanudar(engine, clock, db, backend, track):
    add_event(db, "M", time(9, 0), track_id=track(), end_mode=END_DURATION, duration_min=10)
    start_engine_at(engine, clock, local(2026, 11, 2, 8, 59, 59))
    run_until(engine, clock, local(2026, 11, 2, 9, 0, 1))
    engine.pause()
    assert backend.paused and engine.current.paused
    engine.resume()
    assert not backend.paused
    run_until(engine, clock, local(2026, 11, 2, 9, 10, 1), step=10)
    assert engine.current is None  # la hora de fin se respeta aunque haya habido pausa


# ----------------------------------------------------------------- medianoche y cambio de hora
def test_motor_cruza_la_medianoche(engine, clock, db, backend, track):
    add_event(db, "Noche", time(23, 59), days=frozenset({0}), track_id=track("n.mp3"),
              end_mode=END_TIME, end_time=time(0, 1))
    add_event(db, "Martes", time(0, 0), days=frozenset({1}), track_id=track("t.mp3"), priority=1,
              conflict="omitir")
    start_engine_at(engine, clock, local(2026, 11, 2, 23, 58))
    run_until(engine, clock, local(2026, 11, 3, 0, 0, 0), step=1)
    assert engine.current.title == "Noche"
    run_until(engine, clock, local(2026, 11, 3, 0, 1, 5), step=1)
    assert engine.current is None
    assert any("Omitido «Martes»" in m for m in history(db))


def test_motor_en_el_cambio_de_hora_de_otono(engine, clock, db, backend, track):
    add_event(db, "Doble", time(2, 30), days=frozenset({6}), track_id=track())
    start_engine_at(engine, clock, local(2026, 10, 25, 0, 0))
    run_until(engine, clock, local(2026, 10, 25, 5, 0), step=30)  # 5 h de reloj = 6 h reales
    assert len(backend.played) == 1


def test_motor_en_el_cambio_de_hora_de_primavera(engine, clock, db, backend, track):
    add_event(db, "Hueco", time(2, 30), days=frozenset({6}), track_id=track("h.mp3"))
    add_event(db, "Normal", time(9, 0), days=frozenset({6}), track_id=track("n.mp3"))
    start_engine_at(engine, clock, local(2026, 3, 29, 0, 0))
    run_until(engine, clock, local(2026, 3, 29, 10, 0), step=30)
    assert [os.path.basename(p) for p in backend.played] == ["h.mp3", "n.mp3"]


# ----------------------------------------------------------------- reinicio
def test_al_arrancar_no_suenan_eventos_pasados(engine, clock, db, backend, track):
    add_event(db, "Temprano", time(8, 0), track_id=track())
    start_engine_at(engine, clock, local(2026, 11, 2, 8, 5))  # se enciende tarde
    run_until(engine, clock, local(2026, 11, 2, 8, 10))
    assert backend.played == []


def test_evento_en_curso_se_ofrece_pero_no_arranca_solo(engine, clock, db, backend, track):
    add_event(db, "Recreo", time(11, 0), track_id=track(), end_mode=END_TIME, end_time=time(11, 30))
    start_engine_at(engine, clock, local(2026, 11, 2, 11, 10))
    run_until(engine, clock, local(2026, 11, 2, 11, 11))
    assert backend.played == []
    assert [o.event.name for o in engine.missed_in_progress] == ["Recreo"]
    assert engine.start_missed(engine.missed_in_progress[0])
    assert engine.current.end_utc == local(2026, 11, 2, 11, 30)


def test_reinicio_de_la_aplicacion(qapp, paths, settings, clock, track):
    from aulaaudio.audio import FakeAudioBackend
    from aulaaudio.db import Database

    db1 = Database(paths.db_file)
    add_event(db1, "Persistente", time(9, 0), track_id=db1.add_track(make_file(paths.data_dir, "x.mp3"), "x", 10))
    e1 = PlaybackEngine(db1, settings, FakeAudioBackend(), clock)
    start_engine_at(e1, clock, local(2026, 11, 2, 8, 59, 50))
    e1.shutdown()
    db1.close()  # «apagado»
    clock.set(local(2026, 11, 2, 9, 0, 30))  # vuelve 30 s después de la hora del evento
    db2 = Database(paths.db_file)
    b2 = FakeAudioBackend()
    e2 = PlaybackEngine(db2, settings, b2, clock)
    assert [e.name for e in db2.events()] == ["Persistente"]
    start_engine_at(e2, clock, clock.now())
    run_until(e2, clock, local(2026, 11, 2, 9, 2))
    assert b2.played == []  # no se reproduce con retraso tras reiniciar
    nxt = e2.next_occurrence()
    assert e2.scheduler.local(nxt.start_utc) == local(2026, 11, 3, 9, 0)
    e2.shutdown()
    db2.close()


def test_suspension_omite_eventos_y_avisa(engine, clock, db, backend, track, settings):
    add_event(db, "Durante la suspension", time(10, 0), track_id=track())
    start_engine_at(engine, clock, local(2026, 11, 2, 9, 0))
    clock.set(local(2026, 11, 2, 10, 30))  # el equipo «despierta» 1,5 h después
    engine.tick()
    assert backend.played == []
    msgs = history(db, "aviso")
    assert any("sin funcionar" in m for m in msgs)
    assert any("no estaba funcionando" in m for m in msgs)


def test_pequeno_retraso_dentro_del_margen_si_suena(engine, clock, db, backend, track, settings):
    add_event(db, "Timbre", time(10, 0), track_id=track())
    start_engine_at(engine, clock, local(2026, 11, 2, 9, 59, 50))
    clock.set(local(2026, 11, 2, 10, 0, 20))  # 30 s sin tick (equipo cargado), margen 60 s
    engine.tick()
    assert len(backend.played) == 1


def test_reloj_que_retrocede(engine, clock, db, backend, track):
    add_event(db, "Timbre", time(10, 0), track_id=track())
    start_engine_at(engine, clock, local(2026, 11, 2, 9, 59, 59))
    run_until(engine, clock, local(2026, 11, 2, 10, 0, 2))
    backend.finish()
    clock.set(local(2026, 11, 2, 9, 59, 0))  # alguien atrasa el reloj
    engine.tick()
    run_until(engine, clock, local(2026, 11, 2, 10, 0, 5))
    assert len(backend.played) == 1  # no se repite


# ----------------------------------------------------------------- archivos inexistentes
def test_archivo_inexistente_se_salta(engine, clock, db, backend, track):
    pid = db.add_playlist("L", repeat=False)
    missing = db.add_track(os.path.join(os.path.dirname(db.path), "no_existe.mp3"), "No existe", 1)
    ok = track("ok.mp3")
    db.set_playlist_tracks(pid, [missing, ok])
    add_event(db, "Lista", time(9, 0), playlist_id=pid)
    start_engine_at(engine, clock, local(2026, 11, 2, 8, 59, 59))
    run_until(engine, clock, local(2026, 11, 2, 9, 0, 1))
    assert backend.playing.endswith("ok.mp3")
    assert db.track(missing).status == "falta"
    assert engine.last_incident[0] == "aviso"


def test_todos_los_archivos_faltan(engine, clock, db, backend, audio_dir):
    pid = db.add_playlist("Vacia", repeat=True)
    ids = [db.add_track(str(audio_dir / f"no{i}.mp3"), f"no{i}", 1) for i in range(3)]
    db.set_playlist_tracks(pid, ids)
    add_event(db, "Lista", time(9, 0), playlist_id=pid, end_mode=END_DURATION, duration_min=20)
    start_engine_at(engine, clock, local(2026, 11, 2, 8, 59, 59))
    run_until(engine, clock, local(2026, 11, 2, 9, 0, 3))
    assert engine.current is None and backend.played == []
    assert engine.status()[0] == "incidencia"
    assert any("no se ha podido reproducir ninguna" in m or "ningún archivo" in m for m in history(db, "error"))


def test_archivo_danado_pasa_al_siguiente(qtbot, engine, clock, db, backend, track):
    pid = db.add_playlist("L", repeat=False)
    bad, good = track("bad.mp3"), track("good.mp3")
    db.set_playlist_tracks(pid, [bad, good])
    backend.fail_paths[db.track(bad).path] = "archivo"
    add_event(db, "Lista", time(9, 0), playlist_id=pid)
    start_engine_at(engine, clock, local(2026, 11, 2, 8, 59, 59))
    run_until(engine, clock, local(2026, 11, 2, 9, 0, 1))
    qtbot.waitUntil(lambda: backend.playing is not None and backend.playing.endswith("good.mp3"), timeout=2000)
    assert db.track(bad).status == "error"


def test_evento_sin_audio(engine, clock, db, backend, track):
    tid = track()
    add_event(db, "Huerfano", time(9, 0), track_id=tid)
    db.delete_track(tid)
    start_engine_at(engine, clock, local(2026, 11, 2, 8, 59, 59))
    run_until(engine, clock, local(2026, 11, 2, 9, 0, 1))
    assert engine.current is None
    assert "no tiene ningún audio" in engine.last_incident[1]


# ----------------------------------------------------------------- dispositivos
def test_sin_dispositivo_no_se_promete_reproduccion(engine, clock, db, backend, track):
    backend.problem = "No hay ningún dispositivo de salida de audio disponible."
    add_event(db, "Timbre", time(9, 0), track_id=track())
    start_engine_at(engine, clock, local(2026, 11, 2, 8, 59, 59))
    run_until(engine, clock, local(2026, 11, 2, 9, 0, 1))
    assert backend.played == [] and engine.current is None
    assert engine.status() == ("incidencia", backend.problem) or engine.status()[0] == "incidencia"
    assert any("No se puede reproducir" in m for m in history(db, "error"))


def test_fallo_de_dispositivo_reintenta_una_sola_vez(engine, clock, db, backend, track):
    add_event(db, "Musica", time(9, 0), track_id=track(), end_mode=END_DURATION, duration_min=10)
    start_engine_at(engine, clock, local(2026, 11, 2, 8, 59, 59))
    run_until(engine, clock, local(2026, 11, 2, 9, 0, 1))
    backend.fail(FAIL_DEVICE, "dispositivo desconectado")
    assert engine.current is not None and len(backend.played) == 2  # un reintento
    backend.fail(FAIL_DEVICE, "dispositivo desconectado")
    assert engine.current is None and len(backend.played) == 2  # no hay bucle de reintentos
    assert engine.status()[0] == "incidencia"


def test_dispositivo_vuelve(engine, backend, db):
    backend.problem = "El dispositivo de audio elegido no está conectado."
    backend.devices_changed.emit()
    assert engine.status()[0] == "incidencia"
    backend.problem = None
    engine.acknowledge_incident()
    backend.devices_changed.emit()
    assert engine.status()[0] == "funcionando"
