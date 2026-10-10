# Changelog

## 0.1.0-beta.3 — 2026-10-10

- Fix container discovery compatibility: prefer the local Docker socket API, as
  Unraid Docker Manager does, and retain a CLI fallback.
- Prefer absolute Docker executable paths to avoid PHP-FPM PATH differences.
- Support bounded, individually quoted commands when `proc_open` is disabled.
- Show controlled Docker/configuration errors in the panel; log unexpected error
  types and locations without exception messages or arguments.
- Add discovery failure, Docker API response and disabled-proc_open regressions.
- Increase the Unraid manifest version to `2026.10.10.2`.

## 0.1.0-beta.2 — 2026-10-10

- Publish a standalone installer at a stable GitHub raw URL.
- Add `pluginURL` to enable Unraid's normal plugin update checks.
- Increase the Unraid manifest version to `2026.10.10.1`.
- Document URL installation and manual update checks.

## 0.1.0-beta.1 — 2026-10-10

- Native Unraid Dashboard tile and Tools status panel.
- Existing Newt container discovery, tunnel health file and optional Pangolin API.
- Local HTTP checks, redacted log viewer, confirmed restart and opt-in notifications.
- First beta, tested locally; live Unraid verification remains outstanding.
