#!/usr/bin/env bash
# run-watchdog wrapper.
#   watch.sh --name JOB --expect PATH[,PATH] [--timeout 1800] [--log-dir DIR]
#            [--notify-cmd CMD | --no-notify] -- <command...>
# Runs the command with a time limit, then checks that every expected output file
# was updated (modified after the run started, and not empty). Logs one JSON line per run.
# Exit codes: command's own code when it fails, 124 timeout, 127 command not found,
# 3 silent failure (command exited 0 but an expected file did not change), 0 ok.
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Cron and launchd start with a tiny PATH. Set a known one.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
py=/usr/bin/python3
[ -x "$py" ] || py="$(command -v python3)"
[ -n "$py" ] || { echo "run-watchdog: python3 not found" >&2; exit 127; }
exec "$py" "$here/watch_core.py" "$@"
