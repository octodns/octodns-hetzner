#
#
#

import logging
import shlex
from collections import defaultdict

from octodns.provider.base import BaseProvider
from octodns.record import Record
from octodns.record.ds import DsValue
from octodns.record.tlsa import TlsaValue

# Import exceptions for backward compatibility
from .exceptions import (
    HetznerClientException,
    HetznerClientNotFound,
    HetznerClientUnauthorized,
)

# TODO: remove __VERSION__ with the next major version release
__version__ = __VERSION__ = '1.0.0'

# Export for backward compatibility; guard HetznerClient on successful import
__all__ = [
    'HetznerProvider',
    'HetznerClientException',
    'HetznerClientNotFound',
    'HetznerClientUnauthorized',
]

# Backwards-compatibility: expose HetznerClient at package level when available
try:
    from .dnsapi_client import HetznerClient  # type: ignore

    __all__.append('HetznerClient')
except Exception:
    # Keep import-time failures from breaking consumers that don't use it
    HetznerClient = None  # type: ignore


class HetznerProvider(BaseProvider):
    SUPPORTS_GEO = False
    SUPPORTS_DYNAMIC = False
    SUPPORTS_ROOT_NS = True
    SUPPORTS = set(
        (
            'A',
            'AAAA',
            'CAA',
            'CNAME',
            'DS',
            'MX',
            'NS',
            'PTR',
            'SRV',
            'TLSA',
            'TXT',
        )
    )

    def __init__(self, id, token, *args, **kwargs):
        self.log = logging.getLogger(f'HetznerProvider[{id}]')
        backend = kwargs.pop('backend', 'dnsapi')
        self.log.debug('__init__: id=%s, token=***, backend=%s', id, backend)
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
        if backend == 'hcloud':
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
        elif backend == 'dnsapi':
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
        if backend == 'hcloud':
            from .strategies import HCloudStrategy

            return HCloudStrategy()
        else:
            from .strategies import DNSAPIStrategy

            return DNSAPIStrategy()

    def _append_dot(self, value):
        if value == '@' or value[-1] == '.':
            return value
        return f'{value}.'

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
                zone_id = zone['id']
                self._zone_name_to_id[zone_name] = zone_id
                self._zone_metadata[zone_id] = zone

        return self._zone_metadata[zone_id]

    def _record_ttl(self, record):
        default_ttl = self.zone_metadata(zone_id=record['zone_id'])['ttl']
        return record['ttl'] if 'ttl' in record else default_ttl

    def _data_for_multiple(self, _type, records):
        values = [record['value'].replace(';', '\\;') for record in records]
        return {
            'ttl': self._record_ttl(records[0]),
            'type': _type,
            'values': values,
        }

    _data_for_A = _data_for_multiple
    _data_for_AAAA = _data_for_multiple

    def _data_for_CAA(self, _type, records):
        values = []
        for record in records:
            raw = record['value']
            try:
                parts = shlex.split(raw)
                if len(parts) < 3:
                    raise ValueError('CAA rdata must have at least 3 tokens')
                flags = int(parts[0])
                tag = parts[1]
                value = parts[2]
                values.append({'flags': flags, 'tag': tag, 'value': value})
            except Exception as e:
                # Fallback best-effort for unexpected formats
                self.log.warning(
                    '_data_for_CAA: failed to parse CAA record %r: %s, '
                    'using fallback values (flags=0, tag=issue)',
                    raw,
                    e,
                )
                values.append({'flags': 0, 'tag': 'issue', 'value': raw})
        return {
            'ttl': self._record_ttl(records[0]),
            'type': _type,
            'values': values,
        }

    def _data_for_CNAME(self, _type, records):
        record = records[0]
        return {
            'ttl': self._record_ttl(record),
            'type': _type,
            'value': self._append_dot(record['value']),
        }

    def _data_for_PTR(self, _type, records):
        record = records[0]
        return {
            'ttl': self._record_ttl(record),
            'type': _type,
            'value': self._append_dot(record['value']),
        }

    def _data_for_MX(self, _type, records):
        values = []
        for record in records:
            value_stripped_split = record['value'].strip().split(' ')
            preference = value_stripped_split[0]
            exchange = value_stripped_split[-1]
            values.append(
                {
                    'preference': int(preference),
                    'exchange': self._append_dot(exchange),
                }
            )
        return {
            'ttl': self._record_ttl(records[0]),
            'type': _type,
            'values': values,
        }

    def _data_for_NS(self, _type, records):
        values = []
        for record in records:
            values.append(self._append_dot(record['value']))
        return {
            'ttl': self._record_ttl(records[0]),
            'type': _type,
            'values': values,
        }

    def _data_for_DS(self, _type, records):
        values = []
        for record in records:
            parsed = DsValue.parse_rdata_text(record['value'])
            values.append(parsed)
        return {
            'ttl': self._record_ttl(records[0]),
            'type': _type,
            'values': values,
        }

    def _data_for_SRV(self, _type, records):
        values = []
        for record in records:
            value_stripped = record['value'].strip()
            priority = value_stripped.split(' ')[0]
            weight = value_stripped[len(priority) :].strip().split(' ')[0]
            target = value_stripped.split(' ')[-1]
            port = value_stripped[: -len(target)].strip().split(' ')[-1]
            values.append(
                {
                    'port': int(port),
                    'priority': int(priority),
                    'target': self._append_dot(target),
                    'weight': int(weight),
                }
            )
        return {
            'ttl': self._record_ttl(records[0]),
            'type': _type,
            'values': values,
        }

    _data_for_TXT = _data_for_multiple

    def _data_for_TLSA(self, _type, records):
        values = []
        for record in records:
            parsed = TlsaValue.parse_rdata_text(record['value'])
            values.append(parsed)
        return {
            'ttl': self._record_ttl(records[0]),
            'type': _type,
            'values': values,
        }

    def list_zones(self):
        self.log.debug('list_zones:')
        domains = []
        for d in self._client.domains():
            try:
                name = d.get('name') if isinstance(d, dict) else None
            except Exception:
                name = None
            if name:
                domains.append(f'{name}.')
        return sorted(domains)

    def zone_records(self, zone):
        if zone.name not in self._zone_records:
            try:
                zone_id = self.zone_metadata(zone_name=zone.name)['id']
                self._zone_records[zone.name] = self._client.zone_records_get(
                    zone_id
                )
            except HetznerClientNotFound:
                return []

        return self._zone_records[zone.name]

    def populate(self, zone, target=False, lenient=False):
        self.log.debug(
            'populate: name=%s, target=%s, lenient=%s',
            zone.name,
            target,
            lenient,
        )

        values = defaultdict(lambda: defaultdict(list))
        for record in self.zone_records(zone):
            _type = record['type']
            if _type not in self.SUPPORTS:
                self.log.warning(
                    'populate: skipping unsupported %s record', _type
                )
                continue
            values[record['name']][record['type']].append(record)

        before = len(zone.records)
        for name, types in values.items():
            for _type, records in types.items():
                data_for = getattr(self, f'_data_for_{_type}')
                record = Record.new(
                    zone,
                    name,
                    data_for(_type, records),
                    source=self,
                    lenient=lenient,
                )
                zone.add_record(record, lenient=lenient)

        exists = zone.name in self._zone_records
        self.log.info(
            'populate:   found %s records, exists=%s',
            len(zone.records) - before,
            exists,
        )
        return exists

    def _params_for_multiple(self, record):
        for value in record.values:
            yield {
                'value': value.replace('\\;', ';'),
                'name': record.name,
                'ttl': record.ttl,
                'type': record._type,
            }

    _params_for_A = _params_for_multiple
    _params_for_AAAA = _params_for_multiple

    def _params_for_CAA(self, record):
        for value in record.values:
            data = f'{value.flags} {value.tag} "{value.value}"'
            yield {
                'value': data,
                'name': record.name,
                'ttl': record.ttl,
                'type': record._type,
            }

    def _params_for_single(self, record):
        yield {
            'value': record.value,
            'name': record.name,
            'ttl': record.ttl,
            'type': record._type,
        }

    _params_for_CNAME = _params_for_single
    _params_for_PTR = _params_for_single

    def _params_for_MX(self, record):
        for value in record.values:
            data = f'{value.preference} {value.exchange}'
            yield {
                'value': data,
                'name': record.name,
                'ttl': record.ttl,
                'type': record._type,
            }

    _params_for_NS = _params_for_multiple

    def _params_for_DS(self, record):
        for value in record.values:
            data = f'{value.key_tag} {value.algorithm} {value.digest_type} {value.digest}'
            yield {
                'value': data,
                'name': record.name,
                'ttl': record.ttl,
                'type': record._type,
            }

    def _params_for_SRV(self, record):
        for value in record.values:
            data = (
                f'{value.priority} {value.weight} {value.port} '
                f'{value.target}'
            )
            yield {
                'value': data,
                'name': record.name,
                'ttl': record.ttl,
                'type': record._type,
            }

    _params_for_TXT = _params_for_multiple

    def _params_for_TLSA(self, record):
        for value in record.values:
            data = (
                f'{value.certificate_usage} {value.selector} {value.matching_type} '
                f'{value.certificate_association_data}'
            )
            yield {
                'value': data,
                'name': record.name,
                'ttl': record.ttl,
                'type': record._type,
            }

    def _apply_Create(self, zone_id, change):
        """Delegate create operation to strategy."""
        params_for = getattr(self, f'_params_for_{change.new._type}')
        self._strategy.apply_create(self._client, zone_id, change, params_for)

    def _apply_Update(self, zone_id, change):
        """Delegate update operation to strategy."""
        params_for = getattr(self, f'_params_for_{change.new._type}')
        zone = change.existing.zone
        self._strategy.apply_update(
            self._client, zone_id, change, params_for, self.zone_records(zone)
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
            '_apply: zone=%s, len(changes)=%d', desired.name, len(changes)
        )

        try:
            zone_id = self.zone_metadata(zone_name=desired.name)['id']
        except HetznerClientNotFound:
            self.log.debug('_apply:   no matching zone, creating domain')
            zone_id = self._client.zone_create(desired.name[:-1])['id']

        for change in changes:
            class_name = change.__class__.__name__
            getattr(self, f'_apply_{class_name}')(zone_id, change)

        # Clear out the cache if any
        self._zone_records.pop(desired.name, None)
