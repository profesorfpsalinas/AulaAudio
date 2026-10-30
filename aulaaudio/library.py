"""Biblioteca de audio local.

AulaAudio nunca copia, mueve ni borra los archivos del usuario: solo guarda su ruta.
Para cada pista se guarda la ruta absoluta normalizada, el nombre y el tamaño, de modo que
si se mueve la carpeta de música se puede localizar de nuevo cada archivo por nombre y tamaño.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .audio import SUPPORTED_EXTENSIONS

MAX_SCAN_FILES = 20000  # límite de seguridad al añadir carpetas enormes por error


def normalize(path: str | Path) -> str:
    return os.path.abspath(os.path.expanduser(str(path)))


def is_audio_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_EXTENSIONS


def title_for(path: str | Path) -> str:
    return Path(path).stem.replace("_", " ").strip() or Path(path).name


def _size(path: str) -> int | None:
    try:
        return os.path.getsize(path)
    except OSError:
        return None


@dataclass
class AddResult:
    added: int = 0
    already: int = 0
    rejected: int = 0
    truncated: bool = False


def add_files(db, paths, demo: bool = False) -> AddResult:
    res = AddResult()
    for p in paths:
        p = normalize(p)
        if not is_audio_file(p) or not os.path.isfile(p):
            res.rejected += 1
            continue
        if db.track_by_path(p):
            res.already += 1
            continue
        db.add_track(p, title_for(p), _size(p), demo=demo)
        res.added += 1
    return res


def scan_folder(folder: str | Path) -> tuple[list[str], bool]:
    """Archivos de audio de una carpeta (y subcarpetas), ordenados. No sigue enlaces simbólicos."""
    found: list[str] = []
    for root, dirs, files in os.walk(folder, followlinks=False):
        dirs.sort()
        for name in sorted(files):
            if is_audio_file(name):
                found.append(os.path.join(root, name))
                if len(found) >= MAX_SCAN_FILES:
                    return found, True
    return found, False


def add_folder(db, folder: str | Path) -> AddResult:
    files, truncated = scan_folder(folder)
    res = add_files(db, files)
    res.truncated = truncated
    return res


def check_tracks(db) -> tuple[int, int]:
    """Comprueba que los archivos siguen existiendo y se pueden leer. Devuelve (correctos, con problemas)."""
    ok = bad = 0
    for t in db.tracks():
        if not os.path.isfile(t.path):
            db.update_track_status(t.id, "falta", "El archivo no existe o la carpeta no está disponible.")
            bad += 1
            continue
        try:
            with open(t.path, "rb") as fh:
                fh.read(16)
        except OSError:
            db.update_track_status(t.id, "error", "No se puede leer el archivo (permisos o disco).")
            bad += 1
            continue
        if t.status == "falta" or (t.status == "error" and "leer" in t.status_msg):
            db.update_track_status(t.id, "ok", "")
        ok += 1
    return ok, bad


def relocate_missing(db, new_root: str | Path) -> tuple[int, int]:
    """Busca en `new_root` los archivos que faltan, por nombre y tamaño. Devuelve (encontrados, sin encontrar)."""
    missing = [t for t in db.tracks() if not os.path.isfile(t.path)]
    if not missing:
        return 0, 0
    index: dict[str, list[str]] = {}
    files, _ = scan_folder(new_root)
    for f in files:
        index.setdefault(os.path.basename(f).lower(), []).append(f)
    found = 0
    for t in missing:
        candidates = index.get(os.path.basename(t.path).lower(), [])
        if t.size is not None:
            same_size = [c for c in candidates if _size(c) == t.size]
            candidates = same_size or candidates
        if candidates:
            new_path = normalize(candidates[0])
            if db.track_by_path(new_path) is None:
                db.update_track_path(t.id, new_path, _size(new_path))
                found += 1
    return found, len(missing) - found


# ---------------------------------------------------------------------- M3U
def export_m3u(db, playlist_id: int, dest: str | Path) -> int:
    pl = db.playlist(playlist_id)
    tracks = db.playlist_tracks(playlist_id)
    lines = ["#EXTM3U", f"#PLAYLIST:{pl.name}"]
    for t in tracks:
        secs = int(t.duration_ms / 1000) if t.duration_ms else -1
        lines.append(f"#EXTINF:{secs},{t.title}")
        lines.append(t.path)
    Path(dest).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(tracks)


def parse_m3u(path: str | Path) -> tuple[str | None, list[str]]:
    """Lee una lista M3U/M3U8. Ignora direcciones de Internet y entradas que no son audio."""
    path = Path(path)
    raw = path.read_bytes()[:5_000_000]
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    name = None
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#PLAYLIST:"):
            name = line[10:].strip() or None
            continue
        if line.startswith("#"):
            continue
        if "://" in line and not line.lower().startswith("file://"):
            continue  # sin acceso a red
        if line.lower().startswith("file://"):
            from urllib.parse import unquote, urlparse

            line = unquote(urlparse(line).path)
            if os.name == "nt" and line.startswith("/") and len(line) > 2 and line[2] == ":":
                line = line[1:]
        p = Path(line)
        if not p.is_absolute():
            p = path.parent / p
        if is_audio_file(p):
            entries.append(str(p))
    return name, entries


def import_m3u(db, path: str | Path, name: str | None = None) -> tuple[int, int, int]:
    """Crea una lista a partir de un M3U. Devuelve (id de la lista, pistas añadidas, no encontradas)."""
    m3u_name, entries = parse_m3u(path)
    base = (name or m3u_name or Path(path).stem).strip()[:90] or "Lista importada"
    existing = {p.name for p in db.playlists()}
    final, n = base, 2
    while final in existing:
        final, n = f"{base} ({n})", n + 1
    pid = db.add_playlist(final)
    ids, missing = [], 0
    for e in entries:
        p = normalize(e)
        if not os.path.isfile(p):
            missing += 1
            continue
        t = db.track_by_path(p)
        ids.append(t.id if t else db.add_track(p, title_for(p), _size(p)))
    db.set_playlist_tracks(pid, ids)
    return pid, len(ids), missing
