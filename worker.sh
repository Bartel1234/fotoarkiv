#!/bin/sh
set -u
mkdir -p /control/workers /control/accounts /accounts /download
rm -f /control/workers/*.pid
cleanup() {
  for pidfile in /control/workers/*.pid; do
    [ -f "$pidfile" ] || continue
    pid=$(cat "$pidfile")
    case "$pid" in *[!0-9]*|' '|''|0) continue;; esac
    kill -TERM "$pid" 2>/dev/null || true
  done
  wait
  exit 0
}
trap cleanup TERM INT

start_worker() {
  account=$1
  pidfile="/control/workers/$account.pid"
  if [ "$account" != legacy ]; then
    grep -Fxq -- "$account" /control/accounts.txt 2>/dev/null || return
    state="/control/accounts/$account"
    if [ -f "$state/removal-pending" ]; then
      if [ -f "$pidfile" ]; then
        pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then kill -TERM "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; fi
        rm -f "$pidfile"
      fi
      echo stopped > "$state/worker-stopped"
      return
    fi
    rm -f "$state/worker-stopped"
  fi
  if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then return; fi
  /bin/sh /controller/account-worker.sh "$account" &
  echo "$!" > "$pidfile"
}

# Preserve the previous single-account backup at its original paths.
start_worker legacy
while :; do
  if [ -f /control/accounts.txt ]; then
    while IFS= read -r account; do
      case "$account" in *[!a-z0-9@._+-]*|'') continue;; esac
      start_worker "$account"
    done < /control/accounts.txt
  fi
  sleep 10
done
