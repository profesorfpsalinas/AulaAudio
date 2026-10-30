"""Copias de seguridad y restauración.

Una copia es un archivo .zip con:
- manifest.json  (versión del programa y del esquema, fecha, tipo)
- aulaaudio.db   (copia consistente hecha con la API de copia de SQLite, en caliente)
- config.json

No incluye los archivos de música (solo sus rutas). Protecciones:
- Nunca se sobrescribe una copia existente (apertura en modo exclusivo 'x').
- Antes de restaurar se crea automáticamente una copia «antes_de_restaurar».
- La copia a restaurar se valida: nombres de miembros permitidos, tamaño, integridad de la
  base de datos y versión de esquema compatible.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import __version__
from .db import SCHEMA_VERSION

ALLOWED_MEMBERS = {"manifest.json", "aulaaudio.db", "config.json"}
MAX_UNCOMPRESSED = 500 * 1024 * 1024
PREFIX = "aulaaudio_copia_"


class BackupError(RuntimeError):
    pass


@dataclass
class BackupInfo:
    path: Path
    created: datetime
    kind: str
    size: int


def _unique_path(folder: Path, kind: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = folder / f"{PREFIX}{stamp}_{kind}.zip"
    n = 2
    while base.exists():
        base = folder / f"{PREFIX}{stamp}_{kind}_{n}.zip"
        n += 1
    return base


def create_backup(db, config_file: Path, folder: Path, kind: str = "manual") -> Path:
    return _create(db.conn, config_file, folder, kind, SCHEMA_VERSION)


def backup_before_upgrade(paths) -> Path | None:
    """Si la base de datos existente es de un esquema anterior, la copia antes de migrarla."""
    if not paths.db_file.exists():
        return None
    con = sqlite3.connect(str(paths.db_file))
    try:
        version = con.execute("PRAGMA user_version").fetchone()[0]
        if 0 < version < SCHEMA_VERSION:
            return _create(con, paths.config_file, paths.backup_dir, "antes_de_actualizar", version)
        return None
    finally:
        con.close()


def _create(conn: sqlite3.Connection, config_file: Path, folder: Path, kind: str, schema: int) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    dest = _unique_path(folder, kind)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_db = Path(tmp) / "aulaaudio.db"
        target = sqlite3.connect(str(tmp_db))
        try:
            conn.backup(target)  # copia consistente aunque la base esté en uso
        finally:
            target.close()
        manifest = {
            "aplicacion": "AulaAudio",
            "version_programa": __version__,
            "version_esquema": schema,
            "creada": datetime.now().isoformat(timespec="seconds"),
            "tipo": kind,
        }
        try:
            with open(dest, "xb") as raw, zipfile.ZipFile(raw, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                z.write(tmp_db, "aulaaudio.db")
                if config_file.exists():
                    z.write(config_file, "config.json")
        except Exception:
            if dest.exists():
                dest.unlink()
            raise
    return dest


def list_backups(folder: Path) -> list[BackupInfo]:
    result = []
    if not folder.exists():
        return result
    for p in folder.glob(f"{PREFIX}*.zip"):
        try:
            with zipfile.ZipFile(p) as z:
                m = json.loads(z.read("manifest.json"))
            created = datetime.fromisoformat(m.get("creada"))
            kind = str(m.get("tipo", "?"))
        except Exception:
            created = datetime.fromtimestamp(p.stat().st_mtime)
            kind = "dañada"
        result.append(BackupInfo(p, created, kind, p.stat().st_size))
    result.sort(key=lambda b: b.created, reverse=True)
    return result


def prune_automatic(folder: Path, keep: int) -> int:
    auto = [b for b in list_backups(folder) if b.kind == "automatica"]
    removed = 0
    for b in auto[keep:]:
        try:
            b.path.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def automatic_backup_due(folder: Path) -> bool:
    today = datetime.now().date()
    return not any(b.kind == "automatica" and b.created.date() == today for b in list_backups(folder))


def validate_backup(path: Path, workdir: Path) -> dict:
    """Valida y extrae la copia en `workdir`. Devuelve el manifiesto."""
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise BackupError("El archivo no es una copia de seguridad válida de AulaAudio.") from exc
    with z:
        names = set(z.namelist())
        if not {"manifest.json", "aulaaudio.db"} <= names or not names <= ALLOWED_MEMBERS:
            raise BackupError("La copia no tiene el contenido esperado de AulaAudio.")
        if sum(i.file_size for i in z.infolist()) > MAX_UNCOMPRESSED:
            raise BackupError("La copia es demasiado grande para ser de AulaAudio.")
        try:
            manifest = json.loads(z.read("manifest.json"))
        except ValueError as exc:
            raise BackupError("El manifiesto de la copia está dañado.") from exc
        if manifest.get("aplicacion") != "AulaAudio":
            raise BackupError("La copia no pertenece a AulaAudio.")
        if int(manifest.get("version_esquema", 999)) > SCHEMA_VERSION:
            raise BackupError("La copia procede de una versión más moderna de AulaAudio. Actualice el programa.")
        for name in names:  # nombres fijos, sin rutas: no hay riesgo de salir de workdir
            (workdir / name).write_bytes(z.read(name))
    con = sqlite3.connect(str(workdir / "aulaaudio.db"))
    try:
        ok = con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    except sqlite3.DatabaseError:
        ok = False
    finally:
        con.close()
    if not ok:
        raise BackupError("La base de datos de la copia está dañada.")
    if (workdir / "config.json").exists():
        try:
            json.loads((workdir / "config.json").read_text(encoding="utf-8"))
        except ValueError as exc:
            raise BackupError("La configuración de la copia está dañada.") from exc
    return manifest


def restore_backup(path: Path, db, paths) -> Path:
    """Restaura una copia. Cierra y vuelve a abrir la base de datos.

    Devuelve la ruta de la copia de seguridad automática creada antes de restaurar.
    Si algo falla, los datos actuales se conservan sin cambios.
    """
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        validate_backup(Path(path), work)
        safety = create_backup(db, paths.config_file, paths.backup_dir, kind="antes_de_restaurar")
        db.close()
        try:
            for suffix in ("-wal", "-shm"):
                side = Path(str(paths.db_file) + suffix)
                if side.exists():
                    side.unlink()
            staged = paths.db_file.with_suffix(".db.restaurando")
            shutil.copyfile(work / "aulaaudio.db", staged)
            os.replace(staged, paths.db_file)
            if (work / "config.json").exists():
                staged_cfg = paths.config_file.with_suffix(".json.restaurando")
                shutil.copyfile(work / "config.json", staged_cfg)
                os.replace(staged_cfg, paths.config_file)
        finally:
            db.open()  # migra si la copia era de un esquema anterior
    return safety
