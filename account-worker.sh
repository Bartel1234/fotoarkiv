#!/bin/sh
set -u
account=$1
if [ "$account" = legacy ]; then
  state=/control
  destination=/download
  run_sync() { /app/sync.sh; }
else
  state="/control/accounts/$account"
  destination="/download/$account"
  profile_tmp="/accounts/$account"
  run_sync() { TMPDIR="$profile_tmp" gphotos-cdp -v -dev -headless -dldir "$destination" -run /app/fix_time.sh; }
fi
mkdir -p "$state" "$destination"
if [ "$account" != legacy ]; then mkdir -p "$profile_tmp/gphotos-cdp"; fi
NEXT="$state/next-run"
REQUEST="$state/start-request"
RUNNING="$state/running"
LOG="$state/activity.log"
if [ ! -f "$NEXT" ]; then echo "$(($(date +%s) + 86400))" > "$NEXT"; fi
trap 'exit 0' TERM INT
echo "$(date '+%Y-%m-%d %H:%M:%S') Worker klar: $account" >> "$LOG"
while :; do
  NOW=$(date +%s)
  echo "$NOW" > "$state/heartbeat"
  DUE=$(cat "$NEXT" 2>/dev/null || echo 0)
  case "$DUE" in *[!0-9]*|'') DUE=0;; esac
  if [ -f "$REQUEST" ] || [ "$NOW" -ge "$DUE" ]; then
    rm -f "$REQUEST"
    date '+%Y-%m-%d %H:%M:%S' > "$RUNNING"
    echo "$(date '+%Y-%m-%d %H:%M:%S') Starter synkronisering: $account" >> "$LOG"
    run_sync >> "$LOG" 2>&1
    result=$?
    echo "$result" > "$state/last-exit"
    date '+%Y-%m-%d %H:%M:%S' > "$state/last-run"
    echo "$(date '+%Y-%m-%d %H:%M:%S') Færdig, exitkode $result" >> "$LOG"
    rm -f "$RUNNING"
    HOUR=${SYNC_HOUR:-3}
    case "$HOUR" in *[!0-9]*|'') HOUR=3;; esac
    TODAY=$(date '+%Y-%m-%d')
    TARGET=$(date -d "$TODAY $HOUR:00:00" +%s 2>/dev/null || echo 0)
    NOW=$(date +%s)
    if [ "$TARGET" -le "$NOW" ]; then TARGET=$((TARGET + 86400)); fi
    echo "$TARGET" > "$NEXT"
  fi
  sleep 10
done
