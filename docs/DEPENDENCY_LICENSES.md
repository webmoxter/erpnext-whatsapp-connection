# Dependency license review

Reviewed against `gateway/pnpm-lock.yaml` for the initial development release.

Direct dependencies:

| Package | Version | License |
| --- | --- | --- |
| `baileys` | `7.0.0-rc14` | MIT |
| `pino` | `9.9.5` | MIT |
| `qrcode` | `1.5.4` | MIT |

Notable transitive dependencies include MIT, BSD-3-Clause, Apache-2.0, ISC,
BlueOak-1.0.0, 0BSD, and GPL-3.0 components. In particular, Baileys resolves
`libsignal` 6.0.0 under GPL-3.0. The combined repository is therefore distributed
under GPL-3.0-only. This inventory must be regenerated and reviewed whenever the
lockfile changes.

This review is a distribution-control record, not legal advice.

The v0.1.5 preparation leaves the gateway lockfile and application Python
dependencies unchanged. The disposable integration image adds Debian Chromium
and Liberation fonts for actual native settings-browser acceptance. These are
test-image tools, not gateway-image dependencies or vendored Python-wheel
contents. Chromium is distributed under BSD-style and component-specific
licenses; Liberation fonts use the SIL Open Font License. Debian package
copyright/license files remain in that test image. The browser harness uses
Frappe's existing websockets dependency; it adds no application Python package.
