#
# Unit tests for the hcloud adapter with a fake hcloud client
# to satisfy coverage without network or real dependency.
#

import sys
from types import ModuleType
from unittest import TestCase

from octodns_hetzner.hcloud_adapter import HCloudZonesClient


class FakeRecord:
    def __init__(self, value):
        self.value = value


class FakeRRSet:
    def __init__(self, _id, name, _type, ttl, values):
        self.id = _id
        self.name = name
        self.type = _type
        self.ttl = ttl
        self.records = [FakeRecord(v) for v in values]
        self.updated = None
        self.deleted = False

    def update(self, name, type, records, ttl):
        self.updated = {
            'name': name,
            'type': type,
            'records': records,
            'ttl': ttl,
        }
        # also update internal records
        # Handle both dict and object formats (for ZoneRecord compatibility)
        self.records = [
            FakeRecord(r['value'] if isinstance(r, dict) else r.value)
            for r in records
        ]
        self.ttl = ttl
        return self.updated

    def delete(self, name=None, type=None):
        self.deleted = True
        return True


class FakeZone:
    def __init__(self, _id, name, ttl, rrsets=None):
        self.id = _id
        self.name = name
        self.ttl = ttl
        self.rrsets = rrsets or []
        self.created_rrset = None

    def create_rrset(self, zone_id, name, type, records, ttl):
        # Handle both dict and object formats (for ZoneRecord compatibility)
        values = [
            r['value'] if isinstance(r, dict) else r.value for r in records
        ]
        rr = FakeRRSet('new', name or '', type, ttl, values)
        self.rrsets.append(rr)
        self.created_rrset = {
            'zone_id': zone_id,
            'name': name,
            'type': type,
            'records': records,
            'ttl': ttl,
        }
        return self.created_rrset

    def update_rrset(self, name, type, records, ttl):
        for r in self.rrsets:
            if r.name == (name or '') and r.type == type:
                # Update in place without calling r.update to simulate fallback
                # Handle both dict and object formats (for ZoneRecord compatibility)
                r.records = [
                    FakeRecord(v['value'] if isinstance(v, dict) else v.value)
                    for v in records
                ]
                r.ttl = ttl
                return {
                    'name': name,
                    'type': type,
                    'records': records,
                    'ttl': ttl,
                }
        return None

    def delete_rrset(self, name, type):
        for r in list(self.rrsets):
            if r.name == (name or '') and r.type == type:
                # In fallback, delete may be None; remove directly
                if getattr(r, 'delete', None):
                    r.delete()
                self.rrsets.remove(r)
                return True
        return False


class FakeZones:
    def __init__(self, zones):
        self._zones = {z.id: z for z in zones}
        self._by_name = {z.name: z for z in zones}

    def get_all(self):
        return list(self._zones.values())

    def get_by_id(self, zone_id):
        return self._zones[zone_id]

    def get(self, id_or_name):
        """Get zone by id or name (mimics hcloud API)."""
        # Try as id first
        if id_or_name in self._zones:
            return self._zones[id_or_name]
        # Try as name
        if id_or_name in self._by_name:
            return self._by_name[id_or_name]
        raise KeyError(f'Zone not found: {id_or_name}')

    def get_rrset_all(self, zone):
        """Get all RRSets for a zone (mimics hcloud API)."""
        return zone.rrsets if zone.rrsets is not None else []

    def create(self, name):
        z = FakeZone(name, name, 3600)
        self._zones[name] = z
        self._by_name[name] = z
        return z

    def create_rrset(self, zone, name, type, records, ttl):
        """Create RRSet (mimics hcloud API with zone parameter)."""
        # Handle both dict and object formats (for ZoneRecord compatibility)
        values = [
            r['value'] if isinstance(r, dict) else r.value for r in records
        ]
        rr = FakeRRSet('new2', name or '', type, ttl, values)
        zone.rrsets.append(rr)
        return rr

    def update_rrset(self, rrset, name, type, records, ttl):
        """Update RRSet (mimics hcloud API with rrset parameter)."""
        rrset.updated = {
            'name': name,
            'type': type,
            'records': records,
            'ttl': ttl,
        }
        # Handle both dict and object formats (for ZoneRecord compatibility)
        rrset.records = [
            FakeRecord(r['value'] if isinstance(r, dict) else r.value)
            for r in records
        ]
        rrset.ttl = ttl
        return rrset

    def delete_rrset(self, rrset):
        """Delete RRSet (mimics hcloud API with rrset parameter)."""
        # Find zone containing this rrset
        for zone in self._zones.values():
            if rrset in zone.rrsets:
                try:
                    zone.rrsets.remove(rrset)
                except (AttributeError, TypeError):
                    # rrsets may be immutable (tuple) or otherwise not modifiable
                    pass
                rrset.deleted = True
                return True
        return False


class FakeHCloudClient:
    def __init__(self, token):
        # seeded by test
        self.zones = None


class FakeZoneRecord:
    """Fake ZoneRecord class for testing the real import path."""

    def __init__(self, value, comment=None):
        self.value = value
        self.comment = comment


class TestHCloudAdapter(TestCase):
    def setUp(self):
        # Install a fake 'hcloud' module
        self._orig = sys.modules.get('hcloud')
        fake_mod = ModuleType('hcloud')
        fake_mod.Client = FakeHCloudClient
        sys.modules['hcloud'] = fake_mod

        # Add fake zones.domain module with ZoneRecord for coverage
        fake_zones_mod = ModuleType('hcloud.zones')
        fake_zones_domain_mod = ModuleType('hcloud.zones.domain')
        fake_zones_domain_mod.ZoneRecord = FakeZoneRecord
        fake_zones_mod.domain = fake_zones_domain_mod
        sys.modules['hcloud.zones'] = fake_zones_mod
        sys.modules['hcloud.zones.domain'] = fake_zones_domain_mod

        # Build fake world
        z1 = FakeZone(
            'z1',
            'unit.tests',
            3600,
            rrsets=[
                FakeRRSet('rr1', '', 'A', 300, ['1.2.3.4']),
                FakeRRSet('rr2', 'gone', 'TXT', 600, ['a', 'b']),
            ],
        )
        # Attach zones to client after instantiation
        self.client = HCloudZonesClient('token')
        self.client._hcloud.zones = FakeZones([z1])
        self.client._zones = self.client._hcloud.zones

    def tearDown(self):
        # Restore original module if it existed
        if self._orig is None:
            sys.modules.pop('hcloud', None)
        else:
            sys.modules['hcloud'] = self._orig
        # Clean up fake zones modules
        sys.modules.pop('hcloud.zones', None)
        sys.modules.pop('hcloud.zones.domain', None)

    def test_domains_and_zone_get(self):
        ds = self.client.domains()
        self.assertEqual(1, len(ds))
        self.assertEqual('unit.tests', ds[0]['name'])

        zg = self.client.zone_get('unit.tests')
        self.assertEqual('unit.tests', zg['name'])
        self.assertEqual(3600, zg['ttl'])

    def test_zone_get_not_found_and_zone_create_unsupported(self):
        # zone_get for non-existent zone should raise IndexError
        with self.assertRaises(IndexError):
            self.client.zone_get('no.such.zone')

        # zone_create should raise when client has no create
        orig = getattr(self.client._zones, 'create')
        try:
            setattr(self.client._zones, 'create', None)
            with self.assertRaises(NotImplementedError):
                self.client.zone_create('new.example', 3600)
        finally:
            setattr(self.client._zones, 'create', orig)

    def test_zone_records_get_flattens(self):
        recs = self.client.zone_records_get('z1')
        # 1 A + 2 TXT = 3 flattened records
        self.assertEqual(3, len(recs))
        # Ensure '@' becomes ''
        self.assertTrue(all(r['name'] in ('', 'gone') for r in recs))

        # Add an RRSet named '@' and with no TTL to exercise name normalization
        z = self.client._zones.get_by_id('z1')
        z.rrsets.append(FakeRRSet('rr3', '@', 'NS', None, ['ns1.example.']))
        recs = self.client.zone_records_get('z1')
        self.assertTrue(
            any(r['name'] == '' and r['type'] == 'NS' for r in recs)
        )

    def test_rrset_upsert_update(self):
        # Update existing rrset 'A' '' to include second value
        self.client.rrset_upsert('z1', '', 'A', ['1.2.3.4', '2.2.3.4'], 300)
        # Verify rrset now has 2 records
        z = self.client._zones.get_by_id('z1')
        a_rr = [r for r in z.rrsets if r.type == 'A' and r.name == ''][0]
        self.assertEqual(
            ['1.2.3.4', '2.2.3.4'], [r.value for r in a_rr.records]
        )

    def test_rrset_upsert_create(self):
        # Create new CNAME rrset
        self.client.rrset_upsert('z1', 'www', 'CNAME', ['unit.tests.'], 300)
        z = self.client._zones.get_by_id('z1')
        cn = [r for r in z.rrsets if r.type == 'CNAME' and r.name == 'www']
        self.assertEqual(1, len(cn))

    def test_rrset_delete(self):
        # Delete TXT 'gone'
        self.client.rrset_delete('z1', 'gone', 'TXT')
        z = self.client._zones.get_by_id('z1')
        self.assertFalse(
            any(r.type == 'TXT' and r.name == 'gone' for r in z.rrsets)
        )

    def test_rrset_delete_no_match_and_not_supported(self):
        # No matching rrset returns None
        self.assertIsNone(self.client.rrset_delete('z1', 'missing', 'TXT'))

        # Not supported delete when all delete methods are None
        orig_dZ = FakeZones.delete_rrset
        orig_zone_dZ = FakeZone.delete_rrset
        orig_rrset_d = FakeRRSet.delete
        try:
            FakeZones.delete_rrset = None
            FakeZone.delete_rrset = None
            FakeRRSet.delete = None
            with self.assertRaises(NotImplementedError):
                self.client.rrset_delete('z1', 'gone', 'TXT')
        finally:
            FakeZones.delete_rrset = orig_dZ
            FakeZone.delete_rrset = orig_zone_dZ
            FakeRRSet.delete = orig_rrset_d

    def test_zone_record_compat_shims(self):
        # zone_record_create delegates to rrset_upsert
        self.client.rrset_upsert = lambda *args, **kwargs: {'ok': True}
        self.assertEqual(
            {'ok': True},
            self.client.zone_record_create('z1', '', 'A', '9.9.9.9', 300),
        )

        # zone_record_delete removes a single value or deletes rrset when last
        # (setup has TXT rrset with ['a','b']) remove one -> update, remove other -> delete
        self.client.zone_record_delete('z1', 'rr2:a')  # leaves 'b'
        z = self.client._zones.get_by_id('z1')
        txt = [r for r in z.rrsets if r.type == 'TXT' and r.name == 'gone'][0]
        self.assertEqual(['b'], [r.value for r in txt.records])
        # now remove last value
        self.client.zone_record_delete('z1', 'rr2:b')
        self.assertFalse(
            any(r.type == 'TXT' and r.name == 'gone' for r in z.rrsets)
        )

    def test_zone_create(self):
        out = self.client.zone_create('newzone.test', 3600)
        self.assertEqual('newzone.test', out['name'])

    def test_rrset_upsert_create_update_not_supported(self):
        # Create not supported: block all create_rrset methods
        z3 = FakeZone('z3', 'z3.test', 3600, rrsets=[])
        self.client._zones._zones['z3'] = z3
        orig_cZ = FakeZones.create_rrset
        orig_zone_cZ = FakeZone.create_rrset
        try:
            FakeZones.create_rrset = None
            FakeZone.create_rrset = None
            with self.assertRaises(NotImplementedError):
                self.client.rrset_upsert('z3', 'www', 'A', ['1.1.1.1'], 60)
        finally:
            FakeZones.create_rrset = orig_cZ
            FakeZone.create_rrset = orig_zone_cZ

        # Update not supported: block all update methods
        orig_uZ = FakeZones.update_rrset
        orig_zone_uZ = FakeZone.update_rrset
        orig_rrset_u = FakeRRSet.update
        try:
            FakeZones.update_rrset = None
            FakeZone.update_rrset = None
            FakeRRSet.update = None
            with self.assertRaises(NotImplementedError):
                self.client.rrset_upsert('z1', '', 'A', ['3.3.3.3'], 300)
        finally:
            FakeZones.update_rrset = orig_uZ
            FakeZone.update_rrset = orig_zone_uZ
            FakeRRSet.update = orig_rrset_u

    def test_zone_records_get_rrsets_none_and_ttl_fallback_3600(self):
        # Create zone with rrsets None and ttl None; set rrsets=None after init
        z2 = FakeZone('z2b', 'no-rrsets-2.test', None, rrsets=[])
        z2.rrsets = None
        self.client._zones._zones['z2b'] = z2
        out = self.client.zone_records_get('z2b')
        self.assertEqual([], out)

    def test_zone_record_delete_not_found_returns_none(self):
        self.assertIsNone(self.client.zone_record_delete('z1', 'noid:nothing'))

    def test_rrset_remove_value_update_not_supported_and_delete_except_path(
        self,
    ):
        # Prepare zone with txt rrset of 2 values
        z = FakeZone(
            'zX',
            'update-fail.test',
            3600,
            rrsets=[FakeRRSet('rrX', 'txt', 'TXT', 30, ['a', 'b'])],
        )
        self.client._zones._zones['zX'] = z
        txt = z.rrsets[0]
        # All update methods missing => NotImplemented on removing one value
        orig_uZ = FakeZones.update_rrset
        orig_zone_uZ = FakeZone.update_rrset
        orig_rrset_u = FakeRRSet.update
        try:
            FakeZones.update_rrset = None
            FakeZone.update_rrset = None
            FakeRRSet.update = None
            with self.assertRaises(NotImplementedError):
                self.client.zone_record_delete('zX', f'{txt.id}:a')
        finally:
            FakeZones.update_rrset = orig_uZ
            FakeZone.update_rrset = orig_zone_uZ
            FakeRRSet.update = orig_rrset_u

        # Now single-value delete path with rrsets immutable to trigger except pass
        z2 = FakeZone(
            'zY',
            'delete-except.test',
            3600,
            rrsets=[FakeRRSet('rrY', 'last', 'TXT', 30, ['x'])],
        )
        self.client._zones._zones['zY'] = z2
        z2.rrsets = tuple(z2.rrsets)
        # Ensure target.delete exists so we take delete path
        self.client.zone_record_delete('zY', 'rrY:x')

    def test_rrset_remove_value_delete_not_supported(self):
        z = FakeZone(
            'zZ',
            'del-not-sup.test',
            3600,
            rrsets=[FakeRRSet('rrZ', 'solo', 'TXT', 30, ['x'])],
        )
        self.client._zones._zones['zZ'] = z
        # All delete methods missing => NotImplemented on deleting last value
        orig_dZ = FakeZones.delete_rrset
        orig_zone_dZ = FakeZone.delete_rrset
        orig_rrset_d = FakeRRSet.delete
        try:
            FakeZones.delete_rrset = None
            FakeZone.delete_rrset = None
            FakeRRSet.delete = None
            with self.assertRaises(NotImplementedError):
                self.client.zone_record_delete('zZ', 'rrZ:x')
        finally:
            FakeZones.delete_rrset = orig_dZ
            FakeZone.delete_rrset = orig_zone_dZ
            FakeRRSet.delete = orig_rrset_d

    def test_fallbacks_rrset_ops_and_records_get(self):
        # Create a zone with rrsets None and no zone ttl to test fallbacks
        z2 = FakeZone('z2', 'no-rrsets.test', None, rrsets=None)
        self.client._zones._zones['z2'] = z2
        # zone_records_get should handle rrsets None and return []
        out = self.client.zone_records_get('z2')
        self.assertEqual([], out)

        # Create via self._zones.create_rrset fallback (remove zone.create_rrset)
        setattr(z2, 'create_rrset', None)
        self.client.rrset_upsert('z2', 'www', 'A', ['9.9.9.9'], 60)
        self.assertTrue(
            any(r.type == 'A' and r.name == 'www' for r in z2.rrsets)
        )

        # Update via zone.update_rrset fallback (remove r.update)
        target = [r for r in z2.rrsets if r.type == 'A' and r.name == 'www'][0]
        setattr(target, 'update', None)
        self.client.rrset_upsert('z2', 'www', 'A', ['8.8.8.8'], 60)
        self.assertEqual(['8.8.8.8'], [rec.value for rec in target.records])

        # Delete via zone.delete_rrset fallback (remove r.delete)
        setattr(target, 'delete', None)
        self.client.rrset_delete('z2', 'www', 'A')
        self.assertFalse(
            any(r.type == 'A' and r.name == 'www' for r in z2.rrsets)
        )

        # _rrset_remove_value fallback to zone.update_rrset (remove r.update again)
        # First create a TXT rrset with two values and remove one
        self.client.rrset_upsert('z2', 'txt', 'TXT', ['a', 'b'], 30)
        txt = [r for r in z2.rrsets if r.type == 'TXT' and r.name == 'txt'][0]
        setattr(txt, 'update', None)
        rid = f"{txt.id}:a"
        self.client.zone_record_delete('z2', rid)
        self.assertEqual(['b'], [rec.value for rec in txt.records])

    def test_typeerror_fallbacks_and_service_level(self):
        # Test TypeError exception handling in various operations

        # Create zone for testing
        z = FakeZone('zT', 'typeerr.test', 3600, rrsets=[])
        self.client._zones._zones['zT'] = z

        # Test create_rrset with zone parameter TypeError -> zone_id parameter
        def create_with_zone_id(**kwargs):
            if 'zone' in kwargs:
                raise TypeError('unexpected zone parameter')
            # Handle both dict and object formats (for ZoneRecord compatibility)
            values = [
                r['value'] if isinstance(r, dict) else r.value
                for r in kwargs['records']
            ]
            rr = FakeRRSet(
                'new3', kwargs['name'], kwargs['type'], kwargs['ttl'], values
            )
            z.rrsets.append(rr)
            return rr

        orig_create = FakeZones.create_rrset
        FakeZones.create_rrset = create_with_zone_id
        try:
            self.client.rrset_upsert('zT', 'www', 'A', ['1.1.1.1'], 60)
            self.assertTrue(
                any(r.name == 'www' and r.type == 'A' for r in z.rrsets)
            )
        finally:
            FakeZones.create_rrset = orig_create

        # Test update_rrset with zone-level TypeError -> rrset parameter
        www = [r for r in z.rrsets if r.name == 'www' and r.type == 'A'][0]
        setattr(www, 'update', None)

        def update_with_rrset(self, **kwargs):
            if 'rrset' not in kwargs:
                raise TypeError('missing rrset parameter')
            rrset = kwargs['rrset']
            # Handle both dict and object formats (for ZoneRecord compatibility)
            rrset.records = [
                FakeRecord(r['value'] if isinstance(r, dict) else r.value)
                for r in kwargs['records']
            ]
            return rrset

        orig_update_zone = FakeZone.update_rrset
        FakeZone.update_rrset = update_with_rrset
        try:
            self.client.rrset_upsert('zT', 'www', 'A', ['2.2.2.2'], 60)
            self.assertEqual(['2.2.2.2'], [rec.value for rec in www.records])
        finally:
            FakeZone.update_rrset = orig_update_zone

        # Test delete_rrset with zone-level TypeError -> rrset parameter
        setattr(www, 'delete', None)

        def delete_with_rrset(self, **kwargs):
            if 'rrset' not in kwargs:
                raise TypeError('missing rrset parameter')
            z.rrsets.remove(kwargs['rrset'])
            return True

        orig_delete_zone = FakeZone.delete_rrset
        FakeZone.delete_rrset = delete_with_rrset
        try:
            self.client.rrset_delete('zT', 'www', 'A')
            self.assertFalse(
                any(r.name == 'www' and r.type == 'A' for r in z.rrsets)
            )
        finally:
            FakeZone.delete_rrset = orig_delete_zone

        # Test _rrset_remove_value delete with zone-level TypeError
        self.client.rrset_upsert('zT', 'txt', 'TXT', ['x'], 30)
        txt = [r for r in z.rrsets if r.name == 'txt' and r.type == 'TXT'][0]
        setattr(txt, 'delete', None)

        FakeZone.delete_rrset = delete_with_rrset
        try:
            self.client.zone_record_delete('zT', f'{txt.id}:x')
            self.assertFalse(
                any(r.name == 'txt' and r.type == 'TXT' for r in z.rrsets)
            )
        finally:
            FakeZone.delete_rrset = orig_delete_zone

        # Test _rrset_remove_value update with zone-level TypeError
        self.client.rrset_upsert('zT', 'txt2', 'TXT', ['a', 'b'], 30)
        txt2 = [r for r in z.rrsets if r.name == 'txt2' and r.type == 'TXT'][0]
        setattr(txt2, 'update', None)

        FakeZone.update_rrset = update_with_rrset
        try:
            self.client.zone_record_delete('zT', f'{txt2.id}:a')
            self.assertEqual(['b'], [rec.value for rec in txt2.records])
        finally:
            FakeZone.update_rrset = orig_update_zone

    def test_service_level_only_fallbacks(self):
        # Test service-level-only fallback paths (zone and rrset methods None)

        z = FakeZone('zS', 'service.test', 3600, rrsets=[])
        self.client._zones._zones['zS'] = z
        setattr(z, 'create_rrset', None)

        # Service-level create
        self.client.rrset_upsert('zS', 'www', 'A', ['1.1.1.1'], 60)
        self.assertTrue(
            any(r.name == 'www' and r.type == 'A' for r in z.rrsets)
        )

        # Service-level update
        www = [r for r in z.rrsets if r.name == 'www' and r.type == 'A'][0]
        setattr(www, 'update', None)
        setattr(z, 'update_rrset', None)
        self.client.rrset_upsert('zS', 'www', 'A', ['2.2.2.2'], 60)
        self.assertEqual(['2.2.2.2'], [rec.value for rec in www.records])

        # Service-level delete
        setattr(www, 'delete', None)
        setattr(z, 'delete_rrset', None)
        self.client.rrset_delete('zS', 'www', 'A')
        self.assertFalse(
            any(r.name == 'www' and r.type == 'A' for r in z.rrsets)
        )

        # Service-level delete in _rrset_remove_value (last value)
        self.client.rrset_upsert('zS', 'txt', 'TXT', ['x'], 30)
        txt = [r for r in z.rrsets if r.name == 'txt' and r.type == 'TXT'][0]
        setattr(txt, 'delete', None)
        self.client.zone_record_delete('zS', f'{txt.id}:x')
        self.assertFalse(
            any(r.name == 'txt' and r.type == 'TXT' for r in z.rrsets)
        )

        # Service-level update in _rrset_remove_value (multi-value)
        self.client.rrset_upsert('zS', 'txt2', 'TXT', ['a', 'b'], 30)
        txt2 = [r for r in z.rrsets if r.name == 'txt2' and r.type == 'TXT'][0]
        setattr(txt2, 'update', None)
        self.client.zone_record_delete('zS', f'{txt2.id}:a')
        self.assertEqual(['b'], [rec.value for rec in txt2.records])

    def test_get_zone_exception_handling(self):
        # Test exception handling in _get_zone_by_id_or_name

        # Test get_by_id raising exception -> fallback to get
        orig_get_by_id = FakeZones.get_by_id

        def get_by_id_raises(self, zone_id):
            raise Exception('get_by_id failed')

        FakeZones.get_by_id = get_by_id_raises
        try:
            # Should fall back to get() which works
            zone = self.client._get_zone_by_id_or_name('z1')
            self.assertEqual('unit.tests', zone.name)
        finally:
            FakeZones.get_by_id = orig_get_by_id

        # Test get_by_id returning None -> fallback to get
        def get_by_id_none(self, zone_id):
            return None

        FakeZones.get_by_id = get_by_id_none
        try:
            zone = self.client._get_zone_by_id_or_name('z1')
            self.assertEqual('unit.tests', zone.name)
        finally:
            FakeZones.get_by_id = orig_get_by_id

        # Test both get_by_id and get missing -> KeyError
        FakeZones.get_by_id = None
        orig_get = FakeZones.get
        FakeZones.get = None
        try:
            with self.assertRaises(KeyError):
                self.client._get_zone_by_id_or_name('z1')
        finally:
            FakeZones.get_by_id = orig_get_by_id
            FakeZones.get = orig_get

    def test_get_rrsets_exception_handling(self):
        # Test exception handling in _get_rrsets when zone has no rrsets attribute

        # Create a zone without rrsets attribute by using a simple object
        class ZoneWithoutRRSets:
            pass

        z = ZoneWithoutRRSets()
        orig_get_rrset_all = FakeZones.get_rrset_all

        # Test get_rrset_all raising exception -> return []
        # This tests the except Exception block on lines 384-385
        def get_rrset_all_raises(zone):
            raise RuntimeError('get_rrset_all failed')

        # Replace on instance
        self.client._zones.get_rrset_all = get_rrset_all_raises
        try:
            rrsets = self.client._get_rrsets(z)
            self.assertEqual([], rrsets)
        finally:
            self.client._zones.get_rrset_all = orig_get_rrset_all

        # Test get_rrset_all missing (None) -> return []
        self.client._zones.get_rrset_all = None
        try:
            rrsets = self.client._get_rrsets(z)
            self.assertEqual([], rrsets)
        finally:
            self.client._zones.get_rrset_all = orig_get_rrset_all

    def test_service_create_typeerror_fallback(self):
        # Test TypeError in service-level create_rrset (zone param -> zone_id param)

        z = FakeZone('zErr', 'create-err.test', 3600, rrsets=[])
        self.client._zones._zones['zErr'] = z
        setattr(z, 'create_rrset', None)

        # Service-level create that raises TypeError with zone param
        def create_with_zone_id(self, **kwargs):
            if 'zone' in kwargs:
                raise TypeError('unexpected zone parameter')
            zone = kwargs['zone_id']
            # Handle both dict and object formats (for ZoneRecord compatibility)
            values = [
                r['value'] if isinstance(r, dict) else r.value
                for r in kwargs['records']
            ]
            rr = FakeRRSet(
                'new4', kwargs['name'], kwargs['type'], kwargs['ttl'], values
            )
            self._zones[zone].rrsets.append(rr)
            return rr

        orig_create = FakeZones.create_rrset
        FakeZones.create_rrset = create_with_zone_id
        try:
            self.client.rrset_upsert('zErr', 'www', 'A', ['1.1.1.1'], 60)
            self.assertTrue(
                any(r.name == 'www' and r.type == 'A' for r in z.rrsets)
            )
        finally:
            FakeZones.create_rrset = orig_create

    def test_zonerecord_fallback(self):
        """Test fallback ZoneRecord class when hcloud.zones.domain unavailable."""
        # Remove the zones.domain module to trigger fallback
        orig_zones = sys.modules.pop('hcloud.zones', None)
        orig_zones_domain = sys.modules.pop('hcloud.zones.domain', None)

        try:
            # Create a new client without zones.domain available
            fallback_client = HCloudZonesClient('token2')
            # Verify fallback ZoneRecord class is used
            rec = fallback_client._ZoneRecord(value='test', comment='foo')
            self.assertEqual('test', rec.value)
            self.assertEqual('foo', rec.comment)
        finally:
            # Restore the modules
            if orig_zones is not None:
                sys.modules['hcloud.zones'] = orig_zones
            if orig_zones_domain is not None:
                sys.modules['hcloud.zones.domain'] = orig_zones_domain
