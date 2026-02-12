## 2.0.0 - 2026-02-12

Major:
* Add hcloud backend (mandatory dep) with Strategy Pattern refactoring
  * New `backend` parameter supports `dnsapi` (default) and `hcloud` options
  * hcloud backend uses Hetzner Cloud Zones API via official hcloud-python client (installed by default)
  * Supports additional record types: DS, TLSA, PTR (when using either backend)
  * Refactored to Strategy Pattern for clean separation of backend-specific logic
  * Extracted modules: exceptions.py, dnsapi_client.py, strategies.py
  * Eliminated conditional backend logic from provider
  * list_zones filters invalid/empty names
  * CAA parsing now uses octoDNS core's CaaValue.parse_rdata_text for consistency
  * Centralized TTL fallback (3600) for hcloud adapter
  * Fix zone_create() to pass required `mode` parameter to hcloud API
  * Fix set_rrset_records() calls to not pass unsupported `ttl` parameter
  * Update test mocks to enforce real hcloud API signatures
  * 100% test coverage maintained
  * Zone-by-zone migration: configure multiple providers with different backends
  * Both backends co-exist (until May 2026)
  * Comprehensive migration guide in README
  * No breaking changes - fully backward compatible - [#49](https://github.com/octodns/octodns-hetzner/pull/49)

Minor:
* Add support for dynamic zone configuration via list_zones method - [#47](https://github.com/octodns/octodns-hetzner/pull/47)

Patch:
* Fix hcloud backend to properly fetch RRSets using zone.get_rrset_all() API
  - `_get_rrsets()` now calls `zone.get_rrset_all()` (correct hcloud API)
  - Previously checked non-existent `zone.rrsets` attribute, causing records to appear missing
  - Fixes issue where root-level MX and TXT records were not fetched from the API - [#49](https://github.com/octodns/octodns-hetzner/pull/49)
* Fix hcloud adapter API compatibility and TXT record handling
  * Fix TypeError: BoundZone.update_rrset() got unexpected keyword argument 'name'
    * Use set_rrset_records() for updating RRSet records instead of update_rrset()
    * update_rrset() only accepts rrset and labels parameters
  * Fix TXT records not being properly escaped for hcloud API
    * TXT records must be fully escaped with double quotes per hcloud API requirements
    * Added _quote_txt_value() helper to wrap TXT values in double quotes
  * Fix AttributeError: 'dict' object has no attribute 'to_payload'
    * hcloud-python library expects ZoneRecord objects with to_payload() method
    * Updated rrset_upsert() and _rrset_remove_value() to create ZoneRecord instances
    * Added to_payload() method to fallback ZoneRecord class - [#49](https://github.com/octodns/octodns-hetzner/pull/49)
* Fix TXT record chunking for long values (DKIM keys) in hcloud backend
  - Use `record.chunked_values` instead of `record.values` for TXT params in hcloud backend
  - Long TXT values (>255 chars) are now automatically split into RFC-compliant chunks
  - Fixes hcloud API rejection of DKIM and other long TXT records - [#49](https://github.com/octodns/octodns-hetzner/pull/49)
* Fix hcloud backend TTL updates with correct API methods
  - Use set_rrset_records() + change_rrset_ttl() for RRSet updates
  - Fix regression: update_rrset() only accepts (rrset, labels) per hcloud API
  - Update test mocks to match real hcloud BoundZone API
  - Add debug logging for TTL update operations - [#49](https://github.com/octodns/octodns-hetzner/pull/49)
* Use new [changelet](https://github.com/octodns/changelet) tooling - [#46](https://github.com/octodns/octodns-hetzner/pull/46)

## v1.0.0 - 2025-05-04 - Long overdue 1.0

* Address pending octoDNS 2.x deprecations, require minimum of 1.5.x
* Add hcloud backend with Strategy Pattern for Cloud Zones API support
* Fix hcloud zone creation race condition using action.wait_until_finished()
* Fix hcloud apex record name normalization (`@` vs empty string)
* Fix hcloud zone recreation cache staleness after external deletion

## v0.0.3 - 2023-02-08 - AKA

* Support for `ALIAS` record types

## v0.0.2 - 2022-05-20 - Root NS Support

* Enable management of root NS records

## v0.0.1 - 2022-01-12 - Moving

#### Nothworthy Changes

* Initial extraction of HetznerProvider from octoDNS core

#### Stuff

Nothing
