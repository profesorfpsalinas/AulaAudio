"""Pestaña Historial e incidencias."""
from __future__ import annotations

import csv
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .common import AppContext, guarded, help_label, info

LEVELS = {"info": "Información", "aviso": "Aviso", "error": "Error"}


def _safe_cell(text: str) -> str:
    """Evita que una hoja de cálculo interprete como fórmula un texto escrito por el usuario."""
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


class HistoryTab(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        lay = QVBoxLayout(self)
        lay.addWidget(help_label("Registro de lo que ha sonado y de las incidencias. Los detalles técnicos se guardan "
                                 "también en el archivo de registro (carpeta «Registros»)."))
        row = QHBoxLayout()
        row.addWidget(QLabel("Mostrar:"))
        self.level = QComboBox()
        self.level.addItem("Todo", None)
        self.level.addItem("Solo incidencias (errores)", "error")
        self.level.addItem("Solo avisos", "aviso")
        self.level.addItem("Solo información", "info")
        self.level.currentIndexChanged.connect(self.refresh)
        row.addWidget(self.level)
        row.addStretch(1)
        for text, slot in (("Actualizar", self.refresh), ("Exportar a CSV…", self._export),
                           ("Abrir carpeta de registros", self._open_logs)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        lay.addLayout(row)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Fecha y hora", "Tipo", "Categoría", "Descripción"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self.table, 1)
        self._pending = QTimer(self)
        self._pending.setSingleShot(True)
        self._pending.setInterval(1500)
        self._pending.timeout.connect(self.refresh)
        ctx.engine.history_logged.connect(self._schedule_refresh)
        self.refresh()

    def _schedule_refresh(self) -> None:
        if self.isVisible() and not self._pending.isActive():
            self._pending.start()

    def showEvent(self, e):
        self.refresh()
        super().showEvent(e)

    def _rows(self):
        return self.ctx.db.history(self.level.currentData(), limit=2000)

    def refresh(self) -> None:
        rows = guarded(self, self._rows)
        if rows is None:
            return
        tz = self.ctx.engine.scheduler.tz
        self.table.setRowCount(0)
        for r in rows:
            i = self.table.rowCount()
            self.table.insertRow(i)
            when = datetime.fromisoformat(r["ts"]).astimezone(tz).strftime("%d/%m/%Y %H:%M:%S")
            for c, v in enumerate((when, LEVELS.get(r["level"], r["level"]), r["category"], r["message"])):
                it = QTableWidgetItem(v)
                if r["level"] == "error":
                    it.setForeground(QColor("#b42318"))
                elif r["level"] == "aviso":
                    it.setForeground(QColor("#9a5b00"))
                self.table.setItem(i, c, it)

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exportar historial", "historial_aulaaudio.csv", "CSV (*.csv)")
        if not path:
            return

        def write():
            with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh, delimiter=";")
                w.writerow(["fecha_utc", "tipo", "categoria", "descripcion"])
                for r in self.ctx.db.history(None, limit=100000):
                    w.writerow([r["ts"], r["level"], r["category"], _safe_cell(r["message"])])
            return True

        if guarded(self, write):
            info(self, "Exportar historial", "Historial exportado.")

    def _open_logs(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ctx.paths.log_dir)))
