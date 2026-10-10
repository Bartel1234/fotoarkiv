# Changelog

## 0.1.0-beta.4 — 2026-10-10

- Fix false session-expired errors when saving settings, testing, viewing logs or
  restarting: native `local_prepend.php` consumes the standard CSRF token before
  plugin code executes. Send a separate `pm_csrf_token` copy and validate it
  independently against the current Unraid token.
- Keep native CSRF validation and reject missing, empty or invalid plugin tokens.
- Reproduce the failure and test the fix using native preprocessing fixtures.
- Version JavaScript/CSS URLs to refresh stale browser caches after updating;
  show the full application version in the panel.
- Increase the Unraid manifest version to `2026.10.10.3`.

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
