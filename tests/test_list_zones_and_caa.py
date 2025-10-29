#
# Tests for list_zones hardening and robust CAA parsing
#

from unittest import TestCase
from unittest.mock import Mock

from octodns.zone import Zone

from octodns_hetzner import HetznerProvider


class TestListZonesAndCAA(TestCase):
    def test_list_zones_filters_missing_names(self):
        p = HetznerProvider('test', 'token')
        p._client.domains = Mock(
            return_value=[
                {'id': 'z-ok', 'name': 'ok.com'},
                {'id': 'z-missing'},
                {'id': 'z-none', 'name': None},
                {'id': 'z-empty', 'name': ''},
            ]
        )
        self.assertEqual(['ok.com.'], p.list_zones())

    def test_list_zones_handles_exception_in_get(self):
        # Test that list_zones handles exceptions when calling .get('name')
        p = HetznerProvider('test', 'token')

        # Create a dict subclass that raises an exception when .get() is called
        class BadDomain(dict):
            def get(self, key):
                raise RuntimeError('get failed')

        bad_domain = BadDomain()
        bad_domain['id'] = 'z-bad'

        p._client.domains = Mock(
            return_value=[
                {'id': 'z-ok', 'name': 'ok.com'},
                bad_domain,  # This will trigger the exception handler on lines 285-286
                {'id': 'z-ok2', 'name': 'example.com'},
            ]
        )
        # Should skip the bad domain and return the good ones
        self.assertEqual(['example.com.', 'ok.com.'], p.list_zones())

    def test_populate_caa_parsing_variants(self):
        p = HetznerProvider('test', 'token')
        # Mock zone metadata and records
        p._client.zone_get = Mock(
            return_value={'id': 'unit.tests', 'name': 'unit.tests', 'ttl': 3600}
        )
        p._client.zone_records_get = Mock(
            return_value=[
                {
                    'type': 'CAA',
                    'id': 'c1',
                    'zone_id': 'unit.tests',
                    'name': '',
                    'value': '0 issue "ca.unit.tests"',
                    'ttl': 3600,
                },
                {
                    'type': 'CAA',
                    'id': 'c2',
                    'zone_id': 'unit.tests',
                    'name': '',
                    'value': '128 iodef "mailto:security@example.com"',
                    'ttl': 3600,
                },
                {
                    'type': 'CAA',
                    'id': 'c3',
                    'zone_id': 'unit.tests',
                    'name': '',
                    'value': '0 issuewild "pki.example.com"',
                    'ttl': 3600,
                },
                {
                    'type': 'CAA',
                    'id': 'c4',
                    'zone_id': 'unit.tests',
                    'name': '',
                    'value': 'malformed',  # triggers fallback
                    'ttl': 3600,
                },
            ]
        )

        zone = Zone('unit.tests.', [])
        p.populate(zone)

        caa = [r for r in zone.records if r._type == 'CAA']
        self.assertEqual(1, len(caa))
        values = sorted(
            [
                {'flags': v.flags, 'tag': v.tag, 'value': v.value}
                for v in caa[0].values
            ],
            key=lambda x: (x['flags'], x['tag'], x['value']),
        )

        self.assertIn(
            {'flags': 0, 'tag': 'issue', 'value': 'ca.unit.tests'}, values
        )
        self.assertIn(
            {
                'flags': 128,
                'tag': 'iodef',
                'value': 'mailto:security@example.com',
            },
            values,
        )
        self.assertIn(
            {'flags': 0, 'tag': 'issuewild', 'value': 'pki.example.com'}, values
        )
        # Fallback entry preserves raw string and uses default tag/flags
        self.assertIn(
            {'flags': 0, 'tag': 'issue', 'value': 'malformed'}, values
        )
