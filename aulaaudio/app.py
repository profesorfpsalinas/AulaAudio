"""Arranque de AulaAudio.

Uso:
    python -m aulaaudio                     abre la aplicación
    python -m aulaaudio --minimizado        arranca en la bandeja (lo usa el inicio automático)
    python -m aulaaudio --simular 2026-11-02 [--horas 24]
                                            imprime qué sonaría ese día, sin abrir ventanas
    python -m aulaaudio --modo-simulacion "2026-11-02 08:25" [--velocidad 60] [--silencio]
                                            abre la interfaz con un reloj virtual acelerado
    python -m aulaaudio --datos CARPETA     usa otra carpeta de datos (pruebas, simulación)
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

from . import APP_NAME, __version__
from .paths import AppPaths, default_paths, from_root

log = logging.getLogger("aulaaudio")


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="aulaaudio", description="AulaAudio: música, timbres y avisos del centro.")
    p.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    p.add_argument("--minimizado", action="store_true", help="arrancar en la bandeja del sistema")
    p.add_argument("--datos", metavar="CARPETA", help="carpeta de datos alternativa")
    p.add_argument("--simular", metavar="AAAA-MM-DD", help="mostrar en texto qué sonaría ese día y salir")
    p.add_argument("--desde", metavar="HH:MM", default="00:00", help="hora de inicio de --simular")
    p.add_argument("--horas", type=int, default=24, help="horas a simular con --simular (1-72)")
    p.add_argument("--modo-simulacion", metavar="'AAAA-MM-DD HH:MM'", help="interfaz con reloj virtual")
    p.add_argument("--velocidad", type=float, default=1.0, help="multiplicador del reloj virtual")
    p.add_argument("--silencio", action="store_true", help="no emitir sonido (salida de audio simulada)")
    p.add_argument("--depuracion", action="store_true", help="registro detallado")
    p.add_argument("--diagnostico", action="store_true",
                   help="comprobar la salida de audio (en silencio) y guardar un informe en la carpeta de registros")
    return p.parse_args(argv)


def run_diagnostics(args) -> int:
    """Comprueba dispositivos y decodificación reproduciendo el sonido de prueba a volumen 0."""
    import platform

    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import QCoreApplication, QTimer

    from . import sounds
    from .audio import QtAudioBackend

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    paths = _paths(args)
    lines = [f"{APP_NAME} {__version__} — diagnóstico {datetime.now():%d/%m/%Y %H:%M:%S}",
             f"Sistema: {platform.platform()}", f"Python: {platform.python_version()}  PySide6: {pyside_version}",
             f"Empaquetado: {'sí' if getattr(sys, 'frozen', False) else 'no'}", f"Datos: {paths.data_dir}"]
    backend = QtAudioBackend()
    devs = backend.devices()
    lines.append(f"Dispositivos de salida ({len(devs)}):")
    lines += [f"  - {d.name}{' (predeterminado)' if d.is_default else ''}" for d in devs]
    lines.append(f"Problema de dispositivo: {backend.device_problem() or 'ninguno'}")
    result: list[str] = []
    backend.finished.connect(lambda t: (result.append("correcto"), app.quit()))
    backend.failed.connect(lambda t, k, m: (result.append(f"fallo ({k}): {m}"), app.quit()))
    QTimer.singleShot(8000, lambda: (result.append("sin respuesta en 8 s"), app.quit()))
    if backend.device_problem() is None:
        backend.play(str(sounds.test_sound(paths.data_dir)), 0.0)  # volumen 0: no se oye nada
        app.exec()
    else:
        result.append("no probado: no hay dispositivo")
    lines.append(f"Reproducción de prueba (silenciosa): {result[0]}")
    report = "\n".join(lines)
    (paths.log_dir / "diagnostico.txt").write_text(report + "\n", encoding="utf-8")
    if sys.stdout is not None:
        print(report)
    return 0 if result and result[0] == "correcto" else 1


def _paths(args) -> AppPaths:
    paths = from_root(Path(args.datos)) if args.datos else default_paths()
    paths.ensure()
    return paths


def run_cli_simulation(args) -> int:
    from zoneinfo import ZoneInfo

    from PySide6.QtCore import QCoreApplication

    from .config import ConfigStore
    from .db import Database
    from .models import parse_hhmm
    from .simulation import simulate

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)  # noqa: F841 (necesario para QObject/QTimer)
    paths = _paths(args)
    settings = ConfigStore(paths.config_file).load()
    db = Database(paths.db_file)
    try:
        day = datetime.strptime(args.simular, "%Y-%m-%d").date()
        t = parse_hhmm(args.desde)
    except ValueError as exc:
        print(f"Fecha u hora no válida: {exc}")
        return 2
    tz = ZoneInfo(settings.zona_horaria)
    start = datetime(day.year, day.month, day.day, t.hour, t.minute, tzinfo=tz)
    hours = max(1, min(72, args.horas))
    entries = simulate(db, settings, start, start + timedelta(hours=hours))
    print(f"Simulación de {APP_NAME} — {start:%d/%m/%Y %H:%M} durante {hours} h ({settings.zona_horaria})")
    for e in entries:
        print(f"{e.when:%d/%m %H:%M:%S}  {e.level.upper():6} {e.message}")
    if not entries:
        print("No sonaría nada en ese periodo.")
    db.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.diagnostico:
        return run_diagnostics(args)
    if args.simular:
        from .system import setup_logging

        setup_logging(_paths(args).log_dir, args.depuracion)
        return run_cli_simulation(args)

    from PySide6.QtCore import QLockFile
    from PySide6.QtWidgets import QApplication, QMessageBox

    from . import backup
    from .audio import FakeAudioBackend, QtAudioBackend
    from .clock import SimulatedClock, SystemClock
    from .config import ConfigStore
    from .db import Database, DatabaseError
    from .engine import PlaybackEngine
    from .system import SleepInhibitor, setup_logging
    from .ui.common import AppContext, ask
    from .ui.main_window import MainWindow, app_icon
    from .ui.style import QSS

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)  # la ventana puede ocultarse en la bandeja

    try:
        paths = _paths(args)
    except OSError as exc:
        QMessageBox.critical(None, APP_NAME, f"No se puede crear la carpeta de datos:\n{exc}")
        return 1
    setup_logging(paths.log_dir, args.depuracion)

    def excepthook(exc_type, exc, tb):  # un error inesperado se registra; la programación sigue
        log.critical("Error no controlado", exc_info=(exc_type, exc, tb))
    sys.excepthook = excepthook

    # Una sola instancia: dos copias abiertas harían sonar los timbres dos veces.
    lock = QLockFile(str(paths.lock_file))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        lock.removeStaleLockFile()
        if not lock.tryLock(100):
            log.info("Se ha intentado abrir una segunda instancia; se rechaza")
            QMessageBox.information(None, APP_NAME, "AulaAudio ya está abierto en este equipo. Busque su icono en la "
                                    "bandeja del sistema (junto al reloj).")
            return 0

    log.info("Inicio de %s %s (datos en %s)", APP_NAME, __version__, paths.data_dir)
    store = ConfigStore(paths.config_file)
    settings = store.load()

    try:
        backup.backup_before_upgrade(paths)
    except Exception as exc:
        log.error("No se pudo hacer la copia previa a la actualización: %s", exc)
    db = None
    while db is None:
        try:
            db = Database(paths.db_file)
            if not db.integrity_ok():
                db.close()
                raise DatabaseError("La comprobación de integridad de la base de datos ha fallado.")
        except DatabaseError as exc:
            db = None
            log.critical("Base de datos no disponible: %s", exc)
            copies = backup.list_backups(paths.backup_dir)
            good = [c for c in copies if c.kind != "dañada"]
            if not good or not ask(None, "Problema con la base de datos",
                                   f"{exc}\n\n¿Quiere restaurar la copia de seguridad más reciente "
                                   f"({good[0].created:%d/%m/%Y %H:%M})?" if good else str(exc),
                                   yes="Restaurar copia", no="Salir", danger=True):
                QMessageBox.critical(None, APP_NAME, "AulaAudio no puede continuar sin base de datos. Consulte el "
                                     "manual de mantenimiento («Recuperación ante fallos»).")
                return 1
            stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
            try:
                # Se conservan los archivos dañados (no se borran), junto con su diario WAL:
                # si el WAL se quedara junto a una base nueva, SQLite intentaría aplicarlo.
                for suffix in ("", "-wal", "-shm"):
                    f = Path(str(paths.db_file) + suffix)
                    if f.exists():
                        f.rename(Path(f"{paths.db_file}.danada_{stamp}{suffix}"))
                restored = Database(paths.db_file)
                backup.restore_backup(good[0].path, restored, paths)
                restored.close()
                settings = store.load()
            except Exception as exc2:
                log.critical("Fallo al restaurar: %s", exc2)
                QMessageBox.critical(None, APP_NAME, f"No se ha podido restaurar la copia: {exc2}")
                return 1

    try:
        db.prune_history(settings.dias_historial)
        if settings.copia_automatica and backup.automatic_backup_due(paths.backup_dir):
            backup.create_backup(db, paths.config_file, paths.backup_dir, "automatica")
            backup.prune_automatic(paths.backup_dir, settings.copias_automaticas_a_conservar)
    except Exception as exc:
        log.error("Mantenimiento inicial incompleto: %s", exc)

    simulated = bool(args.modo_simulacion)
    if simulated:
        from zoneinfo import ZoneInfo

        try:
            start = datetime.strptime(args.modo_simulacion, "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(settings.zona_horaria))
        except ValueError:
            QMessageBox.critical(None, APP_NAME, "Formato de --modo-simulacion: \"AAAA-MM-DD HH:MM\"")
            return 2
        clock = SimulatedClock(start, speed=max(0.1, min(3600.0, args.velocidad)))
    else:
        clock = SystemClock()
    backend = FakeAudioBackend() if args.silencio else QtAudioBackend()
    engine = PlaybackEngine(db, settings, backend, clock)
    inhibitor = SleepInhibitor()
    if settings.impedir_suspension:
        inhibitor.enable()
    ctx = AppContext(paths, db, store, settings, engine, backend, clock, inhibitor)
    if store.last_load_warning:
        db.add_history("aviso", "sistema", store.last_load_warning)
    db.add_history("info", "sistema", f"AulaAudio {__version__} iniciado" + (" en modo simulación." if simulated else "."))

    window = MainWindow(ctx, simulated=simulated)
    if args.minimizado and window.tray is not None or (settings.iniciar_minimizado and window.tray is not None):
        window.hide()
    else:
        window.show()
    engine.start()
    engine.tick()
    if not settings.primera_ejecucion_completada:
        window.show_normal()
        window.first_run()

    def on_quit():
        log.info("Cierre ordenado de AulaAudio")
        engine.shutdown()
        try:
            db.add_history("info", "sistema", "AulaAudio cerrado.")
        finally:
            db.close()
        inhibitor.disable()
        lock.unlock()

    def on_session_end(_manager):  # cierre de sesión o apagado: salir sin bloquearlo
        window._really_quit = True

    app.commitDataRequest.connect(on_session_end)
    app.aboutToQuit.connect(on_quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
