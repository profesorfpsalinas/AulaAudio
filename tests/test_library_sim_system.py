"""Biblioteca, listas M3U, modo de simulación, arranque automático y datos de ejemplo."""
import os
from datetime import time
from pathlib import Path

from aulaaudio import demo, library, simulation, system
from aulaaudio.models import END_TIME
from conftest import add_event, local, make_file


# ----------------------------------------------------------------- biblioteca
def test_anadir_carpeta_sin_copiar_archivos(db, audio_dir):
    make_file(audio_dir, "a.mp3")
    make_file(audio_dir / "sub", "b.ogg")
    make_file(audio_dir, "notas.txt")
    before = sorted(p.name for p in audio_dir.rglob("*"))
    res = library.add_folder(db, audio_dir)
    assert res.added == 2
    assert sorted(p.name for p in audio_dir.rglob("*")) == before  # nada se mueve ni se crea
    assert library.add_folder(db, audio_dir).already == 2


def test_rechaza_no_audio(db, audio_dir):
    res = library.add_files(db, [make_file(audio_dir, "virus.exe"), str(audio_dir / "no_existe.mp3")])
    assert res.added == 0 and res.rejected == 2


def test_busqueda(db, audio_dir):
    library.add_files(db, [make_file(audio_dir, "Himno_del_centro.mp3"), make_file(audio_dir, "timbre.wav")])
    assert [t.title for t in db.tracks("himno")] == ["Himno del centro"]


def test_comprobar_y_localizar_archivos_movidos(db, tmp_path):
    old = tmp_path / "Musica"
    library.add_files(db, [make_file(old, "a.mp3", 100), make_file(old, "b.mp3", 200)])
    new = tmp_path / "Disco" / "MusicaNueva"
    new.parent.mkdir()
    os.rename(old, new)
    ok, bad = library.check_tracks(db)
    assert (ok, bad) == (0, 2) and all(t.status == "falta" for t in db.tracks())
    found, missing = library.relocate_missing(db, tmp_path / "Disco")
    assert (found, missing) == (2, 0)
    assert all(t.status == "ok" and t.path.startswith(str(new)) for t in db.tracks())


def test_m3u_exportar_importar(db, audio_dir, tmp_path):
    ids = [db.add_track(make_file(audio_dir, n), n, 1) for n in ("1.mp3", "2.mp3")]
    pid = db.add_playlist("Recreo")
    db.set_playlist_tracks(pid, list(reversed(ids)))
    out = tmp_path / "recreo.m3u8"
    assert library.export_m3u(db, pid, out) == 2
    new_id, n, missing = library.import_m3u(db, out)
    assert (n, missing) == (2, 0)
    assert db.playlist(new_id).name == "Recreo (2)"  # no sustituye la lista existente
    assert [t.title for t in db.playlist_tracks(new_id)] == ["2.mp3", "1.mp3"]


def test_m3u_ignora_internet_y_relativas(tmp_path, audio_dir):
    make_file(audio_dir, "local.mp3")
    m3u = audio_dir / "lista.m3u"
    m3u.write_text("#EXTM3U\nhttp://servidor/remoto.mp3\nlocal.mp3\nprograma.exe\n", encoding="utf-8")
    name, entries = library.parse_m3u(m3u)
    assert entries == [str(audio_dir / "local.mp3")]


# ----------------------------------------------------------------- simulación
def test_simulacion_no_modifica_datos(db, settings, track):
    add_event(db, "Timbre", time(8, 30), track_id=track("t.mp3"), kind="timbre", priority=8)
    add_event(db, "Recreo", time(11, 0), track_id=track("m.mp3"), kind="musica", end_mode=END_TIME,
              end_time=time(11, 30))
    history_before = len(db.history())
    entries = simulation.simulate(db, settings, local(2026, 11, 2, 8, 0), local(2026, 11, 2, 12, 0))
    text = [f"{e.when:%H:%M} {e.message}" for e in entries]
    assert "08:30 Inicio de «Timbre»." in text
    assert any(t.startswith("11:00 Inicio de «Recreo»") for t in text)
    assert any(t.startswith("11:30 Fin de «Recreo»") for t in text)
    assert len(db.history()) == history_before


def test_simulacion_respeta_festivos(db, settings, track):
    from datetime import date

    from aulaaudio.models import CalendarException

    add_event(db, "Timbre", time(8, 30), track_id=track())
    db.save_exception(CalendarException(name="Fiesta", kind="festivo", date_from=date(2026, 11, 2),
                                        date_to=date(2026, 11, 2)))
    assert simulation.simulate(db, settings, local(2026, 11, 2, 0, 0), local(2026, 11, 2, 23, 0), step_seconds=30) == []


def test_simulacion_ejemplo_completo(db, settings, paths):
    demo.load_demo(db, paths.demo_sounds_dir)
    for e in db.events():
        e.enabled = True
        db.save_event(e)
    entries = simulation.simulate(db, settings, local(2026, 11, 2, 8, 0), local(2026, 11, 2, 15, 0))
    starts = [e for e in entries if e.message.startswith("Inicio")]
    assert len(starts) == 11
    assert not [e for e in entries if e.level == "error"]


# ----------------------------------------------------------------- datos de ejemplo
def test_ejemplos_desactivados_y_borrables(db, paths, audio_dir):
    own = db.add_track(make_file(audio_dir, "propia.mp3"), "Propia", 1)
    demo.load_demo(db, paths.demo_sounds_dir)
    assert db.events() and all(e.demo and not e.enabled for e in db.events())
    assert all(e.name.startswith("[EJEMPLO]") for e in db.events())
    db.delete_demo_data()
    assert db.events() == [] and [t.id for t in db.tracks()] == [own]


# ----------------------------------------------------------------- sistema (sin tocar el SO real)
def test_autostart_linux_en_carpeta_temporal(tmp_path):
    cfg = tmp_path / "xdg"
    assert not system.is_autostart_enabled(cfg)
    system.set_autostart(True, cfg)
    f = system.autostart_desktop_file(cfg)
    text = f.read_text(encoding="utf-8")
    assert "Exec=" in text and "--minimizado" in text and system.is_autostart_enabled(cfg)
    system.set_autostart(False, cfg)
    assert not f.exists()


def test_orden_de_inicio_automatico_desde_codigo_fuente():
    args = system.launch_command()
    assert Path(args[1]).name == "AulaAudio.pyw" and Path(args[1]).is_file()
    assert args[-1] == "--minimizado"
    # en Windows se escribe como una sola cadena con las rutas entre comillas si tienen espacios
    assert system._quote_windows(["C:\\Program Files\\x.exe", "--minimizado"]) == '"C:\\Program Files\\x.exe" --minimizado'


def test_pista_con_error_vuelve_a_correcto_al_sonar_bien(qapp, db, settings, clock, track):
    from aulaaudio.audio import FakeAudioBackend
    from aulaaudio.engine import PlaybackEngine

    tid = track()
    db.update_track_status(tid, "error", "fallo antiguo")
    b = FakeAudioBackend()
    e = PlaybackEngine(db, settings, b, clock)
    e.play_manual("x", track_id=tid)
    b.finish()
    assert db.track(tid).status == "ok"
    e.shutdown()


def test_exec_desktop_escapa_rutas():
    out = system._desktop_exec(["/opt/Aula Audio/aulaaudio", "--minimizado"])
    assert out == '"/opt/Aula Audio/aulaaudio" --minimizado'


def test_rutas_separadas(paths):
    dirs = {paths.config_dir, paths.data_dir, paths.backup_dir, paths.log_dir}
    assert len(dirs) == 4 and all(Path(d).is_dir() for d in dirs)
