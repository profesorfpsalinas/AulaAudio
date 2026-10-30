"""Genera packaging/aulaaudio.ico y packaging/aulaaudio.png a partir del icono dibujado en código."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from aulaaudio.ui.main_window import make_icon_pixmap  # noqa: E402

app = QApplication(sys.argv)
out = ROOT / "packaging"
out.mkdir(exist_ok=True)
make_icon_pixmap(256).save(str(out / "aulaaudio.png"), "PNG")
if not make_icon_pixmap(256).save(str(out / "aulaaudio.ico"), "ICO"):
    sys.exit("No se pudo generar el .ico (falta el complemento de imagen ICO de Qt)")
print("Iconos generados en", out)
