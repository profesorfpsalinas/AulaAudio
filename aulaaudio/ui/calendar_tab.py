"""Pestaña Calendario: excepciones, eventos extraordinarios, consulta de un día y simulación."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import QDate, Qt, QTime
from PySide6.QtGui import QBrush, QColor, QTextCharFormat
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCalendarWidget,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from ..models import EXC_ALT, EXCEPTION_KINDS, KINDS, SILENT_EXCEPTIONS, CalendarException, ValidationError, fmt_hhmm
from ..simulation import simulate
from .common import AppContext, ask, error, guarded, help_label, info, long_date
from .event_dialog import EventDialog
from .schedule_tab import EventTable, new_event_defaults


def _qd(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


def _pd(q: QDate) -> date:
    return date(q.year(), q.month(), q.day())


class ExceptionDialog(QDialog):
    def __init__(self, ctx: AppContext, exc: CalendarException, parent=None):
        super().__init__(parent)
        self.ctx, self.exc = ctx, exc
        self.setWindowTitle("Excepción del calendario")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(exc.name)
        self.name.setMaxLength(100)
        self.name.setPlaceholderText("Por ejemplo: Vacaciones de Navidad")
        form.addRow("Nombre:", self.name)
        self.kind = QComboBox()
        for k, v in EXCEPTION_KINDS.items():
            self.kind.addItem(v, k)
        self.kind.setCurrentIndex(list(EXCEPTION_KINDS).index(exc.kind))
        self.kind.currentIndexChanged.connect(self._update)
        form.addRow("Tipo:", self.kind)
        self.d_from, self.d_to = QDateEdit(_qd(exc.date_from)), QDateEdit(_qd(exc.date_to))
        for w in (self.d_from, self.d_to):
            w.setCalendarPopup(True)
            w.setDisplayFormat("dd/MM/yyyy")
        self.d_from.dateChanged.connect(lambda q: self.d_to.setDate(q) if self.d_to.date() < q else None)
        form.addRow("Desde:", self.d_from)
        form.addRow("Hasta (incluido):", self.d_to)
        self.sched = QComboBox()
        for s in ctx.db.schedules():
            self.sched.addItem(s.name, s.id)
        if exc.schedule_id is not None:
            self.sched.setCurrentIndex(max(0, self.sched.findData(exc.schedule_id)))
        form.addRow("Horario a usar:", self.sched)
        self.notes = QLineEdit(exc.notes)
        self.notes.setMaxLength(500)
        form.addRow("Notas:", self.notes)
        lay.addLayout(form)
        lay.addWidget(help_label("Las excepciones prevalecen sobre la programación ordinaria. Los días «sin sonido» "
                                 "no suena ningún evento semanal; los eventos extraordinarios de esa fecha sí suenan."))
        bb = QDialogButtonBox()
        bb.addButton("Guardar", QDialogButtonBox.ButtonRole.AcceptRole)
        bb.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._update()

    def _update(self) -> None:
        self.sched.setEnabled(self.kind.currentData() == EXC_ALT)

    def _accept(self) -> None:
        e = self.exc
        e.name, e.kind = self.name.text(), self.kind.currentData()
        e.date_from, e.date_to = _pd(self.d_from.date()), _pd(self.d_to.date())
        e.schedule_id = self.sched.currentData() if e.kind == EXC_ALT else None
        e.notes = self.notes.text()
        try:
            e.validate()
        except ValidationError as exc:
            error(self, "Revise los datos", str(exc))
            return
        self.accept()


class CalendarTab(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs)
        tabs.addTab(self._build_exceptions(), "Festivos, vacaciones y cambios")
        tabs.addTab(self._build_oneoff(), "Eventos extraordinarios")
        tabs.addTab(self._build_query(), "Consultar una fecha")
        tabs.addTab(self._build_sim(), "Simulación")
        ctx.data_changed.connect(self.refresh)
        self.refresh()

    # ----------------------------------------------------------------- excepciones
    def _build_exceptions(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(help_label("Indique aquí los festivos, vacaciones, días no lectivos y los días en los que se "
                                 "usa otro horario (por ejemplo, jornada reducida)."))
        self.exc_table = QTableWidget(0, 4)
        self.exc_table.setHorizontalHeaderLabels(["Nombre", "Tipo", "Fechas", "Horario"])
        self.exc_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.exc_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.exc_table.verticalHeader().setVisible(False)
        self.exc_table.setAlternatingRowColors(True)
        self.exc_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.exc_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.exc_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.exc_table.doubleClicked.connect(self._edit_exc)
        lay.addWidget(self.exc_table, 1)
        row = QHBoxLayout()
        b = QPushButton("➕ Nueva excepción")
        b.setObjectName("primary")
        b.clicked.connect(self._new_exc)
        row.addWidget(b)
        b = QPushButton("Editar")
        b.clicked.connect(self._edit_exc)
        row.addWidget(b)
        row.addStretch(1)
        b = QPushButton("Eliminar")
        b.setObjectName("danger")
        b.clicked.connect(self._del_exc)
        row.addWidget(b)
        lay.addLayout(row)
        return w

    def _selected_exc(self) -> int | None:
        rows = {i.row() for i in self.exc_table.selectedIndexes()}
        return self.exc_table.item(min(rows), 0).data(Qt.ItemDataRole.UserRole) if rows else None

    def _new_exc(self) -> None:
        today = self.ctx.local_now().date()
        dlg = ExceptionDialog(self.ctx, CalendarException(date_from=today, date_to=today), self)
        if dlg.exec() == QDialog.DialogCode.Accepted and guarded(self, lambda: self.ctx.db.save_exception(dlg.exc)):
            self.ctx.notify_data_changed()

    def _edit_exc(self) -> None:
        xid = self._selected_exc()
        exc = next((e for e in self.ctx.db.exceptions() if e.id == xid), None)
        if exc is None:
            return
        dlg = ExceptionDialog(self.ctx, exc, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and guarded(self, lambda: self.ctx.db.save_exception(dlg.exc)):
            self.ctx.notify_data_changed()

    def _del_exc(self) -> None:
        xid = self._selected_exc()
        if xid is not None and ask(self, "Eliminar excepción", "¿Eliminar esta excepción? Esos días volverá a sonar "
                                   "el horario ordinario.", yes="Eliminar", danger=True):
            guarded(self, lambda: self.ctx.db.delete_exception(xid))
            self.ctx.notify_data_changed()

    # ----------------------------------------------------------------- eventos puntuales
    def _build_oneoff(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(help_label("Avisos y eventos que suenan solo en una fecha concreta (por ejemplo, un aviso de "
                                 "simulacro o la música de una fiesta). Suenan aunque ese día sea festivo."))
        self.oneoff = EventTable()
        self.oneoff.doubleClicked.connect(self._edit_oneoff)
        lay.addWidget(self.oneoff, 1)
        row = QHBoxLayout()
        b = QPushButton("➕ Nuevo evento extraordinario")
        b.setObjectName("primary")
        b.clicked.connect(self._new_oneoff)
        row.addWidget(b)
        for text, slot in (("Editar", self._edit_oneoff), ("Duplicar", self._dup_oneoff)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        b = QPushButton("Eliminar")
        b.setObjectName("danger")
        b.clicked.connect(self._del_oneoff)
        row.addWidget(b)
        lay.addLayout(row)
        return w

    def _new_oneoff(self) -> None:
        ev = new_event_defaults("aviso")
        ev.date = self.ctx.local_now().date() + timedelta(days=1)
        ev.days = frozenset()
        dlg = EventDialog(self.ctx, ev, self, "Nuevo evento extraordinario")
        if dlg.exec() == QDialog.DialogCode.Accepted and guarded(self, lambda: self.ctx.db.save_event(dlg.result_event())):
            self.ctx.notify_data_changed()

    def _edit_oneoff(self) -> None:
        ids = self.oneoff.selected_ids()
        ev = self.ctx.db.event(ids[0]) if ids else None
        if ev is None:
            return
        dlg = EventDialog(self.ctx, ev, self, "Editar evento extraordinario")
        if dlg.exec() == QDialog.DialogCode.Accepted and guarded(self, lambda: self.ctx.db.save_event(dlg.result_event())):
            self.ctx.notify_data_changed()

    def _dup_oneoff(self) -> None:
        for eid in self.oneoff.selected_ids():
            guarded(self, lambda: self.ctx.db.duplicate_event(eid))
        self.ctx.notify_data_changed()

    def _del_oneoff(self) -> None:
        ids = self.oneoff.selected_ids()
        if ids and ask(self, "Eliminar", f"¿Eliminar {len(ids)} evento(s) extraordinario(s)?", yes="Eliminar", danger=True):
            for eid in ids:
                guarded(self, lambda: self.ctx.db.delete_event(eid))
            self.ctx.notify_data_changed()

    # ----------------------------------------------------------------- consultar día
    def _build_query(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        self.cal = QCalendarWidget()
        self.cal.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        self.cal.setGridVisible(True)
        self.cal.selectionChanged.connect(self._show_day)
        self.cal.currentPageChanged.connect(lambda *_: self._paint_calendar())
        left = QVBoxLayout()
        left.addWidget(self.cal)
        left.addWidget(help_label("En rojo: días sin sonido. En naranja: días con otro horario."))
        left.addStretch(1)
        lay.addLayout(left, 1)
        right = QVBoxLayout()
        self.day_title = QLabel()
        self.day_title.setObjectName("section")
        self.day_reason = QLabel()
        self.day_reason.setWordWrap(True)
        self.day_list = QListWidget()
        self.day_list.setAlternatingRowColors(True)
        right.addWidget(self.day_title)
        right.addWidget(self.day_reason)
        right.addWidget(self.day_list, 1)
        lay.addLayout(right, 1)
        return w

    def _paint_calendar(self) -> None:
        self.cal.setDateTextFormat(QDate(), QTextCharFormat())  # limpia
        y, m = self.cal.yearShown(), self.cal.monthShown()
        first = date(y, m, 1) - timedelta(days=7)
        silent, alt = QTextCharFormat(), QTextCharFormat()
        silent.setBackground(QBrush(QColor("#f8c9c5")))
        alt.setBackground(QBrush(QColor("#fde2b8")))
        for e in self.ctx.db.exceptions():
            d = max(e.date_from, first)
            last = min(e.date_to, first + timedelta(days=50))
            while d <= last:
                self.cal.setDateTextFormat(_qd(d), silent if e.kind in SILENT_EXCEPTIONS else alt)
                d += timedelta(days=1)

    def _show_day(self) -> None:
        d = _pd(self.cal.selectedDate())
        sch = self.ctx.engine.scheduler
        plan = sch.day_plan(d)
        self.day_title.setText(long_date(d).capitalize())
        self.day_reason.setText(plan.reason)
        self.day_list.clear()
        for o in plan.occurrences:
            end = f" → {fmt_hhmm(sch.local(o.end_utc).time())}" if o.end_utc else ""
            extra = "  (extraordinario)" if o.event.is_one_off else ""
            self.day_list.addItem(f"{fmt_hhmm(sch.local(o.start_utc).time())}{end}  ·  {KINDS[o.event.kind]}: "
                                  f"{o.event.name}  (prioridad {o.priority}){extra}")
        if not plan.occurrences:
            self.day_list.addItem("Ese día no sonará nada.")

    # ----------------------------------------------------------------- simulación
    def _build_sim(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(help_label("Avanza virtualmente por el horario con las mismas reglas que el uso real "
                                 "(prioridades, conflictos, reanudaciones) y muestra qué ocurriría. No emite sonido "
                                 "ni modifica la programación. Si no se conoce la duración de un archivo se suponen "
                                 "10 s para timbres y avisos y 3 min para la música."))
        row = QHBoxLayout()
        row.addWidget(QLabel("Fecha:"))
        self.sim_date = QDateEdit()
        self.sim_date.setCalendarPopup(True)
        self.sim_date.setDisplayFormat("dd/MM/yyyy")
        self.sim_date.setDate(_qd(self.ctx.local_now().date()))
        row.addWidget(self.sim_date)
        row.addWidget(QLabel("desde"))
        self.sim_from = QTimeEdit(QTime(7, 0))
        self.sim_from.setDisplayFormat("HH:mm")
        row.addWidget(self.sim_from)
        row.addWidget(QLabel("durante"))
        self.sim_hours = QSpinBox()
        self.sim_hours.setRange(1, 24 * 3)
        self.sim_hours.setValue(12)
        self.sim_hours.setSuffix(" h")
        row.addWidget(self.sim_hours)
        b = QPushButton("▶ Simular")
        b.setObjectName("primary")
        b.clicked.connect(self._simulate)
        row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.sim_table = QTableWidget(0, 3)
        self.sim_table.setHorizontalHeaderLabels(["Hora", "Tipo", "Qué ocurre"])
        self.sim_table.verticalHeader().setVisible(False)
        self.sim_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sim_table.setAlternatingRowColors(True)
        self.sim_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.sim_table, 1)
        return w

    def _simulate(self) -> None:
        tz = self.ctx.engine.scheduler.tz
        d = _pd(self.sim_date.date())
        t = self.sim_from.time()
        start = datetime(d.year, d.month, d.day, t.hour(), t.minute(), tzinfo=tz)
        end = start + timedelta(hours=self.sim_hours.value())
        step = 5 if self.sim_hours.value() <= 24 else 10
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            entries = guarded(self, lambda: simulate(self.ctx.db, self.ctx.settings, start, end, step_seconds=step))
        finally:
            QApplication.restoreOverrideCursor()
        if entries is None:
            return
        self.sim_table.setRowCount(0)
        labels = {"info": "Información", "aviso": "Aviso", "error": "Error"}
        for e in entries:
            r = self.sim_table.rowCount()
            self.sim_table.insertRow(r)
            when = e.when.strftime("%d/%m %H:%M:%S")
            for c, v in enumerate((when, labels.get(e.level, e.level), e.message)):
                it = QTableWidgetItem(v)
                if e.level != "info":
                    it.setForeground(QColor("#b42318"))
                self.sim_table.setItem(r, c, it)
        if not entries:
            info(self, "Simulación", "En ese periodo no sonaría nada.")

    # ----------------------------------------------------------------- refresco
    def refresh(self) -> None:
        names = {s.id: s.name for s in self.ctx.db.schedules()}
        self.exc_table.setRowCount(0)
        for e in self.ctx.db.exceptions():
            r = self.exc_table.rowCount()
            self.exc_table.insertRow(r)
            dates = e.date_from.strftime("%d/%m/%Y") + ("" if e.date_to == e.date_from else
                                                        " – " + e.date_to.strftime("%d/%m/%Y"))
            for c, v in enumerate((e.name, EXCEPTION_KINDS[e.kind], dates, names.get(e.schedule_id, ""))):
                it = QTableWidgetItem(v)
                it.setData(Qt.ItemDataRole.UserRole, e.id)
                self.exc_table.setItem(r, c, it)
        self.oneoff.fill(self.ctx.db.events(one_off=True), self.ctx.db)
        self._paint_calendar()
        self._show_day()
