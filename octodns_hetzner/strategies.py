#
#
#

"""Apply strategies for different DNS backends.

This module implements the Strategy pattern to handle differences
between record-based (dnsapi) and RRSet-based (hcloud) APIs.
"""

from typing import Callable, List, Protocol


class ApplyStrategy(Protocol):
    """Protocol for DNS change application strategies.

    Different backends have different write semantics:
    - dnsapi: per-record CRUD operations
    - hcloud: RRSet-based upserts and deletes
    """

    def apply_create(
        self, client, zone_id: str, change, params_generator: Callable
    ) -> None:
        """Apply a Create change.

        Args:
            client: DNS client instance
            zone_id: Zone identifier
            change: octoDNS Change object
            params_generator: Function that generates record parameters
        """
        ...

    def apply_update(
        self, client, zone_id: str, change, params_generator: Callable
    ) -> None:
        """Apply an Update change.

        Args:
            client: DNS client instance
            zone_id: Zone identifier
            change: octoDNS Change object
            params_generator: Function that generates record parameters
        """
        ...

    def apply_delete(
        self, client, zone_id: str, change, zone_records: List
    ) -> None:
        """Apply a Delete change.

        Args:
            client: DNS client instance
            zone_id: Zone identifier
            change: octoDNS Change object
            zone_records: Current zone records (for record-based deletion)
        """
        ...


class DNSAPIStrategy:
    """Strategy for record-based API (dnsapi backend).

    This strategy implements per-record CRUD operations:
    - Create: Create each value as a separate record
    - Update: Delete existing records, then create new ones
    - Delete: Delete each matching record individually
    """

    def apply_create(
        self, client, zone_id: str, change, params_generator: Callable
    ) -> None:
        """Create records one by one."""
        new = change.new
        for params in params_generator(new):
            client.zone_record_create(
                zone_id,
                params['name'],
                params['type'],
                params['value'],
                params['ttl'],
            )

    def apply_update(
        self,
        client,
        zone_id: str,
        change,
        params_generator: Callable,
        zone_records: List = None,
    ) -> None:
        """Update via delete-then-create strategy."""
        # It's simpler to delete-then-recreate than to update
        self.apply_delete(client, zone_id, change, zone_records)
        self.apply_create(client, zone_id, change, params_generator)

    def apply_delete(
        self, client, zone_id: str, change, zone_records: List
    ) -> None:
        """Delete matching records one by one."""
        existing = change.existing
        for record in zone_records:
            if (
                existing.name == record['name']
                and existing._type == record['type']
            ):
                client.zone_record_delete(zone_id, record['id'])


class HCloudStrategy:
    """Strategy for RRSet-based API (hcloud backend).

    This strategy implements RRSet-based operations:
    - Create: Upsert entire RRSet with all values
    - Update: Upsert (RRSet replacement is idempotent)
    - Delete: Delete entire RRSet for name+type
    """

    def apply_create(
        self, client, zone_id: str, change, params_generator: Callable
    ) -> None:
        """Create/upsert entire RRSet."""
        new = change.new
        # Collect all values for the RRSet
        values = [p['value'] for p in params_generator(new)]
        # Single RRSet upsert with all values
        client.rrset_upsert(zone_id, new.name, new._type, values, new.ttl)

    def apply_update(
        self,
        client,
        zone_id: str,
        change,
        params_generator: Callable,
        zone_records: List = None,
    ) -> None:
        """Update via RRSet replacement (idempotent upsert)."""
        # RRSet upsert is idempotent - just upsert the new values
        # zone_records not needed for RRSet-based updates
        self.apply_create(client, zone_id, change, params_generator)

    def apply_delete(
        self, client, zone_id: str, change, zone_records: List
    ) -> None:
        """Delete entire RRSet for name+type."""
        existing = change.existing
        # Delete entire RRSet in one operation
        client.rrset_delete(zone_id, existing.name, existing._type)
