"""Worker for iOS 27 device-initiated Pair on Device pairing."""
import asyncio
import platform

from PySide6.QtCore import QThread, Signal


class WifiPairThread(QThread):
    pin_ready = Signal(str)
    status = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def run(self):
        try:
            result = asyncio.run(self._pair_host())
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.succeeded.emit(result)

    async def _pair_host(self):
        from pymobiledevice3.remote.tunnel_service import (
            PairableHostInfo,
            serve_pairable_host,
        )

        host_info = PairableHostInfo(name=platform.node() or "GoldenNugget PC")

        def pin_callback(pin: str):
            self.pin_ready.emit(str(pin))

        def waiting_callback(elapsed: float):
            self.status.emit(f"Waiting for iPhone… ({int(elapsed)}s)")

        self.status.emit(
            "Open Settings > Developer > Paired Macs on your iPhone, "
            "then tap this computer under Other Devices."
        )
        result = await serve_pairable_host(
            host_info,
            pin_callback=pin_callback,
            timeout=300,
            waiting_callback=waiting_callback,
        )
        peer = result.peer_device
        return {
            "udid": str(peer.udid),
            "device_name": str(peer.name),
            "device_model": str(peer.model),
            "record_path": str(result.record_path),
            "host_name": host_info.name,
        }
