"""Pestaña Programación: horarios, eventos semanales, copia de días y vistas semanal / 24 h."""
from __future__ import annotations

from datetime import timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..models import (
    CONFLICTS,
    DAY_NAMES,
    DEFAULT_PRIORITY,
    END_AUDIO,
    END_DURATION,
    END_TIME,
    KINDS,
    Event,
    days_to_text,
    fmt_hhmm,
)
from .common import AppContext, ask, guarded, help_label, info, long_date
from .event_dialog import EventDialog


def source_names(db) -> tuple[dict, dict]:
    return {t.id: t for t in db.tracks()}, {p.id: p.name for p in db.playlists()}


def describe_source(ev: Event, tracks: dict, playlists: dict) -> str:
    if ev.playlist_id is not None:
        return "Lista: " + playlists.get(ev.playlist_id, "(eliminada)")
    if ev.track_id is not None:
        t = tracks.get(ev.track_id)
        if t is None:
            return "(archivo eliminado)"
        return t.title + ("" if t.status == "ok" else "  ⚠")
    return "⚠ sin audio"


def describe_end(ev: Event) -> str:
    if ev.end_mode == END_DURATION:
        return f"{ev.duration_min} min"
    if ev.end_mode == END_TIME and ev.end_time:
        return fmt_hhmm(ev.end_time) + (" (+1 día)" if ev.end_time <= ev.start else "")
    return "fin del audio"


def new_event_defaults(kind: str = "musica") -> Event:
    from datetime import time

    return Event(kind=kind, days=frozenset(range(5)), start=time(8, 0), end_mode=END_TIME if kind == "musica" else END_AUDIO,
                 end_time=time(8, 15), priority=DEFAULT_PRIORITY[kind],
                 conflict="esperar" if kind == "musica" else "interrumpir", resume=kind == "musica")


class EventTable(QTableWidget):
    HEADERS = ["Activo", "Hora", "Finaliza", "Nombre", "Tipo", "Días / fecha", "Audio", "Prior.", "Si coincide"]

    def __init__(self):
        super().__init__(0, len(self.HEADERS))
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        h = self.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

    def fill(self, events: list[Event], db) -> None:
        tracks, pls = source_names(db)
        self.setRowCount(0)
        for ev in events:
            r = self.rowCount()
            self.insertRow(r)
            when = ev.date.strftime("%d/%m/%Y") if ev.date else days_to_text(ev.days)
            values = ["Sí" if ev.enabled else "No", fmt_hhmm(ev.start), describe_end(ev), ev.name, KINDS[ev.kind],
                      when, describe_source(ev, tracks, pls), str(ev.priority), CONFLICTS[ev.conflict].split(" (")[0]]
            for c, v in enumerate(values):
                it = QTableWidgetItem(v)
                it.setData(Qt.ItemDataRole.UserRole, ev.id)
                if not ev.enabled:
                    it.setForeground(Qt.GlobalColor.gray)
                self.setItem(r, c, it)

    def selected_ids(self) -> list[int]:
        rows = sorted({i.row() for i in self.selectedIndexes()})
        return [self.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in rows]


class CopyDayDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Copiar la programación de un día")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Copiar los eventos del día:"))
        self.source = QComboBox()
        for n in DAY_NAMES:
            self.source.addItem(n.capitalize())
        lay.addWidget(self.source)
        lay.addWidget(QLabel("A los días:"))
        grid = QGridLayout()
        self.targets = []
        for i, n in enumerate(DAY_NAMES):
            cb = QCheckBox(n.capitalize())
            self.targets.append(cb)
            grid.addWidget(cb, i // 4, i % 4)
        lay.addLayout(grid)
        self.replace = QCheckBox("Sustituir la programación que ya tengan esos días")
        lay.addWidget(self.replace)
        lay.addWidget(help_label("Si marca «sustituir», los eventos que ahora suenan esos días dejarán de hacerlo "
                                 "(los que se queden sin ningún día se eliminarán)."))
        bb = QDialogButtonBox()
        bb.addButton("Copiar", QDialogButtonBox.ButtonRole.AcceptRole)
        bb.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


class WeekView(QWidget):
    """Lo que sonará cada día de una semana concreta, con las excepciones ya aplicadas."""

    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.offset = 0
        lay = QVBoxLayout(self)
        nav = QHBoxLayout()
        b_prev, b_today, b_next = QPushButton("◀ Semana anterior"), QPushButton("Esta semana"), QPushButton("Semana siguiente ▶")
        b_prev.clicked.connect(lambda: self._move(-1))
        b_next.clicked.connect(lambda: self._move(1))
        b_today.clicked.connect(lambda: self._move(0))
        self.title = QLabel()
        self.title.setObjectName("section")
        nav.addWidget(b_prev)
        nav.addWidget(b_today)
        nav.addWidget(b_next)
        nav.addStretch(1)
        nav.addWidget(self.title)
        lay.addLayout(nav)
        grid = QHBoxLayout()
        self.cols = []
        for _ in range(7):
            col = QVBoxLayout()
            head = QLabel()
            head.setWordWrap(True)
            head.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lst = QListWidget()
            col.addWidget(head)
            col.addWidget(lst, 1)
            grid.addLayout(col)
            self.cols.append((head, lst))
        lay.addLayout(grid, 1)
        ctx.data_changed.connect(self.refresh)
        self.refresh()

    def _move(self, step: int) -> None:
        self.offset = 0 if step == 0 else self.offset + step
        self.refresh()

    def refresh(self) -> None:
        sch = self.ctx.engine.scheduler
        today = self.ctx.local_now().date()
        monday = today - timedelta(days=today.weekday()) + timedelta(weeks=self.offset)
        self.title.setText(f"Semana del {monday.strftime('%d/%m/%Y')} al {(monday + timedelta(days=6)).strftime('%d/%m/%Y')}")
        for i, (head, lst) in enumerate(self.cols):
            d = monday + timedelta(days=i)
            plan = sch.day_plan(d)
            style = "font-weight:bold;" + ("color:#0b63b6;" if d == today else "")
            note = "" if plan.reason == "Horario ordinario." else f"<br><span style='color:#b42318'>{plan.reason.split('.')[0]}</span>"
            head.setText(f"<span style='{style}'>{DAY_NAMES[i].capitalize()} {d.day:02d}/{d.month:02d}</span>{note}")
            lst.clear()
            for o in plan.occurrences:
                end = f"-{fmt_hhmm(sch.local(o.end_utc).time())}" if o.end_utc else ""
                lst.addItem(f"{fmt_hhmm(o.event.start)}{end} {o.event.name}")
            if not plan.occurrences:
                lst.addItem("(sin eventos)")


class Next24View(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        lay = QVBoxLayout(self)
        lay.addWidget(help_label("Eventos que sonarán en las próximas 24 horas, con festivos y cambios de horario aplicados."))
        self.lst = QListWidget()
        self.lst.setAlternatingRowColors(True)
        lay.addWidget(self.lst)
        b = QPushButton("Actualizar")
        b.clicked.connect(self.refresh)
        lay.addWidget(b, alignment=Qt.AlignmentFlag.AlignLeft)
        ctx.data_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        sch = self.ctx.engine.scheduler
        now = self.ctx.clock.now()
        self.lst.clear()
        for o in sch.occurrences_between(now, now + timedelta(hours=24), include_start=False):
            loc = sch.local(o.start_utc)
            end = f" → {fmt_hhmm(sch.local(o.end_utc).time())}" if o.end_utc else ""
            self.lst.addItem(f"{long_date(loc).capitalize()}  {fmt_hhmm(loc.time())}{end}  ·  "
                             f"{KINDS[o.event.kind]}: {o.event.name}  (prioridad {o.priority})")
        if self.lst.count() == 0:
            self.lst.addItem("No hay eventos en las próximas 24 horas.")


class ScheduleTab(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs)

        page = QWidget()
        lay = QVBoxLayout(page)
        top = QHBoxLayout()
        top.addWidget(QLabel("Horario:"))
        self.sched = QComboBox()
        self.sched.setMinimumWidth(260)
        self.sched.currentIndexChanged.connect(self.refresh_events)
        top.addWidget(self.sched)
        for text, slot in (("Nuevo horario…", self._new_schedule), ("Renombrar…", self._rename_schedule),
                           ("Duplicar…", self._dup_schedule), ("Usar como ordinario", self._default_schedule),
                           ("Eliminar horario", self._del_schedule)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            top.addWidget(b)
        top.addStretch(1)
        lay.addLayout(top)
        lay.addWidget(help_label("El «horario ordinario» se usa todos los días salvo excepciones. Puede crear otros "
                                 "horarios (jornada reducida, día especial…) y asignarlos a fechas en «Calendario y excepciones»."))

        filt = QHBoxLayout()
        filt.addWidget(QLabel("Mostrar:"))
        self.day_filter = QComboBox()
        self.day_filter.addItem("Todos los días", -1)
        for i, n in enumerate(DAY_NAMES):
            self.day_filter.addItem(n.capitalize(), i)
        self.day_filter.currentIndexChanged.connect(self.refresh_events)
        filt.addWidget(self.day_filter)
        filt.addStretch(1)
        lay.addLayout(filt)

        self.table = EventTable()
        self.table.doubleClicked.connect(self._edit)
        lay.addWidget(self.table, 1)

        btns = QHBoxLayout()
        b_new = QPushButton("➕ Nuevo evento")
        b_new.setObjectName("primary")
        b_new.clicked.connect(self._new)
        btns.addWidget(b_new)
        for text, slot in (("Editar", self._edit), ("Duplicar", self._duplicate), ("Activar / desactivar", self._toggle),
                           ("Copiar un día a otros…", self._copy_day)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            btns.addWidget(b)
        btns.addStretch(1)
        b_del = QPushButton("Eliminar")
        b_del.setObjectName("danger")
        b_del.clicked.connect(self._delete)
        btns.addWidget(b_del)
        lay.addLayout(btns)
        tabs.addTab(page, "Eventos semanales")

        self.week = WeekView(ctx)
        tabs.addTab(self.week, "Vista semanal")
        self.next24 = Next24View(ctx)
        tabs.addTab(self.next24, "Próximas 24 horas")
        self.subtabs = tabs

        ctx.data_changed.connect(self.refresh)
        self.refresh()

    # ----------------------------------------------------------------- datos
    def current_schedule(self) -> int | None:
        return self.sched.currentData()

    def refresh(self) -> None:
        sid = self.current_schedule()
        self.sched.blockSignals(True)
        self.sched.clear()
        for s in self.ctx.db.schedules():
            self.sched.addItem(s.name + ("  (ordinario)" if s.is_default else ""), s.id)
        idx = self.sched.findData(sid) if sid is not None else 0
        self.sched.setCurrentIndex(max(0, idx))
        self.sched.blockSignals(False)
        self.refresh_events()

    def refresh_events(self) -> None:
        sid = self.current_schedule()
        if sid is None:
            return
        evs = self.ctx.db.events(schedule_id=sid, one_off=False)
        day = self.day_filter.currentData()
        if day is not None and day >= 0:
            evs = [e for e in evs if day in e.days]
        self.table.fill(evs, self.ctx.db)

    def _changed(self) -> None:
        self.ctx.notify_data_changed()

    # ----------------------------------------------------------------- eventos
    def _new(self) -> None:
        ev = new_event_defaults()
        ev.schedule_id = self.current_schedule()
        dlg = EventDialog(self.ctx, ev, self, "Nuevo evento")
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if guarded(self, lambda: self.ctx.db.save_event(dlg.result_event())):
                self._changed()

    def _edit(self) -> None:
        ids = self.table.selected_ids()
        if not ids:
            info(self, "Editar", "Seleccione primero un evento de la tabla.")
            return
        ev = self.ctx.db.event(ids[0])
        if ev is None:
            return
        dlg = EventDialog(self.ctx, ev, self, "Editar evento")
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if guarded(self, lambda: self.ctx.db.save_event(dlg.result_event())):
                self._changed()

    def _duplicate(self) -> None:
        ids = self.table.selected_ids()
        for eid in ids:
            guarded(self, lambda: self.ctx.db.duplicate_event(eid))
        if ids:
            self._changed()

    def _toggle(self) -> None:
        ids = self.table.selected_ids()
        for eid in ids:
            ev = self.ctx.db.event(eid)
            if ev:
                guarded(self, lambda: self.ctx.db.set_event_enabled(eid, not ev.enabled))
        if ids:
            self._changed()

    def _delete(self) -> None:
        ids = self.table.selected_ids()
        if not ids:
            return
        if ask(self, "Eliminar eventos", f"¿Eliminar {len(ids)} evento(s)? Esta acción no se puede deshacer "
               "(salvo restaurando una copia de seguridad).", yes="Eliminar", danger=True):
            for eid in ids:
                guarded(self, lambda: self.ctx.db.delete_event(eid))
            self._changed()

    def _copy_day(self) -> None:
        dlg = CopyDayDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        src = dlg.source.currentIndex()
        targets = [i for i, c in enumerate(dlg.targets) if c.isChecked() and i != src]
        if not targets:
            info(self, "Copiar día", "No ha elegido ningún día de destino distinto del de origen.")
            return
        if dlg.replace.isChecked() and not ask(self, "Sustituir programación",
                                               "Se sustituirá la programación de los días elegidos. ¿Continuar?",
                                               yes="Sustituir", danger=True):
            return
        n = guarded(self, lambda: self.ctx.db.copy_day(self.current_schedule(), src, targets, dlg.replace.isChecked()))
        if n is not None:
            self._changed()
            info(self, "Copiar día", f"Programación copiada. Eventos modificados: {n}.")

    # ----------------------------------------------------------------- horarios
    def _new_schedule(self) -> None:
        name, ok = QInputDialog.getText(self, "Nuevo horario", "Nombre del horario (p. ej. «Jornada reducida»):")
        if ok and name.strip():
            sid = guarded(self, lambda: self.ctx.db.add_schedule(name))
            if sid:
                self._changed()
                self.sched.setCurrentIndex(self.sched.findData(sid))

    def _rename_schedule(self) -> None:
        sid = self.current_schedule()
        current = next((s.name for s in self.ctx.db.schedules() if s.id == sid), "")
        name, ok = QInputDialog.getText(self, "Renombrar horario", "Nuevo nombre:", text=current)
        if ok and name.strip():
            guarded(self, lambda: self.ctx.db.rename_schedule(sid, name))
            self._changed()

    def _dup_schedule(self) -> None:
        sid = self.current_schedule()
        name, ok = QInputDialog.getText(self, "Duplicar horario", "Nombre de la copia:")
        if ok and name.strip():
            new = guarded(self, lambda: self.ctx.db.duplicate_schedule(sid, name))
            if new:
                self._changed()
                self.sched.setCurrentIndex(self.sched.findData(new))

    def _default_schedule(self) -> None:
        sid = self.current_schedule()
        if ask(self, "Horario ordinario", "¿Usar este horario como horario ordinario (todos los días salvo excepciones)?"):
            guarded(self, lambda: self.ctx.db.set_default_schedule(sid))
            self._changed()

    def _del_schedule(self) -> None:
        sid = self.current_schedule()
        n = len(self.ctx.db.events(schedule_id=sid))
        if ask(self, "Eliminar horario", f"Se eliminará el horario y sus {n} evento(s). ¿Continuar?",
               yes="Eliminar", danger=True):
            guarded(self, lambda: self.ctx.db.delete_schedule(sid))
            self._changed()
