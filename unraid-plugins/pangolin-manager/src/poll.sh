#!/bin/bash
# Invoked once per minute by Unraid cron. The second sample is scheduled at +30s.
set -eu
if [[ ! -f /usr/local/emhttp/plugins/pangolin-manager/worker.php ]]; then exit 0; fi
if [[ "${1:-}" != "once" ]]; then
  (sleep 30; /usr/local/emhttp/plugins/pangolin-manager/poll.sh once) >/dev/null 2>&1 &
fi
exec /usr/bin/php /usr/local/emhttp/plugins/pangolin-manager/worker.php
