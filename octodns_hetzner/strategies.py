#
#
#

"""Apply strategies for the Hetzner Cloud DNS backend.

This module implements the RRSet-based write semantics used by the
Hetzner Cloud (hcloud) API.
"""

from typing import Callable, List, Protocol


class ApplyStrategy(Protocol):
    """Protocol for DNS change application strategies.

    The hcloud backend uses RRSet-based upserts and deletes.
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
