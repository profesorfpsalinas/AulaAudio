"""Música libre para recreos: archivos incluidos, licencia e instalación en la biblioteca."""
from pathlib import Path

from aulaaudio import musica_libre


def test_estan_las_ocho_piezas_y_la_licencia():
    files = musica_libre.bundled_files()
    assert len(files) == 8 and musica_libre.available()
    for f in files:
        head = f.read_bytes()[:3]
        assert head == b"ID3", f"{f.name} no es un MP3 con etiquetas"
        assert 1_000_000 < f.stat().st_size < 5_000_000  # unos 2 minutos y medio a 128 kbps
    lic = (musica_libre.SOURCE_DIR / musica_libre.LICENSE_FILE).read_text(encoding="utf-8")
    assert "CC0" in lic and "dominio público" in lic


def test_instalar_crea_lista_aleatoria_y_copia_a_datos(db, paths):
    res = musica_libre.install(db, paths.data_dir)
    assert res.added == 8 and res.playlist_created
    pl = db.playlist(res.playlist_id)
    assert pl.name == musica_libre.PLAYLIST_NAME and pl.mode == "aleatorio" and pl.repeat
    tracks = db.playlist_tracks(res.playlist_id)
    assert [t.title for t in tracks] == list(musica_libre.TITLES.values())
    for t in tracks:  # copiadas a la carpeta de datos: sobreviven a una actualización del programa
        assert Path(t.path).parent == Path(paths.data_dir) / musica_libre.FOLDER_NAME and Path(t.path).is_file()
    assert (Path(paths.data_dir) / musica_libre.FOLDER_NAME / musica_libre.LICENSE_FILE).is_file()


def test_repetir_no_duplica_y_respeta_los_cambios_del_usuario(db, paths, track):
    first = musica_libre.install(db, paths.data_dir)
    extra = track("mi-cancion.mp3")
    ids = [t.id for t in db.playlist_tracks(first.playlist_id)][1:] + [extra]  # quita una, añade otra
    db.set_playlist_tracks(first.playlist_id, ids)
    again = musica_libre.install(db, paths.data_dir)
    assert again.added == 0 and again.already == 8 and not again.playlist_created
    assert again.playlist_id == first.playlist_id
    final = [t.id for t in db.playlist_tracks(first.playlist_id)]
    assert len(final) == 9 and extra in final and len(set(final)) == 9
    assert len(db.tracks()) == 9


def test_recupera_archivos_borrados(db, paths):
    res = musica_libre.install(db, paths.data_dir)
    victim = next(iter((res.folder).glob("*.mp3")))
    victim.unlink()
    musica_libre.install(db, paths.data_dir)
    assert victim.is_file()


def test_sin_musica_incluida_avisa(db, paths, tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        musica_libre.install(db, paths.data_dir, source=tmp_path / "vacia")


def test_boton_de_la_biblioteca(qtbot, monkeypatch, paths, db, settings, backend, clock):
    from aulaaudio.config import ConfigStore
    from aulaaudio.engine import PlaybackEngine
    from aulaaudio.ui.common import AppContext
    from aulaaudio.ui.library_tab import LibraryTab

    shown = []
    monkeypatch.setattr("aulaaudio.ui.library_tab.info", lambda parent, title, text: shown.append(text))
    engine = PlaybackEngine(db, settings, backend, clock)
    ctx = AppContext(paths, db, ConfigStore(paths.config_file), settings, engine, backend, clock)
    tab = LibraryTab(ctx)
    qtbot.addWidget(tab)
    tab.btn_free_music.click()
    assert shown and "Piezas añadidas: 8" in shown[0] and "CC0" in shown[0]
    assert tab.tracks.rowCount() == 8
    engine.shutdown()
