#!/bin/sh
set -u
mkdir -p /control/workers /control/accounts /accounts /download
rm -f /control/workers/*.pid
trap 'jobs -p | xargs -r kill; wait; exit 0' TERM INT

start_worker() {
  account=$1
  pidfile="/control/workers/$account.pid"
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
