# -*- mode: python ; coding: utf-8 -*-
# Especificación de PyInstaller para AulaAudio (Windows y Linux).
# Se construye en modo «carpeta» (onedir): arranca más rápido y es más fiable que un único .exe.
# Uso (desde la raíz del proyecto):  pyinstaller packaging/aulaaudio.spec --noconfirm
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
ICON = str(ROOT / "packaging" / ("aulaaudio.ico" if sys.platform == "win32" else "aulaaudio.png"))

# Módulos de Qt que AulaAudio no usa: se excluyen para reducir tamaño.
EXCLUDES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech", "PySide6.QtRemoteObjects", "PySide6.QtScxml",
    "tkinter", "unittest", "pytest", "pydoc",
]

a = Analysis(
    [str(ROOT / "AulaAudio.pyw")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ROOT / "config.example.json"), "."), (str(ROOT / "LICENCIAS_TERCEROS.md"), ".")],
    hiddenimports=["tzdata", "PySide6.QtMultimedia"],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="AulaAudio",
    console=False,  # aplicación de ventana; los mensajes van al registro
    icon=ICON,
    upx=False,  # UPX provoca falsos positivos de antivirus
)
coll = COLLECT(exe, a.binaries, a.datas, name="AulaAudio", upx=False)
