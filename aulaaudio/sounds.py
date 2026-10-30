"""Sonidos generados por el propio programa (prueba de sonido y datos de ejemplo).

Se sintetizan con la biblioteca estándar, por lo que no hay problemas de licencia ni hace
falta descargar nada. Se escriben en la carpeta de datos la primera vez que se necesitan.
"""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

RATE = 22050


def _write(path: Path, samples: list[float]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 30000)) for s in samples))
    tmp.replace(path)
    return path


def _bell_note(freq: float, seconds: float, decay: float = 3.0) -> list[float]:
    n = int(RATE * seconds)
    out = []
    for i in range(n):
        t = i / RATE
        env = math.exp(-decay * t) * min(1.0, t * 200)
        s = (math.sin(2 * math.pi * freq * t) + 0.5 * math.sin(2 * math.pi * freq * 2.76 * t)
             + 0.25 * math.sin(2 * math.pi * freq * 5.4 * t))
        out.append(0.45 * env * s)
    return out


def _tone(freq: float, seconds: float, volume: float = 0.5) -> list[float]:
    n = int(RATE * seconds)
    fade = int(RATE * 0.02)
    out = []
    for i in range(n):
        env = min(1.0, i / fade, (n - i) / fade)
        out.append(volume * env * math.sin(2 * math.pi * freq * i / RATE))
    return out


def test_sound(folder: Path) -> Path:
    p = folder / "prueba_de_sonido.wav"
    if not p.exists():
        _write(p, _tone(440, 0.4) + _tone(554.37, 0.4) + _tone(659.25, 0.7))
    return p


def demo_bell(folder: Path) -> Path:
    p = folder / "EJEMPLO_timbre.wav"
    if not p.exists():
        _write(p, _bell_note(659.25, 1.2) + _bell_note(523.25, 2.0) + _bell_note(659.25, 1.2) + _bell_note(523.25, 2.4))
    return p


def demo_notice(folder: Path) -> Path:
    p = folder / "EJEMPLO_aviso.wav"
    if not p.exists():
        _write(p, _tone(523.25, 0.25) + _tone(659.25, 0.25) + _tone(783.99, 0.25) + _tone(1046.5, 0.6))
    return p


def demo_music(folder: Path, index: int) -> Path:
    """Melodía sencilla y suave (unos 20 s), claramente identificada como ejemplo."""
    p = folder / f"EJEMPLO_musica_{index}.wav"
    if p.exists():
        return p
    scales = [[261.63, 293.66, 329.63, 392.0, 440.0], [220.0, 261.63, 293.66, 329.63, 392.0]]
    scale = scales[index % 2]
    pattern = [0, 2, 4, 2, 3, 1, 0, 4, 3, 2, 1, 0, 2, 3, 4, 2]
    samples: list[float] = []
    for rep in range(2):
        for k, step in enumerate(pattern):
            f = scale[step] * (2 if rep and k % 4 == 0 else 1)
            samples += [0.6 * s for s in _bell_note(f, 0.6, decay=4.0)]
    return _write(p, samples)
