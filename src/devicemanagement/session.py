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


def unregister_remote_pairing_device(udid: str) -> None:
    """Remove a device's active RemoteXPC preference without deleting its saved record."""
    if udid:
        _REMOTE_PAIRING_DEVICES.pop(_normalise_udid(udid), None)


def get_registered_remote_pairing_devices() -> tuple[str, ...]:
    """Return the original UDIDs registered for RemoteXPC pairing."""
    return tuple(_REMOTE_PAIRING_DEVICES.values())


async def _ensure_remote_unlock_key(provider) -> bool:
    """Populate a Pair-on-Device record's remote-unlock key when the peer supports it.

    PairableHost's initial record deliberately contains an empty key. Some RSD
    services, including mobilebackup2's remote shim, need this key in the RSD
    check-in EscrowBag. The paired RemotePairing control connection can request
    the key after pair-verify has established its encrypted session.
    """
    import logging
    import plistlib

    logger = logging.getLogger(__name__)
    try:
        record_path = provider.pair_record_path
        record = plistlib.loads(record_path.read_bytes())
    except Exception as exc:
        logger.warning("Could not read Pair-on-Device record for remote unlock: %s", exc)
        return False

    if not isinstance(record, dict):
        logger.warning("Pair-on-Device record is not a dictionary; skipping remote unlock setup")
        return False
    if record.get("remote_unlock_host_key"):
        return True

    try:
        await provider._create_remote_unlock()
    except Exception as exc:
        logger.warning("The paired device could not provide a remote-unlock key: %s", exc)
        return False

    remote_unlock_key = getattr(provider, "remote_unlock_host_key", None)
    if not remote_unlock_key:
        logger.info("The paired device does not expose a remote-unlock key")
        return False

    # Preserve the PairableHost identity fields. RemotePairingProtocol.save_pair_record()
    # would rewrite this file in the host-initiated record format and drop
    # host_identifier/host_alt_irk, which Pair-on-Device needs for future verify.
    record["remote_unlock_host_key"] = remote_unlock_key
    temporary_path = record_path.with_name(record_path.name + ".tmp")
    try:
        temporary_path.write_bytes(plistlib.dumps(record))
        temporary_path.replace(record_path)
    except OSError as exc:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        logger.warning("Could not persist remote-unlock key to pairing record: %s", exc)
        return False

    logger.info("Stored remote-unlock key in Pair-on-Device record for %s", provider.remote_identifier)
    return True


def _preferred_rsd_tunnel(serial: str):
    """Return a no-root RemotePairing RSD tunnel for a device-initiated pairing.

    pymobiledevice3's generic PreferredRsdTunnel tries USB lockdown first on modern
    iOS. A device that was paired under iOS 27 Settings > Developer > Paired Macs
    may only advertise the RemotePairing service over Wi-Fi, so use the same
    userspace tunnel machinery but select that paired service directly.
    """
    from pymobiledevice3.remote.userspace_tunnel import UserspaceRsdTunnel

    class PairOnDeviceRsdTunnel(UserspaceRsdTunnel):
        async def _aopen_locked(self):
            import asyncio
            from contextlib import AsyncExitStack
            from pymobiledevice3.remote import userspace_tunnel, tunnel_service
            from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
            from pymobiledevice3.common import get_home_folder
            from pymobiledevice3.pair_records import get_local_pairing_record, get_remote_pairing_record_filename

            if userspace_tunnel._active_tunnel is not None:
                raise RuntimeError(
                    "A RemoteXPC userspace tunnel is already active in this process. "
                    "Close the active device operation before pairing another device."
                )

            tunnel_service.USE_USERSPACE_TUNNEL = True
            stack = AsyncExitStack()
            try:
                services = await tunnel_service.get_remote_pairing_tunnel_services(
                    udid=self.serial,
                    bonjour_timeout=8.0,
                )
                if not services:
                    raise RuntimeError(
                        "No RemotePairing service was found for this iOS 27 pairing. "
                        "Keep the iPhone awake, unlock it, and ensure both devices share Wi-Fi."
                    )
                provider = services[0]
                stack.push_async_callback(provider.close)
                for unused in services[1:]:
                    try:
                        await unused.close()
                    except Exception:
                        pass

                # PairableHost initially persists an empty remote_unlock_host_key.
                # Ask for it over the already-verified RemotePairing control connection
                # before starting services that need an escrow bag.
                await _ensure_remote_unlock_key(provider)

                tunnel_result = await stack.enter_async_context(provider.start_tcp_tunnel())
                self.tun = tunnel_result.client.tun
                self.tun.set_peer(tunnel_result.address)

                dial_plane = await stack.enter_async_context(
                    userspace_tunnel.UserspaceDialPlane(self.tun, tunnel_result.address)
                )
                pairing_udid = self.serial

                class PairOnDeviceRemoteServiceDiscoveryService(RemoteServiceDiscoveryService):
                    async def start_lockdown_service(self, name: str, include_escrow_bag: bool = False):
                        # PairableHost records initially have an empty key. Never
                        # send an empty EscrowBag; it can cause RSD to reject the
                        # StartService request instead of reporting a useful error.
                        if include_escrow_bag:
                            try:
                                record = get_local_pairing_record(
                                    get_remote_pairing_record_filename(pairing_udid),
                                    get_home_folder(),
                                )
                            except Exception:
                                record = None
                            if not record or not record.get("remote_unlock_host_key"):
                                include_escrow_bag = False
                        return await super().start_lockdown_service(
                            name, include_escrow_bag=include_escrow_bag
                        )

                rsd = PairOnDeviceRemoteServiceDiscoveryService(
                    (tunnel_result.address, tunnel_result.port),
                    open_connection=dial_plane.dial,
                    auxiliary_metadata=tunnel_result.auxiliary_metadata,
                )
                stack.push_async_callback(rsd.close)
                await rsd.connect()

                if str(getattr(rsd, "udid", "")).replace("-", "").casefold() != str(
                    self.serial
                ).replace("-", "").casefold():
                    raise RuntimeError(
                        "RemotePairing reached a different device than the saved pairing record."
                    )
            except BaseException:
                await stack.aclose()
                tunnel_service.USE_USERSPACE_TUNNEL = False
                self.tun = None
                raise

            self._exit_stack = stack
            self.rsd = rsd
            # Keep ownership explicit if recovery must retain RSD beyond its context.
            rsd._pair_on_device_tunnel_owner = self
            userspace_tunnel._active_tunnel = self
            userspace_tunnel.USERSPACE_ACTIVE = True
            self._transport_watcher = asyncio.create_task(
                self._watch_transport_closed(tunnel_result.client),
                name=f"pair-on-device-tunnel-watcher-{tunnel_result.address}",
            )
            return rsd

    return PairOnDeviceRsdTunnel(serial=serial, autopair=False, remotepairing_fallback=False)


def is_remote_pairing_registered(serial: Optional[str]) -> bool:
    """Whether the given UDID was registered through iOS 27 Pair on Device."""
    return _normalise_udid(serial) in _REMOTE_PAIRING_DEVICES


async def open_remote_pairing_session(serial: str):
    """Open an RSD provider whose userspace tunnel remains alive for the caller.

    Unlike lockdown_session, this returns an explicitly owned live session.
    Call close_device_session when finished to close the RSD and tunnel.
    """
    tunnel = _preferred_rsd_tunnel(str(serial))
    rsd = await tunnel.aopen()
    rsd._pair_on_device_tunnel_owner = tunnel
    return rsd


async def close_device_session(provider) -> None:
    """Close a USB provider or both halves of a Pair-on-Device RSD session."""
    tunnel = getattr(provider, "_pair_on_device_tunnel_owner", None)
    if tunnel is not None:
        await tunnel.aclose()
        return
    close = getattr(provider, "close", None)
    if callable(close):
        await close()


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
