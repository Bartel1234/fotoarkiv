#!/bin/sh
while :; do
  if [ -f /control/login-request ]; then
    request=$(cat /control/login-request 2>/dev/null || true)
    rm -f /control/login-request
    account=${request%% *}
    case "$account" in
      legacy) profile=/config ;;
      *[!a-z0-9@._+-]*|'') profile='' ;;
      *) profile="/accounts/$account/gphotos-cdp" ;;
    esac
    if [ -n "$profile" ]; then
      mkdir -p "$profile"
      google-chrome --user-data-dir="$profile" --no-sandbox --disable-setuid-sandbox --disable-gpu --disable-nacl --disable-dev-shm-usage https://photos.google.com
    fi
  fi
  sleep 2
done
