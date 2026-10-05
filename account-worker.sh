#!/bin/sh
set -u
account=$1
BACKUP_STATE=${BACKUP_STATE:-/app/backup_state.py}
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
  python3 "$BACKUP_STATE" begin "$state" "$destination" --mode "$run_mode" || return 1
  index_result=0
  if [ "$organize_only" = 2 ]; then python3 "$BACKUP_STATE" repair "$state" "$destination" || return 1; fi
  set_phase checking
  python3 "$BACKUP_STATE" check "$state" "$destination" || return 1
  if [ "$organize_only" = 3 ]; then return 0; fi
  set_phase indexing
  echo "Henter albums og Google-datoer"
  if TMPDIR="$profile_tmp" gphotos-cdp -dev -headless -index-albums -dldir "$destination"; then
    set_phase organizing
    if ! python3 /usr/local/bin/fotoarkiv-organize.py "$destination"; then
      echo "FEJL: Organisering afbrudt; originalfiler bevares"
      return 1
    fi
  else
    index_result=1
    echo "FEJL: Kunne ikke opdatere albumindeks. Tidligere indeks og filer bevares."
    if [ "$organize_only" = 1 ]; then return 1; fi
  fi
  if [ "$organize_only" = 1 ]; then
    set_phase checking
    python3 "$BACKUP_STATE" check "$state" "$destination"
    return $?
  fi
  set_phase downloading
  TMPDIR="$profile_tmp" gphotos-cdp -v -dev -headless -run /usr/local/bin/fotoarkiv-organize-one -dldir "$destination"
  download_result=$?
  if [ -f "$destination/.fotoarkiv/metadata.json" ]; then
    set_phase organizing
    python3 /usr/local/bin/fotoarkiv-organize.py "$destination" || return 1
  fi
  set_phase checking
  python3 "$BACKUP_STATE" check "$state" "$destination" || return 1
  if [ "$index_result" != 0 ]; then return 1; fi
  return "$download_result"
}
if [ "${2:-}" = --run ]; then
  organize_only=${3:-0}
  run_mode=${4:-backup}
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
if [ ! -f "$NEXT" ]; then python3 "$BACKUP_STATE" next "$state" > "$NEXT"; fi
settings_stamp=$(stat -c %y "$state/settings.json" 2>/dev/null || echo none)
history_pid=
sync_pid=
idle_pid=
cleanup() {
  if [ -n "$idle_pid" ]; then
    kill "$idle_pid" 2>/dev/null || true
    wait "$idle_pid" 2>/dev/null || true
  fi
  if [ -n "$sync_pid" ]; then
    /bin/kill -TERM -- "-$sync_pid" 2>/dev/null || true
    sleep 2
    /bin/kill -KILL -- "-$sync_pid" 2>/dev/null || true
    wait "$sync_pid" 2>/dev/null || true
  fi
  if [ -n "$history_pid" ]; then wait "$history_pid" 2>/dev/null || true; fi
  rm -f "$RUNNING" "$state/phase" "$state/phase.tmp"
  exit 0
}
trap cleanup TERM INT
echo "$(date '+%Y-%m-%d %H:%M:%S') Worker klar: $account" >> "$LOG"
while :; do
  NOW=$(date +%s)
  echo "$NOW" > "$state/heartbeat"
  current_stamp=$(stat -c %y "$state/settings.json" 2>/dev/null || echo none)
  if [ "$current_stamp" != "$settings_stamp" ]; then
    python3 "$BACKUP_STATE" next "$state" > "$NEXT"
    settings_stamp=$current_stamp
  fi
  DUE=$(cat "$NEXT" 2>/dev/null || echo 0)
  case "$DUE" in *[!0-9]*|'') DUE=0;; esac
  if [ -f "$state/stop-request" ] && [ ! -f "$RUNNING" ]; then
    rm -f "$REQUEST" "$state/stop-request" "$state/rescan-request" "$state/organize-request" "$state/verify-request" "$state/repair-request"
    echo 130 > "$state/last-exit"
    python3 "$BACKUP_STATE" next "$state" > "$NEXT"
  fi
  if [ -f "$REQUEST" ] || { [ "$DUE" -gt 0 ] && [ "$NOW" -ge "$DUE" ]; }; then
    organize_only=0
    if [ -f "$state/organize-request" ]; then organize_only=1; rm -f "$state/organize-request"; fi
    if [ -f "$state/verify-request" ]; then organize_only=3; rm -f "$state/verify-request"; fi
    while [ "$organize_only" != 3 ] && [ "$(cat /control/login-active 2>/dev/null)" = "$account" ]; do
      set_phase waiting_login
      echo "$(date '+%Y-%m-%d %H:%M:%S') Venter på at login-browseren lukkes: $account" >> "$LOG"
      date +%s > "$state/heartbeat"
      if [ -f "$state/stop-request" ]; then break; fi
      sleep 2
    done
    if [ -f "$state/stop-request" ]; then
      rm -f "$REQUEST" "$state/stop-request" "$state/rescan-request" "$state/organize-request" "$state/verify-request" "$state/repair-request"
      echo "130" > "$state/last-exit"
      echo "$(date '+%Y-%m-%d %H:%M:%S') Backup afbrudt før start: $account" >> "$LOG"
      python3 "$BACKUP_STATE" next "$state" > "$NEXT"
      rm -f "$state/phase" "$state/phase.tmp"
      continue
    fi
    rm -f "$REQUEST"
    # Chrome leaves these symlinks behind if a container is restarted mid-download.
    # No login browser may be active for this account at this point.
    if [ "$organize_only" != 3 ]; then
      rm -f "$profile_tmp/gphotos-cdp/SingletonLock" "$profile_tmp/gphotos-cdp/SingletonCookie" "$profile_tmp/gphotos-cdp/SingletonSocket"
    fi
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
    mode=backup
    if [ "$organize_only" = 1 ]; then mode=organize; fi
    if [ "$organize_only" = 3 ]; then mode=check; fi
    if [ -f "$state/repair-request" ]; then mode=repair; organize_only=2; rm -f "$state/repair-request"; fi
    set_phase starting
    date '+%Y-%m-%d %H:%M:%S' > "$RUNNING"
    echo "$(date '+%Y-%m-%d %H:%M:%S') Starter synkronisering: $account" >> "$LOG"
    setsid /bin/sh "$0" "$account" --run "$organize_only" "$mode" >> "$LOG" 2>&1 &
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
    date '+%Y-%m-%d %H:%M:%S' > "$state/last-run"
    echo "$(date '+%Y-%m-%d %H:%M:%S') Færdig, exitkode $result" >> "$LOG"
    set_phase finishing
    python3 "$BACKUP_STATE" finish "$state" "$destination" --result "$result" >> "$LOG" 2>&1 &
    history_pid=$!
    while kill -0 "$history_pid" 2>/dev/null; do date +%s > "$state/heartbeat"; sleep 1; done
    wait "$history_pid" || true
    history_pid=
    rm -f "$RUNNING" "$state/phase" "$state/phase.tmp"
    echo "$result" > "$state/last-exit"
    python3 "$BACKUP_STATE" next "$state" > "$NEXT"
  fi
  # Waiting on a child lets TERM interrupt the idle poll immediately in dash.
  sleep 10 &
  idle_pid=$!
  wait "$idle_pid" || true
  idle_pid=
done
