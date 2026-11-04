#
# Ensure provider __init__ backend handling is covered without real hcloud
#

import sys
from types import ModuleType
from unittest import TestCase

from octodns_hetzner import HetznerProvider


class DummyZones:
    def get_all(self):
        return []


class DummyHCloudClient:
    def __init__(self, token):
        self.zones = DummyZones()


class TestProviderBackendInit(TestCase):
    def setUp(self):
        # Install fake hcloud module so adapter can import/instantiate safely
        self._orig = sys.modules.get('hcloud')
        mod = ModuleType('hcloud')
        mod.Client = DummyHCloudClient
        sys.modules['hcloud'] = mod

    def tearDown(self):
        if self._orig is None:
            sys.modules.pop('hcloud', None)
        else:
            sys.modules['hcloud'] = self._orig

    def test_init_default_backend(self):
        p = HetznerProvider('init-test', 'token')
        # list_zones calls through and returns an empty list
        self.assertEqual([], p.list_zones())

    def test_init_hcloud_backend(self):
        # Explicit backend='hcloud' keeps working for existing configs
        p = HetznerProvider('init-test', 'token', backend='hcloud')
        self.assertEqual([], p.list_zones())

    def test_init_dnsapi_backend_removed(self):
        """Test that backend='dnsapi' raises ValueError with migration guidance"""
        with self.assertRaises(ValueError) as ctx:
            HetznerProvider('init-test', 'token', backend='dnsapi')
        self.assertIn(
            "backend='dnsapi' is no longer supported", str(ctx.exception)
        )
        self.assertIn("Hetzner Cloud API token", str(ctx.exception))

    def test_init_invalid_backend(self):
        """Test that invalid backend raises ValueError with helpful message"""
        with self.assertRaises(ValueError) as ctx:
            HetznerProvider('init-test', 'token', backend='invalid')
        self.assertIn("Invalid backend 'invalid'", str(ctx.exception))
        self.assertIn("Must be 'hcloud'", str(ctx.exception))
