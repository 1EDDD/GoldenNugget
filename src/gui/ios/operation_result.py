"""Persistent, dismissible result shared by Home and Apply."""
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QLabel, QPushButton, QPlainTextEdit, QVBoxLayout, QHBoxLayout

from src.gui.ios.components import IOSCard
from src.gui.theme import t


def result_text(success, error, reset_pages=None, preview=None):
    tr = lambda text: QCoreApplication.translate("Nugget", text)
    if not success:
        return (error or tr("Operation stopped before completion.")) + "\n\n" + tr(
            "Completion was not confirmed. Open the application log before retrying; follow any recovery instructions shown for your device.")
    lines = []
    if reset_pages is not None:
        lines.append(tr("Restored defaults for selected pages:"))
        lines.extend(tr(getattr(page, 'name', str(page))) for page in reset_pages)
    elif preview is not None:
        lines.append(tr("Settings included in the completed apply:"))
        entries = preview['entries']
        lines.extend(f"{tr(entry['section'])} — {tr(entry['title'])}" for entry in entries.values())
        if not entries:
            lines.append(tr("No plist settings selected."))
        if preview['queued']:
            lines.extend(["", tr("Packages included in the apply:")])
            lines.extend(f"{tr(section)} — {name}" for section, name in preview['queued'])
        skipped = preview['blocked'] + preview.get('skipped_packages', [])
        lines.extend(["", tr("Skipped: {0}").format(len(skipped))])
        lines.extend(tr(name) for name in preview['blocked'])
        lines.extend(preview.get('skipped_packages', []))
        if preview['forced']:
            lines.extend(["", tr("Services forced off by safety rules:"), *preview['forced']])
    else:
        lines.append(tr("Operation completed. A detailed selection summary is unavailable; see the application log."))
    lines.extend(["", tr("Next: check the result on your device. If you turned off Find My before applying, turn it back on after the operation is complete.")])
    return "\n".join(lines)


class OperationResultCard(IOSCard):
    def __init__(self, open_logs, dismiss, parent=None):
        super().__init__(parent)
        self._success = True
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        self.title = QLabel(self)
        self.title.setTextFormat(Qt.PlainText)
        layout.addWidget(self.title)
        self.details = QPlainTextEdit(self)
        self.details.setReadOnly(True)
        self.details.setMinimumHeight(120)
        self.details.setMaximumHeight(220)
        layout.addWidget(self.details)
        actions = QHBoxLayout()
        self.logs_btn = QPushButton(QCoreApplication.translate("Nugget", "Open application log"))
        self.logs_btn.clicked.connect(open_logs)
        self.close_btn = QPushButton(QCoreApplication.translate("Nugget", "Dismiss"))
        self.close_btn.clicked.connect(dismiss)
        actions.addWidget(self.logs_btn)
        actions.addStretch()
        actions.addWidget(self.close_btn)
        layout.addLayout(actions)
        self._retheme()
        self.hide()

    def show_result(self, success, text, is_reset=False):
        self._success = success
        self.title.setText(QCoreApplication.translate("Nugget",
            "Reset complete!" if success and is_reset else "Apply complete!" if success else "Operation failed or stopped"))
        self.details.setPlainText(text)
        self._retheme()
        self.show()

    def _retheme(self):
        super()._retheme()
        if not hasattr(self, 'title'):
            return
        self.title.setStyleSheet(t("process_status_green" if self._success else "process_status_red"))
        self.details.setStyleSheet(t("apply_preview_text"))
        self.logs_btn.setStyleSheet(t("mini_button"))
        self.close_btn.setStyleSheet(t("mini_button"))
