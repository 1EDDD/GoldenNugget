"""Single entry point for opening lockdown connections.

USB and usbmux-discovered Wi-Fi devices use usbmux. Devices paired directly by IP
use a persisted UDID -> hostname mapping so all later service sessions use TCP.
"""
from contextlib import asynccontextmanager
from typing import Optional

from pymobiledevice3.exceptions import NotPairedError
from pymobiledevice3.lockdown import create_using_tcp, create_using_usbmux


_NETWORK_ENDPOINTS: dict[str, str] = {}


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


@asynccontextmanager
async def lockdown_session(serial: Optional[str] = None, *,
                           autopair: bool = True,
                           pair_timeout: Optional[float] = 120.0,
                           use_network: Optional[bool] = None):
    """Open and safely close a lockdown connection.

    :param serial: usbmux serial / UDID.
    :param autopair: request the on-device trust dialog if not paired.
    :param pair_timeout: seconds to wait for trust acceptance.
    :param use_network: True forces the saved TCP endpoint; False forces usbmux;
        None uses TCP only for UDIDs registered by the Wi-Fi pairing flow.
    """
    hostname = _NETWORK_ENDPOINTS.get(_normalise_udid(serial)) if use_network is not False else None
    if use_network is True and not hostname:
        raise ValueError(f"No saved Wi-Fi endpoint for device {serial!r}")

    if hostname:
        ld = await create_using_tcp(
            hostname=hostname, autopair=autopair, pair_timeout=pair_timeout
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
