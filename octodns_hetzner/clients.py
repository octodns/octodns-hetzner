#
#
#

"""Protocol definitions for DNS client interfaces.

This module defines structural typing (PEP 544) for DNS clients,
allowing type checking without requiring explicit inheritance.
"""

from typing import Dict, List, Optional, Protocol


class DNSClient(Protocol):
    """Protocol defining the expected interface for DNS clients.

    Both HetznerClient (dnsapi) and HCloudZonesClient (hcloud) should
    conform to this interface for basic operations.
    """

    def domains(self) -> List[Dict]:
        """List all DNS zones/domains.

        Returns:
            List of dicts with at least 'id' and 'name' keys
        """
        ...

    def zone_get(self, name: str) -> Dict:
        """Get zone metadata by name.

        Args:
            name: Zone name (without trailing dot)

        Returns:
            Dict with 'id', 'name', and 'ttl' keys
        """
        ...

    def zone_records_get(self, zone_id: str) -> List[Dict]:
        """Get all records for a zone.

        Args:
            zone_id: Zone identifier

        Returns:
            List of record dicts with 'id', 'type', 'name', 'value', 'ttl', 'zone_id'
        """
        ...

    def zone_record_create(
        self,
        zone_id: str,
        name: str,
        _type: str,
        value: str,
        ttl: Optional[int] = None,
    ) -> None:
        """Create a single DNS record.

        Args:
            zone_id: Zone identifier
            name: Record name (empty string for zone apex)
            _type: Record type (A, AAAA, etc.)
            value: Record value
            ttl: Optional TTL override
        """
        ...

    def zone_record_delete(self, zone_id: str, record_id: str) -> None:
        """Delete a DNS record.

        Args:
            zone_id: Zone identifier
            record_id: Record identifier
        """
        ...

    def zone_create(self, name: str, ttl: Optional[int] = None) -> Dict:
        """Create a new DNS zone.

        Args:
            name: Zone name (without trailing dot)
            ttl: Optional default TTL

        Returns:
            Dict with zone metadata including 'id'
        """
        ...
