"""Ventana principal, icono de la bandeja del sistema y asistente de primera ejecución."""
from __future__ import annotations

from dataclasses import fields

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMenu,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, __version__, demo
from .backup_tab import BackupTab
from .calendar_tab import CalendarTab
from .common import AppContext, ask, guarded, info
from .history_tab import HistoryTab
from .home import HomeTab
from .library_tab import LibraryTab
from .schedule_tab import ScheduleTab
from .settings_tab import SettingsTab


def make_icon_pixmap(size: int = 256, color: str = "#0b63b6") -> QPixmap:
    """Dibuja el icono (campana sobre círculo) sin depender de archivos externos."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(size * 0.03, size * 0.03, size * 0.94, size * 0.94))
    s = size / 100.0
    bell = QPainterPath()
    bell.moveTo(QPointF(50 * s, 18 * s))
    bell.cubicTo(QPointF(68 * s, 18 * s), QPointF(72 * s, 34 * s), QPointF(72 * s, 50 * s))
    bell.lineTo(QPointF(79 * s, 68 * s))
    bell.lineTo(QPointF(21 * s, 68 * s))
    bell.lineTo(QPointF(28 * s, 50 * s))
    bell.cubicTo(QPointF(28 * s, 34 * s), QPointF(32 * s, 18 * s), QPointF(50 * s, 18 * s))
    p.setBrush(QColor("white"))
    p.drawPath(bell)
    p.drawEllipse(QRectF(42 * s, 70 * s, 16 * s, 12 * s))
    p.end()
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for sz in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(make_icon_pixmap(sz))
    return icon


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext, simulated: bool = False):
        super().__init__()
        self.ctx = ctx
        self._really_quit = False
        self.setWindowTitle(f"{APP_NAME} {__version__}" + (" — MODO SIMULACIÓN" if simulated else ""))
        self.setWindowIcon(app_icon())
        self.resize(1180, 800)
        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(10, 10, 10, 10)
        if simulated:
            banner = QLabel("MODO SIMULACIÓN: el reloj es virtual. Use este modo solo para pruebas.")
            banner.setObjectName("simbanner")
            banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(banner)
        self.tabs = QTabWidget()
        self.home = HomeTab(ctx)
        self.schedule = ScheduleTab(ctx)
        self.library = LibraryTab(ctx)
        self.calendar = CalendarTab(ctx)
        self.settings_tab = SettingsTab(ctx)
        self.history = HistoryTab(ctx)
        self.backups = BackupTab(ctx, self._after_restore)
        for w, name in ((self.home, "Inicio"), (self.schedule, "Programación"), (self.library, "Biblioteca de audio"),
                        (self.calendar, "Calendario y excepciones"), (self.settings_tab, "Configuración"),
                        (self.history, "Historial e incidencias"), (self.backups, "Copias de seguridad")):
            self.tabs.addTab(w, name)
        self.home.go_schedule.connect(lambda: self._go(self.schedule, sub=1))
        self.home.go_library.connect(lambda: self.tabs.setCurrentWidget(self.library))
        lay.addWidget(self.tabs)
        self.setCentralWidget(central)
        self.statusBar().showMessage("Listo")
        self._setup_tray()
        ctx.engine.incident.connect(self._on_incident)
        ctx.engine.changed.connect(self._update_tray)

    def _go(self, widget, sub: int | None = None) -> None:
        self.tabs.setCurrentWidget(widget)
        if sub is not None and hasattr(widget, "subtabs"):
            widget.subtabs.setCurrentIndex(sub)

    # ----------------------------------------------------------------- bandeja
    def _setup_tray(self) -> None:
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(app_icon(), self)
        menu = QMenu()
        a_show = QAction("Mostrar AulaAudio", menu)
        a_show.triggered.connect(self.show_normal)
        a_stop = QAction("Detener la reproducción", menu)
        a_stop.triggered.connect(self.ctx.engine.stop)
        a_quit = QAction("Salir de AulaAudio…", menu)
        a_quit.triggered.connect(self.request_quit)
        menu.addAction(a_show)
        menu.addAction(a_stop)
        menu.addSeparator()
        menu.addAction(a_quit)
        self._tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_normal()
                                    if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                                                  QSystemTrayIcon.ActivationReason.DoubleClick) else None)
        self.tray.show()
        self._update_tray()

    def _update_tray(self) -> None:
        if self.tray is None:
            return
        code, text = self.ctx.engine.status()
        cur = self.ctx.engine.current
        playing = f"\nSonando: {cur.title}" if cur else ""
        label = {"funcionando": "Funcionando", "detenido": "Automatización desactivada", "incidencia": "Incidencia"}[code]
        self.tray.setToolTip(f"AulaAudio — {label}{playing}"[:127])

    def show_normal(self) -> None:
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()

    def _on_incident(self, level: str, message: str) -> None:
        self.statusBar().showMessage(message, 15000)
        if self.tray is not None and level == "error" and not self.isVisible():
            self.tray.showMessage("AulaAudio: incidencia", message[:250], QSystemTrayIcon.MessageIcon.Warning, 10000)

    # ----------------------------------------------------------------- cierre
    def closeEvent(self, event) -> None:
        if self._really_quit:
            event.accept()
            return
        if self.tray is not None and self.ctx.settings.minimizar_a_bandeja:
            event.ignore()
            self.hide()
            if not self.ctx.settings.aviso_bandeja_mostrado:
                self.tray.showMessage("AulaAudio sigue funcionando",
                                      "La programación continúa. Para salir, use el menú del icono de la bandeja.",
                                      QSystemTrayIcon.MessageIcon.Information, 8000)
                self.ctx.settings.aviso_bandeja_mostrado = True
                self.ctx.save_settings()
            return
        event.ignore()
        self.request_quit()

    def request_quit(self) -> None:
        self.show_normal()
        if ask(self, "Salir de AulaAudio", "Si sale de AulaAudio NO sonarán los timbres ni la música programados "
               "hasta que vuelva a abrirlo. ¿Salir?", yes="Salir", danger=True):
            self._really_quit = True
            if self.tray is not None:
                self.tray.hide()
            QApplication.instance().quit()

    # ----------------------------------------------------------------- restauración
    def _after_restore(self) -> None:
        fresh = self.ctx.config_store.load()
        for f in fields(fresh):  # se actualiza el mismo objeto que comparten motor e interfaz
            setattr(self.ctx.settings, f.name, getattr(fresh, f.name))
        self.ctx.engine.apply_settings(self.ctx.settings)
        self.ctx.notify_data_changed()
        self.ctx.settings_changed.emit()

    # ----------------------------------------------------------------- primera ejecución
    def first_run(self) -> None:
        s = self.ctx.settings
        if s.primera_ejecucion_completada:
            return
        load = ask(self, "Bienvenida a AulaAudio",
                   "AulaAudio reproduce automáticamente la música, los timbres y los avisos del centro.\n\n"
                   "Pasos recomendados:\n"
                   "1. Conecte el equipo de sonido y pulse «Prueba de sonido» en Inicio.\n"
                   "2. Añada su música y sus timbres en «Biblioteca de audio».\n"
                   "3. Cree los eventos en «Programación» y los festivos en «Calendario».\n"
                   "4. Compruebe el resultado en «Calendario → Simulación».\n\n"
                   "¿Quiere cargar un horario de ejemplo para empezar? Los eventos de ejemplo se crean "
                   "DESACTIVADOS y se pueden borrar después.",
                   yes="Cargar ejemplos", no="Empezar vacío")
        if load:
            guarded(self, lambda: demo.load_demo(self.ctx.db, self.ctx.paths.demo_sounds_dir))
            self.ctx.notify_data_changed()
            info(self, "Ejemplos cargados", "Revise los eventos [EJEMPLO] en «Programación» y active los que quiera.")
        s.primera_ejecucion_completada = True
        self.ctx.save_settings()
