#
# Tests for the hcloud backend integration
#

from unittest import TestCase
from unittest.mock import Mock, call

from octodns.record import Record
from octodns.zone import Zone

from octodns_hetzner import HetznerProvider


class TestHetznerProviderHCloud(TestCase):
    def _provider_with_mock_client(self):
        # Construct with default backend to avoid importing real hcloud
        provider = HetznerProvider("test", "token", strict_supports=False)
        mock = Mock()
        provider._client = mock
        provider._backend = "hcloud"
        # Update strategy to match hcloud backend
        from octodns_hetzner.strategies import HCloudStrategy

        provider._strategy = HCloudStrategy()
        return provider, mock

    def test_apply_create_groups_values_into_rrset(self):
        provider, client = self._provider_with_mock_client()

        # No existing zone/records
        client.zone_get.side_effect = IndexError("zone not found")
        client.zone_create.return_value = {
            "id": "unit.tests",
            "name": "unit.tests",
            "ttl": 3600,
        }
        client.zone_records_get.return_value = []

        # Desired zone with grouped values for A and TXT, plus a CNAME
        zone = Zone("unit.tests.", [])
        zone.add_record(
            Record.new(
                zone,
                "",
                {"ttl": 300, "type": "A", "values": ["1.2.3.4", "1.2.3.5"]},
            )
        )
        zone.add_record(
            Record.new(
                zone,
                "www",
                {"ttl": 300, "type": "CNAME", "value": "unit.tests."},
            )
        )
        zone.add_record(
            Record.new(
                zone, "txt", {"ttl": 600, "type": "TXT", "values": ["a", "b"]}
            )
        )

        plan = provider.plan(zone)
        self.assertEqual(3, len(plan.changes))
        applied = provider.apply(plan)
        self.assertEqual(3, applied)

        # Three rrset upserts, one per name+type
        # TXT values are pre-quoted via chunked_values for hcloud backend
        client.rrset_upsert.assert_has_calls(
            [
                call("unit.tests", "", "A", ["1.2.3.4", "1.2.3.5"], 300),
                call("unit.tests", "www", "CNAME", ["unit.tests."], 300),
                call("unit.tests", "txt", "TXT", ['"a"', '"b"'], 600),
            ],
            any_order=True,
        )

    def test_apply_update_replaces_rrset(self):
        provider, client = self._provider_with_mock_client()

        client.zone_get.return_value = {
            "id": "unit.tests",
            "name": "unit.tests",
            "ttl": 3600,
        }
        # Existing flattened records (from rrset A '')
        client.zone_records_get.return_value = [
            {
                "id": "rr1:1.2.3.4",
                "type": "A",
                "name": "",
                "value": "1.2.3.4",
                "ttl": 300,
                "zone_id": "unit.tests",
            }
        ]

        # Desired adds another value to the RRSet
        zone = Zone("unit.tests.", [])
        zone.add_record(
            Record.new(
                zone,
                "",
                {"ttl": 300, "type": "A", "values": ["1.2.3.4", "2.2.3.4"]},
            )
        )

        plan = provider.plan(zone)
        self.assertTrue(plan.exists)
        self.assertEqual(1, len(plan.changes))
        provider.apply(plan)

        client.rrset_upsert.assert_called_once_with(
            "unit.tests", "", "A", ["1.2.3.4", "2.2.3.4"], 300
        )

    def test_apply_delete_rrset(self):
        provider, client = self._provider_with_mock_client()

        client.zone_get.return_value = {
            "id": "unit.tests",
            "name": "unit.tests",
            "ttl": 3600,
        }
        # Existing flattened TXT rrset with two values
        client.zone_records_get.return_value = [
            {
                "id": "rrtxt:a",
                "type": "TXT",
                "name": "gone",
                "value": "a",
                "ttl": 600,
                "zone_id": "unit.tests",
            },
            {
                "id": "rrtxt:b",
                "type": "TXT",
                "name": "gone",
                "value": "b",
                "ttl": 600,
                "zone_id": "unit.tests",
            },
        ]

        # Desired has no TXT 'gone'
        zone = Zone("unit.tests.", [])

        plan = provider.plan(zone)
        self.assertTrue(plan.exists)
        # Delete for the entire RRSet
        deletes = [c for c in plan.changes if c.__class__.__name__ == "Delete"]
        self.assertEqual(1, len(deletes))
        provider.apply(plan)

        client.rrset_delete.assert_called_once_with("unit.tests", "gone", "TXT")

    def test_apply_new_zone_with_records_succeeds(self):
        """Verify zone creation + immediate record creation works.

        This tests the fix for the race condition where a newly created zone
        isn't immediately queryable via the API due to eventual consistency.
        """
        provider, client = self._provider_with_mock_client()

        client.zone_get.side_effect = IndexError("zone not found")
        client.zone_create.return_value = {
            "id": "new.zone",
            "name": "new.zone",
            "ttl": 3600,
        }
        client.zone_records_get.return_value = []
        client.rrset_upsert.return_value = None

        zone = Zone("new.zone.", [])
        zone.add_record(
            Record.new(
                zone,
                "",
                {"ttl": 300, "type": "A", "values": ["1.2.3.4", "5.6.7.8"]},
            )
        )

        plan = provider.plan(zone)
        self.assertEqual(1, len(plan.changes))

        applied = provider.apply(plan)
        self.assertEqual(1, applied)

        client.zone_create.assert_called_once_with("new.zone")
        client.rrset_upsert.assert_called_once()

    def test_apply_ttl_update_existing_rrset(self):
        """Verify TTL updates work on existing RRSets."""
        provider, client = self._provider_with_mock_client()

        client.zone_get.return_value = {
            "id": "unit.tests",
            "name": "unit.tests",
            "ttl": 3600,
        }
        # Existing A RRSet with TTL=300
        client.zone_records_get.return_value = [
            {
                "id": "rr1:1.2.3.4",
                "type": "A",
                "name": "",
                "value": "1.2.3.4",
                "ttl": 300,
                "zone_id": "unit.tests",
            }
        ]

        # Desired updates TTL to 600 and changes values
        zone = Zone("unit.tests.", [])
        zone.add_record(
            Record.new(
                zone,
                "",
                {"ttl": 600, "type": "A", "values": ["1.2.3.4", "5.6.7.8"]},
            )
        )

        plan = provider.plan(zone)
        self.assertTrue(plan.exists)
        self.assertEqual(1, len(plan.changes))

        # Apply the update
        provider.apply(plan)

        # Verify rrset_upsert was called with new TTL=600
        client.rrset_upsert.assert_called_once_with(
            "unit.tests", "", "A", ["1.2.3.4", "5.6.7.8"], 600
        )

    def test_txt_long_value_chunked(self):
        """Test that long TXT values (>255 chars) are properly chunked.

        This tests the fix for DKIM keys and other long TXT records.
        Values >255 chars should be split into RFC-compliant chunks.
        """
        provider, client = self._provider_with_mock_client()

        client.zone_get.return_value = {
            "id": "unit.tests",
            "name": "unit.tests",
            "ttl": 3600,
        }
        client.zone_records_get.return_value = []

        # Create a long DKIM-style value (400 chars, >255 limit)
        # Use escaped semicolons as octodns requires
        long_value = r"v=DKIM1\;k=rsa\;p=" + "A" * 382  # Total: 400 chars

        zone = Zone("unit.tests.", [])
        zone.add_record(
            Record.new(
                zone,
                "dkim._domainkey",
                {"ttl": 300, "type": "TXT", "value": long_value},
            )
        )

        plan = provider.plan(zone)
        self.assertEqual(1, len(plan.changes))
        provider.apply(plan)

        # Verify rrset_upsert was called
        client.rrset_upsert.assert_called_once()
        call_args = client.rrset_upsert.call_args

        # Check zone_id, name, type
        self.assertEqual("unit.tests", call_args[0][0])
        self.assertEqual("dkim._domainkey", call_args[0][1])
        self.assertEqual("TXT", call_args[0][2])

        # The values list should contain ONE item (one logical TXT record)
        values = call_args[0][3]
        self.assertEqual(1, len(values))

        # The value should be chunked format: '"chunk1" "chunk2"'
        chunked_value = values[0]
        self.assertTrue(chunked_value.startswith('"'))
        self.assertTrue(chunked_value.endswith('"'))
        # Should contain the chunk separator '" "'
        self.assertIn('" "', chunked_value)

    def test_txt_boundary_255_chars_no_chunking(self):
        """Test that TXT values exactly 255 chars don't need chunking."""
        provider, client = self._provider_with_mock_client()

        client.zone_get.return_value = {
            "id": "unit.tests",
            "name": "unit.tests",
            "ttl": 3600,
        }
        client.zone_records_get.return_value = []

        # Exactly 255 chars - should NOT be chunked
        value_255 = "A" * 255

        zone = Zone("unit.tests.", [])
        zone.add_record(
            Record.new(
                zone, "spf", {"ttl": 300, "type": "TXT", "value": value_255}
            )
        )

        plan = provider.plan(zone)
        provider.apply(plan)

        call_args = client.rrset_upsert.call_args
        values = call_args[0][3]
        self.assertEqual(1, len(values))

        # Should be quoted but NOT chunked (no '" "' separator)
        chunked_value = values[0]
        self.assertEqual(f'"{value_255}"', chunked_value)
        self.assertNotIn('" "', chunked_value)

    def test_txt_boundary_256_chars_minimal_chunking(self):
        """Test that TXT values of 256 chars get minimal chunking."""
        provider, client = self._provider_with_mock_client()

        client.zone_get.return_value = {
            "id": "unit.tests",
            "name": "unit.tests",
            "ttl": 3600,
        }
        client.zone_records_get.return_value = []

        # 256 chars - should be chunked into 255 + 1
        value_256 = "A" * 256

        zone = Zone("unit.tests.", [])
        zone.add_record(
            Record.new(
                zone, "spf", {"ttl": 300, "type": "TXT", "value": value_256}
            )
        )

        plan = provider.plan(zone)
        provider.apply(plan)

        call_args = client.rrset_upsert.call_args
        values = call_args[0][3]
        self.assertEqual(1, len(values))

        # Should be chunked
        chunked_value = values[0]
        self.assertIn('" "', chunked_value)

    def test_txt_multiple_short_values_separate_rrs(self):
        """Test that multiple short TXT values stay as separate entries.

        Multiple values in a TXT record should remain as separate values,
        not be collapsed into one. This is important for site verification
        records where you need multiple distinct TXT records.
        """
        provider, client = self._provider_with_mock_client()

        client.zone_get.return_value = {
            "id": "unit.tests",
            "name": "unit.tests",
            "ttl": 3600,
        }
        client.zone_records_get.return_value = []

        zone = Zone("unit.tests.", [])
        zone.add_record(
            Record.new(
                zone,
                "verify",
                {
                    "ttl": 300,
                    "type": "TXT",
                    "values": [
                        "google-site-verification=abc123",
                        "facebook-domain-verification=xyz789",
                        "ms=ms12345678",
                    ],
                },
            )
        )

        plan = provider.plan(zone)
        provider.apply(plan)

        call_args = client.rrset_upsert.call_args
        values = call_args[0][3]

        # Should have 3 separate values (3 RRs in the RRSet)
        self.assertEqual(3, len(values))

        # Each should be quoted but not chunked together
        for v in values:
            self.assertTrue(v.startswith('"'))
            self.assertTrue(v.endswith('"'))

    def test_txt_embedded_quotes_escaped(self):
        """Test that TXT values with embedded quotes are properly escaped."""
        provider, client = self._provider_with_mock_client()

        client.zone_get.return_value = {
            "id": "unit.tests",
            "name": "unit.tests",
            "ttl": 3600,
        }
        client.zone_records_get.return_value = []

        # Value with embedded double quotes
        value_with_quotes = r"v=DKIM1\;k=\"rsa\"\;p=ABC"

        zone = Zone("unit.tests.", [])
        zone.add_record(
            Record.new(
                zone,
                "dkim",
                {"ttl": 300, "type": "TXT", "value": value_with_quotes},
            )
        )

        plan = provider.plan(zone)
        provider.apply(plan)

        call_args = client.rrset_upsert.call_args
        values = call_args[0][3]
        self.assertEqual(1, len(values))

        # Value should be properly quoted
        chunked_value = values[0]
        self.assertTrue(chunked_value.startswith('"'))
        self.assertTrue(chunked_value.endswith('"'))
