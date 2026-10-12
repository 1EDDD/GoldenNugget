from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton

from src.gui.ios.components import IOSPrimaryButton
from src.gui.theme import t, theme_pixmap, ColorThemeManager


class ConnectDevicePlaceholder(QWidget):
    """Full-screen placeholder shown while no supported iPhone is connected.

    Occupies the iOS content stack on its own (outside the nav-bar root), so
    it renders edge-to-edge with no back button. Self-connects to the color
    theme signal and repaints via :meth:`_retheme`.
    """

    ICON_PX = 120

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setObjectName("iosContainer")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(18)
        layout.setAlignment(Qt.AlignCenter)

        self._icon_lbl = QLabel(self)
        self._icon_lbl.setFixedSize(self.ICON_PX, self.ICON_PX)
        self._icon_lbl.setAlignment(Qt.AlignCenter)
        self._icon_lbl.setStyleSheet("background-color: transparent;")
        layout.addWidget(self._icon_lbl, 0, Qt.AlignHCenter)

        self._title = QLabel(
            QCoreApplication.translate("Nugget", "No device connected"), self)
        self._title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._title)

        self._message = QLabel(
            QCoreApplication.translate(
                "Nugget", "Connect an Apple device with iOS 26.2+"), self)
        self._message.setAlignment(Qt.AlignCenter)
        self._message.setWordWrap(True)
        layout.addWidget(self._message)

        self._refresh_btn = IOSPrimaryButton(
            QCoreApplication.translate("Nugget", "Refresh"), self)
        self._refresh_btn.setFixedWidth(200)
        self._refresh_btn.clicked.connect(self._refresh)
        layout.addWidget(self._refresh_btn, 0, Qt.AlignHCenter)

        self._continue_btn = QPushButton(
            QCoreApplication.translate("Nugget", "Continue without a device"), self)
        self._continue_btn.setCursor(Qt.PointingHandCursor)
        self._continue_btn.clicked.connect(self.window.continue_without_device)
        layout.addWidget(self._continue_btn, 0, Qt.AlignHCenter)

        self._retheme()
        ColorThemeManager.instance().theme_changed.connect(self._retheme)

    def _refresh(self):
        try:
            self.window.refresh_devices()
        except Exception:
            pass

    def _retheme(self):
        c = ColorThemeManager.instance().colors
        self.setStyleSheet(t("page_bg"))
        self._icon_lbl.setPixmap(theme_pixmap(
            ":/icon/phone.svg", c.text_secondary, self.ICON_PX,
            self.devicePixelRatioF()))
        self._title.setStyleSheet(t("home_title"))
        self._message.setStyleSheet(t("home_subtitle"))
        self._continue_btn.setStyleSheet(t("mini_button"))
