#
# Ensure provider __init__ 'backend=hcloud' branch is covered without real hcloud
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

    def test_init_hcloud_backend_branch(self):
        p = HetznerProvider('init-test', 'token', backend='hcloud')
        # Backend flag remembered
        self.assertEqual('hcloud', p._backend)
        # list_zones calls through and returns an empty list
        self.assertEqual([], p.list_zones())

    def test_init_invalid_backend(self):
        """Test that invalid backend raises ValueError with helpful message"""
        with self.assertRaises(ValueError) as ctx:
            HetznerProvider('init-test', 'token', backend='invalid')
        self.assertIn("Invalid backend 'invalid'", str(ctx.exception))
        self.assertIn("Must be 'dnsapi' or 'hcloud'", str(ctx.exception))
