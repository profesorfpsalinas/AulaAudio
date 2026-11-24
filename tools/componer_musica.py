"""Compositor de la música libre de AulaAudio para recreos.

Genera piezas ORIGINALES por composición algorítmica y síntesis (no usa muestras ni
grabaciones de nadie) y las guarda en MP3 con sus etiquetas. El resultado se dedica al
dominio público (CC0 1.0): se puede reproducir en público, copiar y modificar sin licencias
ni pagos a entidades de gestión.

Uso (desde la raíz del proyecto; necesita numpy, scipy y ffmpeg con libmp3lame):
    python tools/componer_musica.py                 # todas las piezas en aulaaudio/musica
    python tools/componer_musica.py --solo 1 --wav  # una pieza, también en WAV

El resultado es reproducible: cada pieza usa una semilla fija.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile

SR = 44100
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "aulaaudio" / "musica"
MAJOR = [0, 2, 4, 5, 7, 9, 11]


# ============================================================== utilidades de síntesis
def mtof(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


_TABLES: dict = {}
TABLE_N = 4096


def _table(kind: str, harmonics: int) -> np.ndarray:
    key = (kind, harmonics)
    if key in _TABLES:
        return _TABLES[key]
    ph = np.arange(TABLE_N) / TABLE_N * 2 * np.pi
    w = np.zeros(TABLE_N)
    for k in range(1, harmonics + 1):
        if kind == "saw":
            w += np.sin(k * ph) / k
        elif kind == "square" and k % 2:
            w += np.sin(k * ph) / k
        elif kind == "tri" and k % 2:
            w += ((-1) ** ((k - 1) // 2)) * np.sin(k * ph) / (k * k)
        elif kind == "pulse25":
            w += np.sin(k * np.pi * 0.25) / k * np.cos(k * ph)
    if kind == "sine":
        w = np.sin(ph)
    w /= np.max(np.abs(w)) or 1
    _TABLES[key] = w
    return w


def osc(kind: str, freq, n: int, phase: float = 0.0) -> np.ndarray:
    """Oscilador de tabla sin aliasing (armónicos limitados por la frecuencia)."""
    f = np.broadcast_to(np.asarray(freq, dtype=float), (n,))
    fmax = float(np.max(f)) if n else 1.0
    harmonics = int(max(1, min(64, 16000 // max(fmax, 1))))
    tab = _table(kind, harmonics)
    pos = (phase + np.cumsum(f) / SR) % 1.0 * TABLE_N
    i0 = pos.astype(int)
    frac = pos - i0
    return tab[i0] * (1 - frac) + tab[(i0 + 1) % TABLE_N] * frac


def adsr(n: int, a: float, d: float, s: float, r: float, gate: int) -> np.ndarray:
    """Envolvente: ataque, caída hasta s, sostenido hasta `gate` muestras y extinción r."""
    env = np.zeros(n)
    na, nd, nr = max(1, int(a * SR)), max(1, int(d * SR)), max(1, int(r * SR))
    gate = min(gate, n)
    seg = np.ones(gate) * s
    seg[:min(na, gate)] = np.linspace(0, 1, na)[:gate]
    if gate > na:
        k = min(nd, gate - na)
        seg[na:na + k] = np.linspace(1, s, nd)[:k]
    env[:gate] = seg
    last = env[gate - 1] if gate else 0
    tail = min(nr, n - gate)
    env[gate:gate + tail] = last * np.linspace(1, 0, nr)[:tail]
    return env


def lowpass(x: np.ndarray, cutoff: float, order: int = 2) -> np.ndarray:
    sos = signal.butter(order, min(cutoff, SR * 0.45), "low", fs=SR, output="sos")
    return signal.sosfilt(sos, x)


def highpass(x: np.ndarray, cutoff: float, order: int = 2) -> np.ndarray:
    sos = signal.butter(order, cutoff, "high", fs=SR, output="sos")
    return signal.sosfilt(sos, x)


def bandpass(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    sos = signal.butter(2, [lo, min(hi, SR * 0.45)], "band", fs=SR, output="sos")
    return signal.sosfilt(sos, x)


# ============================================================== instrumentos (notas)
def inst_epiano(f, dur, vel, rng):
    n = int((dur + 1.2) * SR)
    t = np.arange(n) / SR
    idx = 1.6 * np.exp(-t * 2.5) + 0.25
    mod = np.sin(2 * np.pi * f * t) * idx
    car = np.sin(2 * np.pi * f * t + mod)
    tine = 0.06 * np.sin(2 * np.pi * f * 7.02 * t) * np.exp(-t * 9)
    env = adsr(n, 0.004, 1.4, 0.35, 0.35, int(dur * SR)) * np.exp(-t * 0.6)
    return (car + tine) * env * vel * 0.5


def inst_pluck(f, dur, vel, rng, bright=0.5):
    """Cuerda pulsada (Karplus-Strong), calculada por periodos para que sea rápida."""
    n = int((dur + 0.8) * SR)
    N = max(2, int(SR / f))
    y = np.zeros(n)
    y[:N] = lowpass(rng.uniform(-1, 1, N), 2000 + 6000 * bright)
    g = 0.996 * 0.5
    for start in range(N, n, N):
        end = min(start + N, n)
        idx = np.arange(start, end)
        y[start:end] = g * (y[idx - N] + y[idx - N - 1])
    env = adsr(n, 0.001, 0.05, 1.0, 0.12, int(dur * SR))
    return y * env * vel * 0.6


def inst_marimba(f, dur, vel, rng):
    n = int((dur + 0.6) * SR)
    t = np.arange(n) / SR
    y = (np.sin(2 * np.pi * f * t) * np.exp(-t * 5.5)
         + 0.35 * np.sin(2 * np.pi * f * 3.93 * t) * np.exp(-t * 16)
         + 0.08 * np.sin(2 * np.pi * f * 9.2 * t) * np.exp(-t * 40))
    y *= np.minimum(1, t / 0.002)
    return y * vel * 0.55


def inst_bell(f, dur, vel, rng):
    n = int((dur + 1.5) * SR)
    t = np.arange(n) / SR
    mod = np.sin(2 * np.pi * f * 3.5 * t) * 2.0 * np.exp(-t * 3)
    y = np.sin(2 * np.pi * f * t + mod) * np.exp(-t * 2.2) * np.minimum(1, t / 0.003)
    return y * vel * 0.3


def inst_chip(f, dur, vel, rng, kind="square"):
    n = int((dur + 0.06) * SR)
    t = np.arange(n) / SR
    vib = 1 + 0.006 * np.sin(2 * np.pi * 5.5 * t) * np.clip((t - 0.12) / 0.1, 0, 1)
    y = osc(kind, f * vib, n)
    env = adsr(n, 0.003, 0.08, 0.7, 0.05, int(dur * SR * 0.92))
    return lowpass(y, 9000) * env * vel * 0.32


def inst_lead(f, dur, vel, rng):
    n = int((dur + 0.3) * SR)
    t = np.arange(n) / SR
    vib = 1 + 0.004 * np.sin(2 * np.pi * 5 * t) * np.clip((t - 0.2) / 0.2, 0, 1)
    y = 0.6 * osc("saw", f * vib, n) + 0.6 * osc("saw", f * 1.004 * vib, n, 0.3) + 0.4 * osc("sine", f * vib, n)
    y = lowpass(y, 2400 + 600 * vel)
    env = adsr(n, 0.015, 0.2, 0.75, 0.18, int(dur * SR))
    return y * env * vel * 0.22


def inst_pad(f, dur, vel, rng):
    n = int((dur + 1.6) * SR)
    y = sum(osc("saw", f * d, n, p) for d, p in ((1, 0), (1.006, 0.33), (0.994, 0.66), (2.003, 0.1)))
    y = lowpass(y, 1100, order=2)
    env = adsr(n, 0.7, 0.5, 0.85, 1.4, int(dur * SR))
    return y * env * vel * 0.07


def inst_subbass(f, dur, vel, rng):
    n = int((dur + 0.12) * SR)
    y = osc("sine", f, n) + 0.25 * osc("tri", f * 2, n)
    y = np.tanh(y * 1.3)
    env = adsr(n, 0.006, 0.15, 0.85, 0.08, int(dur * SR * 0.95))
    return y * env * vel * 0.5


def inst_fingerbass(f, dur, vel, rng):
    n = int((dur + 0.15) * SR)
    t = np.arange(n) / SR
    y = osc("saw", f, n)
    y = lowpass(y, 350 + 900 * vel, order=2) * 0.7 + 0.6 * osc("sine", f, n)
    env = adsr(n, 0.004, 0.25, 0.55, 0.07, int(dur * SR * 0.9)) * (0.85 + 0.15 * np.exp(-t * 6))
    return np.tanh(y * 1.4) * env * vel * 0.45


def inst_tribass(f, dur, vel, rng):
    n = int((dur + 0.03) * SR)
    y = osc("tri", f, n)
    env = adsr(n, 0.002, 0.02, 1.0, 0.02, int(dur * SR * 0.9))
    return y * env * vel * 0.55


INSTRUMENTS = {"epiano": inst_epiano, "pluck": inst_pluck, "marimba": inst_marimba, "bell": inst_bell,
               "chip": inst_chip, "chip25": lambda f, d, v, r: inst_chip(f, d, v, r, "pulse25"),
               "lead": inst_lead, "pad": inst_pad, "subbass": inst_subbass, "fingerbass": inst_fingerbass,
               "tribass": inst_tribass}


# ============================================================== percusión
def drum(kind: str, vel: float, rng) -> np.ndarray:
    if kind == "kick":
        n = int(0.45 * SR)
        t = np.arange(n) / SR
        f = 48 + 110 * np.exp(-t * 32)
        y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7.5)
        click = rng.uniform(-1, 1, n) * np.exp(-t * 400) * 0.25
        return np.tanh((y + click) * 1.5) * vel * 0.75
    if kind == "snare":
        n = int(0.3 * SR)
        t = np.arange(n) / SR
        noise = bandpass(rng.uniform(-1, 1, n), 900, 7000) * np.exp(-t * 17)
        tone = np.sin(2 * np.pi * 185 * t) * np.exp(-t * 28) * 0.6
        return (noise * 1.2 + tone) * vel * 0.42
    if kind == "clap":
        n = int(0.35 * SR)
        t = np.arange(n) / SR
        env = np.zeros(n)
        for k, off in enumerate((0, 0.011, 0.022)):
            i = int(off * SR)
            env[i:] += np.exp(-(t[: n - i]) * (180 if k < 2 else 13))
        return bandpass(rng.uniform(-1, 1, n), 900, 3500) * env * vel * 0.35
    if kind in ("hat", "ohat"):
        n = int((0.07 if kind == "hat" else 0.35) * SR)
        t = np.arange(n) / SR
        y = highpass(rng.uniform(-1, 1, n), 7000) * np.exp(-t * (55 if kind == "hat" else 9))
        return y * vel * 0.22
    if kind == "shaker":
        n = int(0.11 * SR)
        t = np.arange(n) / SR
        env = np.minimum(1, t / 0.02) * np.exp(-t * 35)
        return bandpass(rng.uniform(-1, 1, n), 4500, 11000) * env * vel * 0.2
    if kind == "rim":
        n = int(0.08 * SR)
        t = np.arange(n) / SR
        y = np.sin(2 * np.pi * 1700 * t) * np.exp(-t * 90) + 0.4 * np.sin(2 * np.pi * 520 * t) * np.exp(-t * 60)
        return y * vel * 0.3
    if kind == "chipnoise":  # caja de videoconsola: ruido de baja resolución
        n = int(0.18 * SR)
        t = np.arange(n) / SR
        steps = np.repeat(rng.uniform(-1, 1, n // 6 + 1), 6)[:n]
        return steps * np.exp(-t * 22) * vel * 0.3
    if kind == "chiphat":
        n = int(0.04 * SR)
        t = np.arange(n) / SR
        steps = np.repeat(rng.uniform(-1, 1, n // 2 + 1), 2)[:n]
        return highpass(steps, 5000) * np.exp(-t * 90) * vel * 0.18
    if kind == "chipkick":
        n = int(0.2 * SR)
        t = np.arange(n) / SR
        f = 60 + 180 * np.exp(-t * 40)
        return osc("square", f, n) * np.exp(-t * 18) * vel * 0.35
    raise ValueError(kind)


# ============================================================== mezcla
@dataclass
class Bus:
    name: str
    pan: float = 0.0  # -1 izquierda, 1 derecha
    gain: float = 1.0
    reverb: float = 0.0  # envío a la reverberación
    data: np.ndarray = field(default_factory=lambda: np.zeros((0, 2)))


class Mixer:
    def __init__(self, seconds: float):
        self.n = int(seconds * SR) + SR * 3
        self.buses: dict[str, Bus] = {}

    def bus(self, name, pan=0.0, gain=1.0, reverb=0.0):
        b = Bus(name, pan, gain, reverb, np.zeros((self.n, 2)))
        self.buses[name] = b
        return b

    def add(self, name: str, start_s: float, mono: np.ndarray, pan: float | None = None):
        b = self.buses[name]
        i = int(start_s * SR)
        if i >= self.n:
            return
        mono = mono[: self.n - i]
        p = b.pan if pan is None else pan
        left, right = np.cos((p + 1) * np.pi / 4), np.sin((p + 1) * np.pi / 4)
        b.data[i:i + len(mono), 0] += mono * left * b.gain
        b.data[i:i + len(mono), 1] += mono * right * b.gain

    def render(self, rng, reverb_seconds=1.9, duck_from: str | None = None, duck_amount=0.0) -> np.ndarray:
        out = np.zeros((self.n, 2))
        send = np.zeros((self.n, 2))
        duck = None
        if duck_from and duck_from in self.buses and duck_amount > 0:
            k = np.abs(self.buses[duck_from].data).sum(axis=1)
            k = signal.lfilter([1 - 0.9995], [1, -0.9995], k)  # envolvente lenta
            k = k / (k.max() or 1)
            duck = 1 - duck_amount * np.clip(k * 3, 0, 1)
        for b in self.buses.values():
            d = b.data
            if duck is not None and b.name not in (duck_from, "drums", "bass"):
                d = d * duck[:, None]
            out += d
            send += d * b.reverb
        # reverberación por convolución con una respuesta sintética estéreo
        m = int(reverb_seconds * SR)
        t = np.arange(m) / SR
        ir = rng.normal(0, 1, (m, 2)) * np.exp(-t * 6.9 / reverb_seconds)[:, None]
        ir = np.stack([lowpass(ir[:, c], 5500) for c in range(2)], axis=1)
        ir[: int(0.022 * SR)] = 0  # predelay
        ir /= np.sqrt((ir ** 2).sum(axis=0))
        wet = np.stack([signal.fftconvolve(send[:, c], ir[:, c])[: self.n] for c in range(2)], axis=1)
        out += highpass(wet.T, 200).T * 0.9
        return out


def master(x: np.ndarray, target_rms_db=-19.0, ceiling_db=-1.0) -> np.ndarray:
    x = np.stack([highpass(x[:, c], 32) for c in range(2)], axis=1)
    # ecualización suave: menos 60-150 Hz y algo más de brillo (altavoces de pasillo y patio)
    lows = np.stack([bandpass(x[:, c], 55, 160) for c in range(2)], axis=1)
    highs = np.stack([highpass(x[:, c], 3500) for c in range(2)], axis=1)
    x = x - 0.3 * lows + 0.35 * highs
    # compresión suave 2:1 por encima del umbral (detector RMS de 60 ms)
    mono = np.sqrt(signal.lfilter([1 / 2646], [1, -(1 - 1 / 2646)], (x ** 2).mean(axis=1)) + 1e-12)
    level = 20 * np.log10(mono + 1e-9)
    ref = 20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-9)
    over = np.maximum(0, level - (ref + 4))
    gain = 10 ** (-(over * 0.5) / 20)
    x = x * gain[:, None]
    # volumen homogéneo entre piezas
    rms = np.sqrt((x[np.abs(x).sum(axis=1) > 1e-4] ** 2).mean())
    x = x * (10 ** (target_rms_db / 20) / rms)
    # limitador con anticipación de 5 ms
    ceiling = 10 ** (ceiling_db / 20)
    peak = np.abs(x).max(axis=1)
    need = np.minimum(1, ceiling / np.maximum(peak, 1e-9))
    from scipy.ndimage import minimum_filter1d
    need = minimum_filter1d(need, size=int(0.005 * SR) * 2 + 1)
    smooth = signal.lfilter([0.002], [1, -0.998], need - 1) + 1
    g = np.minimum(need, smooth)
    x = x * g[:, None]
    return np.clip(x, -ceiling, ceiling)


# ============================================================== armonía y melodía
def chord_degrees(root_deg: int, seventh: bool = False) -> list[int]:
    return [root_deg, root_deg + 2, root_deg + 4] + ([root_deg + 6] if seventh else [])


def deg_to_midi(key: int, deg: int) -> int:
    return key + 12 * (deg // 7) + MAJOR[deg % 7]


def voicing(key: int, root_deg: int, seventh: bool, center: int, prev: list[int] | None) -> list[int]:
    """Acorde en registro medio con el menor movimiento posible respecto al anterior."""
    pcs = [deg_to_midi(key, d) % 12 for d in chord_degrees(root_deg, seventh)]
    best, best_cost = None, 1e9
    for inv in range(len(pcs)):
        order = pcs[inv:] + pcs[:inv]
        notes, base = [], center - 6
        for pc in order:
            m = base + ((pc - base) % 12)
            while notes and m <= notes[-1]:
                m += 12
            notes.append(m)
        cost = abs(np.mean(notes) - center) * 0.6
        if prev:
            cost += sum(min(abs(a - b) for b in prev) for a in notes)
        if cost < best_cost:
            best, best_cost = notes, cost
    return best


RHYTHM_CELLS = {
    "lento": [[(0, 1)], [(0, 2)], [(0, 0.5), (0.5, 0.5)], [(0, 1.5), (1.5, 0.5)], [None]],
    "medio": [[(0, 1)], [(0, 0.5), (0.5, 0.5)], [(0, 0.75), (0.75, 0.25)], [(0.5, 0.5)], [(0, 1.5), (1.5, 0.5)],
              [(0, 0.5), (0.5, 1.0)]],
    "rapido": [[(0, 0.5), (0.5, 0.5)], [(0, 0.25), (0.25, 0.25), (0.5, 0.5)], [(0, 1)], [(0.5, 0.5)],
               [(0, 0.75), (0.75, 0.25)], [(0, 0.5), (0.5, 0.25), (0.75, 0.25)]],
}


def make_rhythm(rng, feel: str, beats: int = 8) -> list[tuple[float, float]]:
    """Ritmo de un motivo de 2 compases (en pulsos). Termina con una nota larga."""
    cells = RHYTHM_CELLS[feel]
    out, b = [], 0.0
    while b < beats - 2:
        cell = cells[rng.integers(len(cells))]
        if cell[0] is None:
            span = 1
        else:
            span = 1 if max(st + du for st, du in cell) <= 1 else 2
            out += [(b + st, du) for st, du in cell]
        b += span
    out.append((b, beats - b - (0.25 if feel != "lento" else 0)))
    return out


def make_contour(rng, length: int) -> list[int]:
    steps, last = [], 0
    for _ in range(length):
        if last and abs(last) >= 3:
            s = -np.sign(last) * rng.choice([1, 2])  # tras un salto, paso en sentido contrario
        else:
            s = rng.choice([-2, -1, -1, 1, 1, 2, 0, 3, -3], p=[.1, .2, .1, .2, .1, .1, .06, .07, .07])
        steps.append(int(s))
        last = s
    return steps


def realize(key, rhythm, contour, chords_by_beat, start_deg, lo, hi, end_on_root=False):
    """Convierte ritmo + contorno en notas.

    En los tiempos fuertes la nota pertenece al acorde, elegida en el sentido del contorno;
    se evitan más de dos notas iguales seguidas y los saltos mayores de una sexta."""
    lo_deg = next(d for d in range(-14, 40) if deg_to_midi(key, d) >= lo)
    hi_deg = max(d for d in range(-14, 40) if deg_to_midi(key, d) <= hi)
    notes, deg, repeats = [], start_deg, 0
    for i, (st, du) in enumerate(rhythm):
        prev = deg
        step = contour[(i - 1) % len(contour)] if i else 0
        target = prev + step
        if target > hi_deg or target < lo_deg:  # rebota en los extremos del registro
            target = prev - step
        chord = chords_by_beat(st)
        strong = (st % 2 == 0) or du >= 1 or i == len(rhythm) - 1
        if strong:
            roots = [chord[0]] if (end_on_root and i == len(rhythm) - 1) else chord
            tones = [c + 7 * o for c in roots for o in range(-3, 6) if lo_deg <= c + 7 * o <= hi_deg]

            def cost(t):
                c = abs(t - target)
                if step and np.sign(t - prev) != np.sign(step):
                    c += 1.5  # respetar el sentido de la frase
                if t == prev and repeats >= 1:
                    c += 4
                if abs(t - prev) > 5:
                    c += 3
                return c
            deg = min(tones, key=lambda t: (cost(t), t))
        else:
            deg = max(lo_deg, min(hi_deg, target))
            if deg == prev and repeats >= 1:
                deg = prev + (1 if prev < hi_deg else -1)
        repeats = repeats + 1 if deg == prev else 0
        notes.append((st, du, deg_to_midi(key, deg), deg))
    return notes


# ============================================================== piezas
@dataclass
class Style:
    titulo: str
    bpm: float
    key: int
    seed: int
    estructura: list  # (nombre_sección, compases, progresión por compás, capas)
    melodia: str
    acordes: str
    bajo: str
    arpegio: str | None
    pad: bool
    bateria: str
    feel: str
    swing: float = 0.0
    septimas: bool = False
    reverb: float = 0.25
    duck: float = 0.0
    descripcion: str = ""


P1 = [0, 4, 5, 3]  # I  V  vi IV
P2 = [5, 3, 0, 4]  # vi IV I  V
P3 = [0, 5, 3, 4]  # I  vi IV V
P4 = [1, 4, 0, 5]  # ii V  I  vi
P5 = [3, 4, 2, 5]  # IV V  iii vi
P6 = [0, 3, 0, 4]  # I  IV I  V
P7 = [3, 0, 4, 5]  # IV I  V  vi


def S(nombre, compases, prog, *capas):
    return (nombre, compases, prog, set(capas))


PIEZAS = [
    Style("Patio soleado", 118, 60, 101, [
        S("intro", 4, P1, "acordes", "hat"), S("A", 8, P1, "acordes", "bajo", "bat", "mel"),
        S("B", 8, P2, "acordes", "bajo", "bat", "mel", "arp", "clap"),
        S("A", 8, P1, "acordes", "bajo", "bat", "mel", "arp"),
        S("B", 8, P2, "acordes", "bajo", "bat", "mel", "arp", "clap"),
        S("C", 8, P5, "acordes", "bajo", "pad", "mel", "hat"),
        S("A", 8, P1, "acordes", "bajo", "bat", "mel", "arp", "clap"),
        S("B", 8, P2, "acordes", "bajo", "bat", "mel", "arp", "clap"),
        S("fin", 4, [0, 0, 0, 0], "acordes", "pad")],
        "pluck", "epiano", "subbass", "marimba", True, "pop", "medio", duck=0.25,
        descripcion="Pop alegre y luminoso."),
    Style("Bocadillo a la carrera", 140, 67, 202, [
        S("intro", 4, P6, "arp", "hat"), S("A", 8, P6, "arp", "bajo", "bat", "mel"),
        S("B", 8, P3, "arp", "bajo", "bat", "mel", "clap"), S("A", 8, P6, "arp", "bajo", "bat", "mel"),
        S("B", 8, P3, "arp", "bajo", "bat", "mel", "clap"), S("C", 8, P7, "bajo", "mel", "hat", "arp"),
        S("C", 8, P7, "bajo", "mel", "bat", "arp"), S("A", 8, P6, "arp", "bajo", "bat", "mel"),
        S("B", 8, P3, "arp", "bajo", "bat", "mel", "clap"), S("A", 8, P6, "arp", "bajo", "bat", "mel"),
        S("B", 8, P3, "arp", "bajo", "bat", "mel", "clap"), S("fin", 4, [0, 4, 0, 0], "arp", "bajo")],
        "chip", "chip25", "tribass", "chip25", False, "chip", "rapido", reverb=0.12,
        descripcion="Estilo videojuego clásico, rápido y animado."),
    Style("Siesta de nubes", 82, 65, 303, [
        S("intro", 4, P4, "acordes", "hat"), S("A", 8, P4, "acordes", "bajo", "bat", "mel"),
        S("B", 8, P7, "acordes", "bajo", "bat", "mel", "pad"), S("A", 8, P4, "acordes", "bajo", "bat", "mel"),
        S("C", 8, P5, "acordes", "pad", "mel", "hat"), S("B", 8, P7, "acordes", "bajo", "bat", "mel", "pad", "arp"),
        S("A", 8, P4, "acordes", "bajo", "bat", "mel", "arp"), S("fin", 4, [1, 4, 0, 0], "acordes", "pad")],
        "bell", "epiano", "fingerbass", "pluck", True, "lofi", "lento", swing=0.62, septimas=True, reverb=0.3,
        duck=0.15, descripcion="Lo-fi tranquilo, para recreos relajados."),
    Style("Rayuela", 112, 62, 404, [
        S("intro", 4, P6, "bajo", "bat"), S("A", 8, P6, "acordes", "bajo", "bat", "mel"),
        S("B", 8, P1, "acordes", "bajo", "bat", "mel", "clap", "arp"), S("A", 8, P6, "acordes", "bajo", "bat", "mel"),
        S("C", 8, P5, "acordes", "bajo", "hat", "pad", "mel"),
        S("B", 8, P1, "acordes", "bajo", "bat", "mel", "clap", "arp"),
        S("A", 8, P6, "acordes", "bajo", "bat", "mel", "clap"),
        S("B", 8, P1, "acordes", "bajo", "bat", "mel", "clap", "arp"),
        S("fin", 4, [0, 3, 4, 0], "acordes", "bajo", "bat")],
        "lead", "pluck", "fingerbass", None, True, "funk", "medio", reverb=0.2, duck=0.2,
        descripcion="Funky y bailable, con bajo marcado."),
    Style("Brisa en el pasillo", 92, 69, 505, [
        S("intro", 4, P3, "pad", "arp"), S("A", 8, P3, "pad", "arp", "bajo", "bat", "mel"),
        S("B", 8, P2, "pad", "arp", "bajo", "bat", "mel", "acordes"), S("A", 8, P3, "pad", "arp", "bajo", "bat", "mel"),
        S("C", 8, P5, "pad", "acordes", "mel"), S("B", 8, P2, "pad", "arp", "bajo", "bat", "mel", "acordes"),
        S("A", 8, P3, "pad", "arp", "bajo", "bat", "mel"), S("fin", 4, [0, 3, 0, 0], "pad", "arp")],
        "marimba", "epiano", "subbass", "pluck", True, "ambient", "lento", reverb=0.38,
        descripcion="Ambiente suave y espacioso."),
    Style("Vuelta a clase", 104, 70, 606, [
        S("intro", 4, P2, "acordes", "shaker"), S("A", 8, P2, "acordes", "bajo", "bat", "mel"),
        S("B", 8, P1, "acordes", "bajo", "bat", "mel", "arp", "clap"), S("A", 8, P2, "acordes", "bajo", "bat", "mel", "arp"),
        S("C", 8, P4, "acordes", "pad", "mel", "shaker"), S("B", 8, P1, "acordes", "bajo", "bat", "mel", "arp", "clap"),
        S("A", 8, P2, "acordes", "bajo", "bat", "mel", "clap"), S("fin", 4, [3, 4, 0, 0], "acordes", "pad")],
        "marimba", "pluck", "subbass", "bell", True, "pop2", "medio", reverb=0.22, duck=0.2,
        descripcion="Pop con marimba, alegre y desenfadado."),
    Style("Canicas", 126, 64, 707, [
        S("intro", 4, P3, "arp", "hat"), S("A", 8, P3, "acordes", "arp", "bajo", "bat", "mel"),
        S("B", 8, P1, "acordes", "arp", "bajo", "bat", "mel", "clap"), S("A", 8, P3, "acordes", "arp", "bajo", "bat", "mel"),
        S("B", 8, P1, "acordes", "arp", "bajo", "bat", "mel", "clap"), S("C", 8, P7, "acordes", "pad", "mel", "hat"),
        S("A", 8, P3, "acordes", "arp", "bajo", "bat", "mel", "clap"),
        S("B", 8, P1, "acordes", "arp", "bajo", "bat", "mel", "clap"),
        S("B", 8, P1, "acordes", "arp", "bajo", "bat", "mel", "clap"), S("fin", 4, [0, 4, 0, 0], "acordes", "arp")],
        "lead", "pluck", "subbass", "marimba", True, "pop", "medio", reverb=0.2, duck=0.25,
        descripcion="Pop enérgico, para recreos con mucho movimiento."),
    Style("Merienda tranquila", 76, 63, 808, [
        S("intro", 4, P4, "acordes", "shaker"), S("A", 8, P4, "acordes", "bajo", "bat", "mel"),
        S("B", 8, P2, "acordes", "bajo", "bat", "mel", "arp"), S("A", 8, P4, "acordes", "bajo", "bat", "mel", "pad"),
        S("C", 8, P7, "acordes", "pad", "mel"), S("B", 8, P2, "acordes", "bajo", "bat", "mel", "arp"),
        S("fin", 4, [1, 4, 0, 0], "acordes", "pad")],
        "pluck", "epiano", "fingerbass", "bell", True, "lofi", "lento", swing=0.6, septimas=True, reverb=0.32,
        duck=0.12, descripcion="Lo-fi cálido y pausado."),
]


DRUMS = {  # (instrumento, pulsos dentro del compás, intensidad)
    "pop": [("kick", [0, 1.5, 2], 1), ("snare", [1, 3], .8), ("hat", [i / 2 for i in range(8)], .5)],
    "pop2": [("kick", [0, 2, 2.5], 1), ("snare", [1, 3], .7), ("shaker", [i / 4 for i in range(16)], .5)],
    "chip": [("chipkick", [0, 2], 1), ("chipnoise", [1, 3], .9), ("chiphat", [i / 2 for i in range(8)], .6)],
    "lofi": [("kick", [0, 2.5], .85), ("snare", [1, 3], .5), ("hat", [i / 2 for i in range(8)], .35),
             ("rim", [3.5], .3)],
    "funk": [("kick", [0, 0.75, 2.5], 1), ("snare", [1, 3], .85), ("hat", [i / 4 for i in range(16)], .4),
             ("ohat", [3.5], .4)],
    "ambient": [("kick", [0, 2], .6), ("rim", [3], .35), ("shaker", [i / 4 for i in range(16)], .3)],
}

BASS_PATTERNS = {  # (pulso, duración, intervalo en grados: 0 fundamental, 4 quinta, 7 octava)
    "subbass": [(0, 1.5, 0), (1.5, 0.5, 0), (2, 1.5, 0), (3.5, 0.5, 4)],
    "fingerbass": [(0, 0.75, 0), (0.75, 0.25, 0), (1.5, 0.5, 7), (2, 0.75, 0), (2.75, 0.25, 4), (3.5, 0.5, 7)],
    "tribass": [(i / 2, 0.45, 7 if i % 2 else 0) for i in range(8)],
}


def compose(st: Style, rng) -> tuple[np.ndarray, float]:
    beat = 60 / st.bpm
    bars = sum(s[1] for s in st.estructura)
    total = bars * 4 * beat
    mix = Mixer(total + 4)
    mix.bus("drums", 0, 0.8, 0.06)
    mix.bus("bass", 0, 0.7, 0.0)
    mix.bus("chords", -0.25, 0.75, st.reverb)
    mix.bus("arp", 0.35, 0.45, st.reverb + 0.1)
    mix.bus("pad", 0, 0.8, st.reverb + 0.2)
    mix.bus("mel", 0.08, 1.0, st.reverb + 0.05)

    def at(b):  # pulso -> segundos, con swing en las corcheas a contratiempo
        whole, frac = divmod(b, 1)
        if st.swing and abs(frac - 0.5) < 1e-6:
            frac = st.swing
        return (whole + frac) * beat

    lo, hi = st.key + 2, st.key + 21
    melodies: dict[str, list] = {}
    prev_voicing = None
    bar0 = 0
    for si, (name, nbars, prog, layers) in enumerate(st.estructura):
        last_section = si == len(st.estructura) - 1
        for b in range(nbars):
            deg = prog[b % len(prog)]
            t0 = (bar0 + b) * 4
            chord = chord_degrees(deg, st.septimas)
            # ---------------- acordes
            if "acordes" in layers:
                v = voicing(st.key, deg, st.septimas, st.key + 7, prev_voicing)
                prev_voicing = v
                if st.acordes == "epiano":
                    hits = [(0, 1.4), (1.5, 0.4), (2, 1.9)] if st.feel != "lento" else [(0, 3.8)]
                elif st.acordes == "pluck":
                    hits = [(0, .4), (0.75, .4), (1.5, .4), (2.5, .4), (3, .9)]
                else:  # chip
                    hits = [(0, 0.45), (1.5, 0.45), (2.5, 0.45)]
                if last_section and b == nbars - 1:
                    hits = [(0, 3.9)]
                for hb, hd in hits:
                    for k, m in enumerate(v):
                        strum = k * 0.012 if st.feel == "lento" else 0
                        mix.add("chords", at(t0 + hb) + strum,
                                INSTRUMENTS[st.acordes](mtof(m), hd * beat, 0.5 + 0.1 * rng.random(), rng))
            # ---------------- arpegio
            if "arp" in layers and st.arpegio:
                tones = sorted(deg_to_midi(st.key, d) + 12 for d in chord)
                tones = tones + [tones[0] + 12]
                step = 0.25 if st.feel == "rapido" else 0.5
                seq = [0, 1, 2, 3, 2, 1] if st.feel != "lento" else [0, 2, 1, 3]
                for i in range(int(4 / step)):
                    m = tones[seq[i % len(seq)] % len(tones)]
                    vel = 0.35 + (0.15 if i % 2 == 0 else 0) + 0.05 * rng.random()
                    mix.add("arp", at(t0 + i * step), INSTRUMENTS[st.arpegio](mtof(m), step * beat * 0.9, vel, rng))
            # ---------------- pad
            if "pad" in layers and st.pad:
                for d in chord[:3]:
                    mix.add("pad", at(t0), inst_pad(mtof(deg_to_midi(st.key, d) - 12), 4 * beat, 0.7, rng))
            # ---------------- bajo
            if "bajo" in layers:
                root = deg_to_midi(st.key, deg) - 24
                while root < 33:
                    root += 12
                for pb, pd, iv in BASS_PATTERNS[st.bajo]:
                    m = root + (12 if iv == 7 else 7 if iv == 4 else 0)
                    if last_section and b == nbars - 1 and pb > 0:
                        continue
                    dur = 3.9 if last_section and b == nbars - 1 else pd
                    mix.add("bass", at(t0 + pb), INSTRUMENTS[st.bajo](mtof(m), dur * beat, 0.8, rng))
            # ---------------- batería
            if layers & {"bat", "hat", "clap", "shaker"} and not (last_section and b == nbars - 1):
                for kind, beats_, vel in DRUMS[st.bateria]:
                    if "bat" not in layers and kind not in ("hat", "shaker", "chiphat", "rim"):
                        if not ("clap" in layers and kind in ("snare", "chipnoise")):
                            continue
                    for db in beats_:
                        accent = 1.0 if db % 1 == 0 else 0.75
                        mix.add("drums", at(t0 + db), drum(kind, vel * accent * (0.9 + 0.2 * rng.random()), rng),
                                pan=(0.3 if kind in ("hat", "shaker", "chiphat", "ohat") else 0))
                if "clap" in layers and "bat" in layers and st.bateria != "chip":
                    for db in (1, 3):
                        mix.add("drums", at(t0 + db), drum("clap", 0.6, rng))
                if b == nbars - 1 and "bat" in layers and not last_section:  # redoble de paso
                    for k in range(4):
                        mix.add("drums", at(t0 + 3 + k * 0.25),
                                drum("chipnoise" if st.bateria == "chip" else "snare", 0.35 + 0.12 * k, rng))
        # ---------------- melodía (por secciones: A y B se repiten reconocibles)
        if "mel" in layers or (last_section and name == "fin"):
            if name not in melodies:
                phrase = []
                motif_r = make_rhythm(rng, st.feel)
                motif_c = make_contour(rng, 12)
                for half in range(nbars // 2):
                    r = motif_r if half % 2 == 0 else make_rhythm(rng, st.feel)
                    c = motif_c if half != 2 else make_contour(rng, 12)
                    end_root = half == nbars // 2 - 1
                    phrase.append((r, c, end_root))
                melodies[name] = phrase
            phrase = melodies[name]
            start_deg = 4 if name != "B" else 7
            notes_all = []
            for half, (r, c, end_root) in enumerate(phrase):
                base_bar = bar0 + half * 2

                def chords_by_beat(beat_in, base=half * 2):
                    return chord_degrees(prog[(base + int(beat_in // 4)) % len(prog)], st.septimas)
                notes = realize(st.key, r, c, chords_by_beat, start_deg, lo, hi, end_on_root=end_root)
                start_deg = notes[-1][3]
                notes_all += [(base_bar * 4 + s, d, m) for s, d, m, _ in notes]
            if name == "fin":
                notes_all = [n for n in notes_all if n[0] < (bar0 + nbars - 1) * 4]
            repeat = sum(1 for s in st.estructura[:si] if s[0] == name)
            octave = 12 if (repeat >= 2 and name == "A") else 0
            if notes_all and max(m for _, _, m in notes_all) + octave > 86:  # nunca más agudo que re6
                octave = 0
            for s, d, m in notes_all:
                vel = 0.75 + 0.1 * rng.random() + (0.08 if s % 4 == 0 else 0)
                mix.add("mel", at(s), INSTRUMENTS[st.melodia](mtof(m + octave), d * beat * 0.95, vel, rng))
        bar0 += nbars
    audio = mix.render(rng, duck_from="drums" if st.duck else None, duck_amount=st.duck)
    end = int((total + 2.5) * SR)
    audio = audio[:end]
    fade = int(2.0 * SR)
    audio[-fade:] *= np.linspace(1, 0, fade)[:, None] ** 2
    audio[: int(0.01 * SR)] *= np.linspace(0, 1, int(0.01 * SR))[:, None]
    return master(audio), total + 2.5


def slug(text: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return "".join(ch if ch.isalnum() else "-" for ch in t).strip("-")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--solo", type=int, help="generar solo la pieza N")
    p.add_argument("--wav", action="store_true", help="guardar también en WAV")
    p.add_argument("--salida", default=str(OUT_DIR))
    args = p.parse_args(argv)
    out = Path(args.salida)
    out.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("Falta ffmpeg.")
        return 1
    for i, st in enumerate(PIEZAS, 1):
        if args.solo and args.solo != i:
            continue
        rng = np.random.default_rng(st.seed)
        audio, secs = compose(st, rng)
        name = f"{i:02d}-{slug(st.titulo)}"
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / f"{name}.wav"
            wavfile.write(wav, SR, (audio * 32767).astype(np.int16))
            if args.wav:
                shutil.copy(wav, out / wav.name)
            mp3 = out / f"{name}.mp3"
            subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame",
                            "-b:a", "128k", "-id3v2_version", "3",
                            "-metadata", f"title={st.titulo}", "-metadata", "artist=AulaAudio",
                            "-metadata", "album=Música libre para recreos", "-metadata", f"track={i}/{len(PIEZAS)}",
                            "-metadata", "genre=Instrumental", "-metadata", "date=2026",
                            "-metadata", "copyright=CC0 1.0 - Dominio público",
                            "-metadata", "comment=Música original generada por AulaAudio. Dominio público (CC0): "
                                         "uso libre, también en público, sin licencias.",
                            str(mp3)], check=True)
        peak = 20 * np.log10(np.abs(audio).max())
        rms = 20 * np.log10(np.sqrt((audio ** 2).mean()))
        print(f"{mp3.name}: {int(secs // 60)}:{int(secs % 60):02d}  pico {peak:.1f} dBFS  RMS {rms:.1f} dBFS  "
              f"{mp3.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
