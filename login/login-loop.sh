#!/bin/sh
rm -f /control/login-active
trap 'rm -f /control/login-active; exit 0' TERM INT EXIT
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
      state=/control
      if [ "$account" != legacy ]; then state="/control/accounts/$account"; fi
      while [ -f "$state/running" ]; do sleep 5; done
      mkdir -p "$profile"
      echo "$account" > /control/login-active
      rm -f "$profile/SingletonLock" "$profile/SingletonCookie" "$profile/SingletonSocket"
      echo "$(date '+%Y-%m-%d %H:%M:%S') Åbner login-browser for $account" >> /control/login-browser.log
      google-chrome --user-data-dir="$profile" --no-sandbox --disable-setuid-sandbox --disable-gpu --disable-nacl --disable-dev-shm-usage --start-maximized --no-first-run https://photos.google.com >> /control/login-browser.log 2>&1
      echo "$(date '+%Y-%m-%d %H:%M:%S') Browser lukket for $account (exitkode $?)" >> /control/login-browser.log
      rm -f /control/login-active
    fi
  fi
  sleep 2
done
