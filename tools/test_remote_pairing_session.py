#!/usr/bin/env python3
"""Regression tests for the iOS 27 Pair on Device transport route."""

import asyncio
import plistlib
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.devicemanagement import session
from src.gui.thread_workers.wifi_pair_worker import WifiPairThread


class _FakeProvider:
    def __init__(self, udid):
        self.udid = udid


class _FakeRsdTunnel:
    def __init__(self, provider):
        self.provider = provider
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self.provider

    async def __aexit__(self, exc_type, exc, tb):
        self.exited = True
        return False


class _FakeLockdown:
    paired = True

    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class RemotePairingSessionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._remote_before = dict(session._REMOTE_PAIRING_DEVICES)
        self._network_before = dict(session._NETWORK_ENDPOINTS)
        session._REMOTE_PAIRING_DEVICES.clear()
        session._NETWORK_ENDPOINTS.clear()

    def tearDown(self):
        session._REMOTE_PAIRING_DEVICES.clear()
        session._REMOTE_PAIRING_DEVICES.update(self._remote_before)
        session._NETWORK_ENDPOINTS.clear()
        session._NETWORK_ENDPOINTS.update(self._network_before)

    async def test_registered_pair_on_device_uses_rsd_tunnel(self):
        udid = "A1B2-C3D4"
        session.register_remote_pairing_device(udid)
        self.assertEqual(
            session.get_registered_remote_pairing_devices(),
            (udid,),
        )

        provider = _FakeProvider("a1b2c3d4")
        tunnel = _FakeRsdTunnel(provider)
        with patch.object(session, "_preferred_rsd_tunnel", return_value=tunnel) as factory:
            async with session.lockdown_session(udid, autopair=False) as actual:
                self.assertIs(actual, provider)
                self.assertTrue(tunnel.entered)
                self.assertFalse(tunnel.exited)

        factory.assert_called_once_with(udid)
        self.assertTrue(tunnel.exited)

    async def test_explicit_usbmux_still_overrides_remote_pair_registration(self):
        udid = "A1B2-C3D4"
        session.register_remote_pairing_device(udid)
        lockdown = _FakeLockdown()

        async def fake_create_using_usbmux(**kwargs):
            self.assertEqual(kwargs["serial"], udid)
            return lockdown

        with (
            patch.object(session, "_preferred_rsd_tunnel") as remote_factory,
            patch.object(session, "create_using_usbmux", side_effect=fake_create_using_usbmux),
        ):
            async with session.lockdown_session(udid, autopair=False, use_network=False) as actual:
                self.assertIs(actual, lockdown)

        remote_factory.assert_not_called()
        self.assertTrue(lockdown.closed)

    async def test_remote_tunnel_identity_must_match_requested_device(self):
        expected = "A1B2-C3D4"
        session.register_remote_pairing_device(expected)
        tunnel = _FakeRsdTunnel(_FakeProvider("FFFF-EEEE"))

        with patch.object(session, "_preferred_rsd_tunnel", return_value=tunnel):
            with self.assertRaisesRegex(RuntimeError, "different device"):
                async with session.lockdown_session(expected, use_remote_pairing=True):
                    self.fail("A mismatched RemoteXPC provider must never be yielded")

        self.assertTrue(tunnel.exited)

    async def test_pair_on_device_uses_saved_remote_pairing_service_no_root(self):
        udid = "A1B2-C3D4"

        class FakeTun:
            def __init__(self):
                self.peer = None

            def set_peer(self, address):
                self.peer = address

        class FakeTunnelClient:
            def __init__(self):
                self.tun = FakeTun()

            async def wait_closed(self):
                await asyncio.Future()

        class FakePairingProvider:
            def __init__(self):
                self.client = FakeTunnelClient()
                self.closed = False

            @asynccontextmanager
            async def start_tcp_tunnel(self):
                yield SimpleNamespace(
                    client=self.client,
                    address="fd00::1",
                    port=58743,
                    auxiliary_metadata={},
                )

            async def close(self):
                self.closed = True

        class FakeDialPlane:
            def __init__(self, tun, address):
                self.tun = tun
                self.address = address
                self.dial = AsyncMock()

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        class FakeRsd:
            def __init__(self, address, open_connection, auxiliary_metadata):
                self.address = address
                self.open_connection = open_connection
                self.auxiliary_metadata = auxiliary_metadata
                self.udid = None
                self.closed = False
                self.start_service_calls = []

            async def connect(self):
                self.udid = udid

            async def start_lockdown_service(self, name, include_escrow_bag=False):
                self.start_service_calls.append((name, include_escrow_bag))
                return "started"

            async def close(self):
                self.closed = True

        from pymobiledevice3.remote import userspace_tunnel, tunnel_service
        from pymobiledevice3.remote import remote_service_discovery
        from pymobiledevice3 import pair_records

        provider = FakePairingProvider()
        with (
            patch.object(userspace_tunnel, "_active_tunnel", None),
            patch.object(userspace_tunnel, "USERSPACE_ACTIVE", False),
            patch.object(tunnel_service, "USE_USERSPACE_TUNNEL", False),
            patch.object(
                tunnel_service,
                "get_remote_pairing_tunnel_services",
                new=AsyncMock(return_value=[provider]),
            ) as discover,
            patch.object(userspace_tunnel, "UserspaceDialPlane", FakeDialPlane),
            patch.object(remote_service_discovery, "RemoteServiceDiscoveryService", FakeRsd),
            patch.object(pair_records, "get_local_pairing_record", return_value={"remote_unlock_host_key": ""}),
        ):
            tunnel = session._preferred_rsd_tunnel(udid)
            async with tunnel as rsd:
                self.assertEqual(rsd.udid, udid)
                self.assertEqual(rsd.address, ("fd00::1", 58743))
                self.assertEqual(provider.client.tun.peer, "fd00::1")
                await rsd.start_lockdown_service(
                    "com.apple.mobilebackup2.shim.remote", include_escrow_bag=True
                )
                self.assertEqual(
                    rsd.start_service_calls,
                    [("com.apple.mobilebackup2.shim.remote", False)],
                )
            discover.assert_awaited_once_with(udid=udid, bonjour_timeout=8.0)
        self.assertTrue(provider.closed)

    async def test_remote_unlock_key_is_persisted_without_dropping_pairable_host_identity(self):
        record = {
            "private_key": b"p" * 32,
            "host_identifier": "STABLE-HOST-ID",
            "host_alt_irk": b"h" * 16,
            "peer_alt_irk": b"d" * 16,
            "remote_unlock_host_key": "",
        }
        with tempfile.TemporaryDirectory() as temp:
            record_path = Path(temp) / "remote_A1B2-C3D4.plist"
            record_path.write_bytes(plistlib.dumps(record))

            class FakeUnlockProvider:
                pair_record_path = record_path
                remote_identifier = "A1B2-C3D4"
                remote_unlock_host_key = ""

                async def _create_remote_unlock(self):
                    self.remote_unlock_host_key = "base64-encoded-remote-key"

            provider = FakeUnlockProvider()
            self.assertTrue(await session._ensure_remote_unlock_key(provider))
            updated = plistlib.loads(record_path.read_bytes())
            self.assertEqual(updated["remote_unlock_host_key"], "base64-encoded-remote-key")
            self.assertEqual(updated["host_identifier"], "STABLE-HOST-ID")
            self.assertEqual(updated["host_alt_irk"], b"h" * 16)
            self.assertEqual(updated["peer_alt_irk"], b"d" * 16)

    async def test_remote_unlock_key_helper_does_not_request_a_key_twice(self):
        record = {"remote_unlock_host_key": "already-present"}
        with tempfile.TemporaryDirectory() as temp:
            record_path = Path(temp) / "remote_A1B2-C3D4.plist"
            record_path.write_bytes(plistlib.dumps(record))

            class FakeUnlockProvider:
                pair_record_path = record_path
                remote_identifier = "A1B2-C3D4"

                async def _create_remote_unlock(self):
                    raise AssertionError("existing key should be reused")

            self.assertTrue(await session._ensure_remote_unlock_key(FakeUnlockProvider()))

    def test_pairing_worker_reuses_host_identity_from_saved_record(self):
        record = {
            "host_identifier": "STABLE-HOST-ID",
            "host_alt_irk": b"i" * 16,
            "private_key": b"k" * 32,
        }
        with tempfile.TemporaryDirectory() as temp:
            record_path = Path(temp) / "pair-record.plist"
            record_path.write_bytes(plistlib.dumps(record))
            worker = WifiPairThread(None, [str(record_path)])
            self.assertEqual(worker._load_host_identity(), {
                "identifier": "STABLE-HOST-ID",
                "alt_irk": b"i" * 16,
                "private_key": b"k" * 32,
            })


if __name__ == "__main__":
    unittest.main()
