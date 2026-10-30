"""Configuración de la aplicación (config.json).

Se guarda de forma atómica: se escribe un archivo temporal, se fuerza a disco y se
sustituye el original con os.replace(). Antes se conserva la versión anterior como
config.json.bak. Si el archivo está dañado se recupera la copia .bak o los valores
predeterminados, y se informa de ello.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass, fields
from pathlib import Path

log = logging.getLogger(__name__)

DEVICE_FALLBACK_DEFAULT = "predeterminado"  # usar el dispositivo predeterminado del sistema
DEVICE_FALLBACK_NONE = "no_reproducir"  # no reproducir y avisar


@dataclass
class Settings:
    volumen_general: int = 80  # 0-100
    dispositivo_id: str = ""  # vacío = predeterminado del sistema
    dispositivo_nombre: str = ""
    si_falta_dispositivo: str = DEVICE_FALLBACK_DEFAULT
    automatizacion_activa: bool = True
    zona_horaria: str = "Europe/Madrid"
    margen_retraso_segundos: int = 60  # tolerancia para eventos que llegan con retraso
    fundido_salida_segundos: int = 3  # fundido al terminar la música por hora
    prioridad_manual: int = 5
    minimizar_a_bandeja: bool = True
    iniciar_minimizado: bool = False
    impedir_suspension: bool = True
    dias_historial: int = 180
    copia_automatica: bool = True
    copias_automaticas_a_conservar: int = 14
    primera_ejecucion_completada: bool = False
    aviso_bandeja_mostrado: bool = False

    def validated(self) -> "Settings":
        """Corrige valores fuera de rango en lugar de fallar."""
        s = Settings(**asdict(self))
        s.volumen_general = _clamp(s.volumen_general, 0, 100, 80)
        s.margen_retraso_segundos = _clamp(s.margen_retraso_segundos, 5, 600, 60)
        s.fundido_salida_segundos = _clamp(s.fundido_salida_segundos, 0, 15, 3)
        s.prioridad_manual = _clamp(s.prioridad_manual, 1, 10, 5)
        s.dias_historial = _clamp(s.dias_historial, 7, 3650, 180)
        s.copias_automaticas_a_conservar = _clamp(s.copias_automaticas_a_conservar, 1, 365, 14)
        if s.si_falta_dispositivo not in (DEVICE_FALLBACK_DEFAULT, DEVICE_FALLBACK_NONE):
            s.si_falta_dispositivo = DEVICE_FALLBACK_DEFAULT
        if not isinstance(s.zona_horaria, str) or not _valid_tz(s.zona_horaria):
            s.zona_horaria = "Europe/Madrid"
        s.dispositivo_id = str(s.dispositivo_id or "")[:500]
        s.dispositivo_nombre = str(s.dispositivo_nombre or "")[:300]
        for f in fields(Settings):
            if f.type == "bool":
                setattr(s, f.name, bool(getattr(s, f.name)))
        return s


def _clamp(value, lo, hi, default):
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _valid_tz(name: str) -> bool:
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(name)
        return True
    except Exception:
        return False


class ConfigStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.last_load_warning: str | None = None

    def load(self) -> Settings:
        self.last_load_warning = None
        for candidate in (self.path, self.path.with_suffix(".json.bak")):
            if not candidate.exists():
                continue
            try:
                raw = json.loads(candidate.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    raise ValueError("formato no válido")
                known = {f.name for f in fields(Settings)}
                settings = Settings(**{k: v for k, v in raw.items() if k in known}).validated()
                if candidate != self.path:
                    self.last_load_warning = (
                        "La configuración estaba dañada y se ha recuperado la copia anterior."
                    )
                return settings
            except (OSError, ValueError, TypeError) as exc:
                log.error("No se pudo leer %s: %s", candidate.name, exc)
        if self.path.exists():
            self.last_load_warning = (
                "La configuración estaba dañada; se han aplicado los valores predeterminados."
            )
        return Settings()

    def save(self, settings: Settings) -> None:
        settings = settings.validated()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(asdict(settings), ensure_ascii=False, indent=2)
        tmp = self.path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        if self.path.exists():
            try:
                shutil.copy2(self.path, self.path.with_suffix(".json.bak"))
            except OSError as exc:  # no impide guardar
                log.warning("No se pudo conservar la copia anterior de la configuración: %s", exc)
        os.replace(tmp, self.path)  # sustitución atómica: nunca queda un archivo a medias
