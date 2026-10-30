"""Integración con el sistema operativo, siempre sin privilegios de administrador.

- Registro rotativo de incidencias (1 MB x 5 archivos).
- Arranque automático con la sesión del usuario, solo si se activa expresamente:
  Windows: valor en HKEY_CURRENT_USER\\...\\Run (no requiere administrador).
  Linux: archivo ~/.config/autostart/aulaaudio.desktop (estándar XDG).
- Evitar la suspensión automática mientras el programa está abierto (Windows,
  SetThreadExecutionState; se deshace al cerrar). No modifica la configuración de energía.
No se ejecuta ningún comando de shell.
"""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "AulaAudio"


def setup_logging(log_dir: Path, debug: bool = False) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    fh = RotatingFileHandler(log_dir / "aulaaudio.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    root.addHandler(fh)
    if sys.stderr is not None:
        sh = logging.StreamHandler()
        sh.setLevel(logging.WARNING)
        root.addHandler(sh)


def launch_command() -> list[str]:
    """Orden para arrancar este mismo programa (empaquetado o desde el código fuente)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--minimizado"]
    exe = sys.executable
    if os.name == "nt":
        pyw = Path(exe).with_name("pythonw.exe")
        if pyw.exists():
            exe = str(pyw)
    # Ruta absoluta al lanzador: funciona sea cual sea la carpeta de trabajo al iniciar sesión.
    launcher = Path(__file__).resolve().parent.parent / "AulaAudio.pyw"
    return [exe, str(launcher), "--minimizado"]


def _quote_windows(args: list[str]) -> str:
    import subprocess

    return subprocess.list2cmdline(args)  # solo formatea la cadena; no ejecuta nada


def _desktop_exec(args: list[str]) -> str:
    out = []
    for a in args:
        if any(c in a for c in ' \t\n"\'\\$`'):
            a = '"' + a.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`") + '"'
        out.append(a.replace("%", "%%"))
    return " ".join(out)


def autostart_desktop_file(config_home: Path | None = None) -> Path:
    base = config_home or Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "autostart" / "aulaaudio.desktop"


def is_autostart_enabled(config_home: Path | None = None) -> bool:
    if sys.platform == "win32" and config_home is None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                winreg.QueryValueEx(k, RUN_VALUE)
                return True
        except OSError:
            return False
    return autostart_desktop_file(config_home).exists()


def set_autostart(enabled: bool, config_home: Path | None = None) -> None:
    args = launch_command()
    if sys.platform == "win32" and config_home is None:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enabled:
                winreg.SetValueEx(k, RUN_VALUE, 0, winreg.REG_SZ, _quote_windows(args))
            else:
                try:
                    winreg.DeleteValue(k, RUN_VALUE)
                except FileNotFoundError:
                    pass
        return
    f = autostart_desktop_file(config_home)
    if enabled:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(
            "[Desktop Entry]\nType=Application\nName=AulaAudio\n"
            "Comment=Música, timbres y avisos del centro educativo\n"
            f"Exec={_desktop_exec(args)}\nTerminal=false\nX-GNOME-Autostart-enabled=true\n",
            encoding="utf-8",
        )
    elif f.exists():
        f.unlink()


class SleepInhibitor:
    """Pide al sistema que no se suspenda por inactividad mientras AulaAudio esté abierto."""

    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001

    def __init__(self):
        self.active = False

    @property
    def supported(self) -> bool:
        return sys.platform == "win32"

    def enable(self) -> bool:
        if not self.supported:
            return False
        import ctypes

        res = ctypes.windll.kernel32.SetThreadExecutionState(self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED)
        self.active = res != 0
        return self.active

    def disable(self) -> None:
        if self.supported and self.active:
            import ctypes

            ctypes.windll.kernel32.SetThreadExecutionState(self.ES_CONTINUOUS)
            self.active = False
