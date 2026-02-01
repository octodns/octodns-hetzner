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
