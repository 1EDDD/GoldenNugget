"""Explain the selected device's support using the same local rules as the UI."""
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QPushButton

from src.controllers.hotload import HotLoad
from src.gui.ios.compat import compatibility_reasons
from src.gui.theme import ColorThemeManager, t
from src.tweaks.registry import SPECS
from src.tweaks.tweak_names import TweakID


def support_lines(manager):
    tr = lambda text: QCoreApplication.translate("Nugget", text)
    version = manager.get_current_device_version() or ""
    model = manager.get_current_device_model() or ""
    safety = HotLoad(manager.pref_manager.settings)
    context = dict(device_version=version, device_model=model)
    hidden = safety.hidden_tweak_names(**context)
    hidden_reasons = safety.hidden_feature_reasons(**context)
    supported = manager.get_current_device_is_supported_by_fork()
    lines = [tr("Device: {0} · iOS {1}").format(model, version)]
    if not supported:
        lines.append(tr("Applying tweaks requires iOS 26.2 or newer."))
    elif manager.get_current_device_partially_supported():
        lines.append(tr("Partially Supported: iOS 27 uses an experimental protective backup and restore workflow. This status does not mean every tweak is unavailable."))
    else:
        lines.append(tr("This iOS version is supported by GoldenNugget."))
    lines.append(tr("Availability below follows the app's compatibility rules; it is not a test of effects on the device."))
    available, unavailable, blocked = [], [], []
    kill = safety.kill_rule(**context)
    for spec in SPECS:
        if spec.disabled:
            continue
        title = tr(spec.title)
        label = f"{tr(spec.section.value)} — {title}"
        reasons = compatibility_reasons(spec.id, version, model)
        rule = safety.rule_for(spec.id, **context)
        if kill:
            blocked.append(f"{label}: {kill.get('reason') or tr('Application blocked by safety rules')}")
        elif spec.id.name in hidden:
            reason = hidden_reasons.get(safety.feature_for(spec.id))
            blocked.append(f"{label}: {reason or tr('Section hidden by safety rules')}")
        elif rule:
            blocked.append(f"{label}: {rule.get('reason') or tr('Blocked by safety rules')}")
        elif not supported:
            unavailable.append(f"{label}: {tr('Requires iOS 26.2 or newer')}")
        elif reasons:
            unavailable.append(f"{label}: {'; '.join(reasons)}")
        else:
            available.append(label)
    for title, entries in ((tr("Blocked by safety rules"), blocked),
                           (tr("Unavailable for this device"), unavailable)):
        lines.extend(["", f"{title} ({len(entries)})", *entries])
    hidden_features = sorted(safety.hidden_features(**context))
    if hidden_features:
        lines.extend(["", tr("Hidden feature pages"), *hidden_features])
    lines.extend(["", tr("Other feature pages")])
    for title, tid in (("PosterBoard", TweakID.PosterBoard),
                       ("Templates", TweakID.Templates),
                       ("Daemons", TweakID.Daemons),
                       ("Status Bar", TweakID.StatusBar),
                       ("Icon Themes", TweakID.IconThemes),
                       ("Passcode Theme", None)):
        rule = kill or (safety.rule_for(tid, **context) if tid is not None else None)
        feature = safety.feature_for(tid)
        if feature in hidden_reasons:
            state = hidden_reasons[feature] or tr("Section hidden by safety rules")
        elif rule:
            state = rule.get("reason") or tr("Blocked by safety rules")
        elif not supported:
            state = tr("Requires iOS 26.2 or newer")
        else:
            state = tr("No additional restrictions listed; setup requirements are shown on the page")
        lines.append(f"{tr(title)}: {state}")
    forced = safety.disabled_daemons(**context)
    if forced:
        lines.extend(["", tr("Services forced off by safety rules")])
        lines.extend(f"{name}: {reason or tr('Forced off by safety rules')}"
                     for name, reason in sorted(forced.items()))
    if not safety.is_enabled():
        lines.extend(["", tr("HotLoad safety rules are turned off in Settings.")])
    lines.extend(["", f"{tr('Available registry tweaks')} ({len(available)})", *available])
    return lines


class DeviceSupportDialog(QDialog):
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle(QCoreApplication.translate("Nugget", "Device compatibility"))
        self.resize(720, 540)
        layout = QVBoxLayout(self)
        self.details = QPlainTextEdit(self)
        self.details.setReadOnly(True)
        self.details.setPlainText("\n".join(support_lines(manager)))
        layout.addWidget(self.details)
        close = QPushButton(QCoreApplication.translate("Nugget", "Close"), self)
        close.setObjectName("cancelBtn")
        close.clicked.connect(self.reject)
        layout.addWidget(close)
        ColorThemeManager.instance().theme_changed.connect(self._retheme)
        self._retheme()

    def _retheme(self):
        self.setStyleSheet(t("confirm_dialog"))
        self.details.setStyleSheet(t("apply_preview_text"))
