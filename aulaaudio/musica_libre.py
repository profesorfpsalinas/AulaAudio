"""Música libre para recreos incluida con AulaAudio (CC0, dominio público).

Las piezas viajan con el programa (carpeta aulaaudio/musica). Al pulsar «Añadir música libre
para recreos» se copian a la carpeta de datos del centro (así siguen disponibles aunque se
actualice o reinstale el programa), se añaden a la biblioteca y se crea o completa la lista
«Recreo — música libre» en orden aleatorio y con repetición. Repetirlo no duplica nada.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import library

SOURCE_DIR = Path(__file__).resolve().parent / "musica"
FOLDER_NAME = "musica_libre"
PLAYLIST_NAME = "Recreo — música libre"
TITLES = {
    "01-patio-soleado.mp3": "Patio soleado",
    "02-bocadillo-a-la-carrera.mp3": "Bocadillo a la carrera",
    "03-siesta-de-nubes.mp3": "Siesta de nubes",
    "04-rayuela.mp3": "Rayuela",
    "05-brisa-en-el-pasillo.mp3": "Brisa en el pasillo",
    "06-vuelta-a-clase.mp3": "Vuelta a clase",
    "07-canicas.mp3": "Canicas",
    "08-merienda-tranquila.mp3": "Merienda tranquila",
}
LICENSE_FILE = "LEEME.txt"


@dataclass
class InstallResult:
    added: int = 0
    already: int = 0
    playlist_id: int | None = None
    playlist_created: bool = False
    folder: Path | None = None


def bundled_files(source: Path = SOURCE_DIR) -> list[Path]:
    """Piezas incluidas con el programa (solo las conocidas, en orden)."""
    return [source / name for name in TITLES if (source / name).is_file()]


def available(source: Path = SOURCE_DIR) -> bool:
    return len(bundled_files(source)) == len(TITLES)


def install(db, data_dir: Path, source: Path = SOURCE_DIR) -> InstallResult:
    files = bundled_files(source)
    if not files:
        raise FileNotFoundError("No se encuentra la música incluida con el programa. Reinstale AulaAudio.")
    dest = Path(data_dir) / FOLDER_NAME
    dest.mkdir(parents=True, exist_ok=True)
    lic = source / LICENSE_FILE
    if lic.is_file():
        shutil.copy2(lic, dest / LICENSE_FILE)
    res = InstallResult(folder=dest)
    track_ids = []
    for src in files:
        target = dest / src.name
        if not target.exists() or target.stat().st_size != src.stat().st_size:
            tmp = target.with_suffix(".tmp")
            shutil.copy2(src, tmp)
            os.replace(tmp, target)
        path = library.normalize(target)
        existing = db.track_by_path(path)
        if existing:
            res.already += 1
            track_ids.append(existing.id)
            if existing.status != "ok":
                db.update_track_status(existing.id, "ok", "")
        else:
            track_ids.append(db.add_track(path, TITLES[src.name], target.stat().st_size))
            res.added += 1
    pl = next((p for p in db.playlists() if p.name == PLAYLIST_NAME), None)
    if pl is None:
        res.playlist_id = db.add_playlist(PLAYLIST_NAME, mode="aleatorio", repeat=True)
        res.playlist_created = True
        db.set_playlist_tracks(res.playlist_id, track_ids)
    else:
        res.playlist_id = pl.id
        current = [t.id for t in db.playlist_tracks(pl.id)]
        db.set_playlist_tracks(pl.id, current + [t for t in track_ids if t not in current])
    return res
