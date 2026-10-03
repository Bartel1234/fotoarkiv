#!/bin/sh
set -eu
python - <<'PY'
import os
password = os.environ.get('APP_PASSWORD', '')
if len(password) < 12 or password == 'SKIFT_TIL_EN_LANG_ADGANGSKODE':
    raise SystemExit('Set APP_PASSWORD to at least 12 characters in .env')
PY
case "$RESOLUTION" in *[!0-9x]*|'') echo 'Invalid RESOLUTION; use WIDTHxHEIGHT' >&2; exit 1;; esac
mkdir -p /control /control/accounts /control/workers /accounts /config /download
# Preserve the original account profile without copying or moving credentials.
if [ "$(readlink /tmp/gphotos-cdp 2>/dev/null || true)" != /config ]; then
  echo 'Expected /tmp/gphotos-cdp to point to /config; refusing to replace an existing profile' >&2
  exit 1
fi
exec /usr/bin/supervisord -n -c /container/supervisord.conf
