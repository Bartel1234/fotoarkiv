#!/bin/sh
set -u
account=$1
if [ "$account" = legacy ]; then
  state=/control
  destination=/download
  profile_tmp=/tmp
else
  state="/control/accounts/$account"
  destination="/download/$account"
  profile_tmp="/accounts/$account"
fi
set_phase() {
  printf "%s\n" "$1" > "$state/phase.tmp"
  mv -f "$state/phase.tmp" "$state/phase"
}
run_sync() {
  set_phase indexing
  echo "Henter albums og Google-datoer"
  if TMPDIR="$profile_tmp" gphotos-cdp -dev -headless -index-albums -dldir "$destination"; then
    set_phase organizing
    if ! python3 /usr/local/bin/fotoarkiv-organize.py "$destination"; then
      echo "FEJL: Organisering afbrudt; originalfiler bevares"
      return 1
    fi
  else
    echo "FEJL: Kunne ikke opdatere albumindeks. Tidligere indeks og filer bevares."
    if [ "$organize_only" = 1 ]; then return 1; fi
  fi
  if [ "$organize_only" = 1 ]; then return 0; fi
  set_phase downloading
  TMPDIR="$profile_tmp" gphotos-cdp -v -dev -headless -run /usr/local/bin/fotoarkiv-organize-one -dldir "$destination"
  download_result=$?
  if [ -f "$destination/.fotoarkiv/metadata.json" ]; then
    set_phase organizing
    python3 /usr/local/bin/fotoarkiv-organize.py "$destination" || return 1
  fi
  return "$download_result"
}
if [ "${2:-}" = --run ]; then
  organize_only=${3:-0}
  run_sync
  exit $?
fi
mkdir -p "$state" "$destination" "$profile_tmp/gphotos-cdp"
NEXT="$state/next-run"
REQUEST="$state/start-request"
RUNNING="$state/running"
LOG="$state/activity.log"
# A restarted account worker owns no job yet.
rm -f "$RUNNING" "$state/phase" "$state/phase.tmp"
if [ ! -f "$NEXT" ]; then echo "$(($(date +%s) + 86400))" > "$NEXT"; fi
sync_pid=
cleanup() {
  if [ -n "$sync_pid" ]; then /bin/kill -TERM -- "-$sync_pid" 2>/dev/null || true; fi
  rm -f "$RUNNING" "$state/phase" "$state/phase.tmp"
  exit 0
}
trap cleanup TERM INT
echo "$(date '+%Y-%m-%d %H:%M:%S') Worker klar: $account" >> "$LOG"
while :; do
  NOW=$(date +%s)
  echo "$NOW" > "$state/heartbeat"
  DUE=$(cat "$NEXT" 2>/dev/null || echo 0)
  case "$DUE" in *[!0-9]*|'') DUE=0;; esac
  if [ -f "$state/stop-request" ] && [ ! -f "$RUNNING" ]; then
    rm -f "$REQUEST" "$state/stop-request" "$state/rescan-request" "$state/organize-request"
    echo 130 > "$state/last-exit"
    echo "$(($(date +%s) + 86400))" > "$NEXT"
  fi
  if [ -f "$REQUEST" ] || [ "$NOW" -ge "$DUE" ]; then
    organize_only=0
    if [ -f "$state/organize-request" ]; then organize_only=1; rm -f "$state/organize-request"; fi
    while [ "$(cat /control/login-active 2>/dev/null)" = "$account" ]; do
      set_phase waiting_login
      echo "$(date '+%Y-%m-%d %H:%M:%S') Venter på at login-browseren lukkes: $account" >> "$LOG"
      date +%s > "$state/heartbeat"
      if [ -f "$state/stop-request" ]; then break; fi
      sleep 2
    done
    if [ -f "$state/stop-request" ]; then
      rm -f "$REQUEST" "$state/stop-request" "$state/rescan-request" "$state/organize-request"
      echo "130" > "$state/last-exit"
      echo "$(date '+%Y-%m-%d %H:%M:%S') Backup afbrudt før start: $account" >> "$LOG"
      echo "$(($(date +%s) + 86400))" > "$NEXT"
      rm -f "$state/phase" "$state/phase.tmp"
      continue
    fi
    rm -f "$REQUEST"
    # Chrome leaves these symlinks behind if a container is restarted mid-download.
    # No login browser may be active for this account at this point.
    rm -f "$profile_tmp/gphotos-cdp/SingletonLock" "$profile_tmp/gphotos-cdp/SingletonCookie" "$profile_tmp/gphotos-cdp/SingletonSocket"
    # A full rescan preserves the downloaded item directories and archives
    # the old cursor outside the download folder before starting from oldest.
    if [ -f "$state/rescan-request" ]; then
      if [ -f "$destination/.lastdone" ]; then
        if cp "$destination/.lastdone" "$state/lastdone-before-rescan"; then
          rm "$destination/.lastdone"
        else
          echo "$(date '+%Y-%m-%d %H:%M:%S') Kunne ikke gemme positionen; fuld gennemgang afbrudt: $account" >> "$LOG"
          rm -f "$state/rescan-request"
          continue
        fi
      fi
      rm -f "$state/rescan-request"
      echo "$(date '+%Y-%m-%d %H:%M:%S') Starter fuld gennemgang; eksisterende filer bevares: $account" >> "$LOG"
    fi
    set_phase starting
    date '+%Y-%m-%d %H:%M:%S' > "$RUNNING"
    echo "$(date '+%Y-%m-%d %H:%M:%S') Starter synkronisering: $account" >> "$LOG"
    setsid /bin/sh "$0" "$account" --run "$organize_only" >> "$LOG" 2>&1 &
    sync_pid=$!
    stopped=0
    while kill -0 "$sync_pid" 2>/dev/null; do
      date +%s > "$state/heartbeat"
      if [ -f "$state/stop-request" ]; then
        stopped=1
        set_phase stopping
        echo "$(date '+%Y-%m-%d %H:%M:%S') Afbryder backup: $account" >> "$LOG"
        /bin/kill -TERM -- "-$sync_pid" 2>/dev/null || true
        for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
          /bin/kill -0 -- "-$sync_pid" 2>/dev/null || break
          date +%s > "$state/heartbeat"
          sleep 1
        done
        /bin/kill -KILL -- "-$sync_pid" 2>/dev/null || true
        break
      fi
      sleep 2
    done
    wait "$sync_pid"
    result=$?
    sync_pid=
    if [ "$stopped" = 1 ] || [ -f "$state/stop-request" ]; then result=130; fi
    rm -f "$state/stop-request"
    echo "$result" > "$state/last-exit"
    date '+%Y-%m-%d %H:%M:%S' > "$state/last-run"
    echo "$(date '+%Y-%m-%d %H:%M:%S') Færdig, exitkode $result" >> "$LOG"
    rm -f "$RUNNING" "$state/phase" "$state/phase.tmp"
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
