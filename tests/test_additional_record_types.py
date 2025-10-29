#
# Tests for additional record types supported by Hetzner & octoDNS
#

from unittest import TestCase
from unittest.mock import Mock

from octodns.record import Record
from octodns.zone import Zone

from octodns_hetzner import HetznerProvider


class TestAdditionalRecordTypes(TestCase):
    def test_populate_ds_tlsa_ptr(self):
        provider = HetznerProvider('test', 'token')
        # Mock dnsapi client methods
        provider._client.zone_get = Mock(
            return_value={'id': 'unit.tests', 'name': 'unit.tests', 'ttl': 3600}
        )
        provider._client.zone_records_get = Mock(
            return_value=[
                # DS values: key_tag algorithm digest_type digest
                {
                    'type': 'DS',
                    'id': 'd1',
                    'created': '',
                    'modified': '',
                    'zone_id': 'unit.tests',
                    'name': '',
                    'value': '2371 8 2 31FDAB6F0B7B7E3D2C0BFF8B1E0E5417D38F0212D5E2B4CE6E3E9CDA0F0B0C99',
                    'ttl': 3600,
                },
                # TLSA: usage selector matching-type data
                {
                    'type': 'TLSA',
                    'id': 't1',
                    'created': '',
                    'modified': '',
                    'zone_id': 'unit.tests',
                    'name': '_443._tcp',
                    'value': '3 1 1 AABBCCDDEEFF',
                    'ttl': 600,
                },
                # PTR
                {
                    'type': 'PTR',
                    'id': 'p1',
                    'created': '',
                    'modified': '',
                    'zone_id': 'unit.tests',
                    'name': '4.3.2.1.in-addr.arpa',
                    'value': 'ptr.unit.tests.',
                    'ttl': 300,
                },
            ]
        )

        zone = Zone('unit.tests.', [])
        provider.populate(zone)

        types = {r._type for r in zone.records}
        self.assertIn('DS', types)
        self.assertIn('TLSA', types)
        self.assertIn('PTR', types)

    def test_apply_ds_tlsa_ptr(self):
        provider = HetznerProvider('test', 'token', strict_supports=False)
        provider._client.zone_get = Mock(
            return_value={'id': 'unit.tests', 'name': 'unit.tests', 'ttl': 3600}
        )
        provider._client.zone_records_get = Mock(return_value=[])
        provider._client.zone_record_create = Mock()

        zone = Zone('unit.tests.', [])
        # DS
        zone.add_record(
            Record.new(
                zone,
                '',
                {
                    'ttl': 3600,
                    'type': 'DS',
                    'values': [
                        {
                            'key_tag': 2371,
                            'algorithm': 8,
                            'digest_type': 2,
                            'digest': '31FDAB',
                        }
                    ],
                },
            )
        )
        # TLSA
        zone.add_record(
            Record.new(
                zone,
                '_443._tcp',
                {
                    'ttl': 600,
                    'type': 'TLSA',
                    'values': [
                        {
                            'certificate_usage': 3,
                            'selector': 1,
                            'matching_type': 1,
                            'certificate_association_data': 'AABBCC',
                        }
                    ],
                },
            )
        )
        # PTR
        zone.add_record(
            Record.new(
                zone,
                '4.3.2.1.in-addr.arpa',
                {'ttl': 300, 'type': 'PTR', 'value': 'ptr.unit.tests.'},
            )
        )

        plan = provider.plan(zone)
        self.assertEqual(3, len(plan.changes))
        provider.apply(plan)

        calls = provider._client.zone_record_create.call_args_list
        self.assertEqual(3, len(calls))
        # Ensure individual calls were made with expected positional args
        args_list = [c.args for c in calls]
        self.assertIn(
            ('unit.tests', '', 'DS', '2371 8 2 31FDAB', 3600), args_list
        )
        self.assertIn(
            ('unit.tests', '_443._tcp', 'TLSA', '3 1 1 AABBCC', 600), args_list
        )
        self.assertIn(
            (
                'unit.tests',
                '4.3.2.1.in-addr.arpa',
                'PTR',
                'ptr.unit.tests.',
                300,
            ),
            args_list,
        )
