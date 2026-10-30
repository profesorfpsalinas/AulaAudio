"""Pestaña Copias de seguridad y restauración."""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import backup
from .common import AppContext, ask, error, guarded, help_label, info

KIND_TEXT = {"manual": "Manual", "automatica": "Automática", "antes_de_restaurar": "Antes de restaurar",
             "antes_de_actualizar": "Antes de actualizar", "dañada": "⚠ Dañada"}


class BackupTab(QWidget):
    def __init__(self, ctx: AppContext, on_restored):
        super().__init__()
        self.ctx = ctx
        self.on_restored = on_restored
        lay = QVBoxLayout(self)
        lay.addWidget(help_label(
            "Una copia guarda la programación, el calendario, las listas, el historial y la configuración. "
            "No incluye los archivos de música: haga también copia de su carpeta de música. Se recomienda "
            "exportar una copia a un pendrive o a una carpeta de red al terminar de configurar."))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Fecha", "Tipo", "Tamaño"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        b = QPushButton("💾 Crear copia ahora")
        b.setObjectName("primary")
        b.clicked.connect(self._create)
        row.addWidget(b)
        for text, slot in (("Exportar copia seleccionada…", self._export), ("Abrir carpeta de copias", self._open)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        for text, slot in (("Restaurar la seleccionada…", self._restore_selected),
                           ("Restaurar desde un archivo…", self._restore_file)):
            b = QPushButton(text)
            b.setObjectName("danger")
            b.clicked.connect(slot)
            row.addWidget(b)
        lay.addLayout(row)
        self.refresh()

    def showEvent(self, e):
        self.refresh()
        super().showEvent(e)

    def refresh(self) -> None:
        self.items = backup.list_backups(self.ctx.paths.backup_dir)
        self.table.setRowCount(0)
        for b in self.items:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, v in enumerate((b.created.strftime("%d/%m/%Y %H:%M:%S"), KIND_TEXT.get(b.kind, b.kind),
                                   f"{b.size / 1024:.0f} KB")):
                it = QTableWidgetItem(v)
                it.setToolTip(str(b.path))
                self.table.setItem(r, c, it)

    def _selected(self):
        rows = {i.row() for i in self.table.selectedIndexes()}
        return self.items[min(rows)] if rows else None

    def _create(self) -> None:
        p = guarded(self, lambda: backup.create_backup(self.ctx.db, self.ctx.paths.config_file,
                                                       self.ctx.paths.backup_dir, "manual"))
        if p:
            self.refresh()
            info(self, "Copia de seguridad", f"Copia creada:\n{p.name}")

    def _export(self) -> None:
        b = self._selected()
        if b is None:
            info(self, "Exportar", "Seleccione una copia de la lista.")
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Exportar copia", b.path.name, "Copia de AulaAudio (*.zip)")
        if not dest:
            return
        # El diálogo del sistema ya pide confirmación si el archivo existe.
        if guarded(self, lambda: shutil.copy2(b.path, dest)):
            info(self, "Exportar", "Copia exportada.")

    def _open(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ctx.paths.backup_dir)))

    def _restore_selected(self) -> None:
        b = self._selected()
        if b is None:
            info(self, "Restaurar", "Seleccione una copia de la lista.")
            return
        self._restore(b.path)

    def _restore_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Restaurar copia", "", "Copia de AulaAudio (*.zip)")
        if path:
            self._restore(Path(path))

    def _restore(self, path: Path) -> None:
        if not ask(self, "Restaurar copia de seguridad",
                   "Se sustituirán la programación, el calendario, las listas y la configuración actuales por los "
                   "de la copia. Antes se guardará automáticamente una copia del estado actual. ¿Continuar?",
                   yes="Restaurar", danger=True):
            return
        self.ctx.engine.stop()
        try:
            safety = backup.restore_backup(path, self.ctx.db, self.ctx.paths)
        except backup.BackupError as exc:
            error(self, "No se puede restaurar", str(exc) + "\n\nSus datos actuales no se han modificado.")
            return
        except Exception as exc:
            error(self, "No se puede restaurar", f"Error al restaurar: {exc}\n\nSi algo no funciona, restaure la copia "
                  "«Antes de restaurar» de esta lista.")
            return
        self.on_restored()
        self.refresh()
        info(self, "Restaurar", f"Copia restaurada correctamente.\nEl estado anterior se ha guardado en:\n{safety.name}")
