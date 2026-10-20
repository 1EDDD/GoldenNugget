from PySide6.QtCore import QSettings

# Settings are stored under the "GoldenNugget" organization. Keys that are not
# present there fall back to the legacy "Nugget" organization so existing users
# keep their settings after the rename. Everything written goes to "GoldenNugget",
# which always takes priority when read back.

NEW_ORG = "GoldenNugget"
LEGACY_ORG = "Nugget"


class Settings:
    """Stores under "GoldenNugget" and reads through to "Nugget"."""

    def __init__(self, app: str = "settings"):
        self._primary = QSettings(NEW_ORG, app)
        self._legacy = QSettings(LEGACY_ORG, app)

    def allKeys(self) -> list[str]:
        """Return all known keys, including settings left in the legacy store.

        Keep the Qt QSettings-compatible spelling because callers use this
        wrapper in place of QSettings. Primary-store keys take precedence.
        """
        return sorted(set(self._legacy.allKeys()) | set(self._primary.allKeys()))

    def contains(self, key: str) -> bool:
        return self._primary.contains(key) or self._legacy.contains(key)

    def value(self, key: str, defaultValue=None, type=None):
        # PySide6 6.11's QSettings.value crashes (SIGBUS in shiboken's
        # checkType) when None is passed positionally for the `type` argument,
        # so only forward it when an actual type is given.
        store = self._primary if self._primary.contains(key) else self._legacy
        if type is None:
            return store.value(key, defaultValue)
        return store.value(key, defaultValue, type)

    def setValue(self, key: str, value):
        self._primary.setValue(key, value)

    def remove(self, key: str):
        self._primary.remove(key)
        self._legacy.remove(key)

    def sync(self):
        self._primary.sync()
        self._legacy.sync()



def settings_keys(settings) -> list[str]:
    """Return persisted setting keys across current and legacy settings stores.

    Older Settings wrappers used by existing checkouts may not expose the
    QSettings-compatible allKeys method. Keep callers resilient to those
    versions rather than letting a device refresh or pairing action crash.
    """
    getter = getattr(settings, "allKeys", None)
    if callable(getter):
        try:
            return sorted({str(key) for key in getter()})
        except (AttributeError, RuntimeError, TypeError):
            # Fall back to the wrapped QSettings stores below.
            pass

    keys: set[str] = set()
    for attribute in ("_primary", "_legacy"):
        store = getattr(settings, attribute, None)
        if store is None:
            continue
        for method_name in ("allKeys", "all_keys", "keys"):
            store_getter = getattr(store, method_name, None)
            if not callable(store_getter):
                continue
            try:
                keys.update(str(key) for key in store_getter())
                break
            except (AttributeError, RuntimeError, TypeError):
                continue

    # Support other QSettings-like wrappers as a final compatibility fallback.
    for method_name in ("all_keys", "keys"):
        fallback = getattr(settings, method_name, None)
        if not callable(fallback):
            continue
        try:
            keys.update(str(key) for key in fallback())
            break
        except (AttributeError, RuntimeError, TypeError):
            continue

    return sorted(keys)
