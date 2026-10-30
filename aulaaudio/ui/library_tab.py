"""Pestaña Biblioteca de audio: pistas y listas de reproducción."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import library
from ..models import Playlist
from .common import AppContext, ask, error, guarded, help_label, info
from .event_dialog import AUDIO_FILTER

STATUS_TEXT = {"ok": "Correcto", "falta": "⚠ No se encuentra", "error": "⚠ Error"}


def fmt_ms(ms: int | None) -> str:
    if not ms:
        return ""
    s = ms // 1000
    return f"{s // 60}:{s % 60:02d}"


class LibraryTab(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.addWidget(help_label("AulaAudio no copia ni mueve sus archivos: solo recuerda dónde están. "
                                  "Recuerde que el centro debe tener derechos para reproducir públicamente la música."))
        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split, 1)

        # ---------------- pistas
        left = QWidget()
        ll = QVBoxLayout(left)
        t = QLabel("Pistas de la biblioteca")
        t.setObjectName("section")
        ll.addWidget(t)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por nombre…")
        self.search.textChanged.connect(self.refresh_tracks)
        ll.addWidget(self.search)
        self.tracks = QTableWidget(0, 4)
        self.tracks.setHorizontalHeaderLabels(["Nombre", "Duración", "Estado", "Ubicación"])
        self.tracks.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tracks.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tracks.setAlternatingRowColors(True)
        self.tracks.verticalHeader().setVisible(False)
        h = self.tracks.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.tracks.setColumnWidth(1, 80)
        self.tracks.setColumnWidth(3, 220)
        self.tracks.doubleClicked.connect(self._listen)
        ll.addWidget(self.tracks, 1)
        r1, r2 = QHBoxLayout(), QHBoxLayout()
        for row, items in ((r1, (("Añadir archivos…", self._add_files), ("Añadir carpeta…", self._add_folder),
                                 ("▶ Escuchar", self._listen), ("■ Parar", ctx.engine.stop))),
                           (r2, (("Comprobar archivos", self._check), ("Localizar archivos movidos…", self._relocate),
                                 ("Quitar de la biblioteca", self._remove)))):
            for text, slot in items:
                b = QPushButton(text)
                b.clicked.connect(slot)
                row.addWidget(b)
            row.addStretch(1)
        ll.addLayout(r1)
        ll.addLayout(r2)
        split.addWidget(left)

        # ---------------- listas
        right = QWidget()
        rl = QVBoxLayout(right)
        t = QLabel("Listas de reproducción")
        t.setObjectName("section")
        rl.addWidget(t)
        self.playlists = QListWidget()
        self.playlists.currentItemChanged.connect(lambda *_: self.refresh_items())
        rl.addWidget(self.playlists, 1)
        pr = QHBoxLayout()
        for text, slot in (("Nueva…", self._new_pl), ("Renombrar…", self._rename_pl), ("Duplicar", self._dup_pl),
                           ("Eliminar", self._del_pl)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            pr.addWidget(b)
        rl.addLayout(pr)
        pr2 = QHBoxLayout()
        for text, slot in (("Importar M3U…", self._import), ("Exportar M3U…", self._export)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            pr2.addWidget(b)
        pr2.addStretch(1)
        rl.addLayout(pr2)
        opts = QHBoxLayout()
        opts.addWidget(QLabel("Orden:"))
        self.mode = QComboBox()
        self.mode.addItem("Secuencial", "secuencial")
        self.mode.addItem("Aleatorio", "aleatorio")
        self.mode.currentIndexChanged.connect(self._save_opts)
        opts.addWidget(self.mode)
        self.repeat = QCheckBox("Repetir la lista mientras dure el evento")
        self.repeat.toggled.connect(self._save_opts)
        opts.addWidget(self.repeat)
        opts.addStretch(1)
        rl.addLayout(opts)
        t = QLabel("Pistas de la lista seleccionada")
        t.setObjectName("section")
        rl.addWidget(t)
        self.items = QListWidget()
        self.items.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        rl.addWidget(self.items, 2)
        ir = QHBoxLayout()
        for text, slot in (("◀ Añadir pistas seleccionadas", self._add_to_pl), ("Quitar", self._remove_from_pl),
                           ("▲ Subir", lambda: self._move(-1)), ("▼ Bajar", lambda: self._move(1)),
                           ("▶ Escuchar lista", self._listen_pl)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            ir.addWidget(b)
        rl.addLayout(ir)
        split.addWidget(right)
        split.setSizes([600, 500])

        ctx.data_changed.connect(self.refresh)
        self.refresh()

    # ----------------------------------------------------------------- refresco
    def refresh(self) -> None:
        self.refresh_tracks()
        current = self._current_pl_id()
        self.playlists.blockSignals(True)
        self.playlists.clear()
        for pl in self.ctx.db.playlists():
            it = QListWidgetItem(pl.name)
            it.setData(Qt.ItemDataRole.UserRole, pl.id)
            self.playlists.addItem(it)
            if pl.id == current:
                self.playlists.setCurrentItem(it)
        if self.playlists.currentItem() is None and self.playlists.count():
            self.playlists.setCurrentRow(0)
        self.playlists.blockSignals(False)
        self.refresh_items()

    def refresh_tracks(self) -> None:
        tracks = self.ctx.db.tracks(self.search.text().strip())
        self.tracks.setRowCount(0)
        for t in tracks:
            r = self.tracks.rowCount()
            self.tracks.insertRow(r)
            for c, v in enumerate((t.title, fmt_ms(t.duration_ms), STATUS_TEXT.get(t.status, t.status), t.path)):
                it = QTableWidgetItem(v)
                it.setData(Qt.ItemDataRole.UserRole, t.id)
                if c == 2 and t.status != "ok":
                    it.setForeground(Qt.GlobalColor.red)
                    it.setToolTip(t.status_msg)
                self.tracks.setItem(r, c, it)

    def _current_pl_id(self) -> int | None:
        it = self.playlists.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def refresh_items(self) -> None:
        pid = self._current_pl_id()
        self.items.clear()
        for w in (self.mode, self.repeat):
            w.blockSignals(True)
        if pid is not None:
            pl = self.ctx.db.playlist(pid)
            if pl:
                self.mode.setCurrentIndex(self.mode.findData(pl.mode))
                self.repeat.setChecked(pl.repeat)
            for t in self.ctx.db.playlist_tracks(pid):
                it = QListWidgetItem(t.title + ("" if t.status == "ok" else "   ⚠"))
                it.setData(Qt.ItemDataRole.UserRole, t.id)
                self.items.addItem(it)
        for w in (self.mode, self.repeat):
            w.blockSignals(False)

    def _selected_track_ids(self) -> list[int]:
        rows = sorted({i.row() for i in self.tracks.selectedIndexes()})
        return [self.tracks.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in rows]

    def _changed(self) -> None:
        self.ctx.notify_data_changed()

    # ----------------------------------------------------------------- pistas
    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Añadir archivos de audio", "", AUDIO_FILTER)
        if paths:
            res = guarded(self, lambda: library.add_files(self.ctx.db, paths))
            if res:
                self._changed()
                info(self, "Añadir archivos", f"Añadidos: {res.added}. Ya estaban: {res.already}. "
                     f"No admitidos: {res.rejected}.")

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Añadir una carpeta de música")
        if folder:
            res = guarded(self, lambda: library.add_folder(self.ctx.db, folder))
            if res:
                self._changed()
                extra = "\nLa carpeta tenía demasiados archivos; solo se han añadido los primeros." if res.truncated else ""
                info(self, "Añadir carpeta", f"Añadidos: {res.added}. Ya estaban: {res.already}.{extra}")

    def _listen(self) -> None:
        ids = self._selected_track_ids()
        if not ids:
            info(self, "Escuchar", "Seleccione una pista.")
            return
        t = self.ctx.db.track(ids[0])
        cur = self.ctx.engine.current
        if cur and not ask(self, "Ya está sonando algo", f"Ahora suena «{cur.title}». ¿Detenerlo para escuchar la pista?",
                           yes="Escuchar"):
            return
        if not self.ctx.engine.play_manual("Escucha: " + t.title, track_id=t.id, kind="prueba"):
            msg = self.ctx.engine.last_incident[1] if self.ctx.engine.last_incident else ""
            error(self, "No se puede reproducir", msg or "No se ha podido reproducir la pista.")

    def _check(self) -> None:
        res = guarded(self, lambda: library.check_tracks(self.ctx.db))
        if res:
            self._changed()
            ok, bad = res
            msg = f"Archivos correctos: {ok}. Con problemas: {bad}."
            if bad:
                msg += "\n\nSi ha movido la carpeta de música, use «Localizar archivos movidos…»."
            info(self, "Comprobar archivos", msg)

    def _relocate(self) -> None:
        if guarded(self, lambda: library.check_tracks(self.ctx.db)) is None:
            return
        self._changed()
        if not any(t.status == "falta" for t in self.ctx.db.tracks()):
            info(self, "Localizar archivos", "No falta ningún archivo.")
            return
        folder = QFileDialog.getExistingDirectory(self, "¿Dónde está ahora la música? Elija la carpeta nueva")
        if not folder:
            return
        res = guarded(self, lambda: library.relocate_missing(self.ctx.db, folder))
        if res:
            found, not_found = res
            self._changed()
            info(self, "Localizar archivos", f"Archivos localizados de nuevo: {found}. Sin encontrar: {not_found}.")

    def _remove(self) -> None:
        ids = self._selected_track_ids()
        if not ids:
            return
        used = sorted({n for tid in ids for n in self.ctx.db.events_using_track(tid)})
        warn = (f"\n\nAtención: lo usan estos eventos, que se quedarán sin audio: {', '.join(used[:8])}"
                + ("…" if len(used) > 8 else "")) if used else ""
        if ask(self, "Quitar de la biblioteca", f"¿Quitar {len(ids)} pista(s) de la biblioteca? Los archivos NO se "
               f"borran del disco.{warn}", yes="Quitar", danger=bool(used)):
            for tid in ids:
                guarded(self, lambda: self.ctx.db.delete_track(tid))
            self._changed()

    # ----------------------------------------------------------------- listas
    def _new_pl(self) -> None:
        name, ok = QInputDialog.getText(self, "Nueva lista", "Nombre de la lista:")
        if ok and name.strip():
            if guarded(self, lambda: self.ctx.db.add_playlist(name)):
                self._changed()

    def _rename_pl(self) -> None:
        pid = self._current_pl_id()
        if pid is None:
            return
        pl = self.ctx.db.playlist(pid)
        name, ok = QInputDialog.getText(self, "Renombrar lista", "Nuevo nombre:", text=pl.name)
        if ok and name.strip():
            pl.name = name
            guarded(self, lambda: self.ctx.db.update_playlist(pl))
            self._changed()

    def _dup_pl(self) -> None:
        pid = self._current_pl_id()
        if pid is None:
            return
        pl = self.ctx.db.playlist(pid)
        name, ok = QInputDialog.getText(self, "Duplicar lista", "Nombre de la copia:", text=pl.name[:90] + " (copia)")
        if ok and name.strip():
            if guarded(self, lambda: self.ctx.db.duplicate_playlist(pid, name)):
                self._changed()

    def _del_pl(self) -> None:
        pid = self._current_pl_id()
        if pid is None:
            return
        used = self.ctx.db.events_using_playlist(pid)
        warn = f"\n\nLa usan estos eventos, que se quedarán sin audio: {', '.join(used[:8])}" if used else ""
        if ask(self, "Eliminar lista", "¿Eliminar la lista? Los archivos no se borran." + warn, yes="Eliminar", danger=True):
            guarded(self, lambda: self.ctx.db.delete_playlist(pid))
            self._changed()

    def _save_opts(self) -> None:
        pid = self._current_pl_id()
        if pid is None:
            return
        pl = self.ctx.db.playlist(pid)
        guarded(self, lambda: self.ctx.db.update_playlist(Playlist(pl.id, pl.name, self.mode.currentData(),
                                                                    self.repeat.isChecked(), pl.demo)))
        self.ctx.engine.reload()

    def _item_ids(self) -> list[int]:
        return [self.items.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.items.count())]

    def _save_items(self, ids: list[int]) -> None:
        pid = self._current_pl_id()
        guarded(self, lambda: self.ctx.db.set_playlist_tracks(pid, ids))
        self.refresh_items()

    def _add_to_pl(self) -> None:
        if self._current_pl_id() is None:
            info(self, "Listas", "Cree o seleccione primero una lista.")
            return
        ids = self._selected_track_ids()
        if not ids:
            info(self, "Listas", "Seleccione pistas en la tabla de la izquierda.")
            return
        self._save_items(self._item_ids() + ids)

    def _remove_from_pl(self) -> None:
        rows = sorted({self.items.row(i) for i in self.items.selectedItems()})
        ids = [tid for i, tid in enumerate(self._item_ids()) if i not in rows]
        self._save_items(ids)

    def _move(self, step: int) -> None:
        row = self.items.currentRow()
        ids = self._item_ids()
        new = row + step
        if row < 0 or not 0 <= new < len(ids):
            return
        ids[row], ids[new] = ids[new], ids[row]
        self._save_items(ids)
        self.items.setCurrentRow(new)

    def _listen_pl(self) -> None:
        pid = self._current_pl_id()
        if pid is None:
            return
        cur = self.ctx.engine.current
        if cur and not ask(self, "Ya está sonando algo", f"Ahora suena «{cur.title}». ¿Detenerlo?", yes="Escuchar"):
            return
        if not self.ctx.engine.play_manual(self.playlists.currentItem().text(), playlist_id=pid):
            msg = self.ctx.engine.last_incident[1] if self.ctx.engine.last_incident else ""
            error(self, "No se puede reproducir", msg or "No se ha podido reproducir la lista.")

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importar lista M3U", "", "Listas M3U (*.m3u *.m3u8)")
        if path:
            res = guarded(self, lambda: library.import_m3u(self.ctx.db, path))
            if res:
                _, n, missing = res
                self._changed()
                info(self, "Importar lista", f"Lista creada con {n} pista(s). No encontradas: {missing}.")

    def _export(self) -> None:
        pid = self._current_pl_id()
        if pid is None:
            return
        name = self.playlists.currentItem().text()
        safe = "".join(c for c in name if c.isalnum() or c in " -_()").strip() or "lista"
        path, _ = QFileDialog.getSaveFileName(self, "Exportar lista", safe + ".m3u8", "Lista M3U8 (*.m3u8)")
        if path:
            n = guarded(self, lambda: library.export_m3u(self.ctx.db, pid, path))
            if n is not None:
                info(self, "Exportar lista", f"Lista exportada con {n} pista(s).")
