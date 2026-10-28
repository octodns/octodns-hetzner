#
#
#

import json
from os.path import dirname, join
from unittest import TestCase
from unittest.mock import Mock, call

from octodns.provider.yaml import YamlProvider
from octodns.record import Record
from octodns.zone import Zone

from octodns_hetzner import (
    HetznerClientNotFound,
    HetznerClientUnauthorized,
    HetznerProvider,
)


class TestHetznerProvider(TestCase):
    expected = Zone('unit.tests.', [])
    source = YamlProvider(
        'test', join(dirname(__file__), 'config'), escaped_semicolons=False
    )
    source.populate(expected)

    def _provider_with_mock_client(self, **kwargs):
        provider = HetznerProvider('test', 'token', **kwargs)
        client = Mock()
        provider._client = client
        return provider, client

    def _fixture(self, name):
        with open(join(dirname(__file__), 'fixtures', name)) as fh:
            return json.load(fh)

    def test_populate(self):
        provider, client = self._provider_with_mock_client()

        # Non-existent zone doesn't populate anything
        client.zone_get.side_effect = HetznerClientNotFound
        zone = Zone('unit.tests.', [])
        self.assertFalse(provider.populate(zone))
        self.assertEqual(set(), zone.records)

        # No diffs == no changes
        client.zone_get.side_effect = None
        client.zone_get.return_value = self._fixture('hetzner-zones.json')[
            'zones'
        ][0]
        records = self._fixture('hetzner-records.json')['records']
        for record in records:
            if record['name'] == '@':
                record['name'] = ''
        client.zone_records_get.return_value = records

        zone = Zone('unit.tests.', [])
        self.assertTrue(provider.populate(zone))
        self.assertEqual(15, len(zone.records))
        changes = self.expected.changes(zone, provider)
        self.assertEqual(0, len(changes))

        # 2nd populate makes no network calls/all from cache
        client.zone_records_get.reset_mock()
        again = Zone('unit.tests.', [])
        provider.populate(again)
        self.assertEqual(15, len(again.records))
        client.zone_records_get.assert_not_called()

    def test_apply(self):
        provider, client = self._provider_with_mock_client(
            strict_supports=False
        )

        # non-existent domain, create everything
        client.zone_get.side_effect = HetznerClientNotFound
        client.zone_create.return_value = {
            'id': 'unit.tests',
            'name': 'unit.tests',
            'ttl': 3600,
        }
        plan = provider.plan(self.expected)

        # One RRSet per supported name+type
        n = len(self.expected.records) - 7
        self.assertEqual(n, len(plan.changes))
        self.assertEqual(n, provider.apply(plan))
        self.assertFalse(plan.exists)

        client.zone_create.assert_called_once_with('unit.tests')
        client.rrset_upsert.assert_has_calls(
            [
                call('unit.tests', '', 'A', ['1.2.3.4', '1.2.3.5'], 300),
                call(
                    'unit.tests', '', 'CAA', ['0 issue "ca.unit.tests"'], 3600
                ),
                call(
                    'unit.tests',
                    '',
                    'NS',
                    ['ns1.unit.tests.', 'ns2.unit.tests.'],
                    3600,
                ),
                call('unit.tests', '_imap._tcp', 'SRV', ['0 0 0 .'], 600),
                call('unit.tests', '_pop3._tcp', 'SRV', ['0 0 0 .'], 600),
                call(
                    'unit.tests',
                    '_srv._tcp',
                    'SRV',
                    [
                        '10 20 30 foo-1.unit.tests.',
                        '12 20 30 foo-2.unit.tests.',
                    ],
                    600,
                ),
                call(
                    'unit.tests',
                    'aaaa',
                    'AAAA',
                    ['2601:644:500:e210:62f8:1dff:feb8:947a'],
                    600,
                ),
                call('unit.tests', 'cname', 'CNAME', ['unit.tests.'], 300),
                call('unit.tests', 'included', 'CNAME', ['unit.tests.'], 3600),
                call(
                    'unit.tests',
                    'mx',
                    'MX',
                    [
                        '10 smtp-4.unit.tests.',
                        '20 smtp-2.unit.tests.',
                        '30 smtp-3.unit.tests.',
                        '40 smtp-1.unit.tests.',
                    ],
                    300,
                ),
                call('unit.tests', 'ptr', 'PTR', ['foo.bar.com.'], 300),
                call('unit.tests', 'sub', 'NS', ['6.2.3.4.', '7.2.3.4.'], 3600),
                call(
                    'unit.tests',
                    'txt',
                    'TXT',
                    [
                        '"Bah bah black sheep"',
                        '"have you any wool."',
                        '"v=DKIM1;k=rsa;s=email;h=sha256;'
                        'p=A/kinda+of/long/string+with+numb3rs"',
                    ],
                    600,
                ),
                call('unit.tests', 'www', 'A', ['2.2.3.6'], 300),
                call('unit.tests', 'www.sub', 'A', ['2.2.3.6'], 300),
            ],
            any_order=True,
        )
        self.assertEqual(n, client.rrset_upsert.call_count)

        client.reset_mock()

        # delete 1 and update 1
        client.zone_get.side_effect = None
        client.zone_get.return_value = {
            'id': 'unit.tests',
            'name': 'unit.tests',
            'ttl': 3600,
        }
        client.zone_records_get.return_value = [
            {
                'type': 'A',
                'id': 'one',
                'zone_id': 'unit.tests',
                'name': 'www',
                'value': '1.2.3.4',
                'ttl': 300,
            },
            {
                'type': 'A',
                'id': 'two',
                'zone_id': 'unit.tests',
                'name': 'www',
                'value': '2.2.3.4',
                'ttl': 300,
            },
            {
                'type': 'A',
                'id': 'three',
                'zone_id': 'unit.tests',
                'name': 'ttl',
                'value': '3.2.3.4',
                'ttl': 600,
            },
        ]

        wanted = Zone('unit.tests.', [])
        wanted.add_record(
            Record.new(
                wanted, 'ttl', {'ttl': 300, 'type': 'A', 'value': '3.2.3.4'}
            )
        )

        plan = provider.plan(wanted)
        self.assertTrue(plan.exists)
        self.assertEqual(2, len(plan.changes))
        self.assertEqual(2, provider.apply(plan))
        client.zone_create.assert_not_called()
        # Update replaces the ttl RRSet, delete removes the whole www RRSet
        client.rrset_upsert.assert_called_once_with(
            'unit.tests', 'ttl', 'A', ['3.2.3.4'], 300
        )
        client.rrset_delete.assert_called_once_with('unit.tests', 'www', 'A')

    def test_list_zones(self):
        provider, client = self._provider_with_mock_client()
        client.domains.return_value = self._fixture('hetzner-zones.json')[
            'zones'
        ]

        self.assertEqual(['unit.tests.'], provider.list_zones())

    def test_exceptions(self):
        self.assertEqual('Not Found', str(HetznerClientNotFound()))
        self.assertEqual('Unauthorized', str(HetznerClientUnauthorized()))

    def test_hcloud_backend_import_error(self):
        """Test ImportError when hcloud backend is requested but unavailable."""
        import sys
        from unittest.mock import MagicMock

        # Save original module
        orig_hcloud_adapter = sys.modules.get('octodns_hetzner.hcloud_adapter')

        try:
            # Create a mock module that raises ImportError when HCloudZonesClient is accessed
            mock_module = MagicMock()
            type(mock_module).HCloudZonesClient = property(
                lambda self: (_ for _ in ()).throw(
                    ImportError("No module named 'hcloud'")
                )
            )

            # Replace the module in sys.modules to force the import to use our mock
            sys.modules['octodns_hetzner.hcloud_adapter'] = mock_module

            # Try to create provider with hcloud backend - should fail
            with self.assertRaises(ImportError) as ctx:
                HetznerProvider('test', 'token', backend='hcloud')

            # Verify error message mentions hcloud and reinstall
            self.assertIn('hcloud', str(ctx.exception))
            self.assertIn('required dependency', str(ctx.exception))
            self.assertIn('reinstall', str(ctx.exception))

        finally:
            # Restore original module
            if orig_hcloud_adapter is not None:
                sys.modules['octodns_hetzner.hcloud_adapter'] = (
                    orig_hcloud_adapter
                )
            else:
                sys.modules.pop('octodns_hetzner.hcloud_adapter', None)
