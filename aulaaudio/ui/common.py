"""Contexto compartido de la interfaz y utilidades de diálogo."""
from __future__ import annotations

import logging
from datetime import datetime

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from ..db import DatabaseError
from ..models import DAY_NAMES, MONTH_NAMES, ValidationError

log = logging.getLogger(__name__)


class AppContext(QObject):
    """Agrupa los servicios de la aplicación y avisa a las pestañas cuando cambian los datos."""

    data_changed = Signal()
    settings_changed = Signal()

    def __init__(self, paths, db, config_store, settings, engine, backend, clock, sleep_inhibitor=None):
        super().__init__()
        self.paths, self.db, self.config_store = paths, db, config_store
        self.settings, self.engine, self.backend, self.clock = settings, engine, backend, clock
        self.sleep_inhibitor = sleep_inhibitor

    def notify_data_changed(self) -> None:
        self.engine.reload()
        self.data_changed.emit()

    def save_settings(self) -> bool:
        try:
            self.config_store.save(self.settings)
        except OSError as exc:
            log.error("No se pudo guardar la configuración: %s", exc)
            return False
        self.engine.apply_settings(self.settings)
        if self.sleep_inhibitor is not None:
            if self.settings.impedir_suspension:
                self.sleep_inhibitor.enable()
            else:
                self.sleep_inhibitor.disable()
        self.settings_changed.emit()
        return True

    def local_now(self) -> datetime:
        return self.engine.scheduler.local(self.clock.now())


def long_date(d) -> str:
    return f"{DAY_NAMES[d.weekday()]}, {d.day} de {MONTH_NAMES[d.month - 1]} de {d.year}"


def ask(parent: QWidget, title: str, text: str, yes: str = "Sí", no: str = "Cancelar",
        danger: bool = False) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Icon.Warning if danger else QMessageBox.Icon.Question)
    yes_btn = box.addButton(yes, QMessageBox.ButtonRole.AcceptRole)
    no_btn = box.addButton(no, QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(no_btn if danger else yes_btn)
    box.exec()
    return box.clickedButton() is yes_btn


def info(parent: QWidget, title: str, text: str) -> None:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Icon.Information)
    box.addButton("Aceptar", QMessageBox.ButtonRole.AcceptRole)
    box.exec()


def error(parent: QWidget, title: str, text: str) -> None:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Icon.Critical)
    box.addButton("Aceptar", QMessageBox.ButtonRole.AcceptRole)
    box.exec()


def guarded(parent: QWidget, action, title: str = "No se ha podido completar la operación"):
    """Ejecuta `action` mostrando un mensaje comprensible si falla. Devuelve su resultado o None."""
    try:
        return action()
    except ValidationError as exc:
        error(parent, "Revise los datos", str(exc))
    except DatabaseError as exc:
        log.exception("Error de base de datos")
        error(parent, title, str(exc))
    except OSError as exc:
        log.exception("Error de archivo")
        error(parent, title, f"Error de archivo o carpeta: {exc.strerror or exc}")
    except Exception as exc:  # último recurso: registrar sin cerrar la aplicación
        log.exception("Error inesperado")
        error(parent, title, f"Se ha producido un error inesperado. Queda anotado en el registro.\n({type(exc).__name__})")
    return None


def big_button(text: str, object_name: str = "big") -> QPushButton:
    b = QPushButton(text)
    b.setObjectName(object_name)
    b.setMinimumHeight(56)
    b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def help_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("help")
    lbl.setWordWrap(True)
    return lbl


def card() -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    return f
