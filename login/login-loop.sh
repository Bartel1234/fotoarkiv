#!/bin/sh
browser_pid=''
cleanup() {
  if [ -n "$browser_pid" ] && kill -0 "$browser_pid" 2>/dev/null; then
    kill -TERM "$browser_pid" 2>/dev/null || true
    wait "$browser_pid" 2>/dev/null || true
  fi
  rm -f /control/login-active /control/login-heartbeat
}
ack_removals() {
  for marker in /control/accounts/*/removal-pending; do
    [ -f "$marker" ] || continue
    removal_state=${marker%/removal-pending}
    removal_account=${removal_state##*/}
    if [ -n "$browser_pid" ] && [ "${account:-}" = "$removal_account" ]; then continue; fi
    echo stopped > "$removal_state/login-stopped"
  done
}
trap 'cleanup; exit 0' TERM INT
trap cleanup EXIT
rm -f /control/login-active /control/login-close-request
while :; do
  ack_removals
  date +%s > /control/login-heartbeat
  if [ -f /control/login-request ]; then
    request=$(cat /control/login-request 2>/dev/null || true)
    rm -f /control/login-request
    account=${request%% *}
    case "$account" in
      legacy) profile=/config ;;
      *[!a-z0-9@._+-]*|'') profile='' ;;
      *) profile="/accounts/$account/gphotos-cdp" ;;
    esac
    if [ "$account" != legacy ] && { ! grep -Fxq -- "$account" /control/accounts.txt 2>/dev/null || [ -f "/control/accounts/$account/removal-pending" ]; }; then profile=''; fi
    if [ -n "$profile" ]; then
      state=/control
      if [ "$account" != legacy ]; then state="/control/accounts/$account"; fi
      cancelled=false
      while [ -f "$state/running" ]; do
        date +%s > /control/login-heartbeat
        if [ -f "$state/removal-pending" ] || [ "$(cat /control/login-close-request 2>/dev/null)" = "$account" ]; then
          rm -f /control/login-close-request
          cancelled=true
          break
        fi
        sleep 2
      done
      if [ "$cancelled" = true ]; then continue; fi
      if [ "$account" != legacy ] && [ -f "$state/removal-pending" ]; then continue; fi
      mkdir -p "$profile"
      echo "$account" > /control/login-active
      rm -f "$profile/SingletonLock" "$profile/SingletonCookie" "$profile/SingletonSocket"
      echo "$(date '+%Y-%m-%d %H:%M:%S') Åbner login-browser for $account" >> /control/login-browser.log
      google-chrome --user-data-dir="$profile" --no-sandbox --disable-setuid-sandbox --disable-gpu --disable-nacl --disable-dev-shm-usage --start-maximized --no-first-run https://photos.google.com >> /control/login-browser.log 2>&1 &
      browser_pid=$!
      closing=false
      while kill -0 "$browser_pid" 2>/dev/null; do
        ack_removals
        date +%s > /control/login-heartbeat
        # Repeated clicks must not queue a second browser for the same account.
        if [ -f /control/login-request ]; then
          queued=$(cat /control/login-request 2>/dev/null || true)
          if [ "${queued%% *}" = "$account" ]; then
            rm -f /control/login-request
          elif [ "$closing" = false ]; then
            kill -TERM "$browser_pid" 2>/dev/null || true
            closing=true
          fi
        fi
        if [ -f "$state/removal-pending" ] || [ "$(cat /control/login-close-request 2>/dev/null)" = "$account" ]; then
          rm -f /control/login-close-request
          if [ "$closing" = false ]; then
            echo "$(date '+%Y-%m-%d %H:%M:%S') Afslutter login via portalen: $account" >> /control/login-browser.log
            kill -TERM "$browser_pid" 2>/dev/null || true
            closing=true
          fi
        fi
        sleep 2
      done
      wait "$browser_pid"
      result=$?
      browser_pid=''
      echo "$(date '+%Y-%m-%d %H:%M:%S') Browser lukket for $account (exitkode $result)" >> /control/login-browser.log
      rm -f /control/login-active
    fi
  else
    # No Chrome process is owned by this loop, so any old marker is stale.
    rm -f /control/login-active /control/login-close-request
  fi
  sleep 2
done
