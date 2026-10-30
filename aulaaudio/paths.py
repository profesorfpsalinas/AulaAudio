"""Ubicación de los datos de la aplicación.

El código, la configuración, la base de datos, las copias y los registros se guardan
en carpetas separadas dentro del perfil del usuario, nunca en la carpeta del programa.
Así una actualización o reinstalación no sustituye los datos del centro.

- Windows: %LOCALAPPDATA%\\AulaAudio\\{config,datos,copias,registros}
- Linux:   ~/.config/aulaaudio, ~/.local/share/aulaaudio/{datos,copias}, ~/.local/state/aulaaudio/registros

La variable de entorno AULAAUDIO_HOME (o la opción --datos) fuerza una carpeta raíz
única; se usa en pruebas y en el modo de simulación.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    config_dir: Path
    data_dir: Path
    backup_dir: Path
    log_dir: Path

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.json"

    @property
    def db_file(self) -> Path:
        return self.data_dir / "aulaaudio.db"

    @property
    def demo_sounds_dir(self) -> Path:
        return self.data_dir / "sonidos_ejemplo"

    @property
    def lock_file(self) -> Path:
        return self.data_dir / "aulaaudio.lock"

    def ensure(self) -> None:
        for d in (self.config_dir, self.data_dir, self.backup_dir, self.log_dir):
            d.mkdir(parents=True, exist_ok=True)


def from_root(root: Path) -> AppPaths:
    root = Path(root)
    return AppPaths(root / "config", root / "datos", root / "copias", root / "registros")


def default_paths() -> AppPaths:
    override = os.environ.get("AULAAUDIO_HOME")
    if override:
        return from_root(Path(override))
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "AulaAudio"
        return from_root(base)
    home = Path.home()
    config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config") / "aulaaudio"
    data = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share") / "aulaaudio"
    state = Path(os.environ.get("XDG_STATE_HOME") or home / ".local" / "state") / "aulaaudio"
    return AppPaths(config, data / "datos", data / "copias", state / "registros")
