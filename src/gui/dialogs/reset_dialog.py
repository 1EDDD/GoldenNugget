from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QCheckBox, QVBoxLayout, QSizePolicy
from PySide6.QtCore import QCoreApplication
from src.gui.theme import ColorThemeManager, t

from src.gui.pages.pages_list import Page, get_resettable_pages

class ResetDialog(QDialog):
    def __init__(self, device_manager, apply_reset=lambda x: None, parent=None):
        super().__init__(parent)
        self.device_manager = device_manager
        self.apply_reset = apply_reset
        self.selected_pages: list[Page] = []

        QBtn = (
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )

        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.setWindowTitle(QCoreApplication.translate('Nugget', 'Restore Defaults'))
        self.buttonBox.button(QDialogButtonBox.Ok).setText(QCoreApplication.translate('Nugget', 'Restore Defaults'))
        self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(False)

        layout = QVBoxLayout()
        message = QLabel(QCoreApplication.translate('Nugget',
            'Select the sections whose original values you want to restore. Turning off a tweak only excludes it from the next apply.'))
        message.setWordWrap(True)
        message.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(message)

        pages = get_resettable_pages(self.device_manager)
        for page in pages:
            pageChk = QCheckBox(page.getPageName())
            pageChk.toggled.connect(lambda checked, p=page: self.toggle_page(checked, p))
            layout.addWidget(pageChk)

        layout.addWidget(self.buttonBox)
        self.setLayout(layout)
        self.setMinimumWidth(480)
        self._retheme()
        ColorThemeManager.instance().theme_changed.connect(self._retheme)

    def _retheme(self):
        self.setStyleSheet(t('confirm_dialog'))

    def toggle_page(self, checked: bool, page: Page):
        if checked:
            self.selected_pages.append(page)
        else:
            try:
                self.selected_pages.remove(page)
            except Exception:
                print("Page not found in list, ignoring error.")
        self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(bool(self.selected_pages))

    def accept(self):
        super().accept()
        if len(self.selected_pages) > 0:
            self.apply_reset(self.selected_pages)
        # otherwise, ignore
