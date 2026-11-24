"""Pestaña Calendario: excepciones, eventos extraordinarios, consulta de un día y simulación."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, QStandardPaths, Qt, QTime
from PySide6.QtGui import QBrush, QColor, QTextCharFormat
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCalendarWidget,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from .. import backup, vacaciones
from ..models import (
    EXC_ALT,
    EXCEPTION_KINDS,
    KINDS,
    CalendarException,
    ValidationError,
    describe_overlap,
    find_overlaps,
    fmt_hhmm,
)
from ..power import shutdown_decision
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
        self.cb_sounds = QCheckBox("Silenciar la programación de sonidos (música, timbres y avisos semanales)")
        self.cb_sounds.setChecked(exc.suspend_sounds)
        form.addRow("Esos días:", self.cb_sounds)
        self.cb_shutdown = QCheckBox("No apagar el equipo a la hora programada")
        self.cb_shutdown.setChecked(exc.suspend_shutdown)
        form.addRow("", self.cb_shutdown)
        self.notes = QLineEdit(exc.notes)
        self.notes.setMaxLength(500)
        form.addRow("Notas:", self.notes)
        lay.addLayout(form)
        lay.addWidget(help_label("Las excepciones prevalecen sobre la programación ordinaria. Las fechas «desde» y "
                                 "«hasta» están incluidas. Si se silencian los sonidos no suena ningún evento semanal "
                                 "(los eventos extraordinarios de esa fecha sí suenan). Si coinciden varias "
                                 "excepciones se aplica la más restrictiva."))
        bb = QDialogButtonBox()
        bb.addButton("Guardar", QDialogButtonBox.ButtonRole.AcceptRole)
        bb.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._update()

    def _update(self) -> None:
        alt = self.kind.currentData() == EXC_ALT
        self.sched.setEnabled(alt)
        self.cb_sounds.setEnabled(not alt)
        if alt:
            self.cb_sounds.setChecked(False)

    def _accept(self) -> None:
        e = self.exc
        e.name, e.kind = self.name.text(), self.kind.currentData()
        e.date_from, e.date_to = _pd(self.d_from.date()), _pd(self.d_to.date())
        e.schedule_id = self.sched.currentData() if e.kind == EXC_ALT else None
        e.notes = self.notes.text()
        e.suspend_sounds = self.cb_sounds.isChecked()
        e.suspend_shutdown = self.cb_shutdown.isChecked()
        try:
            e.validate()
        except ValidationError as exc:
            error(self, "Revise los datos", str(exc))
            return
        others = [x for x in self.ctx.db.exceptions() if x.id != e.id]
        clashes = [describe_overlap(a, b) for a, b in find_overlaps(others + [e]) if a is e or b is e]
        if clashes and not ask(self, "Periodos solapados", "Este periodo coincide con:\n\n• " +
                               "\n• ".join(clashes) + "\n\nEsos días se aplicará la opción más restrictiva. "
                               "¿Guardar de todos modos?", yes="Guardar"):
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
                                 "usa otro horario (por ejemplo, jornada reducida). En cada periodo puede elegir si se "
                                 "silencian los sonidos, si no se apaga el equipo, o ambas cosas. Al terminar el "
                                 "periodo vuelve sola la programación habitual. Puede importar y exportar el "
                                 "calendario como archivo vacaciones.json."))
        self.exc_table = QTableWidget(0, 5)
        self.exc_table.setHorizontalHeaderLabels(["Nombre", "Tipo", "Fechas", "Se suspende", "Horario"])
        self.exc_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.exc_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.exc_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.exc_table.verticalHeader().setVisible(False)
        self.exc_table.setAlternatingRowColors(True)
        self.exc_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.exc_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.exc_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.exc_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.exc_table.doubleClicked.connect(self._edit_exc)
        lay.addWidget(self.exc_table, 1)
        self.overlap_lbl = help_label("")
        self.overlap_lbl.setStyleSheet("color: #b54708;")
        lay.addWidget(self.overlap_lbl)
        row = QHBoxLayout()
        b = QPushButton("➕ Nueva excepción")
        b.setObjectName("primary")
        b.clicked.connect(self._new_exc)
        row.addWidget(b)
        for text, slot in (("Editar", self._edit_exc), ("Duplicar para el año siguiente", self._dup_next_year)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        b = QPushButton("Eliminar")
        b.setObjectName("danger")
        b.clicked.connect(self._del_exc)
        row.addWidget(b)
        lay.addLayout(row)
        row = QHBoxLayout()
        b = QPushButton("📥 Importar vacaciones.json…")
        b.clicked.connect(self._import_json)
        row.addWidget(b)
        b = QPushButton("📤 Exportar vacaciones.json…")
        b.clicked.connect(self._export_json)
        row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        return w

    def _selected_exc(self) -> int | None:
        rows = {i.row() for i in self.exc_table.selectedIndexes()}
        return self.exc_table.item(min(rows), 0).data(Qt.ItemDataRole.UserRole) if rows else None

    def _selected_exc_ids(self) -> list[int]:
        rows = sorted({i.row() for i in self.exc_table.selectedIndexes()})
        return [self.exc_table.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in rows]

    def _safety_backup(self, reason: str) -> bool:
        """Copia de seguridad antes de cambios en bloque. Devuelve False si el usuario cancela."""
        p = self.ctx.paths
        try:
            backup.create_backup(self.ctx.db, p.config_file, p.backup_dir, reason)
            return True
        except Exception as exc:  # no bloquear si no se puede hacer la copia, pero avisar
            return ask(self, "Copia de seguridad", f"No se ha podido hacer la copia de seguridad previa ({exc}). "
                       "¿Continuar de todos modos?", yes="Continuar", danger=True)

    def _dup_next_year(self) -> None:
        ids = set(self._selected_exc_ids())
        current = self.ctx.db.exceptions()
        chosen = [e for e in current if e.id in ids]
        if not chosen:
            info(self, "Duplicar para el año siguiente", "Seleccione en la lista los periodos que quiere copiar "
                 "(puede seleccionar varios con Ctrl o Mayús).")
            return
        copies, warnings = vacaciones.next_year_copies(chosen, current)
        if not copies:
            info(self, "Duplicar para el año siguiente", "\n".join(warnings) or "No hay nada que copiar.")
            return
        lines = "\n".join(f"• {c.name}: {c.date_from:%d/%m/%Y} – {c.date_to:%d/%m/%Y}" for c in copies)
        extra = ("\n\nAvisos:\n" + "\n".join(warnings)) if warnings else ""
        if not ask(self, "Duplicar para el año siguiente", f"Se crearán estos periodos:\n\n{lines}{extra}\n\n"
                   "Revise después las fechas que cambian cada año (Semana Santa, Carnaval, puentes).",
                   yes="Crear"):
            return
        if self._safety_backup("antes_de_duplicar") and \
                guarded(self, lambda: self.ctx.db.save_exceptions(copies)) is not None:
            self.ctx.notify_data_changed()

    def _import_json(self) -> None:
        start = str(Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)))
        path, _ = QFileDialog.getOpenFileName(self, "Importar vacaciones y festivos", start,
                                              "Calendario de vacaciones (*.json);;Todos los archivos (*)")
        if not path:
            return
        try:
            result = vacaciones.read_file(Path(path))
        except vacaciones.VacationFileError as exc:
            error(self, "No se ha importado nada", f"{exc}\n\nCorrija el archivo y vuelva a importarlo. "
                  "La programación actual no ha cambiado.")
            return
        if not result.items:
            info(self, "Importar", "El archivo no contiene ningún periodo.")
            return
        box = QMessageBox(self)
        box.setWindowTitle("Importar vacaciones.json")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(f"El archivo contiene {len(result.items)} periodo(s) y festivo(s).\n\n"
                    "¿Quiere añadirlos a los que ya hay, o sustituir todos los festivos, vacaciones y días no "
                    "lectivos actuales? (Los cambios de horario se conservan siempre.)")
        b_add = box.addButton("Añadir", QMessageBox.ButtonRole.AcceptRole)
        b_rep = box.addButton("Sustituir", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(b_add)
        box.exec()
        if box.clickedButton() not in (b_add, b_rep):
            return
        replace = box.clickedButton() is b_rep
        to_add, warnings = vacaciones.merge_plan(self.ctx.db.exceptions(), result.items, replace)
        warnings = result.warnings + [w for w in warnings if w not in result.warnings]
        summary = f"Se van a {'sustituir los periodos actuales por' if replace else 'añadir'} {len(to_add)} periodo(s)."
        if warnings:
            summary += "\n\nRevise estos avisos:\n• " + "\n• ".join(warnings[:15])
            if len(warnings) > 15:
                summary += f"\n• … y {len(warnings) - 15} más."
        if not to_add and not replace:
            info(self, "Importar", summary)
            return
        if not ask(self, "Importar vacaciones.json", summary + "\n\nAntes se hará una copia de seguridad.",
                   yes="Importar", danger=replace):
            return
        if not self._safety_backup("antes_de_importar"):
            return
        kinds = tuple(k for k in EXCEPTION_KINDS if k != EXC_ALT) if replace else ()
        if guarded(self, lambda: self.ctx.db.save_exceptions(to_add, kinds)) is not None:
            self.ctx.db.add_history("info", "calendario", f"Importados {len(to_add)} periodo(s) desde {Path(path).name}.")
            self.ctx.notify_data_changed()
            info(self, "Importar", f"Importación completada: {len(to_add)} periodo(s). Ya están en vigor, sin "
                 "necesidad de reiniciar el programa.")

    def _export_json(self) -> None:
        items = [e for e in self.ctx.db.exceptions() if e.kind != EXC_ALT]
        if not items:
            info(self, "Exportar", "No hay festivos ni vacaciones que exportar.")
            return
        start = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)) / \
            vacaciones.FILE_NAME
        path, _ = QFileDialog.getSaveFileName(self, "Exportar vacaciones y festivos", str(start),
                                              "Calendario de vacaciones (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        bak = guarded(self, lambda: vacaciones.write_file(Path(path), items) or "")
        if bak is None:
            return
        extra = f"\n\nEl archivo anterior se ha conservado como {Path(bak).name}." if bak else ""
        info(self, "Exportar", f"Se han guardado {len(items)} periodo(s) en {path}.{extra}")

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
        if xid is not None and ask(self, "Eliminar excepción", "¿Eliminar esta excepción? Esos días volverán a "
                                   "aplicarse el horario y el apagado habituales.", yes="Eliminar", danger=True):
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
        left.addWidget(help_label("En rojo: días sin sonido. En naranja: días con otro horario. En azul: días en "
                                  "los que solo se suspende el apagado del equipo."))
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
        silent, alt, nooff = QTextCharFormat(), QTextCharFormat(), QTextCharFormat()
        silent.setBackground(QBrush(QColor("#f8c9c5")))
        alt.setBackground(QBrush(QColor("#fde2b8")))
        nooff.setBackground(QBrush(QColor("#cfe3f7")))
        rank = {}
        for e in self.ctx.db.exceptions():
            fmt, level = (silent, 3) if e.silences else (alt, 2) if e.kind == EXC_ALT else (nooff, 1)
            d = max(e.date_from, first)
            last = min(e.date_to, first + timedelta(days=50))
            while d <= last:
                if level > rank.get(d, 0):  # el color de la excepción más restrictiva
                    rank[d] = level
                    self.cal.setDateTextFormat(_qd(d), fmt)
                d += timedelta(days=1)

    def _show_day(self) -> None:
        d = _pd(self.cal.selectedDate())
        sch = self.ctx.engine.scheduler
        plan = sch.day_plan(d)
        self.day_title.setText(long_date(d).capitalize())
        reason = plan.reason
        if self.ctx.settings.apagado_activo:
            dec = shutdown_decision(d, self.ctx.settings, sch.data.exceptions, sch.tz)
            reason += "\n⏻ " + dec.text(sch.tz)
        self.day_reason.setText(reason)
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
            values = (e.name, EXCEPTION_KINDS[e.kind], dates, e.suspended_text(), names.get(e.schedule_id, ""))
            for c, v in enumerate(values):
                it = QTableWidgetItem(v)
                it.setData(Qt.ItemDataRole.UserRole, e.id)
                self.exc_table.setItem(r, c, it)
        pairs = find_overlaps(self.ctx.db.exceptions())
        self.overlap_lbl.setText(("⚠ Periodos solapados (se aplica la opción más restrictiva): " +
                                  "; ".join(describe_overlap(a, b) for a, b in pairs[:4]) +
                                  (" …" if len(pairs) > 4 else "")) if pairs else "")
        self.overlap_lbl.setVisible(bool(pairs))
        self.oneoff.fill(self.ctx.db.events(one_off=True), self.ctx.db)
        self._paint_calendar()
        self._show_day()
