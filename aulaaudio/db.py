"""Acceso a la base de datos SQLite local.

- Todas las consultas son parametrizadas (nunca se concatenan datos del usuario en SQL).
- Modo WAL + synchronous=FULL: un corte de luz no corrompe la base de datos; como mucho se
  pierde la última operación no confirmada.
- Las escrituras van dentro de transacciones (`with db.tx():`).
- El esquema se versiona con PRAGMA user_version y se migra hacia delante.
"""
from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator

from .models import (
    CalendarException,
    Event,
    Playlist,
    Schedule,
    Track,
    ValidationError,
    fmt_hhmm,
    parse_hhmm,
)

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1

SCHEMA_V1 = """
CREATE TABLE schedules (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    is_default INTEGER NOT NULL DEFAULT 0,
    demo INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE tracks (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    size INTEGER,
    duration_ms INTEGER,
    status TEXT NOT NULL DEFAULT 'ok',
    status_msg TEXT NOT NULL DEFAULT '',
    added_at TEXT NOT NULL,
    demo INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE playlists (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    mode TEXT NOT NULL DEFAULT 'secuencial' CHECK (mode IN ('secuencial','aleatorio')),
    repeat INTEGER NOT NULL DEFAULT 1,
    demo INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE playlist_items (
    id INTEGER PRIMARY KEY,
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    position INTEGER NOT NULL
);
CREATE INDEX idx_items_playlist ON playlist_items(playlist_id, position);
CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    schedule_id INTEGER REFERENCES schedules(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('musica','timbre','aviso')),
    days TEXT NOT NULL DEFAULT '',
    date TEXT,
    start_time TEXT NOT NULL,
    end_mode TEXT NOT NULL CHECK (end_mode IN ('fin_audio','duracion','hora_fin')),
    duration_min INTEGER,
    end_time TEXT,
    track_id INTEGER REFERENCES tracks(id) ON DELETE SET NULL,
    playlist_id INTEGER REFERENCES playlists(id) ON DELETE SET NULL,
    volume INTEGER,
    enabled INTEGER NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 3,
    conflict TEXT NOT NULL DEFAULT 'interrumpir',
    resume INTEGER NOT NULL DEFAULT 0,
    demo INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE TABLE calendar_exceptions (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    date_from TEXT NOT NULL,
    date_to TEXT NOT NULL,
    schedule_id INTEGER REFERENCES schedules(id) ON DELETE SET NULL,
    notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE history (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    level TEXT NOT NULL,
    category TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE INDEX idx_history_ts ON history(ts);
"""

MIGRATIONS = {1: SCHEMA_V1}


class DatabaseError(RuntimeError):
    """Error de base de datos con mensaje comprensible."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path | str):
        self.path = str(path)
        self.conn: sqlite3.Connection | None = None
        self.open()

    # ------------------------------------------------------------------ conexión
    def open(self) -> None:
        try:
            if self.path != ":memory:":
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(self.path, isolation_level=None, timeout=10)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.conn.execute("PRAGMA busy_timeout = 10000")
            if self.path != ":memory:":
                self.conn.execute("PRAGMA journal_mode = WAL")
            self.conn.execute("PRAGMA synchronous = FULL")
            self._migrate()
        except sqlite3.DatabaseError as exc:
            self.close()
            raise DatabaseError(
                "No se puede abrir la base de datos. Puede estar dañada; "
                "restaure una copia de seguridad. Detalle técnico: " + str(exc)
            ) from exc

    def close(self) -> None:
        if self.conn is not None:
            try:
                self.conn.close()
            finally:
                self.conn = None

    def _migrate(self) -> None:
        current = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if current > SCHEMA_VERSION:
            raise DatabaseError(
                "La base de datos procede de una versión más moderna de AulaAudio. "
                "Actualice el programa antes de abrirla."
            )
        for version in range(current + 1, SCHEMA_VERSION + 1):
            with self.tx():  # cada migración es atómica: o se aplica entera o no se aplica
                for stmt in MIGRATIONS[version].split(";"):
                    if stmt.strip():
                        self.conn.execute(stmt)
                self.conn.execute(f"PRAGMA user_version = {int(version)}")
        if self.conn.execute("SELECT COUNT(*) FROM schedules").fetchone()[0] == 0:
            with self.tx():
                self.conn.execute(
                    "INSERT INTO schedules(name, is_default) VALUES (?, 1)", ("Horario ordinario",)
                )

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        if self.conn is None:
            raise DatabaseError("La base de datos no está abierta.")
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            yield self.conn
            self.conn.execute("COMMIT")
        except BaseException:
            try:
                self.conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise

    def q(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        if self.conn is None:
            raise DatabaseError("La base de datos no está abierta.")
        try:
            return self.conn.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("Error al leer la base de datos: " + str(exc)) from exc

    def x(self, sql: str, params: tuple | dict = ()) -> int:
        """Ejecuta una escritura en su propia transacción y devuelve lastrowid."""
        try:
            with self.tx() as c:
                cur = c.execute(sql, params)
                return cur.lastrowid
        except sqlite3.IntegrityError as exc:
            if "UNIQUE" in str(exc):
                raise ValidationError("Ya existe un elemento con ese nombre o ruta.") from exc
            raise DatabaseError("Los datos no son coherentes: " + str(exc)) from exc
        except sqlite3.Error as exc:
            raise DatabaseError("No se ha podido guardar en la base de datos: " + str(exc)) from exc

    def integrity_ok(self) -> bool:
        try:
            return self.q("PRAGMA quick_check")[0][0] == "ok"
        except DatabaseError:
            return False

    def schema_version(self) -> int:
        return self.q("PRAGMA user_version")[0][0]

    def backup_to(self, dest: Path) -> None:
        """Copia consistente en caliente usando la API de copia de SQLite."""
        target = sqlite3.connect(str(dest))
        try:
            self.conn.backup(target)
        finally:
            target.close()

    # ------------------------------------------------------------------ horarios
    def schedules(self) -> list[Schedule]:
        return [Schedule(r["id"], r["name"], bool(r["is_default"]), bool(r["demo"]))
                for r in self.q("SELECT * FROM schedules ORDER BY is_default DESC, name")]

    def default_schedule_id(self) -> int:
        rows = self.q("SELECT id FROM schedules WHERE is_default = 1 LIMIT 1")
        if rows:
            return rows[0]["id"]
        rows = self.q("SELECT id FROM schedules ORDER BY id LIMIT 1")
        return rows[0]["id"]

    def add_schedule(self, name: str, demo: bool = False) -> int:
        name = _clean_name(name)
        return self.x("INSERT INTO schedules(name, demo) VALUES (?, ?)", (name, int(demo)))

    def rename_schedule(self, sid: int, name: str) -> None:
        self.x("UPDATE schedules SET name = ? WHERE id = ?", (_clean_name(name), sid))

    def set_default_schedule(self, sid: int) -> None:
        with self.tx() as c:
            c.execute("UPDATE schedules SET is_default = 0")
            c.execute("UPDATE schedules SET is_default = 1 WHERE id = ?", (sid,))

    def delete_schedule(self, sid: int) -> None:
        if sid == self.default_schedule_id():
            raise ValidationError("No se puede eliminar el horario ordinario. Elija otro como ordinario antes.")
        self.x("DELETE FROM schedules WHERE id = ?", (sid,))

    def duplicate_schedule(self, sid: int, new_name: str) -> int:
        new_id = self.add_schedule(new_name)
        for ev in self.events(schedule_id=sid):
            ev.id = None
            ev.schedule_id = new_id
            ev.demo = False
            self.save_event(ev)
        return new_id

    # ------------------------------------------------------------------ eventos
    @staticmethod
    def _row_to_event(r: sqlite3.Row) -> Event:
        return Event(
            id=r["id"], name=r["name"], kind=r["kind"], schedule_id=r["schedule_id"],
            days=frozenset(int(d) for d in r["days"].split(",") if d != ""),
            date=date.fromisoformat(r["date"]) if r["date"] else None,
            start=parse_hhmm(r["start_time"]), end_mode=r["end_mode"],
            duration_min=r["duration_min"],
            end_time=parse_hhmm(r["end_time"]) if r["end_time"] else None,
            track_id=r["track_id"], playlist_id=r["playlist_id"], volume=r["volume"],
            enabled=bool(r["enabled"]), priority=r["priority"], conflict=r["conflict"],
            resume=bool(r["resume"]), demo=bool(r["demo"]),
        )

    def events(self, schedule_id: int | None = None, one_off: bool | None = None) -> list[Event]:
        sql, params = "SELECT * FROM events WHERE 1=1", []
        if schedule_id is not None:
            sql += " AND schedule_id = ?"
            params.append(schedule_id)
        if one_off is True:
            sql += " AND date IS NOT NULL"
        elif one_off is False:
            sql += " AND date IS NULL"
        sql += " ORDER BY date, start_time, priority DESC, name"
        return [self._row_to_event(r) for r in self.q(sql, tuple(params))]

    def event(self, eid: int) -> Event | None:
        rows = self.q("SELECT * FROM events WHERE id = ?", (eid,))
        return self._row_to_event(rows[0]) if rows else None

    def save_event(self, ev: Event) -> int:
        ev.validate()
        params = (
            ev.schedule_id if ev.date is None else None, ev.name, ev.kind,
            ",".join(str(d) for d in sorted(ev.days)) if ev.date is None else "",
            ev.date.isoformat() if ev.date else None, fmt_hhmm(ev.start), ev.end_mode,
            ev.duration_min if ev.end_mode == "duracion" else None,
            fmt_hhmm(ev.end_time) if ev.end_mode == "hora_fin" and ev.end_time else None,
            ev.track_id, ev.playlist_id, ev.volume, int(ev.enabled), int(ev.priority),
            ev.conflict, int(ev.resume), int(ev.demo), _now_iso(),
        )
        if ev.id is None:
            ev.id = self.x(
                "INSERT INTO events(schedule_id, name, kind, days, date, start_time, end_mode, "
                "duration_min, end_time, track_id, playlist_id, volume, enabled, priority, "
                "conflict, resume, demo, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                params,
            )
        else:
            self.x(
                "UPDATE events SET schedule_id=?, name=?, kind=?, days=?, date=?, start_time=?, "
                "end_mode=?, duration_min=?, end_time=?, track_id=?, playlist_id=?, volume=?, "
                "enabled=?, priority=?, conflict=?, resume=?, demo=?, updated_at=? WHERE id=?",
                params + (ev.id,),
            )
        return ev.id

    def delete_event(self, eid: int) -> None:
        self.x("DELETE FROM events WHERE id = ?", (eid,))

    def set_event_enabled(self, eid: int, enabled: bool) -> None:
        self.x("UPDATE events SET enabled = ?, updated_at = ? WHERE id = ?", (int(enabled), _now_iso(), eid))

    def duplicate_event(self, eid: int) -> int:
        ev = self.event(eid)
        if ev is None:
            raise ValidationError("El evento ya no existe.")
        ev.id = None
        ev.demo = False
        ev.name = (ev.name + " (copia)")[:100]
        return self.save_event(ev)

    def copy_day(self, schedule_id: int, source_day: int, target_days: list[int], replace: bool) -> int:
        """Copia la programación de un día a otros días del mismo horario.

        Los eventos semanales tienen un conjunto de días, así que copiar consiste en añadir
        los días destino a cada evento que suena el día origen. Si `replace` es True, antes
        se quitan los días destino del resto de eventos (los que se quedan sin días se borran).
        Devuelve el número de eventos afectados.
        """
        targets = {d for d in target_days if 0 <= d <= 6 and d != source_day}
        if not targets:
            return 0
        affected = 0
        try:
            with self.tx() as c:
                rows = c.execute(
                    "SELECT id, days FROM events WHERE schedule_id = ? AND date IS NULL", (schedule_id,)
                ).fetchall()
                for r in rows:
                    days = {int(d) for d in r["days"].split(",") if d != ""}
                    new = set(days)
                    if source_day in days:
                        new |= targets
                    elif replace:
                        new -= targets
                    if new == days:
                        continue
                    affected += 1
                    if new:
                        c.execute("UPDATE events SET days = ?, updated_at = ? WHERE id = ?",
                                  (",".join(str(d) for d in sorted(new)), _now_iso(), r["id"]))
                    else:
                        c.execute("DELETE FROM events WHERE id = ?", (r["id"],))
        except sqlite3.Error as exc:
            raise DatabaseError("No se ha podido copiar la programación: " + str(exc)) from exc
        return affected

    # ------------------------------------------------------------------ pistas
    @staticmethod
    def _row_to_track(r: sqlite3.Row) -> Track:
        return Track(r["id"], r["path"], r["title"], r["size"], r["duration_ms"],
                     r["status"], r["status_msg"], bool(r["demo"]))

    def tracks(self, search: str = "") -> list[Track]:
        if search:
            like = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            rows = self.q("SELECT * FROM tracks WHERE title LIKE ? ESCAPE '\\' OR path LIKE ? ESCAPE '\\' "
                          "ORDER BY title COLLATE NOCASE", (like, like))
        else:
            rows = self.q("SELECT * FROM tracks ORDER BY title COLLATE NOCASE")
        return [self._row_to_track(r) for r in rows]

    def track(self, tid: int) -> Track | None:
        rows = self.q("SELECT * FROM tracks WHERE id = ?", (tid,))
        return self._row_to_track(rows[0]) if rows else None

    def track_by_path(self, path: str) -> Track | None:
        rows = self.q("SELECT * FROM tracks WHERE path = ?", (path,))
        return self._row_to_track(rows[0]) if rows else None

    def add_track(self, path: str, title: str, size: int | None, demo: bool = False) -> int:
        existing = self.track_by_path(path)
        if existing:
            return existing.id
        return self.x("INSERT INTO tracks(path, title, size, added_at, demo) VALUES (?,?,?,?,?)",
                      (path, title[:200], size, _now_iso(), int(demo)))

    def update_track_status(self, tid: int, status: str, msg: str = "") -> None:
        self.x("UPDATE tracks SET status = ?, status_msg = ? WHERE id = ?", (status, msg[:300], tid))

    def update_track_path(self, tid: int, path: str, size: int | None) -> None:
        self.x("UPDATE tracks SET path = ?, size = ?, status = 'ok', status_msg = '' WHERE id = ?",
               (path, size, tid))

    def update_track_duration(self, tid: int, duration_ms: int) -> None:
        self.x("UPDATE tracks SET duration_ms = ? WHERE id = ?", (int(duration_ms), tid))

    def delete_track(self, tid: int) -> None:
        """Quita la pista de la biblioteca (el archivo del usuario no se toca)."""
        self.x("DELETE FROM tracks WHERE id = ?", (tid,))

    def events_using_track(self, tid: int) -> list[str]:
        return [r["name"] for r in self.q("SELECT name FROM events WHERE track_id = ?", (tid,))]

    # ------------------------------------------------------------------ listas
    def playlists(self) -> list[Playlist]:
        return [Playlist(r["id"], r["name"], r["mode"], bool(r["repeat"]), bool(r["demo"]))
                for r in self.q("SELECT * FROM playlists ORDER BY name COLLATE NOCASE")]

    def playlist(self, pid: int) -> Playlist | None:
        rows = self.q("SELECT * FROM playlists WHERE id = ?", (pid,))
        if not rows:
            return None
        r = rows[0]
        return Playlist(r["id"], r["name"], r["mode"], bool(r["repeat"]), bool(r["demo"]))

    def add_playlist(self, name: str, mode: str = "secuencial", repeat: bool = True, demo: bool = False) -> int:
        if mode not in ("secuencial", "aleatorio"):
            raise ValidationError("Modo de reproducción no válido.")
        return self.x("INSERT INTO playlists(name, mode, repeat, demo) VALUES (?,?,?,?)",
                      (_clean_name(name), mode, int(repeat), int(demo)))

    def update_playlist(self, pl: Playlist) -> None:
        if pl.mode not in ("secuencial", "aleatorio"):
            raise ValidationError("Modo de reproducción no válido.")
        self.x("UPDATE playlists SET name = ?, mode = ?, repeat = ? WHERE id = ?",
               (_clean_name(pl.name), pl.mode, int(pl.repeat), pl.id))

    def delete_playlist(self, pid: int) -> None:
        self.x("DELETE FROM playlists WHERE id = ?", (pid,))

    def events_using_playlist(self, pid: int) -> list[str]:
        return [r["name"] for r in self.q("SELECT name FROM events WHERE playlist_id = ?", (pid,))]

    def playlist_tracks(self, pid: int) -> list[Track]:
        rows = self.q("SELECT t.* FROM playlist_items i JOIN tracks t ON t.id = i.track_id "
                      "WHERE i.playlist_id = ? ORDER BY i.position", (pid,))
        return [self._row_to_track(r) for r in rows]

    def set_playlist_tracks(self, pid: int, track_ids: list[int]) -> None:
        try:
            with self.tx() as c:
                c.execute("DELETE FROM playlist_items WHERE playlist_id = ?", (pid,))
                c.executemany("INSERT INTO playlist_items(playlist_id, track_id, position) VALUES (?,?,?)",
                              [(pid, tid, i) for i, tid in enumerate(track_ids)])
        except sqlite3.Error as exc:
            raise DatabaseError("No se ha podido guardar la lista: " + str(exc)) from exc

    def duplicate_playlist(self, pid: int, new_name: str) -> int:
        pl = self.playlist(pid)
        new_id = self.add_playlist(new_name, pl.mode, pl.repeat)
        self.set_playlist_tracks(new_id, [t.id for t in self.playlist_tracks(pid)])
        return new_id

    # ------------------------------------------------------------------ excepciones
    @staticmethod
    def _row_to_exc(r: sqlite3.Row) -> CalendarException:
        return CalendarException(r["id"], r["name"], r["kind"], date.fromisoformat(r["date_from"]),
                                 date.fromisoformat(r["date_to"]), r["schedule_id"], r["notes"])

    def exceptions(self) -> list[CalendarException]:
        return [self._row_to_exc(r) for r in self.q("SELECT * FROM calendar_exceptions ORDER BY date_from")]

    def save_exception(self, e: CalendarException) -> int:
        e.validate()
        params = (e.name, e.kind, e.date_from.isoformat(), e.date_to.isoformat(), e.schedule_id, e.notes)
        if e.id is None:
            e.id = self.x("INSERT INTO calendar_exceptions(name, kind, date_from, date_to, schedule_id, notes) "
                          "VALUES (?,?,?,?,?,?)", params)
        else:
            self.x("UPDATE calendar_exceptions SET name=?, kind=?, date_from=?, date_to=?, schedule_id=?, "
                   "notes=? WHERE id=?", params + (e.id,))
        return e.id

    def delete_exception(self, xid: int) -> None:
        self.x("DELETE FROM calendar_exceptions WHERE id = ?", (xid,))

    # ------------------------------------------------------------------ historial
    def add_history(self, level: str, category: str, message: str) -> None:
        try:
            self.x("INSERT INTO history(ts, level, category, message) VALUES (?,?,?,?)",
                   (_now_iso(), level, category, message[:1000]))
        except (DatabaseError, ValidationError) as exc:  # el historial nunca debe tumbar la aplicación
            log.error("No se pudo registrar en el historial: %s", exc)

    def history(self, level: str | None = None, limit: int = 2000) -> list[sqlite3.Row]:
        if level:
            return self.q("SELECT * FROM history WHERE level = ? ORDER BY id DESC LIMIT ?", (level, limit))
        return self.q("SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,))

    def prune_history(self, keep_days: int) -> int:
        cutoff = datetime.now(timezone.utc).timestamp() - keep_days * 86400
        iso = datetime.fromtimestamp(cutoff, timezone.utc).isoformat(timespec="seconds")
        with self.tx() as c:
            return c.execute("DELETE FROM history WHERE ts < ?", (iso,)).rowcount

    # ------------------------------------------------------------------ datos de ejemplo
    def has_demo_data(self) -> bool:
        return any(self.q(f"SELECT 1 FROM {t} WHERE demo = 1 LIMIT 1")
                   for t in ("events", "playlists", "tracks", "schedules"))

    def delete_demo_data(self) -> None:
        with self.tx() as c:
            for table in ("events", "playlists", "tracks"):
                c.execute(f"DELETE FROM {table} WHERE demo = 1")  # nombres de tabla fijos, no del usuario
            c.execute("DELETE FROM schedules WHERE demo = 1 AND is_default = 0")


def _clean_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValidationError("El nombre no puede estar vacío.")
    if len(name) > 100:
        raise ValidationError("El nombre no puede superar 100 caracteres.")
    return name
