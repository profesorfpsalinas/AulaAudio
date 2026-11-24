"""Cuenta atrás cancelable antes del apagado programado del equipo."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from .common import help_label


class ShutdownDialog(QDialog):
    """Ventana siempre visible con una cuenta atrás. Si nadie la cancela, emite `confirmed`."""

    confirmed = Signal()
    cancelled = Signal()

    def __init__(self, hhmm: str, minutes: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AulaAudio — Apagado programado")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setMinimumWidth(460)
        self._deadline = time.monotonic() + max(1, int(minutes)) * 60
        self._done = False
        lay = QVBoxLayout(self)
        title = QLabel(f"Apagado programado de las {hhmm}")
        title.setObjectName("section")
        lay.addWidget(title)
        self.counter = QLabel()
        self.counter.setObjectName("big")
        self.counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.counter)
        lay.addWidget(help_label("Guarde su trabajo. Si hoy no se debe apagar el equipo, pulse «Cancelar el apagado "
                                 "de hoy»: mañana se apagará a la hora habitual. Los festivos y vacaciones se "
                                 "configuran en «Calendario y excepciones»."))
        row = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancelar el apagado de hoy")
        self.btn_cancel.setObjectName("primary")
        self.btn_cancel.setMinimumHeight(44)
        self.btn_cancel.clicked.connect(self._cancel)
        row.addWidget(self.btn_cancel, 2)
        self.btn_now = QPushButton("Apagar ahora")
        self.btn_now.setObjectName("danger")
        self.btn_now.setMinimumHeight(44)
        self.btn_now.clicked.connect(self._finish)
        row.addWidget(self.btn_now, 1)
        lay.addLayout(row)
        self.btn_cancel.setDefault(True)
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._tick()

    def remaining_seconds(self) -> int:
        return max(0, int(round(self._deadline - time.monotonic())))

    def _tick(self) -> None:
        left = self.remaining_seconds()
        self.counter.setText(f"El equipo se apagará en {left // 60}:{left % 60:02d}")
        if left <= 0:
            self._finish()

    def _cancel(self) -> None:
        if self._done:
            return
        self._done = True
        self._timer.stop()
        self.cancelled.emit()
        self.accept()

    def _finish(self) -> None:
        if self._done:
            return
        self._done = True
        self._timer.stop()
        self.confirmed.emit()
        self.accept()

    def reject(self) -> None:  # cerrar la ventana o pulsar Esc equivale a cancelar
        if not self._done:
            self._cancel()
        else:
            super().reject()
