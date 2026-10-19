from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QFrame
)

from src.controllers.files_handler import get_bundle_files
from src.gui.theme import ColorThemeManager


def _interface_preview(mode: str, dpr: float = 1.0) -> QPixmap:
    """English screenshots of the app, shipped alongside the other Qt assets."""
    pixmap = QPixmap(get_bundle_files(f"src/qt/previews/interface_{mode}_en.png"))
    preview = pixmap.scaled(round(340 * dpr), round(216 * dpr),
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
    preview.setDevicePixelRatio(dpr)
    return preview


class InterfacePickerDialog(QDialog):
    """First-launch dialog: pick Sidebar or Modern interface."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(QCoreApplication.translate("Nugget", "Choose Interface"))
        self.setFixedWidth(420)
        self.choice = None  # "classic" | "ios"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel(QCoreApplication.translate("Nugget", "Welcome to GoldenNugget"))
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self._subtitle = QLabel(QCoreApplication.translate(
            "Nugget", "Choose your interface style"))
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._subtitle)

        layout.addSpacing(8)

        # Sidebar option
        self._classic_frame = QFrame()
        cf_lay = QVBoxLayout(self._classic_frame)
        cf_lay.setContentsMargins(16, 12, 16, 12)
        classic_art = QLabel()
        classic_art.setPixmap(_interface_preview("sidebar", self.devicePixelRatioF()))
        classic_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        classic_art.setStyleSheet("border: none; background: transparent;")
        cf_lay.addWidget(classic_art)
        cf_title = QLabel(QCoreApplication.translate("Nugget", "Sidebar"))
        cf_title.setStyleSheet("font-size: 16px; font-weight: 600; border: none;")
        self._cf_desc = QLabel(QCoreApplication.translate(
            "Nugget", "Sidebar navigation with familiar layout"))
        self._cf_desc.setWordWrap(True)
        cf_lay.addWidget(cf_title)
        cf_lay.addWidget(self._cf_desc)
        self._classic_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        self._classic_frame.mousePressEvent = lambda e: self._pick("classic")
        layout.addWidget(self._classic_frame)

        # Modern option
        self._ios_frame = QFrame()
        io_lay = QVBoxLayout(self._ios_frame)
        io_lay.setContentsMargins(16, 12, 16, 12)
        ios_art = QLabel()
        ios_art.setPixmap(_interface_preview("modern", self.devicePixelRatioF()))
        ios_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ios_art.setStyleSheet("border: none; background: transparent;")
        io_lay.addWidget(ios_art)
        io_title = QLabel(QCoreApplication.translate("Nugget", "Modern"))
        io_title.setStyleSheet("font-size: 16px; font-weight: 600; border: none;")
        self._io_desc = QLabel(QCoreApplication.translate(
            "Nugget", "Full-screen mobile-inspired interface"))
        self._io_desc.setWordWrap(True)
        io_lay.addWidget(io_title)
        io_lay.addWidget(self._io_desc)
        self._ios_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ios_frame.mousePressEvent = lambda e: self._pick("ios")
        layout.addWidget(self._ios_frame)

        self._retheme()
        ColorThemeManager.instance().theme_changed.connect(self._retheme)

    def _retheme(self):
        c = ColorThemeManager.instance().colors
        self.setStyleSheet(f"""
            QDialog {{ background-color: {c.bg_elevated}; }}
            QLabel {{ color: {c.text_primary}; background: transparent; }}
        """)
        self._subtitle.setStyleSheet(f"color: {c.text_secondary}; font-size: 14px;")
        self._classic_frame.setStyleSheet(f"""
            QFrame {{ background-color: {c.surface_hover}; border-radius: 12px; }}
            QFrame:hover {{ background-color: {c.border}; }}
        """)
        self._cf_desc.setStyleSheet(f"color: {c.text_secondary}; font-size: 13px; border: none;")
        self._ios_frame.setStyleSheet(f"""
            QFrame {{ background-color: {c.surface_hover}; border-radius: 12px; }}
            QFrame:hover {{ background-color: {c.border}; }}
        """)
        self._io_desc.setStyleSheet(f"color: {c.text_secondary}; font-size: 13px; border: none;")

    def _pick(self, choice: str):
        self.choice = choice
        self.accept()


class HomeWidgetPickerDialog(QDialog):
    """First-launch dialog: pick the home top-bar widget.

    ``choice`` is ``"storage"`` or ``"presets"`` once the user picks an option.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(QCoreApplication.translate("Nugget", "Choose Home Widget"))
        self.setFixedWidth(420)
        self.choice = None  # "storage" | "presets"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel(QCoreApplication.translate("Nugget", "Customize your Home screen"))
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self._subtitle = QLabel(QCoreApplication.translate(
            "Nugget", "Which widget should appear next to the device picker?"))
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subtitle.setWordWrap(True)
        layout.addWidget(self._subtitle)

        layout.addSpacing(8)

        self._storage_frame = QFrame()
        sf_lay = QVBoxLayout(self._storage_frame)
        sf_lay.setContentsMargins(16, 12, 16, 12)
        sf_title = QLabel(QCoreApplication.translate("Nugget", "Device Storage"))
        sf_title.setStyleSheet("font-size: 16px; font-weight: 600; border: none;")
        self._sf_desc = QLabel(QCoreApplication.translate(
            "Nugget", "Shows the connected iPhone's used and free space."))
        self._sf_desc.setWordWrap(True)
        sf_lay.addWidget(sf_title)
        sf_lay.addWidget(self._sf_desc)
        self._storage_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        self._storage_frame.mousePressEvent = lambda e: self._pick("storage")
        layout.addWidget(self._storage_frame)

        self._presets_frame = QFrame()
        pf_lay = QVBoxLayout(self._presets_frame)
        pf_lay.setContentsMargins(16, 12, 16, 12)
        pf_title = QLabel(QCoreApplication.translate("Nugget", "Presets"))
        pf_title.setStyleSheet("font-size: 16px; font-weight: 600; border: none;")
        self._pf_desc = QLabel(QCoreApplication.translate(
            "Nugget", "Shows the active preset and opens the preset manager."))
        self._pf_desc.setWordWrap(True)
        pf_lay.addWidget(pf_title)
        pf_lay.addWidget(self._pf_desc)
        self._presets_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        self._presets_frame.mousePressEvent = lambda e: self._pick("presets")
        layout.addWidget(self._presets_frame)

        self._retheme()
        ColorThemeManager.instance().theme_changed.connect(self._retheme)

    def _retheme(self):
        c = ColorThemeManager.instance().colors
        self.setStyleSheet(f"""
            QDialog {{ background-color: {c.bg_elevated}; }}
            QLabel {{ color: {c.text_primary}; background: transparent; }}
        """)
        self._subtitle.setStyleSheet(f"color: {c.text_secondary}; font-size: 14px;")
        self._storage_frame.setStyleSheet(f"""
            QFrame {{ background-color: {c.surface_hover}; border-radius: 12px; }}
            QFrame:hover {{ background-color: {c.border}; }}
        """)
        self._sf_desc.setStyleSheet(f"color: {c.text_secondary}; font-size: 13px; border: none;")
        self._presets_frame.setStyleSheet(f"""
            QFrame {{ background-color: {c.surface_hover}; border-radius: 12px; }}
            QFrame:hover {{ background-color: {c.border}; }}
        """)
        self._pf_desc.setStyleSheet(f"color: {c.text_secondary}; font-size: 13px; border: none;")

    def _pick(self, choice: str):
        self.choice = choice
        self.accept()
