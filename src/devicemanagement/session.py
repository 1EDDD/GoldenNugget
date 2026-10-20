"""Single entry point for opening device service sessions.

USB and usbmux-discovered Wi-Fi devices use lockdown/usbmux. Legacy manually
paired TCP endpoints remain supported. iOS 27 "Pair on Device" records use a
no-root RemoteXPC tunnel, exposed by pymobiledevice3 as an RSD service provider.
"""
from contextlib import asynccontextmanager
from typing import Optional

from pymobiledevice3.exceptions import NotPairedError
from pymobiledevice3.lockdown import create_using_tcp, create_using_usbmux


_NETWORK_ENDPOINTS: dict[str, str] = {}
_REMOTE_PAIRING_DEVICES: dict[str, str] = {}


def _normalise_udid(value: Optional[str]) -> str:
    return str(value or "").replace("-", "").casefold()


def register_network_endpoint(udid: str, hostname: str) -> None:
    """Route subsequent sessions for a UDID through its paired TCP endpoint."""
    if not udid or not hostname:
        return
    _NETWORK_ENDPOINTS[_normalise_udid(udid)] = hostname.strip()


def get_registered_network_endpoints() -> dict[str, str]:
    """Return a copy of the in-memory UDID -> host map."""
    return dict(_NETWORK_ENDPOINTS)


def register_remote_pairing_device(udid: str) -> None:
    """Register a device paired through iOS 27's device-initiated Pair on Device."""
    if not udid:
        return
    _REMOTE_PAIRING_DEVICES[_normalise_udid(udid)] = str(udid)


def get_registered_remote_pairing_devices() -> tuple[str, ...]:
    """Return the original UDIDs registered for RemoteXPC pairing."""
    return tuple(_REMOTE_PAIRING_DEVICES.values())


def _preferred_rsd_tunnel(serial: str):
    """Return pymobiledevice3's cross-platform, no-root RSD tunnel context."""
    from pymobiledevice3.remote.rsd_tunnel import PreferredRsdTunnel

    return PreferredRsdTunnel(serial=serial)


@asynccontextmanager
async def lockdown_session(serial: Optional[str] = None, *,
                           autopair: bool = True,
                           pair_timeout: Optional[float] = 120.0,
                           use_network: Optional[bool] = None,
                           use_remote_pairing: Optional[bool] = None):
    """Open and safely close a lockdown/RSD service-provider session.

    :param serial: usbmux serial / UDID.
    :param autopair: request the lockdown trust dialog if not paired.
    :param pair_timeout: seconds to wait for lockdown trust acceptance.
    :param use_network: True forces a saved legacy TCP endpoint; False forces
        usbmux; None follows the registered transport for this UDID.
    :param use_remote_pairing: True forces an iOS 27 RemoteXPC tunnel; False
        disables that route; None follows the registered transport.
    """
    normalized = _normalise_udid(serial)
    hostname = _NETWORK_ENDPOINTS.get(normalized) if use_network is not False else None
    if use_network is True and not hostname:
        raise ValueError(f"No saved Wi-Fi endpoint for device {serial!r}")

    should_use_remote = (
        use_remote_pairing is True
        or (
            use_remote_pairing is None
            and use_network is not False
            and normalized in _REMOTE_PAIRING_DEVICES
            and not hostname
        )
    )

    if should_use_remote:
        if not serial:
            raise ValueError("A device UDID is required for RemoteXPC pairing")
        async with _preferred_rsd_tunnel(str(serial)) as rsd:
            actual_udid = getattr(rsd, "udid", None)
            if actual_udid and _normalise_udid(actual_udid) != normalized:
                raise RuntimeError(
                    "RemoteXPC connected to a different device than requested "
                    f"(expected {serial}, received {actual_udid})"
                )
            yield rsd
        return

    if hostname:
        ld = await create_using_tcp(
            hostname=hostname, autopair=autopair, pair_timeout=pair_timeout,
            keep_alive=True,
        )
    else:
        ld = await create_using_usbmux(
            serial=serial, autopair=autopair, pair_timeout=pair_timeout
        )

    try:
        if autopair and not getattr(ld, "paired", False):
            raise NotPairedError("device did not confirm trust")
        yield ld
    finally:
        try:
            await ld.close()
        except Exception:
            pass
