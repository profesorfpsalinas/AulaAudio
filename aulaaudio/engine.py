"""Motor de reproducción.

Funciona en el hilo principal de Qt con un temporizador (cada 0,5 s) y nunca bloquea la
interfaz: la decodificación de audio la hace QtMultimedia en sus propios hilos.

Reglas de reproducción
----------------------
* Solo hay una reproducción a la vez (la «sesión actual»).
* Cuando llega un evento y ya suena algo, decide su campo «conflicto»:
  - interrumpir: si su prioridad es MAYOR O IGUAL que la de lo que suena, lo detiene y suena.
    Si es menor, no puede interrumpir y se omite (queda registrado).
  - esperar: se pone en cola y suena cuando termine lo actual, si aún está a tiempo
    (antes de su hora de fin, o como máximo 10 minutos después de su hora si no la tiene).
  - omitir: no suena.
* Reanudación: un evento programado interrumpido solo se reanuda si tiene activada la opción
  «reanudar», si su franja horaria sigue abierta y si la interrupción ha durado menos de
  15 minutos. La reproducción manual y las pruebas nunca se reanudan solas.
* La reproducción manual tiene la prioridad configurada (5 por defecto): los timbres y avisos
  con prioridad >= 5 la interrumpen; la música programada (prioridad 3) no.
* Detener (botón) para la sesión actual y vacía la cola y las reanudaciones pendientes:
  después de pulsar Detener no empieza a sonar nada hasta el siguiente evento programado.
* Al arrancar no se reproducen eventos pasados. Si al arrancar hay un evento con franja en
  curso (p. ej. la música del recreo), no se inicia solo: se ofrece «Iniciar ahora».
* Si entre dos comprobaciones pasa más tiempo que el margen de retraso (suspensión,
  hibernación, equipo bloqueado), los eventos de ese hueco se omiten y se avisa.
* Errores de archivo: se marca la pista, se registra y se pasa a la siguiente. Si fallan
  todas las pistas de una vuelta, la sesión se detiene (no hay bucles infinitos).
* Errores de dispositivo: se intenta recuperar una única vez; si vuelve a fallar se detiene
  y se avisa. Nunca se reintenta indefinidamente.
"""
from __future__ import annotations

import logging
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, QTimer, Signal

from .audio import FAIL_DEVICE, AudioBackend
from .config import DEVICE_FALLBACK_DEFAULT, Settings
from .models import (
    CONFLICT_INTERRUPT,
    CONFLICT_WAIT,
    END_AUDIO,
    Track,
    fmt_hhmm,
)
from .scheduler import Occurrence, ScheduleData, Scheduler

log = logging.getLogger(__name__)

WAIT_MAX = timedelta(minutes=10)
RESUME_MAX_GAP = timedelta(minutes=15)
CLOCK_BACKWARDS_TOLERANCE = timedelta(seconds=5)

KIND_AUTO, KIND_MANUAL, KIND_TEST = "auto", "manual", "prueba"


@dataclass
class Session:
    kind: str
    title: str
    tracks: list[Track]
    priority: int
    loop: bool
    shuffle: bool
    end_utc: datetime | None
    volume_factor: float = 1.0
    resume_allowed: bool = False
    occurrence: Occurrence | None = None
    index: int = 0
    position_ms: int = 0
    paused: bool = False
    pass_failures: int = 0
    pass_successes: int = 0
    device_retry_used: bool = False
    interrupted_at: datetime | None = None
    started_at: datetime | None = None

    @property
    def current_track(self) -> Track | None:
        return self.tracks[self.index] if 0 <= self.index < len(self.tracks) else None


@dataclass
class WaitingItem:
    occurrence: Occurrence
    deadline: datetime


class PlaybackEngine(QObject):
    changed = Signal()  # cambia lo que suena, la cola o el estado
    incident = Signal(str, str)  # nivel (aviso|error), mensaje comprensible
    history_logged = Signal()

    def __init__(self, db, settings: Settings, backend: AudioBackend, clock, parent=None):
        super().__init__(parent)
        self.db = db
        self.settings = settings
        self.backend = backend
        self.clock = clock
        self.current: Session | None = None
        self.resume_stack: list[Session] = []
        self.waiting: list[WaitingItem] = []
        self.fired: dict[tuple, datetime] = {}
        self.missed_in_progress: list[Occurrence] = []
        self.last_tick: datetime | None = None
        self.last_incident: tuple[str, str] | None = None
        self._token = -1
        self.file_exists = os.path.isfile  # sustituible en la simulación
        self.scheduler = Scheduler(ScheduleData([], [], 0, {}), settings.zona_horaria)
        self.backend.finished.connect(self._on_finished)
        self.backend.failed.connect(self._on_failed)
        self.backend.duration_known.connect(self._on_duration)
        self.backend.devices_changed.connect(self._on_devices_changed)
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self.tick)
        self.reload()
        self.apply_settings(settings)

    # ------------------------------------------------------------------ ciclo de vida
    def start(self) -> None:
        self._timer.start()

    def shutdown(self) -> None:
        self._timer.stop()
        self.backend.stop()
        self.current = None

    def reload(self) -> None:
        """Recarga la programación desde la base de datos (tras cualquier cambio)."""
        try:
            data = ScheduleData.from_db(self.db)
        except Exception as exc:  # se conserva la programación anterior en memoria
            self._incident("error", f"No se ha podido leer la programación: {exc}")
            return
        self.scheduler = Scheduler(data, self.settings.zona_horaria)
        self.changed.emit()

    def apply_settings(self, settings: Settings) -> None:
        self.settings = settings
        if str(self.scheduler.tz) != settings.zona_horaria:
            self.scheduler = Scheduler(self.scheduler.data, settings.zona_horaria)
        self.backend.select_device(settings.dispositivo_id,
                                   settings.si_falta_dispositivo == DEVICE_FALLBACK_DEFAULT)
        self._apply_volume()
        self.changed.emit()

    # ------------------------------------------------------------------ registro
    def _record(self, level: str, category: str, message: str) -> None:
        getattr(log, "error" if level == "error" else "warning" if level == "aviso" else "info")(message)
        self.db.add_history(level, category, message)
        self.history_logged.emit()

    def _incident(self, level: str, message: str) -> None:
        self._record(level, "incidencia", message)
        self.last_incident = (level, message)
        self.incident.emit(level, message)
        self.changed.emit()

    def acknowledge_incident(self) -> None:
        self.last_incident = None
        self.changed.emit()

    def _hm(self, moment: datetime) -> str:
        return fmt_hhmm(self.scheduler.local(moment).time())

    # ------------------------------------------------------------------ temporizador
    def tick(self) -> None:
        now = self.clock.now()
        if self.last_tick is None:
            self.last_tick = now
            self.missed_in_progress = [o for o in self.scheduler.in_progress(now)
                                       if self.settings.automatizacion_activa]
            for o in self.missed_in_progress:
                self.fired[o.key] = now
            self.changed.emit()
            return
        if now < self.last_tick - CLOCK_BACKWARDS_TOLERANCE:
            self._incident("aviso", "La hora del equipo ha retrocedido. Se continúa desde la nueva hora "
                           "sin repetir los eventos ya reproducidos.")
            self.last_tick = now
            return
        window_start, self.last_tick = self.last_tick, now
        margin = timedelta(seconds=self.settings.margen_retraso_segundos)
        gap = now - window_start
        if gap > margin:
            self._incident("aviso", f"El programa ha estado sin funcionar {int(gap.total_seconds() // 60)} min "
                           "(posible suspensión, hibernación o bloqueo del equipo). "
                           "Los eventos de ese periodo no se reproducen con retraso.")

        # 1) fin de la franja de lo que suena
        cur = self.current
        if cur and cur.end_utc and now >= cur.end_utc:
            self._end_current(f"Fin de «{cur.title}» (hora de finalización).", fade=True)

        # 2) caducidad de la cola y de las reanudaciones
        for w in list(self.waiting):
            if now > w.deadline:
                self.waiting.remove(w)
                self._record("aviso", "reproduccion",
                             f"Omitido «{w.occurrence.event.name}»: estuvo esperando y se pasó su hora.")
        self.resume_stack = [s for s in self.resume_stack if self._can_resume(s, now)]
        self.missed_in_progress = [o for o in self.missed_in_progress if o.end_utc and o.end_utc > now]

        # 3) eventos nuevos
        if self.settings.automatizacion_activa:
            for occ in self.scheduler.occurrences_between(window_start, now, include_start=False):
                if occ.key in self.fired:
                    continue
                self.fired[occ.key] = now
                if now - occ.start_utc > margin:
                    self._record("aviso", "reproduccion",
                                 f"Omitido «{occ.event.name}» de las {self._hm(occ.start_utc)}: "
                                 "el equipo no estaba funcionando a esa hora.")
                    continue
                if occ.end_utc and now >= occ.end_utc:
                    continue
                self._offer(occ, now)

        # 4) si no suena nada, atender la cola
        if self.current is None:
            self._start_next_pending(now)

        cutoff = now - timedelta(days=3)
        self.fired = {k: v for k, v in self.fired.items() if v > cutoff}
        self.changed.emit()

    # ------------------------------------------------------------------ conflictos
    def _offer(self, occ: Occurrence, now: datetime) -> None:
        ev = occ.event
        cur = self.current
        if cur is None:
            self._start_occurrence(occ, now)
            return
        if ev.conflict == CONFLICT_INTERRUPT and occ.priority >= cur.priority:
            self._interrupt_current(now, by=ev.name)
            self._start_occurrence(occ, now)
        elif ev.conflict == CONFLICT_WAIT:
            deadline = occ.end_utc or occ.start_utc + WAIT_MAX
            self.waiting.append(WaitingItem(occ, deadline))
            self._record("info", "reproduccion",
                         f"«{ev.name}» espera a que termine «{cur.title}».")
        else:
            why = ("tiene menor prioridad que" if ev.conflict == CONFLICT_INTERRUPT
                   else "está configurado para no sonar si ya suena")
            self._record("aviso", "reproduccion",
                         f"Omitido «{ev.name}» de las {self._hm(occ.start_utc)}: {why} «{cur.title}».")

    def _can_resume(self, s: Session, now: datetime) -> bool:
        if not s.resume_allowed or s.kind != KIND_AUTO:
            return False
        if s.end_utc is not None and now >= s.end_utc:
            return False
        return s.interrupted_at is not None and now - s.interrupted_at <= RESUME_MAX_GAP

    def _interrupt_current(self, now: datetime, by: str) -> None:
        cur = self.current
        if cur is None:
            return
        cur.position_ms = self.backend.position_ms()
        cur.interrupted_at = now
        self.backend.stop()
        self.current = None
        if self._can_resume(cur, now):
            self.resume_stack.append(cur)
            self.resume_stack = self.resume_stack[-3:]
            self._record("info", "reproduccion", f"«{cur.title}» interrumpido por «{by}»; se reanudará después.")
        else:
            self._record("info", "reproduccion", f"«{cur.title}» interrumpido por «{by}».")

    def _start_next_pending(self, now: datetime) -> None:
        candidates: list[tuple[int, int, object]] = []
        for w in self.waiting:
            candidates.append((w.occurrence.priority, 0, w))
        if self.resume_stack:
            s = self.resume_stack[-1]
            candidates.append((s.priority, 1, s))
        if not candidates:
            return
        _, _, item = max(candidates, key=lambda c: (c[0], c[1]))
        if isinstance(item, WaitingItem):
            self.waiting.remove(item)
            self._start_occurrence(item.occurrence, now)
        else:
            self.resume_stack.remove(item)
            item.interrupted_at = None
            item.paused = False
            self.current = item
            self._record("info", "reproduccion", f"Se reanuda «{item.title}».")
            self._play_current(seek_ms=item.position_ms)

    # ------------------------------------------------------------------ inicio de sesiones
    def _resolve_tracks(self, track_id: int | None, playlist_id: int | None) -> tuple[list[Track], bool, bool, str]:
        """Devuelve (pistas, repetir, aleatorio, nombre del origen)."""
        if playlist_id is not None:
            pl = self.db.playlist(playlist_id)
            if pl is None:
                return [], False, False, "(lista eliminada)"
            return self.db.playlist_tracks(playlist_id), pl.repeat, pl.mode == "aleatorio", pl.name
        if track_id is not None:
            # Un archivo suelto se repite si el evento dura hasta una hora o un tiempo dado;
            # con «al terminar el audio» suena una sola vez (ver _start_occurrence).
            t = self.db.track(track_id)
            return ([t] if t else []), True, False, (t.title if t else "(archivo eliminado)")
        return [], False, False, "(sin audio)"

    def _start_occurrence(self, occ: Occurrence, now: datetime) -> bool:
        ev = occ.event
        try:
            tracks, repeat, shuffle, _ = self._resolve_tracks(ev.track_id, ev.playlist_id)
        except Exception as exc:
            self._incident("error", f"No se ha podido preparar «{ev.name}»: {exc}")
            return False
        loop = repeat and ev.end_mode != END_AUDIO  # «al terminar el audio» nunca repite
        session = Session(
            kind=KIND_AUTO, title=ev.name, tracks=tracks, priority=int(ev.priority), loop=loop,
            shuffle=shuffle, end_utc=occ.end_utc,
            volume_factor=(ev.volume if ev.volume is not None else 100) / 100.0,
            resume_allowed=ev.resume,
            occurrence=occ, started_at=now,
        )
        return self._begin(session)

    def _begin(self, session: Session) -> bool:
        if not session.tracks:
            self._incident("aviso", f"«{session.title}» no tiene ningún audio asignado o la lista está vacía.")
            return False
        problem = self.backend.device_problem()
        if problem:
            self._incident("error", f"No se puede reproducir «{session.title}»: {problem}")
            return False
        if session.shuffle:
            random.shuffle(session.tracks)
        self.current = session
        self._record("info", "reproduccion", f"Inicio de «{session.title}»"
                     + (f" (hasta las {self._hm(session.end_utc)})" if session.end_utc else "") + ".")
        self._play_current()
        return self.current is session

    # ------------------------------------------------------------------ reproducción de pistas
    def _volume(self) -> float:
        factor = self.current.volume_factor if self.current else 1.0
        return max(0.0, min(1.0, self.settings.volumen_general / 100.0 * factor))

    def _apply_volume(self) -> None:
        self.backend.set_volume(self._volume())

    def _play_current(self, seek_ms: int = 0) -> None:
        """Reproduce la pista actual saltando las que no existen. Bucle acotado."""
        s = self.current
        attempts = 0
        while s is self.current and s is not None and attempts <= len(s.tracks) * 2:
            attempts += 1
            track = s.current_track
            if track is None:
                if not self._wrap_or_finish():
                    return
                continue
            if not self.file_exists(track.path):
                msg = f"No se encuentra el archivo «{track.title}» ({track.path}). Se pasa al siguiente."
                if track.status == "falta":  # ya se avisó: solo se anota, sin repetir la incidencia
                    self._record("aviso", "reproduccion", msg)
                else:
                    self._mark_track(track, "falta", "El archivo no existe o la carpeta no está disponible.")
                    self._incident("aviso", msg)
                s.pass_failures += 1
                s.index += 1
                continue
            self._token = self.backend.play(track.path, self._volume())
            if seek_ms:
                self.backend.seek(seek_ms)
            self.changed.emit()
            return
        if s is self.current and s is not None:
            self._end_current(f"«{s.title}» se ha detenido: no hay ningún archivo reproducible.", fade=False, level="error")

    def _wrap_or_finish(self) -> bool:
        """Al acabar la lista: vuelve a empezar si procede. Devuelve False si termina."""
        s = self.current
        all_failed = s.pass_successes == 0 and s.pass_failures >= len(s.tracks)
        if all_failed:
            self._end_current(f"«{s.title}» se ha detenido: no se ha podido reproducir ninguna pista.",
                              fade=False, level="error")
            return False
        if s.loop and s.pass_successes > 0:
            s.index, s.pass_failures, s.pass_successes = 0, 0, 0
            if s.shuffle:
                random.shuffle(s.tracks)
            return True
        self._end_current(f"Fin de «{s.title}».", fade=False)
        return False

    def _on_finished(self, token: int) -> None:
        if token != self._token or self.current is None:
            return
        s = self.current
        s.pass_successes += 1
        s.device_retry_used = False
        if s.current_track and s.current_track.status != "ok":
            self._mark_track(s.current_track, "ok", "")  # se ha reproducido bien: ya no está en error
        s.index += 1
        self._play_current()
        self.tick_soon()

    def _on_failed(self, token: int, kind: str, message: str) -> None:
        if token != self._token or self.current is None:
            return
        s = self.current
        track = s.current_track
        if kind == FAIL_DEVICE:
            if not s.device_retry_used:
                s.device_retry_used = True
                self._incident("aviso", f"Problema con el dispositivo de audio: {message} Se reintenta una vez.")
                self.backend.select_device(self.settings.dispositivo_id,
                                           self.settings.si_falta_dispositivo == DEVICE_FALLBACK_DEFAULT)
                self._play_current()
                return
            self._end_current(f"Reproducción detenida por un fallo del dispositivo de audio: {message}",
                              fade=False, level="error")
            return
        if track:
            self._mark_track(track, "error", message)
            self._incident("aviso", f"No se ha podido reproducir «{track.title}»: {message}")
        s.pass_failures += 1
        s.index += 1
        self._play_current()

    def _on_duration(self, token: int, ms: int) -> None:
        if token == self._token and self.current and self.current.current_track:
            t = self.current.current_track
            if t.duration_ms != ms and t.id is not None:
                t.duration_ms = ms
                try:
                    self.db.update_track_duration(t.id, ms)
                except Exception:
                    pass

    def _on_devices_changed(self) -> None:
        problem = self.backend.device_problem()
        if problem:
            self._incident("error", problem)
        else:
            self._record("info", "sistema", f"Dispositivo de audio en uso: {self.backend.current_device_name()}.")
        self.changed.emit()

    def _mark_track(self, track: Track, status: str, msg: str) -> None:
        track.status = status
        if track.id is not None:
            try:
                self.db.update_track_status(track.id, status, msg)
            except Exception as exc:
                log.error("No se pudo marcar la pista: %s", exc)

    def _end_current(self, message: str, fade: bool, level: str = "info") -> None:
        s = self.current
        if s is None:
            return
        self.current = None
        self._token = -1
        if fade and self.settings.fundido_salida_segundos > 0:
            self.backend.fade_out_and_stop(self.settings.fundido_salida_segundos * 1000)
        else:
            self.backend.stop()
        if level == "info":
            self._record("info", "reproduccion", message)
        else:
            self._incident(level, message)
        self.changed.emit()

    def tick_soon(self) -> None:
        if self.current is None:
            self._start_next_pending(self.clock.now())

    # ------------------------------------------------------------------ acciones del usuario
    def play_manual(self, title: str, track_id: int | None = None, playlist_id: int | None = None,
                    kind: str = KIND_MANUAL) -> bool:
        """Reproducción manual. Sustituye lo que suene: la interfaz pide confirmación antes."""
        tracks, repeat, shuffle, name = self._resolve_tracks(track_id, playlist_id)
        self._user_stop(silent=True)
        session = Session(kind=kind, title=title or name, tracks=tracks,
                          priority=self.settings.prioridad_manual,
                          loop=repeat and kind == KIND_MANUAL and playlist_id is not None,
                          shuffle=shuffle, end_utc=None, started_at=self.clock.now())
        return self._begin(session)

    def play_file_test(self, path: str, title: str = "Prueba de sonido") -> bool:
        self._user_stop(silent=True)
        session = Session(kind=KIND_TEST, title=title, tracks=[Track(None, path, title)],
                          priority=self.settings.prioridad_manual, loop=False, shuffle=False,
                          end_utc=None, started_at=self.clock.now())
        return self._begin(session)

    def start_missed(self, occ: Occurrence) -> bool:
        """Inicia a petición del usuario un evento cuya franja ya había empezado."""
        if occ in self.missed_in_progress:
            self.missed_in_progress.remove(occ)
        self._user_stop(silent=True)
        return self._start_occurrence(occ, self.clock.now())

    def pause(self) -> None:
        if self.current and not self.current.paused:
            self.current.paused = True
            self.backend.pause()
            self._record("info", "reproduccion", f"Pausa de «{self.current.title}».")
            self.changed.emit()

    def resume(self) -> None:
        if self.current and self.current.paused:
            self.current.paused = False
            self.backend.resume()
            self._record("info", "reproduccion", f"Se reanuda «{self.current.title}».")
            self.changed.emit()

    def stop(self) -> None:
        self._user_stop(silent=False)

    def _user_stop(self, silent: bool) -> None:
        had = self.current is not None or self.waiting or self.resume_stack
        title = self.current.title if self.current else None
        self.resume_stack.clear()
        self.waiting.clear()
        self.current = None
        self._token = -1
        self.backend.stop()
        if had and not silent:
            self._record("info", "reproduccion",
                         f"Detenido manualmente{f' «{title}»' if title else ''}.")
        self.changed.emit()

    def set_master_volume(self, value: int) -> None:
        self.settings.volumen_general = max(0, min(100, int(value)))
        self._apply_volume()

    def set_automation(self, enabled: bool) -> None:
        self.settings.automatizacion_activa = bool(enabled)
        self._record("info", "sistema", "Automatización " + ("activada." if enabled else "desactivada."))
        if not enabled:
            self.waiting.clear()
            self.missed_in_progress.clear()
        self.changed.emit()

    # ------------------------------------------------------------------ consultas para la interfaz
    def next_occurrence(self) -> Occurrence | None:
        return self.scheduler.next_occurrence(self.clock.now())

    def status(self) -> tuple[str, str]:
        """(código, texto) — código: funcionando | detenido | incidencia."""
        if self.last_incident and self.last_incident[0] == "error":
            return "incidencia", self.last_incident[1]
        problem = self.backend.device_problem()
        if problem:
            return "incidencia", problem
        if not self.settings.automatizacion_activa:
            return "detenido", "Automatización desactivada: los eventos programados no sonarán."
        if self.last_incident:
            return "incidencia", self.last_incident[1]
        return "funcionando", "Automatización activa: los eventos sonarán a su hora."
