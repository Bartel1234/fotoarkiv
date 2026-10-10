# Pangolin Manager for Unraid

Version **0.1.0-beta.4** · Unraid **7.x** · Danish interface.

A native Unraid plugin for an existing Newt container: Dashboard tile, status panel,
local HTTP checks, optional Pangolin integration API, redacted Newt logs and opt-in
Unraid notifications. Newt continues to run in Docker. No new web server, port or
Python/Node runtime is installed on Unraid.

Start with [INSTALLATION-DA.md](INSTALLATION-DA.md).

## Features and measurement scope

- Native Dashboard tile using Unraid's `$mytiles` integration.
- Tools → Pangolin Manager, with Overview, Settings and Newt Log tabs.
- Container discovery suggests images/names containing `newt` or `pangolin-cli`.
- Tunnel measurement uses the selected container's `HEALTH_FILE` (or a configured
  override) with `docker exec … test -f …`. A stopped/paused/restarting container
  is offline. Without a usable health file/API, tunnel state is **unknown**.
- Optional HTTPS API with a read-only organization key and explicit site ID.
  Current adapter reads `GET <api_base>/org/<org_id>/sites`, supporting explicit
  boolean `online` or known `status` enums. Unknown API formats remain unknown.
- Up to 12 concurrent HTTP GET checks, from **Unraid's network context**, not Newt's
  Docker network or the public internet. Public URLs are navigation links only.
- HTTP health mode accepts 2xx/3xx. 401/403 means unknown health. Reachability mode
  accepts any HTTP response; it establishes server reachability, not application health.
- TLS verification is enabled. Redirects are not followed. Individual HTTP tests
  have a 2.5-second timeout. Subprocesses have bounded runtimes and use argument arrays, or individually
  quoted arguments with the system timeout command when PHP disables `proc_open`.
- Container discovery and inspection prefer the local `/var/run/docker.sock` API,
  with a Docker CLI fallback and absolute executable paths where available.
  Expected Docker errors are shown in the panel without returning raw stderr.
- Status is cached in RAM. Cron samples at each minute and again 30 seconds later.
  The GUI polls at 30 seconds and pauses polling when the tab is hidden.
- Results over 90 seconds old become **unknown**, rather than keeping a green badge.
- Optional notifications after 120 seconds of confirmed faults; recovery only when
  configured checks have known healthy results. No automatic restart or remediation.
- Restart affects only the selected container and requires a confirmation dialog.
- Last 120 log lines from 24 hours, with known container secrets and API token
  removed, plus common credential patterns. Redaction cannot promise removal of
  arbitrary personal data or every possible secret format.

## Security and storage

The UI and endpoint use the existing authenticated Unraid WebGUI. Writes, manual
checks, logs and restart require Unraid's CSRF token. The browser sends the
standard `csrf_token` for native validation and an identical `pm_csrf_token` copy
for the plugin's independent validation, because Unraid consumes its standard
field before endpoint code executes. Neither check is skipped. The plugin does not open a
public endpoint or change Pangolin access rules. Keep Unraid management access
restricted as usual.

Settings live in `/boot/config/plugins/pangolin-manager/settings.json`. This includes
the optional API key; the API never returns that key to the browser. It is **not
encrypted at rest**. Unix permissions are requested, but Unraid's FAT flash filesystem
does not enforce normal Unix file permissions. Flash exports/backups therefore need
the same care as the rest of your Unraid configuration. Use a least-privilege key.

Runtime status, locks and notification state live in `/var/local/pangolin-manager`.
They do not generate continuous writes to the flash drive.

## Installation and lifecycle

`pangolin-manager.plg` contains the entire source package as a base64 payload with a
SHA-256 checksum. The installation does not download third-party dependencies.
The plugin installer restores its UI and cron schedule after a reboot. Uninstalling
via Unraid removes the UI and schedule, preserving settings and the Newt container.

The plugin is hosted in its own directory in the `Bartel1234/fotoarkiv` repository.
Install by pasting this URL into **Plugins → Install Plugin**:

```text
https://raw.githubusercontent.com/Bartel1234/fotoarkiv/main/unraid-plugins/pangolin-manager/pangolin-manager.plg
```

The manifest includes this address as `pluginURL`, so Unraid can check for future
plugin versions through its normal plugin update mechanism. Updates are installed
when the user chooses Update; this does not enable unattended updates. There is no
Community Applications listing yet. Never publish an installation's `settings.json`
or API key in a source repository.

## Build and validation

Build: `python3 build.py`. It produces the `.plg` and a source/install ZIP in `dist/`.
Run `tests/backend.php` with PHP 8.1+ and cURL, `tests/integration.py` with PHP and
Python, and `tests/ui.cjs` with jsdom. `tests/browser.cjs` requires Playwright and a
working browser; it was not completed in this environment.
See [VALIDATION.md](VALIDATION.md) for the performed checks and remaining on-server checks.

## Sources for integration

- [Unraid official custom tile example](https://github.com/unraid/webgui/blob/master/emhttp/plugins/dynamix/DashboardCustomTileExample.page-)
- [Unraid plugin manager](https://github.com/unraid/webgui/blob/master/emhttp/plugins/dynamix.plugin.manager/scripts/plugin)
- [Pangolin Newt configuration](https://docs.pangolin.net/manage/sites/configure-site)
- [Pangolin integration API](https://docs.pangolin.net/manage/integration-api)

The implementation is original; referenced projects were consulted for interface contracts.
