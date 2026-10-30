"""Salida de audio.

`AudioBackend` define la interfaz que usa el motor. Hay dos implementaciones:
- `QtAudioBackend`: reproducción real con QtMultimedia (QMediaPlayer + QAudioOutput).
  Usa los dispositivos del sistema operativo y nunca cambia el volumen general del sistema:
  el volumen se aplica solo a la salida de AulaAudio.
- `FakeAudioBackend`: no emite sonido; se usa en pruebas y en la simulación.

Cada reproducción recibe un número (token). Las señales llevan ese número para que el motor
ignore avisos atrasados de una pista anterior.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer, QUrl, Signal

log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".ogg", ".oga", ".opus", ".flac", ".m4a", ".aac", ".wma"}

FAIL_FILE = "archivo"
FAIL_DEVICE = "dispositivo"


@dataclass(frozen=True)
class OutputDevice:
    id: str
    name: str
    is_default: bool = False


class AudioBackend(QObject):
    finished = Signal(int)  # token: el audio ha llegado a su final
    failed = Signal(int, str, str)  # token, tipo (archivo|dispositivo), mensaje comprensible
    devices_changed = Signal()
    duration_known = Signal(int, int)  # token, duración en ms

    def play(self, path: str, volume: float) -> int: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def stop(self) -> None: ...
    def fade_out_and_stop(self, ms: int) -> None: ...
    def set_volume(self, volume: float) -> None: ...
    def position_ms(self) -> int: ...
    def seek(self, ms: int) -> None: ...
    def devices(self) -> list[OutputDevice]: ...
    def select_device(self, device_id: str, fallback_to_default: bool) -> None: ...
    def current_device_name(self) -> str: ...
    def device_problem(self) -> str | None:
        """Devuelve un mensaje si no se puede reproducir por el dispositivo, o None."""
        ...


def perceptual_to_linear(volume: float) -> float:
    """Convierte un volumen 0..1 de la interfaz (escala perceptual) a ganancia lineal."""
    from PySide6.QtMultimedia import QtAudio

    v = max(0.0, min(1.0, float(volume)))
    return QtAudio.convertVolume(v, QtAudio.VolumeScale.LogarithmicVolumeScale,
                                 QtAudio.VolumeScale.LinearVolumeScale)


class QtAudioBackend(AudioBackend):
    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer

        self._QMediaPlayer = QMediaPlayer
        self._QMediaDevices = QMediaDevices
        self._media_devices = QMediaDevices(self)
        self._output = QAudioOutput(self)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._output)
        self._player.mediaStatusChanged.connect(self._on_status)
        self._player.errorOccurred.connect(self._on_error)
        self._player.durationChanged.connect(self._on_duration)
        self._media_devices.audioOutputsChanged.connect(self._on_outputs_changed)
        self._token = 0
        self._active = False
        self._volume = 1.0
        self._wanted_id = ""
        self._fallback = True
        self._problem: str | None = None
        self._fade = QTimer(self)
        self._fade.setInterval(100)
        self._fade.timeout.connect(self._fade_step)
        self._fade_steps_left = 0
        self._fade_start_vol = 0.0
        self._apply_device()

    # ---------------------------------------------------------------- reproducción
    def play(self, path: str, volume: float) -> int:
        self._fade.stop()
        self._token += 1
        self._active = True
        self._volume = volume
        self._output.setVolume(perceptual_to_linear(volume))
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(os.path.abspath(path)))
        self._player.play()
        return self._token

    def pause(self) -> None:
        self._player.pause()

    def resume(self) -> None:
        self._player.play()

    def stop(self) -> None:
        self._fade.stop()
        self._active = False
        self._token += 1  # invalida cualquier aviso pendiente de la pista detenida
        self._player.stop()
        self._player.setSource(QUrl())

    def fade_out_and_stop(self, ms: int) -> None:
        if ms <= 0 or not self._active:
            self.stop()
            return
        self._token += 1
        self._fade_steps_left = max(1, ms // self._fade.interval())
        self._fade_total = self._fade_steps_left
        self._fade_start_vol = self._volume
        self._fade.start()

    def _fade_step(self) -> None:
        self._fade_steps_left -= 1
        if self._fade_steps_left <= 0:
            self.stop()
            return
        self._output.setVolume(perceptual_to_linear(self._fade_start_vol * self._fade_steps_left / self._fade_total))

    def set_volume(self, volume: float) -> None:
        self._volume = volume
        if not self._fade.isActive():
            self._output.setVolume(perceptual_to_linear(volume))

    def position_ms(self) -> int:
        return int(self._player.position())

    def seek(self, ms: int) -> None:
        if self._player.isSeekable():
            self._player.setPosition(int(ms))

    def _on_status(self, status) -> None:
        S = self._QMediaPlayer.MediaStatus
        if not self._active:
            return
        if status == S.EndOfMedia:
            self._active = False
            self.finished.emit(self._token)
        elif status == S.InvalidMedia:
            self._active = False
            self.failed.emit(self._token, FAIL_FILE, "El archivo no se puede reproducir (formato no compatible o dañado).")

    def _on_error(self, error, message) -> None:
        E = self._QMediaPlayer.Error
        if error == E.NoError or not self._active:
            return
        self._active = False
        log.error("Error de QMediaPlayer (%s): %s", error, message)
        if error == E.ResourceError and self.device_problem():
            self.failed.emit(self._token, FAIL_DEVICE, self.device_problem())
        elif error == E.ResourceError:
            self.failed.emit(self._token, FAIL_FILE, "No se ha podido abrir el archivo de audio.")
        elif error == E.FormatError:
            self.failed.emit(self._token, FAIL_FILE, "Formato de audio no compatible.")
        elif error == E.AccessDeniedError:
            self.failed.emit(self._token, FAIL_FILE, "No hay permiso para leer el archivo.")
        else:
            self.failed.emit(self._token, FAIL_FILE, "Error de reproducción.")

    def _on_duration(self, ms) -> None:
        if ms and ms > 0:
            self.duration_known.emit(self._token, int(ms))

    # ---------------------------------------------------------------- dispositivos
    def devices(self) -> list[OutputDevice]:
        default = self._QMediaDevices.defaultAudioOutput()
        default_id = bytes(default.id()).decode(errors="replace") if not default.isNull() else ""
        result = []
        for d in self._QMediaDevices.audioOutputs():
            did = bytes(d.id()).decode(errors="replace")
            result.append(OutputDevice(did, d.description(), did == default_id))
        return result

    def select_device(self, device_id: str, fallback_to_default: bool) -> None:
        self._wanted_id = device_id or ""
        self._fallback = fallback_to_default
        self._apply_device()

    def _apply_device(self) -> None:
        outputs = self._QMediaDevices.audioOutputs()
        self._problem = None
        if not outputs:
            self._problem = "No hay ningún dispositivo de salida de audio disponible. Compruebe la tarjeta de sonido o los altavoces."
            return
        chosen = None
        if self._wanted_id:
            for d in outputs:
                if bytes(d.id()).decode(errors="replace") == self._wanted_id:
                    chosen = d
            if chosen is None and not self._fallback:
                self._problem = "El dispositivo de audio elegido no está conectado. Conéctelo o elija otro en Configuración."
                return
        if chosen is None:
            chosen = self._QMediaDevices.defaultAudioOutput()
        if self._output.device() != chosen:
            self._output.setDevice(chosen)

    def _on_outputs_changed(self) -> None:
        log.info("Cambio en los dispositivos de audio")
        self._apply_device()
        self.devices_changed.emit()

    def current_device_name(self) -> str:
        dev = self._output.device()
        return dev.description() if not dev.isNull() else "(ninguno)"

    def wanted_device_missing(self) -> bool:
        return bool(self._wanted_id) and all(d.id != self._wanted_id for d in self.devices())

    def device_problem(self) -> str | None:
        return self._problem


class FakeAudioBackend(AudioBackend):
    """Backend silencioso para pruebas y simulación. No toca ningún dispositivo real."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.token = 0
        self.playing: str | None = None
        self.paused = False
        self.volume = 1.0
        self.played: list[str] = []
        self.problem: str | None = None
        self.fail_paths: dict[str, str] = {}  # ruta -> tipo de fallo
        self._devices = [OutputDevice("fake-1", "Altavoces de prueba", True)]
        self.device_name = "Altavoces de prueba"
        self.position = 0

    def play(self, path, volume):
        self.token += 1
        self.playing, self.paused, self.volume, self.position = path, False, volume, 0
        self.played.append(path)
        if path in self.fail_paths:
            kind = self.fail_paths[path]
            tok = self.token
            self.playing = None
            QTimer.singleShot(0, lambda: self.failed.emit(tok, kind, "Fallo simulado"))
        return self.token

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop(self):
        self.token += 1
        self.playing = None
        self.paused = False

    def fade_out_and_stop(self, ms):
        self.stop()

    def set_volume(self, volume):
        self.volume = volume

    def position_ms(self):
        return self.position

    def seek(self, ms):
        self.position = ms

    def devices(self):
        return list(self._devices)

    def select_device(self, device_id, fallback_to_default):
        pass

    def current_device_name(self):
        return self.device_name

    def device_problem(self):
        return self.problem

    # utilidades de prueba
    def finish(self):
        """Simula que la pista actual llega a su final."""
        if self.playing is not None:
            self.playing = None
            self.finished.emit(self.token)

    def fail(self, kind=FAIL_FILE, message="Fallo simulado"):
        if self.playing is not None:
            self.playing = None
            self.failed.emit(self.token, kind, message)
