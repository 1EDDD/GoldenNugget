"""Worker for iOS 27 device-initiated Pair on Device pairing."""

import asyncio
import platform
import plistlib
from pathlib import Path

from PySide6.QtCore import QThread, Signal


class WifiPairThread(QThread):
    pin_ready = Signal(str)
    status = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, parent=None, existing_record_paths=None):
        super().__init__(parent)
        self.existing_record_paths = tuple(existing_record_paths or ())

    def _load_host_identity(self):
        """Reuse the computer identity from an earlier Pair on Device record.

        An iPhone remembers the host identifier and IRK. Generating a new IRK
        with the same identifier can make later pair-setup attempts fail or
        cause the host to disappear from the phone's known-peer list.
        """
        for record_path in self.existing_record_paths:
            try:
                record = plistlib.loads(Path(record_path).read_bytes())
            except Exception:
                # Ignore stale/corrupt old records and try the next saved device.
                continue

            identifier = record.get("host_identifier")
            host_alt_irk = record.get("host_alt_irk")
            private_key = record.get("private_key")
            if (
                isinstance(identifier, str)
                and identifier
                and isinstance(host_alt_irk, bytes)
                and len(host_alt_irk) == 16
                and isinstance(private_key, bytes)
                and len(private_key) == 32
            ):
                return {
                    "identifier": identifier,
                    "alt_irk": host_alt_irk,
                    "private_key": private_key,
                }
        return None

    def run(self):
        try:
            result = asyncio.run(self._pair_host())
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.succeeded.emit(result)

    async def _pair_host(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from pymobiledevice3.remote.tunnel_service import (
            PairableHostInfo,
            serve_pairable_host,
        )

        identity = self._load_host_identity()
        kwargs = {}
        if identity:
            host_info = PairableHostInfo(
                name=platform.node() or "GoldenNugget PC",
                identifier=identity["identifier"],
                alt_irk=identity["alt_irk"],
            )
            kwargs["ed25519_private_key"] = Ed25519PrivateKey.from_private_bytes(
                identity["private_key"]
            )
        else:
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
            **kwargs,
        )
        peer = result.peer_device
        if not peer.udid:
            raise RuntimeError(
                "The iPhone completed the pairing handshake but did not provide a device UDID. "
                "GoldenNugget cannot safely register the device without it."
            )
        return {
            "udid": str(peer.udid),
            "device_name": str(peer.name),
            "device_model": str(peer.model),
            "record_path": str(result.record_path),
            "host_name": host_info.name,
        }
