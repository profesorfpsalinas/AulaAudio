"""11. Copias de seguridad y restauración · 12. Persistencia de la configuración."""
import json
import sqlite3
import zipfile
from datetime import time

import pytest

from aulaaudio import backup
from aulaaudio.config import ConfigStore, Settings
from aulaaudio.db import SCHEMA_VERSION, Database
from conftest import add_event


# ----------------------------------------------------------------- copias
def test_crear_y_restaurar(db, paths, track):
    store = ConfigStore(paths.config_file)
    s = Settings(volumen_general=33)
    store.save(s)
    add_event(db, "Original", time(8, 0), track_id=track())
    copy = backup.create_backup(db, paths.config_file, paths.backup_dir)
    # cambios posteriores que la restauración debe deshacer
    for e in db.events():
        db.delete_event(e.id)
    add_event(db, "Nuevo", time(9, 0), track_id=track("b.mp3"))
    store.save(Settings(volumen_general=90))
    safety = backup.restore_backup(copy, db, paths)
    assert [e.name for e in db.events()] == ["Original"]
    assert store.load().volumen_general == 33
    assert safety.exists() and "antes_de_restaurar" in safety.name
    # la copia de seguridad previa contiene el estado que había justo antes
    backup.restore_backup(safety, db, paths)
    assert [e.name for e in db.events()] == ["Nuevo"]


def test_nunca_se_sobrescriben_copias(db, paths):
    a = backup.create_backup(db, paths.config_file, paths.backup_dir)
    b = backup.create_backup(db, paths.config_file, paths.backup_dir)
    assert a != b and a.exists() and b.exists()
    assert len(backup.list_backups(paths.backup_dir)) == 2


def test_copia_automatica_diaria_y_poda(db, paths):
    assert backup.automatic_backup_due(paths.backup_dir)
    for _ in range(4):
        backup.create_backup(db, paths.config_file, paths.backup_dir, "automatica")
    backup.create_backup(db, paths.config_file, paths.backup_dir, "manual")
    assert not backup.automatic_backup_due(paths.backup_dir)
    assert backup.prune_automatic(paths.backup_dir, keep=2) == 2
    kinds = sorted(b.kind for b in backup.list_backups(paths.backup_dir))
    assert kinds == ["automatica", "automatica", "manual"]  # las manuales no se podan


def test_rechaza_archivo_que_no_es_copia(db, paths, tmp_path):
    bad = tmp_path / "x.zip"
    bad.write_bytes(b"no soy un zip")
    with pytest.raises(backup.BackupError):
        backup.restore_backup(bad, db, paths)
    assert db.integrity_ok()  # los datos actuales siguen intactos


def test_rechaza_rutas_peligrosas(db, paths, tmp_path):
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("manifest.json", json.dumps({"aplicacion": "AulaAudio", "version_esquema": 1}))
        z.writestr("aulaaudio.db", b"")
        z.writestr("../../fuera.txt", b"x")
    with pytest.raises(backup.BackupError, match="contenido"):
        backup.restore_backup(evil, db, paths)
    assert not (tmp_path.parent / "fuera.txt").exists()


def test_rechaza_copia_de_version_futura(db, paths):
    copy = backup.create_backup(db, paths.config_file, paths.backup_dir)
    newer = copy.with_name("futura.zip")
    with zipfile.ZipFile(copy) as src, zipfile.ZipFile(newer, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == "manifest.json":
                m = json.loads(data)
                m["version_esquema"] = SCHEMA_VERSION + 1
                data = json.dumps(m)
            dst.writestr(name, data)
    with pytest.raises(backup.BackupError, match="moderna"):
        backup.restore_backup(newer, db, paths)


def test_rechaza_base_danada_en_copia(db, paths):
    copy = backup.create_backup(db, paths.config_file, paths.backup_dir)
    broken = copy.with_name("rota.zip")
    with zipfile.ZipFile(copy) as src, zipfile.ZipFile(broken, "w") as dst:
        for name in src.namelist():
            dst.writestr(name, b"basura" * 100 if name == "aulaaudio.db" else src.read(name))
    with pytest.raises(backup.BackupError, match="dañada"):
        backup.restore_backup(broken, db, paths)


def test_copia_antes_de_actualizar(paths):
    con = sqlite3.connect(paths.db_file)
    con.execute("CREATE TABLE vieja(x)")
    con.execute("PRAGMA user_version = 0")
    con.close()
    assert backup.backup_before_upgrade(paths) is None  # versión 0: base nueva/vacía
    db = Database(paths.db_file)
    db.close()
    assert backup.backup_before_upgrade(paths) is None  # ya en la versión actual


# ----------------------------------------------------------------- configuración
def test_configuracion_persiste(paths):
    store = ConfigStore(paths.config_file)
    s = Settings(volumen_general=55, automatizacion_activa=False, zona_horaria="Atlantic/Canary")
    store.save(s)
    again = ConfigStore(paths.config_file).load()
    assert (again.volumen_general, again.automatizacion_activa, again.zona_horaria) == (55, False, "Atlantic/Canary")


def test_configuracion_danada_recupera_copia(paths):
    store = ConfigStore(paths.config_file)
    store.save(Settings(volumen_general=40))
    store.save(Settings(volumen_general=60))  # la anterior (40) queda en .bak
    paths.config_file.write_text("{ esto no es json", encoding="utf-8")
    s = store.load()
    assert s.volumen_general == 40 and "recuperado" in store.last_load_warning


def test_configuracion_danada_sin_copia(paths):
    paths.config_file.write_text("[]", encoding="utf-8")
    store = ConfigStore(paths.config_file)
    assert store.load() == Settings() and store.last_load_warning


def test_valores_fuera_de_rango(paths):
    paths.config_file.write_text(json.dumps({"volumen_general": 999, "zona_horaria": "Marte/Base",
                                             "prioridad_manual": "x", "desconocida": 1}), encoding="utf-8")
    s = ConfigStore(paths.config_file).load()
    assert s.volumen_general == 100 and s.zona_horaria == "Europe/Madrid" and s.prioridad_manual == 5


def test_guardado_atomico_no_deja_temporales(paths):
    store = ConfigStore(paths.config_file)
    for v in range(5):
        store.save(Settings(volumen_general=v))
    assert sorted(p.name for p in paths.config_dir.iterdir()) == ["config.json", "config.json.bak"]
