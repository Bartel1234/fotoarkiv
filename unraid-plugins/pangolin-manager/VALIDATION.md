# Validation — 0.1.0-beta.2

Performed locally with PHP 8.3, a real HTTP test server and jsdom:

- PHP, JavaScript and shell syntax checks.
- Backend regression checks for validation, command/header injection, subprocess
  timeout, HTTP classification, unknown API schema, token redaction and notification
  outage/recovery behavior.
- 40 backend regression checks and 15 real HTTP/PHP integration checks with a fixture Docker CLI.
- DOM checks with fixture API responses: status updates, save/settings, CSRF payload,
  restart confirmation/cancel, secret field behavior, hostile labels displayed as
  text, stale status, failed refresh and Dashboard tile interactions.
- Concurrent local HTTP probes tested against five real endpoints: approximately
  0.45 seconds total for five 0.35-second responses.
- Installer XML parsing, embedded payload SHA-256, extracted payload paths and
  install/remove shell syntax checked.

Not performed: installation on a running Unraid server, real Docker interaction,
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

GitHub edition beta.2 adds the hosted installation/update URL and a higher Unraid
manifest version. Application behavior is unchanged. XML, payload checksum,
archive contents and installer scripts were validated after rebuilding. The
published raw manifest must match the locally validated file.
