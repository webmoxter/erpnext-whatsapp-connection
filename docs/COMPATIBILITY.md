# Compatibility policy

| Add-on | Frappe | ERPNext | Python | Node | Upgrade policy |
|---|---|---|---|---|---|
| 0.1.x | 16.x | 16.x | 3.14 | 24.x | Backward-compatible fixes only |

Frappe and ERPNext core files are never patched. Custom applications integrate
through the document, report, and transport provider hooks documented in
`ARCHITECTURE.md`.

Minor releases may add optional fields, adapters, or transports. Patch releases
may fix behavior without changing stored-data meaning. Removing a field, changing
an adapter contract, or requiring a destructive migration requires a new major
version and a documented transition path.

Every upgrade must be tested against a restored site backup before production.
Downgrades across a database migration are supported only by restoring the
pre-upgrade backup; application uninstall is not a rollback mechanism.
