"""Worker for pairing an iPhone over its local Wi-Fi IP address."""
import asyncio

from PySide6.QtCore import QThread, Signal


class WifiPairThread(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, hostname: str, parent=None):
        super().__init__(parent)
        self.hostname = hostname

    def run(self):
        try:
            result = asyncio.run(self._pair())
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.succeeded.emit(result)

    async def _pair(self):
        from pymobiledevice3.lockdown import create_using_tcp

        client = await asyncio.wait_for(
            create_using_tcp(
                hostname=self.hostname,
                autopair=True,
                pair_timeout=120.0,
                keep_alive=True,
            ),
            timeout=135.0,
        )
        try:
            if not getattr(client, "paired", False):
                raise RuntimeError(
                    "The iPhone did not confirm pairing. Unlock it and accept Trust on the iPhone."
                )
            values = client.all_values
            udid = values.get("UniqueDeviceID") or values.get("UDID")
            if not udid:
                raise RuntimeError("The device did not provide its UDID after pairing.")
            return {
                "hostname": self.hostname,
                "udid": str(udid),
                "name": str(values.get("DeviceName") or "iPhone"),
                "version": str(values.get("ProductVersion") or ""),
                "build": str(values.get("BuildVersion") or ""),
                "model": str(values.get("ProductType") or ""),
                "hardware": str(values.get("HardwareModel") or ""),
                "cpu": str(values.get("HardwarePlatform") or ""),
                "locale": await client.get_locale(),
            }
        finally:
            try:
                await client.close()
            except Exception:
                pass
