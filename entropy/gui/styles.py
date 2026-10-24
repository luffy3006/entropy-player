"""Desktop palette and stylesheet."""

APP_STYLE = """
QWidget { background: #171a19; color: #e4e8e2; font-family: 'Noto Sans'; font-size: 13px; }
QMainWindow { background: #171a19; }
QLabel#pageTitle { color: #f2f3ee; font-size: 22px; font-weight: 700; }
QLabel#eyebrow { color: #8a9c8e; font-size: 10px; font-weight: 700; }
QFrame#sidebar { background: #202522; border-right: 1px solid #343c36; }
QTreeWidget, QTableWidget { background: #1b1f1c; border: 1px solid #303832; gridline-color: #2a302b; selection-background-color: #315b49; selection-color: white; }
QHeaderView::section { background: #242a25; color: #9ba99d; border: 0; border-bottom: 1px solid #3b443c; padding: 9px 7px; font-weight: 700; }
QTreeWidget::item { padding: 7px 4px; }
QPushButton { background: #2c352e; border: 1px solid #465248; border-radius: 4px; padding: 7px 11px; }
QPushButton:hover { background: #39483d; }
QPushButton#primary { background: #c8e36d; color: #20271d; border: 0; font-weight: 700; min-width: 36px; }
QPushButton#primary:hover { background: #d7ef82; }
QSlider::groove:horizontal { background: #3c443e; height: 4px; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #c8e36d; border-radius: 2px; }
QSlider::handle:horizontal { background: #e0edbf; width: 12px; margin: -5px 0; border-radius: 6px; }
QComboBox, QLineEdit { background: #222824; border: 1px solid #39433b; border-radius: 4px; padding: 7px; }
QStatusBar { color: #92a096; border-top: 1px solid #343c36; }
"""