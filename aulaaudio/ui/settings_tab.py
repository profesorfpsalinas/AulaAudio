"""Pestaña Configuración."""
from __future__ import annotations

from zoneinfo import available_timezones

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import demo, sounds, system
from ..config import DEVICE_FALLBACK_DEFAULT, DEVICE_FALLBACK_NONE
from .common import AppContext, ask, error, guarded, help_label, info


class SettingsTab(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        lay = QVBoxLayout(body)

        # ---------------- audio
        g = QGroupBox("Audio")
        f = QFormLayout(g)
        f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        dev_row = QHBoxLayout()
        self.device = QComboBox()
        self.device.setMinimumWidth(320)
        dev_row.addWidget(self.device, 1)
        b = QPushButton("Actualizar lista")
        b.clicked.connect(self._fill_devices)
        dev_row.addWidget(b)
        f.addRow("Dispositivo de salida:", dev_row)
        self.device_now = QLabel()
        f.addRow("En uso ahora:", self.device_now)
        self.fallback = QComboBox()
        self.fallback.addItem("Usar el dispositivo predeterminado del sistema y avisar", DEVICE_FALLBACK_DEFAULT)
        self.fallback.addItem("No reproducir y avisar", DEVICE_FALLBACK_NONE)
        f.addRow("Si el dispositivo elegido no está conectado:", self.fallback)
        vol = QHBoxLayout()
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.vol_lbl = QLabel()
        self.volume.valueChanged.connect(lambda v: self.vol_lbl.setText(f"{v} %"))
        vol.addWidget(self.volume, 1)
        vol.addWidget(self.vol_lbl)
        f.addRow("Volumen general:", vol)
        self.fade = QSpinBox()
        self.fade.setRange(0, 15)
        self.fade.setSuffix(" s")
        f.addRow("Fundido al terminar la música por hora:", self.fade)
        b = QPushButton("🔊 Prueba de sonido")
        b.clicked.connect(self._test)
        f.addRow("", b)
        f.addRow("", help_label("AulaAudio solo ajusta su propio volumen; no cambia el volumen general de Windows "
                                "o Linux. Si no oye nada, compruebe también el volumen del sistema y del amplificador."))
        lay.addWidget(g)

        # ---------------- automatización
        g = QGroupBox("Automatización")
        f = QFormLayout(g)
        f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        self.auto = QCheckBox("Reproducir automáticamente los eventos programados")
        f.addRow(self.auto)
        self.margin = QSpinBox()
        self.margin.setRange(5, 600)
        self.margin.setSuffix(" s")
        f.addRow("Retraso máximo admitido:", self.margin)
        f.addRow("", help_label("Si por un bloqueo o una suspensión un evento se detecta más tarde de este margen, "
                                "no se reproduce con retraso (se anota en el historial)."))
        self.manual_prio = QSpinBox()
        self.manual_prio.setRange(1, 10)
        f.addRow("Prioridad de la reproducción manual:", self.manual_prio)
        f.addRow("", help_label("Los eventos programados con prioridad igual o mayor (p. ej. timbres, 8) "
                                "interrumpen la reproducción manual. La música programada (3) no."))
        self.tz = QComboBox()
        self.tz.setEditable(False)
        for z in sorted(available_timezones()):
            if "/" in z and not z.startswith(("Etc/", "SystemV/")):
                self.tz.addItem(z)
        f.addRow("Zona horaria:", self.tz)
        lay.addWidget(g)

        # ---------------- sistema
        g = QGroupBox("Inicio y funcionamiento")
        f = QFormLayout(g)
        f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        self.autostart = QCheckBox("Abrir AulaAudio al iniciar sesión en este equipo")
        f.addRow(self.autostart)
        self.start_min = QCheckBox("Arrancar minimizado (en la bandeja del sistema)")
        f.addRow(self.start_min)
        self.tray = QCheckBox("Al cerrar la ventana, seguir funcionando en la bandeja del sistema")
        f.addRow(self.tray)
        self.sleep = QCheckBox("Impedir que el equipo se suspenda por inactividad mientras AulaAudio está abierto")
        f.addRow(self.sleep)
        if not (ctx.sleep_inhibitor and ctx.sleep_inhibitor.supported):
            self.sleep.setEnabled(False)
            f.addRow("", help_label("En Linux, configure la suspensión desde los ajustes de energía del escritorio."))
        lay.addWidget(g)

        # ---------------- datos
        g = QGroupBox("Datos")
        f = QFormLayout(g)
        f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        p = ctx.paths
        for label, folder in (("Configuración:", p.config_dir), ("Base de datos:", p.data_dir),
                              ("Copias de seguridad:", p.backup_dir), ("Registros:", p.log_dir)):
            row = QHBoxLayout()
            lbl = QLabel(str(folder))
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(lbl, 1)
            b = QPushButton("Abrir")
            b.clicked.connect(lambda _=False, d=folder: QDesktopServices.openUrl(QUrl.fromLocalFile(str(d))))
            row.addWidget(b)
            f.addRow(label, row)
        self.hist_days = QSpinBox()
        self.hist_days.setRange(7, 3650)
        self.hist_days.setSuffix(" días")
        f.addRow("Conservar el historial:", self.hist_days)
        self.auto_backup = QCheckBox("Hacer una copia de seguridad automática cada día")
        f.addRow(self.auto_backup)
        self.keep = QSpinBox()
        self.keep.setRange(1, 365)
        f.addRow("Copias automáticas a conservar:", self.keep)
        demo_row = QHBoxLayout()
        b = QPushButton("Cargar datos de ejemplo")
        b.clicked.connect(self._load_demo)
        demo_row.addWidget(b)
        b = QPushButton("Eliminar datos de ejemplo")
        b.setObjectName("danger")
        b.clicked.connect(self._delete_demo)
        demo_row.addWidget(b)
        demo_row.addStretch(1)
        f.addRow("Ejemplos:", demo_row)
        lay.addWidget(g)

        save = QHBoxLayout()
        save.addStretch(1)
        b = QPushButton("Descartar cambios")
        b.clicked.connect(self.load)
        save.addWidget(b)
        b = QPushButton("Guardar cambios")
        b.setObjectName("primary")
        b.clicked.connect(self._save)
        save.addWidget(b)
        outer.addLayout(save)

        ctx.backend.devices_changed.connect(self._fill_devices)
        ctx.settings_changed.connect(self.load)
        self.load()

    def _fill_devices(self) -> None:
        current = self.ctx.settings.dispositivo_id
        self.device.clear()
        self.device.addItem("Predeterminado del sistema", "")
        for d in self.ctx.backend.devices():
            self.device.addItem(d.name + ("  (predeterminado)" if d.is_default else ""), d.id)
        idx = self.device.findData(current)
        if idx < 0 and current:
            self.device.addItem(f"⚠ {self.ctx.settings.dispositivo_nombre or 'Dispositivo elegido'} (no conectado)", current)
            idx = self.device.count() - 1
        self.device.setCurrentIndex(max(0, idx))
        problem = self.ctx.backend.device_problem()
        self.device_now.setText(("⚠ " + problem) if problem else self.ctx.backend.current_device_name())

    def load(self) -> None:
        s = self.ctx.settings
        self._fill_devices()
        self.fallback.setCurrentIndex(max(0, self.fallback.findData(s.si_falta_dispositivo)))
        self.volume.setValue(s.volumen_general)
        self.vol_lbl.setText(f"{s.volumen_general} %")
        self.fade.setValue(s.fundido_salida_segundos)
        self.auto.setChecked(s.automatizacion_activa)
        self.margin.setValue(s.margen_retraso_segundos)
        self.manual_prio.setValue(s.prioridad_manual)
        self.tz.setCurrentIndex(max(0, self.tz.findText(s.zona_horaria)))
        try:
            self.autostart.setChecked(system.is_autostart_enabled())
        except OSError:
            self.autostart.setChecked(False)
        self.start_min.setChecked(s.iniciar_minimizado)
        self.tray.setChecked(s.minimizar_a_bandeja)
        self.sleep.setChecked(s.impedir_suspension)
        self.hist_days.setValue(s.dias_historial)
        self.auto_backup.setChecked(s.copia_automatica)
        self.keep.setValue(s.copias_automaticas_a_conservar)

    def _save(self) -> None:
        s = self.ctx.settings
        if s.automatizacion_activa and not self.auto.isChecked():
            if not ask(self, "Desactivar automatización", "Con la automatización desactivada no sonarán los timbres "
                       "ni la música programados. ¿Guardar así?", yes="Guardar", danger=True):
                return
        s.dispositivo_id = self.device.currentData() or ""
        s.dispositivo_nombre = self.device.currentText().split("  (")[0] if s.dispositivo_id else ""
        s.si_falta_dispositivo = self.fallback.currentData()
        s.volumen_general = self.volume.value()
        s.fundido_salida_segundos = self.fade.value()
        if s.automatizacion_activa != self.auto.isChecked():
            self.ctx.engine.set_automation(self.auto.isChecked())
        s.margen_retraso_segundos = self.margin.value()
        s.prioridad_manual = self.manual_prio.value()
        s.zona_horaria = self.tz.currentText() or s.zona_horaria
        s.iniciar_minimizado = self.start_min.isChecked()
        s.minimizar_a_bandeja = self.tray.isChecked()
        s.impedir_suspension = self.sleep.isChecked()
        s.dias_historial = self.hist_days.value()
        s.copia_automatica = self.auto_backup.isChecked()
        s.copias_automaticas_a_conservar = self.keep.value()
        try:
            if self.autostart.isChecked() != system.is_autostart_enabled():
                system.set_autostart(self.autostart.isChecked())
        except OSError as exc:
            error(self, "Inicio automático", f"No se ha podido cambiar el inicio automático: {exc}")
        if self.ctx.save_settings():
            self.ctx.engine.reload()
            info(self, "Configuración", "Cambios guardados.")
        else:
            error(self, "Configuración", "No se ha podido guardar la configuración en el disco. "
                  "Compruebe el espacio libre y los permisos de la carpeta de configuración.")

    def _test(self) -> None:
        path = guarded(self, lambda: sounds.test_sound(self.ctx.paths.data_dir))
        if path and not self.ctx.engine.play_file_test(str(path)):
            msg = self.ctx.engine.last_incident[1] if self.ctx.engine.last_incident else ""
            error(self, "Prueba de sonido", "No se ha podido reproducir el sonido de prueba.\n" + msg)

    def _load_demo(self) -> None:
        if ask(self, "Datos de ejemplo", "Se añadirán eventos, una lista y sonidos de ejemplo marcados como "
               "[EJEMPLO]. Los eventos se crean DESACTIVADOS: revíselos y active los que quiera. ¿Continuar?"):
            if guarded(self, lambda: demo.load_demo(self.ctx.db, self.ctx.paths.demo_sounds_dir)) is not False:
                self.ctx.notify_data_changed()

    def _delete_demo(self) -> None:
        if not self.ctx.db.has_demo_data():
            info(self, "Datos de ejemplo", "No hay datos de ejemplo.")
            return
        if ask(self, "Eliminar datos de ejemplo", "Se eliminarán todos los eventos, listas y pistas marcados como "
               "ejemplo. Sus propios datos no se tocan. ¿Continuar?", yes="Eliminar", danger=True):
            guarded(self, self.ctx.db.delete_demo_data)
            self.ctx.notify_data_changed()
