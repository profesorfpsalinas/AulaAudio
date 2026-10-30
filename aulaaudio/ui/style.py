"""Hoja de estilo: claro, alto contraste, tipografía grande y botones amplios."""

STATUS_COLORS = {
    "funcionando": ("#e6f4ea", "#1e7b34"),
    "detenido": ("#fff4e0", "#9a5b00"),
    "incidencia": ("#fde8e8", "#b42318"),
}

QSS = """
QWidget { font-size: 11pt; color: #1f2933; }
QMainWindow, QDialog { background: #f5f7fa; }
QTabWidget::pane { border: 1px solid #d5dbe3; background: #ffffff; border-radius: 6px; }
QTabBar::tab { padding: 10px 18px; margin-right: 2px; background: #e8edf3; border-top-left-radius: 6px;
               border-top-right-radius: 6px; color: #334155; }
QTabBar::tab:selected { background: #ffffff; color: #0b4f8a; font-weight: bold; }
QFrame#card { background: #ffffff; border: 1px solid #d5dbe3; border-radius: 8px; }
QLabel#clock { font-size: 26pt; font-weight: bold; color: #0b4f8a; }
QLabel#date { font-size: 13pt; color: #475569; }
QLabel#section { font-size: 12pt; font-weight: bold; color: #0b4f8a; }
QLabel#big { font-size: 14pt; }
QLabel#help { color: #52606d; }
QLabel#status { font-size: 14pt; font-weight: bold; padding: 12px; border-radius: 8px; }
QLabel#simbanner { background: #6b21a8; color: white; font-weight: bold; padding: 6px; }
QPushButton { padding: 7px 14px; border: 1px solid #b6c2cf; border-radius: 6px; background: #ffffff; }
QPushButton:hover { background: #eef4fb; }
QPushButton:pressed { background: #dce8f5; }
QPushButton:disabled { color: #9aa5b1; background: #f1f3f5; }
QPushButton#big { font-size: 14pt; font-weight: bold; }
QPushButton#primary { background: #0b63b6; color: white; border-color: #0b63b6; font-weight: bold; }
QPushButton#primary:hover { background: #0a56a0; }
QPushButton#danger { background: #ffffff; color: #b42318; border-color: #e5a3a0; }
QPushButton#play { background: #1e7b34; color: white; border-color: #1e7b34; font-size: 14pt; font-weight: bold; }
QPushButton#stop { background: #b42318; color: white; border-color: #b42318; font-size: 14pt; font-weight: bold; }
QPushButton#play:disabled, QPushButton#stop:disabled { background: #c9d1d9; border-color: #c9d1d9; }
QTableWidget, QListWidget, QTreeWidget { background: #ffffff; alternate-background-color: #f6f8fb;
               gridline-color: #e3e8ee; selection-background-color: #cfe3f7; selection-color: #102a43; }
QHeaderView::section { background: #eef2f6; padding: 6px; border: none; border-bottom: 1px solid #d5dbe3;
               font-weight: bold; }
QLineEdit, QComboBox, QSpinBox, QTimeEdit, QDateEdit, QDateTimeEdit, QPlainTextEdit {
               padding: 5px; border: 1px solid #b6c2cf; border-radius: 5px; background: #ffffff; }
QSlider::groove:horizontal { height: 8px; background: #d5dbe3; border-radius: 4px; }
QSlider::handle:horizontal { width: 22px; margin: -8px 0; background: #0b63b6; border-radius: 11px; }
QSlider::sub-page:horizontal { background: #6aa8e0; border-radius: 4px; }
QGroupBox { font-weight: bold; border: 1px solid #d5dbe3; border-radius: 8px; margin-top: 14px; padding-top: 10px;
            background: #ffffff; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: #0b4f8a; }
"""
