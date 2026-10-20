#!/usr/bin/env python3
"""Regression tests for the iOS 27 Pair on Device transport route."""

import unittest
from unittest.mock import patch

from src.devicemanagement import session


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


if __name__ == "__main__":
    unittest.main()
