"""Pestaña Inicio: estado, reloj, próximo evento, lo que suena y controles grandes."""
from __future__ import annotations

from datetime import timedelta

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QRadioButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .. import sounds
from ..models import KINDS, fmt_hhmm
from .common import AppContext, ask, big_button, card, error, guarded, help_label, long_date
from .style import STATUS_COLORS


def describe_wait(delta: timedelta) -> str:
    mins = int(delta.total_seconds() // 60)
    if mins < 1:
        return "en menos de un minuto"
    if mins < 60:
        return f"dentro de {mins} min"
    h, m = divmod(mins, 60)
    if h < 24:
        return f"dentro de {h} h {m:02d} min"
    return f"dentro de {h // 24} días"


class PlaySourceDialog(QDialog):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reproducir ahora")
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        lay.addWidget(help_label("Elija qué quiere reproducir. La reproducción manual no se reanuda sola "
                                 "si la interrumpe un timbre o un aviso."))
        self.rb_pl = QRadioButton("Una lista de reproducción")
        self.rb_tr = QRadioButton("Un archivo de la biblioteca")
        self.cb_pl, self.cb_tr = QComboBox(), QComboBox()
        for pl in ctx.db.playlists():
            self.cb_pl.addItem(pl.name, pl.id)
        for t in ctx.db.tracks():
            self.cb_tr.addItem(t.title, t.id)
        form = QFormLayout()
        form.addRow(self.rb_pl, self.cb_pl)
        form.addRow(self.rb_tr, self.cb_tr)
        lay.addLayout(form)
        (self.rb_pl if self.cb_pl.count() else self.rb_tr).setChecked(True)
        bb = QDialogButtonBox()
        bb.addButton("Reproducir", QDialogButtonBox.ButtonRole.AcceptRole)
        bb.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def choice(self):
        if self.rb_pl.isChecked() and self.cb_pl.count():
            return self.cb_pl.currentText(), None, self.cb_pl.currentData()
        if self.rb_tr.isChecked() and self.cb_tr.count():
            return self.cb_tr.currentText(), self.cb_tr.currentData(), None
        return None


class HomeTab(QWidget):
    go_schedule = Signal()
    go_library = Signal()

    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        eng = ctx.engine
        root = QVBoxLayout(self)
        root.setSpacing(12)

        # estado
        top = QHBoxLayout()
        self.status = QLabel()
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        top.addWidget(self.status, 1)
        self.btn_ack = QPushButton("Entendido")
        self.btn_ack.setToolTip("Marcar la incidencia como vista (sigue en el historial)")
        self.btn_ack.clicked.connect(eng.acknowledge_incident)
        top.addWidget(self.btn_ack)
        self.btn_auto = QPushButton()
        self.btn_auto.setMinimumHeight(44)
        self.btn_auto.clicked.connect(self._toggle_automation)
        top.addWidget(self.btn_auto)
        root.addLayout(top)

        # reloj y eventos
        mid = QHBoxLayout()
        c1 = card()
        l1 = QVBoxLayout(c1)
        self.clock = QLabel()
        self.clock.setObjectName("clock")
        self.date = QLabel()
        self.date.setObjectName("date")
        l1.addWidget(self.clock)
        l1.addWidget(self.date)
        mid.addWidget(c1, 1)
        c2 = card()
        l2 = QVBoxLayout(c2)
        lbl = QLabel("Próximo evento")
        lbl.setObjectName("section")
        l2.addWidget(lbl)
        self.next_lbl = QLabel()
        self.next_lbl.setObjectName("big")
        self.next_lbl.setWordWrap(True)
        l2.addWidget(self.next_lbl)
        lbl = QLabel("Sonando ahora")
        lbl.setObjectName("section")
        l2.addWidget(lbl)
        self.now_lbl = QLabel()
        self.now_lbl.setObjectName("big")
        self.now_lbl.setWordWrap(True)
        l2.addWidget(self.now_lbl)
        mid.addWidget(c2, 2)
        root.addLayout(mid)

        # eventos en curso no iniciados al arrancar
        self.missed_box = card()
        lm = QHBoxLayout(self.missed_box)
        self.missed_lbl = QLabel()
        self.missed_lbl.setWordWrap(True)
        lm.addWidget(self.missed_lbl, 1)
        self.btn_missed = QPushButton("Iniciar ahora")
        self.btn_missed.clicked.connect(self._start_missed)
        lm.addWidget(self.btn_missed)
        root.addWidget(self.missed_box)

        # controles
        controls = QHBoxLayout()
        self.btn_play = big_button("▶  Reproducir…", "play")
        self.btn_pause = big_button("❚❚  Pausar")
        self.btn_resume = big_button("▶  Reanudar")
        self.btn_stop = big_button("■  Detener", "stop")
        for b in (self.btn_play, self.btn_pause, self.btn_resume, self.btn_stop):
            controls.addWidget(b)
        self.btn_play.clicked.connect(self._play)
        self.btn_pause.clicked.connect(eng.pause)
        self.btn_resume.clicked.connect(eng.resume)
        self.btn_stop.clicked.connect(eng.stop)
        root.addLayout(controls)

        vol = QHBoxLayout()
        vol.addWidget(QLabel("Volumen general:"))
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(ctx.settings.volumen_general)
        self.slider.setAccessibleName("Volumen general")
        self.vol_lbl = QLabel(f"{ctx.settings.volumen_general} %")
        self.vol_lbl.setMinimumWidth(50)
        self.slider.valueChanged.connect(self._volume_changed)
        self._vol_save = QTimer(self)
        self._vol_save.setSingleShot(True)
        self._vol_save.setInterval(800)
        self._vol_save.timeout.connect(ctx.save_settings)
        vol.addWidget(self.slider, 1)
        vol.addWidget(self.vol_lbl)
        self.btn_test = QPushButton("🔊 Prueba de sonido")
        self.btn_test.clicked.connect(self._test_sound)
        vol.addWidget(self.btn_test)
        root.addLayout(vol)
        self.device_lbl = help_label("")
        root.addWidget(self.device_lbl)

        bottom = QHBoxLayout()
        upc = QVBoxLayout()
        lbl = QLabel("Próximas 24 horas")
        lbl.setObjectName("section")
        upc.addWidget(lbl)
        self.upcoming = QListWidget()
        self.upcoming.setAlternatingRowColors(True)
        upc.addWidget(self.upcoming)
        bottom.addLayout(upc, 3)
        nav = QVBoxLayout()
        b1 = big_button("📅  Programación semanal")
        b1.clicked.connect(self.go_schedule)
        b2 = big_button("🎵  Biblioteca de audio")
        b2.clicked.connect(self.go_library)
        nav.addWidget(b1)
        nav.addWidget(b2)
        nav.addStretch(1)
        bottom.addLayout(nav, 1)
        root.addLayout(bottom, 1)

        eng.changed.connect(self.refresh)
        ctx.data_changed.connect(self._refresh_upcoming)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick_clock)
        self._timer.start(1000)
        self._last_upcoming_minute = None
        self.refresh()

    # ----------------------------------------------------------------- refresco
    def _tick_clock(self) -> None:
        now = self.ctx.local_now()
        self.clock.setText(now.strftime("%H:%M:%S"))
        self.date.setText(long_date(now).capitalize())
        minute = now.replace(second=0, microsecond=0)
        if minute != self._last_upcoming_minute:
            self._last_upcoming_minute = minute
            self._refresh_upcoming()
            self._refresh_next()

    def _refresh_next(self) -> None:
        eng = self.ctx.engine
        nxt = eng.next_occurrence()
        if nxt is None:
            self.next_lbl.setText("No hay eventos programados en los próximos días.")
        else:
            loc = eng.scheduler.local(nxt.start_utc)
            day = "hoy" if loc.date() == self.ctx.local_now().date() else long_date(loc)
            wait = describe_wait(nxt.start_utc - self.ctx.clock.now())
            self.next_lbl.setText(f"<b>{fmt_hhmm(loc.time())}</b> ({day}) · {KINDS[nxt.event.kind]}: "
                                  f"{nxt.event.name} — {wait}")

    def _refresh_upcoming(self) -> None:
        eng = self.ctx.engine
        now = self.ctx.clock.now()
        self.upcoming.clear()
        occs = eng.scheduler.occurrences_between(now, now + timedelta(hours=24), include_start=False)
        for o in occs:
            loc = eng.scheduler.local(o.start_utc)
            end = f" → {fmt_hhmm(eng.scheduler.local(o.end_utc).time())}" if o.end_utc else ""
            day = "" if loc.date() == self.ctx.local_now().date() else " (mañana)"
            self.upcoming.addItem(f"{fmt_hhmm(loc.time())}{end}{day}   {KINDS[o.event.kind]} · {o.event.name}")
        if not occs:
            self.upcoming.addItem("No hay nada programado en las próximas 24 horas.")

    def refresh(self) -> None:
        eng, s = self.ctx.engine, self.ctx.settings
        code, text = eng.status()
        bg, fg = STATUS_COLORS[code]
        title = {"funcionando": "● Funcionando", "detenido": "■ Detenido", "incidencia": "▲ Incidencia"}[code]
        self.status.setText(f"{title} — {text}")
        self.status.setStyleSheet(f"background:{bg}; color:{fg}; border:1px solid {fg};")
        self.btn_ack.setVisible(eng.last_incident is not None)
        self.btn_auto.setText("Desactivar automatización" if s.automatizacion_activa else "Activar automatización")
        cur = eng.current
        if cur is None:
            self.now_lbl.setText("Nada.")
        else:
            track = cur.current_track
            extra = f" · hasta las {fmt_hhmm(eng.scheduler.local(cur.end_utc).time())}" if cur.end_utc else ""
            state = " (en pausa)" if cur.paused else ""
            origin = {"auto": "Programado", "manual": "Manual", "prueba": "Prueba"}[cur.kind]
            self.now_lbl.setText(f"<b>{cur.title}</b>{state}<br>{origin}{extra}"
                                 + (f"<br>Pista: {track.title}" if track else ""))
        self.btn_pause.setEnabled(cur is not None and not cur.paused)
        self.btn_resume.setEnabled(cur is not None and cur.paused)
        self.btn_stop.setEnabled(cur is not None or bool(eng.waiting))
        missed = eng.missed_in_progress
        self.missed_box.setVisible(bool(missed))
        if missed:
            o = missed[0]
            end = fmt_hhmm(eng.scheduler.local(o.end_utc).time())
            self.missed_lbl.setText(f"«{o.event.name}» está en su franja horaria (hasta las {end}), pero no se ha "
                                    "iniciado porque AulaAudio se abrió después de su hora de comienzo. "
                                    "Por seguridad no empieza solo.")
        dev = self.ctx.backend.current_device_name()
        self.device_lbl.setText(f"Salida de audio: {dev}")
        self._refresh_next()

    # ----------------------------------------------------------------- acciones
    def _confirm_replace(self) -> bool:
        cur = self.ctx.engine.current
        if cur is None:
            return True
        return ask(self, "Ya está sonando algo", f"Ahora suena «{cur.title}». ¿Quiere detenerlo y reproducir lo nuevo?",
                   yes="Detener y reproducir")

    def _play(self) -> None:
        if not self.ctx.db.playlists() and not self.ctx.db.tracks():
            error(self, "Biblioteca vacía", "Añada primero archivos de audio en la pestaña «Biblioteca de audio».")
            return
        dlg = PlaySourceDialog(self.ctx, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        choice = dlg.choice()
        if choice and self._confirm_replace():
            title, tid, pid = choice
            if not self.ctx.engine.play_manual(title, track_id=tid, playlist_id=pid):
                error(self, "No se puede reproducir", self.ctx.engine.last_incident[1] if self.ctx.engine.last_incident
                      else "No se ha podido iniciar la reproducción.")

    def _test_sound(self) -> None:
        if not self._confirm_replace():
            return
        path = guarded(self, lambda: sounds.test_sound(self.ctx.paths.data_dir))
        if path and not self.ctx.engine.play_file_test(str(path)):
            msg = self.ctx.engine.last_incident[1] if self.ctx.engine.last_incident else ""
            error(self, "Prueba de sonido", "No se ha podido reproducir el sonido de prueba.\n" + msg)

    def _volume_changed(self, v: int) -> None:
        self.vol_lbl.setText(f"{v} %")
        self.ctx.engine.set_master_volume(v)
        self._vol_save.start()

    def _toggle_automation(self) -> None:
        s = self.ctx.settings
        if s.automatizacion_activa:
            if not ask(self, "Desactivar automatización",
                       "Si desactiva la automatización NO sonarán los timbres ni la música programados hasta que "
                       "vuelva a activarla. La programación se conserva. ¿Desactivar?", yes="Desactivar", danger=True):
                return
        self.ctx.engine.set_automation(not s.automatizacion_activa)
        self.ctx.save_settings()

    def _start_missed(self) -> None:
        missed = self.ctx.engine.missed_in_progress
        if missed and self._confirm_replace():
            self.ctx.engine.start_missed(missed[0])
