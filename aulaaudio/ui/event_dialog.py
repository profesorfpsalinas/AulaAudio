"""Formulario para crear o editar un evento."""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from datetime import time as _t

from PySide6.QtCore import QDate, Qt, QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from .. import library
from ..audio import SUPPORTED_EXTENSIONS
from ..models import (
    CONFLICTS,
    DAY_NAMES,
    DEFAULT_PRIORITY,
    END_AUDIO,
    END_DURATION,
    END_MODES,
    END_TIME,
    KIND_MUSIC,
    KINDS,
    Event,
    ValidationError,
)
from .common import AppContext, error, guarded, help_label

AUDIO_FILTER = "Audio (" + " ".join("*" + e for e in sorted(SUPPORTED_EXTENSIONS)) + ")"


def _qtime(t) -> QTime:
    return QTime(t.hour, t.minute)


class EventDialog(QDialog):
    def __init__(self, ctx: AppContext, event: Event, parent=None, title: str = "Evento"):
        super().__init__(parent)
        self.ctx = ctx
        # Ojo: no llamarlo «self.event», que taparía el método QWidget.event() de Qt.
        self.ev = replace(event)
        self.setWindowTitle(title)
        self.setMinimumWidth(620)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.name = QLineEdit(event.name)
        self.name.setMaxLength(100)
        self.name.setPlaceholderText("Por ejemplo: Música del recreo")
        form.addRow("Nombre:", self.name)

        self.kind = QComboBox()
        for k, v in KINDS.items():
            self.kind.addItem(v, k)
        self.kind.setCurrentIndex(list(KINDS).index(event.kind))
        self.kind.currentIndexChanged.connect(self._kind_changed)
        form.addRow("Tipo:", self.kind)

        # cuándo
        when = QWidget()
        wl = QVBoxLayout(when)
        wl.setContentsMargins(0, 0, 0, 0)
        self.rb_weekly = QRadioButton("Cada semana, los días:")
        self.rb_date = QRadioButton("Solo en una fecha concreta (evento extraordinario):")
        wl.addWidget(self.rb_weekly)
        days = QHBoxLayout()
        self.day_checks = []
        for i, n in enumerate(DAY_NAMES):
            cb = QCheckBox(n.capitalize()[:3])
            cb.setToolTip(n.capitalize())
            cb.setChecked(i in event.days)
            self.day_checks.append(cb)
            days.addWidget(cb)
        b_lv = QPushButton("L-V")
        b_lv.setToolTip("Marcar de lunes a viernes")
        b_lv.clicked.connect(lambda: [c.setChecked(i < 5) for i, c in enumerate(self.day_checks)])
        days.addWidget(b_lv)
        days.addStretch(1)
        wl.addLayout(days)
        wl.addWidget(self.rb_date)
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd/MM/yyyy")
        d = event.date or ctx.local_now().date()
        self.date.setDate(QDate(d.year, d.month, d.day))
        wl.addWidget(self.date)
        (self.rb_date if event.date else self.rb_weekly).setChecked(True)
        self.rb_weekly.toggled.connect(self._update_enabled)
        form.addRow("Cuándo:", when)

        self.start = QTimeEdit(_qtime(event.start))
        self.start.setDisplayFormat("HH:mm")
        form.addRow("Hora de inicio:", self.start)

        # fin
        endw = QWidget()
        el = QHBoxLayout(endw)
        el.setContentsMargins(0, 0, 0, 0)
        self.end_mode = QComboBox()
        for k, v in END_MODES.items():
            self.end_mode.addItem(v, k)
        self.end_mode.setCurrentIndex(list(END_MODES).index(event.end_mode))
        self.end_mode.currentIndexChanged.connect(self._update_enabled)
        self.duration = QSpinBox()
        self.duration.setRange(1, 720)
        self.duration.setSuffix(" min")
        self.duration.setValue(event.duration_min or 15)
        self.end_time = QTimeEdit(_qtime(event.end_time) if event.end_time else self.start.time().addSecs(1800))
        self.end_time.setDisplayFormat("HH:mm")
        el.addWidget(self.end_mode)
        el.addWidget(self.duration)
        el.addWidget(self.end_time)
        el.addStretch(1)
        form.addRow("Finaliza:", endw)
        self.end_help = help_label("")
        form.addRow("", self.end_help)

        # audio
        srcw = QWidget()
        sl = QVBoxLayout(srcw)
        sl.setContentsMargins(0, 0, 0, 0)
        self.rb_track = QRadioButton("Un archivo:")
        self.rb_pl = QRadioButton("Una lista de reproducción:")
        r1, r2 = QHBoxLayout(), QHBoxLayout()
        self.cb_track = QComboBox()
        self.cb_pl = QComboBox()
        self._fill_sources()
        btn_browse = QPushButton("Examinar…")
        btn_browse.setToolTip("Añadir un archivo a la biblioteca y elegirlo")
        btn_browse.clicked.connect(self._browse)
        r1.addWidget(self.rb_track)
        r1.addWidget(self.cb_track, 1)
        r1.addWidget(btn_browse)
        r2.addWidget(self.rb_pl)
        r2.addWidget(self.cb_pl, 1)
        sl.addLayout(r1)
        sl.addLayout(r2)
        want_pl = event.playlist_id is not None or (event.track_id is None and event.kind == KIND_MUSIC)
        (self.rb_pl if want_pl and self.cb_pl.count() else self.rb_track).setChecked(True)
        self._update_sources()
        form.addRow("Audio:", srcw)

        volw = QWidget()
        vl = QHBoxLayout(volw)
        vl.setContentsMargins(0, 0, 0, 0)
        self.vol_on = QCheckBox("Volumen propio:")
        self.vol_on.setChecked(event.volume is not None)
        self.vol = QSlider(Qt.Orientation.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(event.volume if event.volume is not None else 100)
        self.vol_lbl = QLabel()
        self.vol.valueChanged.connect(lambda v: self.vol_lbl.setText(f"{v} % del general"))
        self.vol_lbl.setText(f"{self.vol.value()} % del general")
        self.vol_on.toggled.connect(self._update_enabled)
        vl.addWidget(self.vol_on)
        vl.addWidget(self.vol, 1)
        vl.addWidget(self.vol_lbl)
        form.addRow("Volumen:", volw)

        self.priority = QSpinBox()
        self.priority.setRange(1, 10)
        self.priority.setValue(event.priority)
        form.addRow("Prioridad (1-10):", self.priority)
        form.addRow("", help_label("Mayor número = más importante. Recomendado: música 3, avisos 6, timbres 8."))
        self.conflict = QComboBox()
        for k, v in CONFLICTS.items():
            self.conflict.addItem(v, k)
        self.conflict.setCurrentIndex(list(CONFLICTS).index(event.conflict))
        form.addRow("Si ya suena algo:", self.conflict)
        self.resume = QCheckBox("Si lo interrumpe otro evento, reanudarlo después (solo dentro de su franja horaria)")
        self.resume.setChecked(event.resume)
        form.addRow("", self.resume)
        self.enabled = QCheckBox("Evento activo")
        self.enabled.setChecked(event.enabled)
        form.addRow("", self.enabled)
        lay.addLayout(form)

        bb = QDialogButtonBox()
        bb.addButton("Guardar", QDialogButtonBox.ButtonRole.AcceptRole)
        bb.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._update_enabled()

    def _fill_sources(self, select_track: int | None = None) -> None:
        self.cb_track.clear()
        self.cb_pl.clear()
        for t in self.ctx.db.tracks():
            mark = "" if t.status == "ok" else "  ⚠ falta" if t.status == "falta" else "  ⚠ error"
            self.cb_track.addItem(t.title + mark, t.id)
        for pl in self.ctx.db.playlists():
            self.cb_pl.addItem(pl.name, pl.id)
        tid = select_track if select_track is not None else self.ev.track_id
        if tid is not None and self.cb_track.findData(tid) >= 0:
            self.cb_track.setCurrentIndex(self.cb_track.findData(tid))
        if self.ev.playlist_id is not None and self.cb_pl.findData(self.ev.playlist_id) >= 0:
            self.cb_pl.setCurrentIndex(self.cb_pl.findData(self.ev.playlist_id))

    def _update_sources(self) -> None:
        """Si no hay listas, la opción «lista» no se puede elegir (y se dice por qué)."""
        has_pl = self.cb_pl.count() > 0
        self.rb_pl.setEnabled(has_pl)
        self.cb_pl.setEnabled(has_pl)
        self.cb_pl.setPlaceholderText("" if has_pl else "(no hay listas: créelas en «Biblioteca de audio»)")
        self.cb_track.setPlaceholderText("" if self.cb_track.count() else "(biblioteca vacía: pulse «Examinar…»)")
        if not has_pl and self.rb_pl.isChecked():
            self.rb_track.setChecked(True)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Elegir archivo de audio", "", AUDIO_FILTER)
        if not path:
            return
        res = guarded(self, lambda: library.add_files(self.ctx.db, [path]))
        if res is None:
            return
        if res.rejected:
            error(self, "Archivo no válido", "Ese archivo no es un formato de audio admitido.")
            return
        t = self.ctx.db.track_by_path(library.normalize(path))
        self._fill_sources(select_track=t.id)
        self._update_sources()
        self.rb_track.setChecked(True)
        self.ctx.data_changed.emit()

    def _kind_changed(self) -> None:
        kind = self.kind.currentData()
        self.priority.setValue(DEFAULT_PRIORITY[kind])
        if kind == KIND_MUSIC:
            (self.rb_pl if self.cb_pl.count() else self.rb_track).setChecked(True)
            self.resume.setChecked(True)
            self.conflict.setCurrentIndex(list(CONFLICTS).index("esperar"))
            if self.end_mode.currentData() == END_AUDIO:
                self.end_mode.setCurrentIndex(list(END_MODES).index(END_TIME))
        else:
            self.rb_track.setChecked(True)
            self.resume.setChecked(False)
            self.conflict.setCurrentIndex(list(CONFLICTS).index("interrumpir"))
            self.end_mode.setCurrentIndex(list(END_MODES).index(END_AUDIO))

    def _update_enabled(self) -> None:
        weekly = self.rb_weekly.isChecked()
        for c in self.day_checks:
            c.setEnabled(weekly)
        self.date.setEnabled(not weekly)
        mode = self.end_mode.currentData()
        self.duration.setVisible(mode == END_DURATION)
        self.end_time.setVisible(mode == END_TIME)
        self.end_help.setText({
            END_AUDIO: "Suena una vez hasta que termina el archivo o la lista (sin repetir).",
            END_DURATION: "Suena durante el tiempo indicado; las listas con «repetir» vuelven a empezar.",
            END_TIME: "Suena hasta esa hora. Si es anterior a la de inicio, termina al día siguiente.",
        }[mode])
        self.vol.setEnabled(self.vol_on.isChecked())

    def _build(self) -> Event:
        ev = self.ev
        ev.name = self.name.text()
        ev.kind = self.kind.currentData()
        if self.rb_weekly.isChecked():
            ev.date = None
            ev.days = frozenset(i for i, c in enumerate(self.day_checks) if c.isChecked())
            if ev.schedule_id is None:
                ev.schedule_id = self.ctx.db.default_schedule_id()
        else:
            q = self.date.date()
            ev.date = date(q.year(), q.month(), q.day())
            ev.days = frozenset()
        st = self.start.time()
        ev.start = _t(st.hour(), st.minute())
        ev.end_mode = self.end_mode.currentData()
        ev.duration_min = self.duration.value() if ev.end_mode == END_DURATION else None
        et = self.end_time.time()
        ev.end_time = _t(et.hour(), et.minute()) if ev.end_mode == END_TIME else None
        if self.rb_track.isChecked():
            ev.track_id, ev.playlist_id = self.cb_track.currentData(), None
        else:
            ev.track_id, ev.playlist_id = None, self.cb_pl.currentData()
        ev.volume = self.vol.value() if self.vol_on.isChecked() else None
        ev.priority = self.priority.value()
        ev.conflict = self.conflict.currentData()
        ev.resume = self.resume.isChecked()
        ev.enabled = self.enabled.isChecked()
        return ev

    def _accept(self) -> None:
        if self.cb_track.count() == 0 and self.cb_pl.count() == 0:
            error(self, "Falta el audio", "La biblioteca de audio está vacía. Pulse «Examinar…» junto a "
                  "«Un archivo» para elegir el sonido de este evento.")
            return
        try:
            self._build().validate()
        except ValidationError as exc:
            error(self, "Revise los datos", str(exc))
            return
        self.accept()

    def result_event(self) -> Event:
        return self.ev
