#!/bin/sh
set -u
mkdir -p /control /download
NEXT=/control/next-run
REQUEST=/control/start-request
RUNNING=/control/running
LOG=/control/activity.log
if [ ! -f "$NEXT" ]; then
  echo "$(($(date +%s) + 86400))" > "$NEXT"
fi
trap 'exit 0' TERM INT
echo "$(date '+%Y-%m-%d %H:%M:%S') Worker klar" >> "$LOG"
while :; do
  NOW=$(date +%s)
  echo "$NOW" > /control/heartbeat
  DUE=$(cat "$NEXT" 2>/dev/null || echo 0)
  if [ -f "$REQUEST" ] || [ "$NOW" -ge "$DUE" ]; then
    rm -f "$REQUEST"
    date '+%Y-%m-%d %H:%M:%S' > "$RUNNING"
    echo "$(date '+%Y-%m-%d %H:%M:%S') Starter synkronisering" >> "$LOG"
    /app/sync.sh >> "$LOG" 2>&1
    RESULT=$?
    echo "$RESULT" > /control/last-exit
    date '+%Y-%m-%d %H:%M:%S' > /control/last-run
    echo "$(date '+%Y-%m-%d %H:%M:%S') Færdig, exitkode $RESULT" >> "$LOG"
    rm -f "$RUNNING"
    # Planlæg altid næste forsøg til næste dag klokken SYNC_HOUR.
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
