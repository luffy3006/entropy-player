"""Theme palettes and stylesheets for the desktop interface."""

THEMES = {
    "Strawberry Blue": {
        "background": "#11151b", "surface": "#191f28", "raised": "#222b36",
        "border": "#303d4a", "text": "#e4edf6", "muted": "#92a6ba",
        "accent": "#42b9f5", "accent_text": "#07151f", "selection": "#174c70",
    },
    "Midnight Teal": {
        "background": "#111918", "surface": "#192321", "raised": "#23312e",
        "border": "#354841", "text": "#e3efea", "muted": "#91aaa0",
        "accent": "#52dbc1", "accent_text": "#081b17", "selection": "#14594f",
    },
    "Classic Green": {
        "background": "#171a19", "surface": "#202522", "raised": "#2c352e",
        "border": "#465248", "text": "#e4e8e2", "muted": "#91a095",
        "accent": "#c8e36d", "accent_text": "#20271d", "selection": "#315b49",
    },
    "Light": {
        "background": "#eef2f6", "surface": "#ffffff", "raised": "#e3eaf1",
        "border": "#c9d3dd", "text": "#1d2b38", "muted": "#607486",
        "accent": "#087fbd", "accent_text": "#ffffff", "selection": "#c5e8fb",
    },
}


def style_for_theme(name: str) -> str:
    colors = THEMES.get(name, THEMES["Strawberry Blue"])
    return f"""
    QWidget {{ background: {colors['background']}; color: {colors['text']}; font-family: 'Noto Sans'; font-size: 13px; }}
    QMainWindow {{ background: {colors['background']}; }}
    QLabel#pageTitle {{ color: {colors['text']}; font-size: 22px; font-weight: 700; }}
    QLabel#eyebrow {{ color: {colors['muted']}; font-size: 10px; font-weight: 700; }}
    QFrame#sidebar {{ background: {colors['surface']}; border-right: 1px solid {colors['border']}; }}
    QFrame#playbackBar {{ background: {colors['surface']}; border-top: 1px solid {colors['border']}; }}
    QTreeWidget, QTableWidget {{ background: {colors['surface']}; border: 1px solid {colors['border']}; gridline-color: {colors['raised']}; selection-background-color: {colors['selection']}; selection-color: {colors['text']}; }}
    QHeaderView::section {{ background: {colors['raised']}; color: {colors['muted']}; border: 0; border-bottom: 1px solid {colors['border']}; padding: 9px 7px; font-weight: 700; }}
    QTreeWidget::item {{ padding: 7px 4px; }}
    QPushButton {{ background: {colors['raised']}; border: 1px solid {colors['border']}; border-radius: 4px; padding: 6px 9px; min-height: 24px; }}
    QPushButton:hover {{ border-color: {colors['accent']}; }}
    QPushButton#primary {{ background: {colors['accent']}; color: {colors['accent_text']}; border: 0; font-weight: 700; }}
    QPushButton#primary:hover {{ background: {colors['accent']}; }}
    QSlider::groove:horizontal {{ background: {colors['border']}; height: 4px; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {colors['accent']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {colors['text']}; width: 12px; margin: -5px 0; border-radius: 6px; }}
    QSlider#volumeSlider::groove:horizontal {{ background: {colors['border']}; height: 8px; border-radius: 4px; }}
    QSlider#volumeSlider::sub-page:horizontal {{ background: {colors['accent']}; border-radius: 4px; }}
    QSlider#volumeSlider::handle:horizontal {{ background: {colors['text']}; border: 2px solid {colors['accent']}; width: 15px; height: 15px; margin: -6px 0; border-radius: 8px; }}
    QComboBox, QLineEdit {{ background: {colors['surface']}; border: 1px solid {colors['border']}; border-radius: 4px; padding: 7px; }}
    QStatusBar {{ color: {colors['muted']}; border-top: 1px solid {colors['border']}; }}
    QMenu {{ background: {colors['surface']}; border: 1px solid {colors['border']}; }}
    """
