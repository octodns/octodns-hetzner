"""
Adapter for Hetzner Cloud DNS Zones (hcloud.zones).

This adapter exposes the minimal interface expected by HetznerProvider's
existing code path, allowing a backend switch without refactoring the
provider's record flow. It intentionally keeps a small surface area.

Notes
- Import of hcloud happens only when this module/class is used (lazy import).
- Write operations are fully supported via RRSet semantics (upsert/delete),
  with compatibility shims for record create/delete to ease provider reuse.
- When zone or RRSet TTLs are unavailable from the API, a conservative
  fallback of 3600 seconds is used.
"""

from typing import Any, Dict, List

DEFAULT_TTL = 3600


class HCloudZonesClient:
    """Thin wrapper around hcloud's Zones client.

    Methods mirror a subset of the existing HetznerClient so the provider can
    operate without broader changes. Both read and write operations are
    supported; writes use RRSet upsert/delete semantics and provide
    compatibility shims for record-level create/delete.
    """

    def __init__(self, token: str):
        from hcloud import Client as HCloudClient  # lazy import

        self._hcloud = HCloudClient(token=token)
        self._zones = self._hcloud.zones

        # Try to import ZoneRecord; fallback to a minimal compatible class for tests
        try:
            from hcloud.zones.domain import ZoneRecord

            self._ZoneRecord = ZoneRecord
        except (ImportError, AttributeError):
            # Fallback for testing or older hcloud versions
            class _FallbackZoneRecord:
                def __init__(self, value, comment=None):
                    self.value = value
                    self.comment = comment

                def to_payload(self):
                    """Generates the request payload from this domain object."""
                    payload = {'value': self.value}
                    if self.comment is not None:
                        payload['comment'] = self.comment
                    return payload

            self._ZoneRecord = _FallbackZoneRecord

    # --- Read methods -----------------------------------------------------

    def domains(self) -> List[Dict]:
        """Return a list of zones with at least a 'name' key.

        Shape aligns with HetznerClient.domains(), which returns dicts.
        """
        zones = self._zones.get_all()
        ret = []
        for z in zones:
            # Best-effort extraction; additional attributes may exist.
            ret.append(
                {'id': getattr(z, 'id', None), 'name': getattr(z, 'name', None)}
            )
        return ret

    def zone_get(self, name: str) -> Dict:
        """Return a zone dict with 'id', 'name', and best-effort 'ttl'."""
        # hcloud typically provides get_all/get_by_id; prefer get_all+filter to
        # avoid relying on a specific helper.
        for z in self._zones.get_all():
            if getattr(z, 'name', None) == name:
                # If zone-level TTL is not exposed, default conservatively.
                ttl = getattr(z, 'ttl', None) or DEFAULT_TTL
                return {'id': getattr(z, 'id', None), 'name': name, 'ttl': ttl}
        # Mirror old client behavior by raising IndexError/KeyError upstream;
        # provider wraps/handles NotFound paths elsewhere.
        raise IndexError('zone not found')

    def zone_records_get(self, zone_id: str) -> List[Dict]:
        """Return flattened per-record dicts derived from RRsets.

        Output keys: 'id', 'type', 'name', 'value', 'ttl', 'zone_id'.
        """
        zone = self._get_zone_by_id_or_name(zone_id)
        rrsets = self._get_rrsets(zone)

        records: List[Dict] = []
        for rrset in rrsets:
            rtype = getattr(rrset, 'type', None)
            ttl = (
                getattr(rrset, 'ttl', None)
                or getattr(zone, 'ttl', None)
                or DEFAULT_TTL
            )
            name = getattr(rrset, 'name', '') or ''
            if name == '@':
                name = ''
            for rec in getattr(rrset, 'records', []) or []:
                value = getattr(rec, 'value', None)
                # Construct a synthetic id from rrset + value to support deletes
                rid = f'{getattr(rrset, "id", "")}:{value}'
                records.append(
                    {
                        'id': rid,
                        'type': rtype,
                        'name': name,
                        'value': value,
                        'ttl': ttl,
                        'zone_id': zone_id,
                    }
                )
        return records

    # --- Write methods (Phase 1: explicit non-support) --------------------

    def zone_record_create(
        self, zone_id: str, name: str, _type: str, value: str, ttl: int = None
    ):
        """Compatibility shim: upsert a single value into the RRSet.

        Provider may call this in legacy flows; prefer rrset_upsert.
        """
        return self.rrset_upsert(zone_id, name, _type, [value], ttl)

    def zone_record_delete(self, zone_id: str, record_id: str):
        """Compatibility shim: record_id is synthetic '<rrset_id>:<value>'.

        Parse and remove the value from the RRSet; delete RRSet if empty.
        """
        rrset_id, _, value = record_id.partition(':')
        return self._rrset_remove_value(zone_id, rrset_id, value)

    def zone_create(
        self, name: str, ttl: int = None, mode: str = "primary"
    ) -> Dict:
        # Best-effort create; fall back to client's create if available
        create = getattr(self._zones, 'create', None)
        if create is None:
            raise NotImplementedError(
                'hcloud backend: zone creation unsupported by client'
            )
        # Pass mode (required) and ttl (optional) to the API
        kwargs = {'name': name, 'mode': mode}
        if ttl is not None:
            kwargs['ttl'] = ttl
        zone = create(**kwargs)
        # Normalize return shape to dict
        return {
            'id': getattr(zone, 'id', None),
            'name': name,
            'ttl': ttl or 3600,
        }

    # --- Value normalization -----------------------------------------------

    def _quote_txt_value(self, value: str) -> str:
        """Wrap TXT record value in double quotes for hcloud API.

        The hcloud API requires TXT records to be fully escaped with double
        quotes. This method ensures values are properly quoted.
        """
        if value.startswith('"') and value.endswith('"'):
            # Already quoted
            return value
        # Escape backslashes and double quotes, then wrap in quotes
        escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'

    # --- RRSet operations --------------------------------------------------

    def rrset_upsert(
        self, zone_id: str, name: str, _type: str, values: List[str], ttl: int
    ):
        """Replace or create RRSet for (name, type) with provided values.

        This is the primary mutation primitive used by the provider.
        """
        zone = self._get_zone_by_id_or_name(zone_id)
        # Try to locate existing rrset
        rrsets = self._get_rrsets(zone)
        target = None
        for r in rrsets:
            if (
                getattr(r, 'name', None) == (name or '')
                and getattr(r, 'type', None) == _type
            ):
                target = r
                break

        # Build records list shape expected by client: [ZoneRecord(value=v), ...]
        # TXT records need to be quoted for the hcloud API
        if _type == 'TXT':
            recs = [
                self._ZoneRecord(value=self._quote_txt_value(v)) for v in values
            ]
        else:
            recs = [self._ZoneRecord(value=v) for v in values]

        if target is None:
            # Create new rrset using zone.create_rrset - TTL is accepted here
            return zone.create_rrset(
                name=name or '@', type=_type, records=recs, ttl=ttl
            )
        else:
            # Update records only (TTL preserved from existing RRSet).
            # set_rrset_records does not accept ttl; use change_rrset_ttl if needed.
            return zone.set_rrset_records(rrset=target, records=recs)

    def rrset_delete(self, zone_id: str, name: str, _type: str):
        zone = self._get_zone_by_id_or_name(zone_id)
        rrsets = self._get_rrsets(zone)
        for r in rrsets:
            if (
                getattr(r, 'name', None) == (name or '')
                and getattr(r, 'type', None) == _type
            ):
                # Use zone.delete_rrset with the rrset object
                return zone.delete_rrset(rrset=r)
        # Nothing to delete
        return None

    # --- Helpers -----------------------------------------------------------

    def _rrset_remove_value(self, zone_id: str, rrset_id: str, value: str):
        zone = self._get_zone_by_id_or_name(zone_id)
        rrsets = self._get_rrsets(zone)
        target = None
        for r in rrsets:
            if str(getattr(r, 'id', '')) == rrset_id:
                target = r
                break
        if target is None:
            return None
        # Remove value and update or delete if empty
        current = [
            getattr(rec, 'value', None)
            for rec in getattr(target, 'records', []) or []
        ]
        new_values = [v for v in current if v != value]
        if not new_values:
            # Delete entire rrset when no values remain
            return zone.delete_rrset(rrset=target)
        # Update rrset with remaining values (TTL preserved from existing RRSet)
        new_records = [self._ZoneRecord(value=v) for v in new_values]
        return zone.set_rrset_records(rrset=target, records=new_records)

    # --- Internal helpers --------------------------------------------------

    def _get_zone_by_id_or_name(self, zone_id_or_name: str) -> Any:
        gb = getattr(self._zones, 'get_by_id', None)
        if callable(gb):
            try:
                z = gb(zone_id_or_name)
                if z is not None:
                    return z
            except Exception:
                pass
        g = getattr(self._zones, 'get', None)
        if callable(g):
            return g(zone_id_or_name)
        raise KeyError(f'Zone not found: {zone_id_or_name}')

    def _get_rrsets(self, zone: Any) -> List[Any]:
        rrsets = getattr(zone, 'rrsets', None)
        if rrsets is not None:
            return rrsets or []
        gr = getattr(self._zones, 'get_rrset_all', None)
        if callable(gr):
            try:
                return gr(zone) or []
            except Exception:
                return []
        return []
