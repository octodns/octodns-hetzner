#
#
#

import logging
from collections import defaultdict

from octodns.provider.base import BaseProvider
from octodns.record import RdataParseError, Record, Rrset
from octodns.record.caa import CaaValue

# There is no public export for the TXT/SPF value type; this is the same
# private class octoDNS core's own tinydns source uses for the equivalent
# raw-text handling (octodns/source/tinydns.py). Flagged upstream on
# octodns/octodns#1452 as a gap: providers that receive raw (non-RDATA)
# TXT/SPF text have no public class to call normalize_raw_text() on.
from octodns.record.chunked import _ChunkedValue as TxtValue

# Import exceptions for backward compatibility
from .exceptions import (
    HetznerClientException,
    HetznerClientNotFound,
    HetznerClientUnauthorized,
)

# TODO: remove __VERSION__ with the next major version release
__version__ = __VERSION__ = '2.0.0'

# Export for backward compatibility; guard HetznerClient on successful import
__all__ = [
    "HetznerProvider",
    "HetznerClientException",
    "HetznerClientNotFound",
    "HetznerClientUnauthorized",
]

# Backwards-compatibility: expose HetznerClient at package level when available
try:
    from .dnsapi_client import HetznerClient  # type: ignore

    __all__.append("HetznerClient")
except Exception:
    # Keep import-time failures from breaking consumers that don't use it
    HetznerClient = None  # type: ignore


class HetznerProvider(BaseProvider):
    SUPPORTS_GEO = False
    SUPPORTS_DYNAMIC = False
    SUPPORTS_ROOT_NS = True
    SUPPORTS = set(
        (
            "A",
            "AAAA",
            "CAA",
            "CNAME",
            "DS",
            "MX",
            "NS",
            "PTR",
            "SRV",
            "TLSA",
            "TXT",
        )
    )

    def __init__(self, id, token, *args, **kwargs):
        self.log = logging.getLogger(f"HetznerProvider[{id}]")
        backend = kwargs.pop("backend", "dnsapi")
        self.log.debug("__init__: id=%s, token=***, backend=%s", id, backend)
        super().__init__(id, *args, **kwargs)

        # Store backend for backward compatibility
        self._backend = backend

        # Factory methods create client and strategy based on backend
        self._client = self._create_client(backend, token)
        self._strategy = self._create_strategy(backend)

        # Cache structures
        self._zone_records = {}
        self._zone_metadata = {}
        self._zone_name_to_id = {}

    def _create_client(self, backend: str, token: str):
        """Factory method for client creation with lazy imports.

        Args:
            backend: Backend type ('dnsapi' or 'hcloud')
            token: API token

        Returns:
            DNS client instance

        Raises:
            ValueError: If backend is invalid
            ImportError: If hcloud backend is requested but not installed
        """
        if backend == "hcloud":
            # Lazy import is fine even with mandatory dependency, improves import time
            try:
                from .hcloud_adapter import HCloudZonesClient

                return HCloudZonesClient(token)
            except ImportError as e:
                # hcloud is a required dependency; guide towards reinstall/fixing env
                raise ImportError(
                    "backend='hcloud' requires the 'hcloud' package (required dependency). "
                    "It should be installed automatically. Please reinstall octodns-hetzner "
                    "or ensure your environment can import 'hcloud'."
                ) from e
        elif backend == "dnsapi":
            from .dnsapi_client import HetznerClient

            return HetznerClient(token)
        else:
            raise ValueError(
                f"Invalid backend '{backend}'. Must be 'dnsapi' or 'hcloud'"
            )

    def _create_strategy(self, backend: str):
        """Factory method for strategy creation.

        Args:
            backend: Backend type ('dnsapi' or 'hcloud')

        Returns:
            Apply strategy instance
        """
        if backend == "hcloud":
            from .strategies import HCloudStrategy

            return HCloudStrategy()
        else:
            from .strategies import DNSAPIStrategy

            return DNSAPIStrategy()

    def _append_dot(self, value):
        if value == "@" or value[-1] == ".":
            return value
        return f"{value}."

    def zone_metadata(self, zone_id=None, zone_name=None):
        if zone_name is not None:
            if zone_name in self._zone_name_to_id:
                zone_id = self._zone_name_to_id[zone_name]
            else:
                try:
                    zone = self._client.zone_get(name=zone_name[:-1])
                except (HetznerClientNotFound, IndexError, KeyError, TypeError):
                    # Normalize adapter/client errors into NotFound so that
                    # callers can handle consistently
                    raise HetznerClientNotFound()
                zone_id = zone["id"]
                self._zone_name_to_id[zone_name] = zone_id
                self._zone_metadata[zone_id] = zone

        return self._zone_metadata[zone_id]

    def _record_ttl(self, record):
        default_ttl = self.zone_metadata(zone_id=record["zone_id"])["ttl"]
        return record["ttl"] if "ttl" in record else default_ttl

    def _rdata_for(self, _type, value):
        """Normalize a raw Hetzner API value into RDATA presentation text.

        Hetzner returns values with the record-name-shaped fields (targets,
        exchanges) missing their trailing dot, so that gets patched in here,
        before handing the string to octoDNS's from_rdata_text() parsers.
        """
        if _type in ("CNAME", "NS", "PTR"):
            return self._append_dot(value)
        elif _type in ("MX", "SRV"):
            # only the trailing field (target/exchange) is a name
            head, _, target = value.strip().rpartition(" ")
            return f"{head} {self._append_dot(target)}"
        elif _type == "CAA":
            try:
                CaaValue.from_rdata_text(value)
            except RdataParseError as e:
                # Fallback best-effort for unexpected formats, matches the
                # previous behavior of _data_for_CAA
                self.log.warning(
                    "_rdata_for: failed to parse CAA record %r: %s, "
                    "using fallback value (flags=0, tag=issue)",
                    value,
                    e,
                )
                return f'0 issue "{value}"'
        return value

    def list_zones(self):
        self.log.debug("list_zones:")
        domains = []
        for d in self._client.domains():
            try:
                name = d.get("name") if isinstance(d, dict) else None
            except Exception:
                name = None
            if name:
                domains.append(f"{name}.")
        return sorted(domains)

    def zone_records(self, zone):
        if zone.name not in self._zone_records:
            try:
                zone_id = self.zone_metadata(zone_name=zone.name)["id"]
                self._zone_records[zone.name] = self._client.zone_records_get(
                    zone_id
                )
            except HetznerClientNotFound:
                return []

        return self._zone_records[zone.name]

    def populate(self, zone, target=False, lenient=False):
        self.log.debug(
            "populate: name=%s, target=%s, lenient=%s",
            zone.name,
            target,
            lenient,
        )

        values = defaultdict(lambda: defaultdict(list))
        for record in self.zone_records(zone):
            _type = record["type"]
            if _type not in self.SUPPORTS:
                self.log.warning(
                    "populate: skipping unsupported %s record", _type
                )
                continue
            values[record["name"]][record["type"]].append(record)

        before = len(zone.records)
        rrsets = []
        for name, types in values.items():
            fqdn = zone.name if name == "@" else f"{name}.{zone.name}"
            for _type, records in types.items():
                ttl = self._record_ttl(records[0])
                if _type == "TXT":
                    # Hetzner returns TXT as raw provider text, not RDATA
                    # presentation format, so these can't go through
                    # Record.from_rrsets() -> TxtValue.from_rdata_text().
                    # dnspython treats an unquoted ';' as a master-file
                    # comment, which silently truncates values like
                    # 'v=DKIM1;k=rsa;s=email;...' down to 'v=DKIM1', and
                    # raises RdataParseError on any unquoted value over 255
                    # chars.
                    #
                    # The quoting we get back is inconsistent (see
                    # ansible-collections/community.dns#48): values over 255
                    # bytes come back as multiple quoted chunks, while
                    # shorter values without spaces keep whatever quoting was
                    # originally written. normalize_raw_text() handles both
                    # -- TxtValue.process() strips the outer quotes and joins
                    # on '" "'.
                    data = {
                        "ttl": ttl,
                        "type": _type,
                        "values": [
                            TxtValue.normalize_raw_text(record["value"])
                            for record in records
                        ],
                    }
                    new_record = Record.new(
                        zone, name, data, source=self, lenient=lenient
                    )
                    zone.add_record(new_record, lenient=lenient)
                else:
                    rrsets.append(
                        Rrset(
                            fqdn,
                            _type,
                            ttl,
                            [
                                self._rdata_for(_type, record["value"])
                                for record in records
                            ],
                        )
                    )

        for record in Record.from_rrsets(
            zone, rrsets, lenient=lenient, source=self
        ):
            zone.add_record(record, lenient=lenient)

        exists = zone.name in self._zone_records
        self.log.info(
            "populate:   found %s records, exists=%s",
            len(zone.records) - before,
            exists,
        )
        return exists

    def _params_for(self, record):
        rrset = record.to_rrset()
        if record._type == "TXT" and self._backend != "hcloud":
            # dnsapi wants raw text rather than the presentation-format
            # RDATA to_rrset() produces. It would accept quoted values, but
            # writing them is a bad trade: Hetzner's re-quoting is
            # inconsistent enough to cause idempotency churn (see
            # ansible-collections/community.dns#48, which settled on
            # unquoted-by-default for Hetzner over exactly this),
            # to_rdata_text() escapes '"' as '\"' which TxtValue.process()
            # never unescapes on the way back in, and Hetzner already chunks
            # long raw values RFC-conformantly on its own side.
            #
            # octoDNS core has normalize_raw_text() for presentation ->
            # internal on read but no inverse for internal -> raw, so
            # unescape by hand.
            rdatas = [value.replace("\\;", ";") for value in record.values]
        else:
            # hcloud is RRSet-native and wants quoted, chunked presentation
            # text -- exactly what to_rrset() emits, matching the
            # record.chunked_values output this replaces.
            rdatas = rrset.rdatas
        for rdata in rdatas:
            yield {
                "value": rdata,
                "name": record.name,
                "ttl": rrset.ttl,
                "type": rrset._type,
            }

    def _apply_Create(self, zone_id, change):
        """Delegate create operation to strategy."""
        self._strategy.apply_create(
            self._client, zone_id, change, self._params_for
        )

    def _apply_Update(self, zone_id, change):
        """Delegate update operation to strategy."""
        zone = change.existing.zone
        self._strategy.apply_update(
            self._client,
            zone_id,
            change,
            self._params_for,
            self.zone_records(zone),
        )

    def _apply_Delete(self, zone_id, change):
        """Delegate delete operation to strategy."""
        zone = change.existing.zone
        self._strategy.apply_delete(
            self._client, zone_id, change, self.zone_records(zone)
        )

    def _apply(self, plan):
        desired = plan.desired
        changes = plan.changes
        self.log.debug(
            "_apply: zone=%s, len(changes)=%d", desired.name, len(changes)
        )

        try:
            zone_id = self.zone_metadata(zone_name=desired.name)["id"]
        except HetznerClientNotFound:
            self.log.debug("_apply:   no matching zone, creating domain")
            zone_id = self._client.zone_create(desired.name[:-1])["id"]

        for change in changes:
            class_name = change.__class__.__name__
            getattr(self, f"_apply_{class_name}")(zone_id, change)

        # Clear out the cache if any
        self._zone_records.pop(desired.name, None)
