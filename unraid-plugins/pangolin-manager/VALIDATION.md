# Validation — 0.1.0-beta.4

Performed locally with PHP 8.3, a real HTTP test server and jsdom:

- PHP, JavaScript and shell syntax checks.
- Backend regression checks for validation, command/header injection, subprocess
  timeout, HTTP classification, unknown API schema, token redaction and notification
  outage/recovery behavior.
- 40 backend regression checks and 30 real HTTP/PHP integration checks. Integration
  runs cover ordinary PHP, native Unraid-style CSRF preprocessing, and native
  preprocessing with `proc_open` disabled. Docker CLI and HTTP API are fixtures.
- Reproduced beta.3 failures with a fixture of native `local_prepend.php` behavior:
  the standard CSRF field is validated, then removed before plugin execution.
  Beta.4 save, test, logs and confirmed restart succeed under that fixture.
- Missing/empty/invalid plugin tokens reject writes, even with a valid native
  token. Rejected saves do not create settings. All POST actions remain protected.
- Docker API list/inspect parsing, CLI fallback, suggested Newt ordering, empty
  list, missing container, malformed responses, controlled errors and secret
  exclusion from error responses.
- The environment prohibits AF_UNIX sockets. Docker API tests replace only the
  transport with a local TCP fixture; real Unix socket access is not verified.
- DOM checks with fixture API responses: status updates, save/settings, CSRF payload,
  restart confirmation/cancel, secret field behavior, hostile labels displayed as
  text, stale status, failed refresh and Dashboard tile interactions.
- Concurrent local HTTP probes tested against five real endpoints: approximately
  0.45 seconds total for five 0.35-second responses.
- Installer XML parsing, embedded payload SHA-256, extracted payload paths and
  install/remove shell syntax checked.

User screenshots confirm installation and the Tools settings page on DeathStar
(Unraid 7.3.2). Beta.2 container discovery failed with an uninformative error.
The exact server-side cause is not confirmed. Beta.3 addresses socket/CLI/PHP
compatibility and supplies actionable errors. A later screenshot confirms
container discovery and selection work on DeathStar, but saving was rejected
with a false session-expired error.

Unraid source `emhttp/plugins/dynamix/include/local_prepend.php` confirms it removes
`$_POST[csrf_token]` and the native CSRF header after validation. Beta.4 fixes the
plugin recheck using a separately named copy, which is still validated against
Unraid state. Beta.4 on-server save verification is pending.

Not performed: direct on-server testing, real Docker interaction,
actual Pangolin/Newt API traffic, cron scheduling after a real reboot and delivery
through Unraid's notification channels. Chromium cannot start in this execution
environment, so full browser tests, screenshots and visual layout verification
were not completed. The included Playwright test is available for an environment
with a working browser; it has not been marked as passed. CSS supports narrow
screens and inherits Unraid theme colors, but appearance needs on-server review.

The first on-server trial should verify:

1. Install, Tools page and Dashboard tile are visible on the user's Unraid version.
2. Select the real Newt container; identify local running/stopped state.
3. Enable/configure health file or API; verify both connected and disconnected state.
4. Add an actual local service and verify both success and failure results.
5. Confirm background status updates with the browser closed; verify reboot persistence.
6. If enabled, exercise a sustained outage and one recovery notification.
7. Verify removal stops future polling without removing Newt or settings.

Beta.4 installer XML, embedded payload checksum, archive contents and installer
scripts were validated after rebuilding. The published raw manifest must match
the locally validated file.
