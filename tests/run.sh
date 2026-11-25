#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/.."
fail=0
expect() { if grep -qF -- "$3" <<<"$2"; then echo "ok   $1"; else echo "FAIL $1: missing '$3'"; fail=1; fi; }
refute() { if grep -qF -- "$3" <<<"$2"; then echo "FAIL $1: should not contain '$3'"; fail=1; else echo "ok   $1"; fi; }
check() { # label, expected, actual
  if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: expected '$2' got '$3'"; fail=1; fi; }
W=scripts/watch.sh
F=tests/fixtures
T=$(mktemp -d)
LOG="$T/log"; NOTE="$T/notify.txt"
j() { jq -r "$2" <<<"$1"; }          # field from a json line
last() { tail -1 "$LOG/runs.jsonl"; }

# (a) succeeds and writes the file
OUT="$T/a.txt"
bash $W --name job-a --expect "$OUT" --log-dir "$LOG" --notify-cmd "echo \$WATCHDOG_JOB:\$WATCHDOG_STATUS >> $NOTE" -- sh -c "echo data > $OUT"; rc=$?
r=$(last)
check a-exit 0 $rc
check a-status ok "$(j "$r" .status)"
check a-name job-a "$(j "$r" .name)"
check a-expect-ok true "$(j "$r" '.expect[0].ok')"
check a-size 5 "$(j "$r" '.expect[0].size')"
check a-exitcode 0 "$(j "$r" .exit_code)"
check a-command sh "$(j "$r" .command)"
[ ! -e "$NOTE" ] && echo "ok   a-no-notification" || { echo "FAIL a notified"; fail=1; }
[ "$(j "$r" '.start | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]{8}Z$")')" = true ] && echo "ok   a-start-format" || { echo "FAIL start format"; fail=1; }

# (b) exit 0 but file NOT touched (old mtime): silent failure
OUT="$T/b.txt"; echo old > "$OUT"; touch -t 202001010000 "$OUT"
msg=$(bash $W --name job-b --expect "$OUT" --log-dir "$LOG" --notify-cmd "echo \$WATCHDOG_JOB:\$WATCHDOG_STATUS >> $NOTE" -- true 2>&1); rc=$?
r=$(last)
check b-exit 3 $rc
check b-status silent_failure "$(j "$r" .status)"
check b-exitcode 0 "$(j "$r" .exit_code)"
check b-reason "not modified during the run" "$(j "$r" '.expect[0].reason')"
expect b-message "$msg" "SILENT FAILURE"
expect b-notified "$(cat "$NOTE")" "job-b:silent_failure"

# (b2) file touched but empty: also silent failure
OUT="$T/b2.txt"
bash $W --name job-b2 --expect "$OUT" --log-dir "$LOG" --no-notify -- sh -c ": > $OUT" >/dev/null 2>&1; rc=$?
r=$(last)
check b2-exit 3 $rc
check b2-reason "file is empty" "$(j "$r" '.expect[0].reason')"

# (b3) missing file, and one good + one bad file together
bash $W --name job-b3 --expect "$T/good.txt,$T/never.txt" --log-dir "$LOG" --no-notify -- sh -c "echo x > $T/good.txt" >/dev/null 2>&1; rc=$?
r=$(last)
check b3-exit 3 $rc
check b3-good true "$(j "$r" '.expect[0].ok')"
check b3-missing "file does not exist" "$(j "$r" '.expect[1].reason')"

# (c) timeout: process group is killed
start=$(date +%s)
bash $W --name job-c --timeout 1 --log-dir "$LOG" --notify-cmd "echo \$WATCHDOG_JOB:\$WATCHDOG_STATUS >> $NOTE" -- sh -c "sleep 31.7; echo late > $T/c.txt" >/dev/null 2>&1; rc=$?
took=$(( $(date +%s) - start ))
r=$(last)
check c-exit 124 $rc
check c-status timeout "$(j "$r" .status)"
[ $took -lt 15 ] && echo "ok   c-returned-fast" || { echo "FAIL c took ${took}s"; fail=1; }
pgrep -f "sleep 31.7" >/dev/null && { echo "FAIL c child still running"; pkill -f "sleep 31.7"; fail=1; } || echo "ok   c-child-killed"
[ ! -e "$T/c.txt" ] && echo "ok   c-no-late-write" || { echo "FAIL c late write"; fail=1; }
expect c-notified "$(cat "$NOTE")" "job-c:timeout"

# (d) exit 1
bash $W --name job-d --log-dir "$LOG" --notify-cmd "echo \$WATCHDOG_JOB:\$WATCHDOG_STATUS >> $NOTE" -- sh -c "exit 1" >/dev/null 2>&1; rc=$?
r=$(last)
check d-exit 1 $rc
check d-status failed "$(j "$r" .status)"
check d-exitcode 1 "$(j "$r" .exit_code)"
expect d-notified "$(cat "$NOTE")" "job-d:failed"

# (e) command not found
bash $W --name job-e --log-dir "$LOG" --no-notify -- definitely-not-a-command-xyz >/dev/null 2>&1; rc=$?
r=$(last)
check e-exit 127 $rc
check e-status command_not_found "$(j "$r" .status)"

# (f) tiny PATH from cron still finds standard tools
env -i HOME="$HOME" /bin/bash $W --name job-f --log-dir "$LOG" --no-notify -- ls / >/dev/null 2>&1; rc=$?
check f-minimal-env 0 $rc

# log: one JSON line per run, 8 runs so far
check log-lines 8 "$(wc -l < "$LOG/runs.jsonl" | tr -d ' ')"
jq -e . "$LOG/runs.jsonl" >/dev/null && echo "ok   log-valid-json" || { echo "FAIL log json"; fail=1; }

# no command after --
bash $W --name x --log-dir "$LOG" >/dev/null 2>&1; [ $? -eq 2 ] && echo "ok   usage-error" || { echo "FAIL usage"; fail=1; }

# digest
d=$(python3 scripts/digest.py --jobs $F/jobs.json --log-dir $F/logs --now 2026-11-26T12:00:00Z); rc=$?
check digest-exit 1 $rc
expect digest-header "$d" "Run-watchdog digest for 2026-11-26"
expect digest-ran "$d" "RAN: 3"
expect digest-ran-1 "$d" "  nightly-report (1 run)"
expect digest-failed "$d" "FAILED: 2"
expect digest-silentfail "$d" "backup at 02:00: SILENT FAILURE, exit code 3, missing: ~/backup/latest.tar (not modified during the run)"
expect digest-failed-1 "$d" "frequent-check at 11:30: FAILED, exit code 1"
expect digest-silent "$d" "SILENT: 3"
expect digest-weekly "$d" "weekly-audit: no run for 16.1 days (expected weekly)"
expect digest-hourly "$d" "hourly-sync: no run for 4.0 hours (expected hourly)"
expect digest-never "$d" "never-started: never ran (expected daily)"
expect digest-unlisted "$d" "not in jobs.json: old-thing"
refute digest-nightly-not-silent "$d" "nightly-report: no run"
d=$(python3 scripts/digest.py --jobs $F/jobs.json --log-dir $F/logs --now 2026-11-26T12:00:00Z --utc-offset 5)
expect digest-offset "$d" "backup at 07:00"

# wrap plan: proposal only
c=$(python3 scripts/wrap_plan.py $F/crontab.txt --watch /w/watch.sh)
expect cron-count "$c" "Jobs found: 3"
expect cron-simple "$c" "@daily /w/watch.sh --name python3-3 --expect REPLACE_WITH_OUTPUT_PATH --timeout 1800 -- /usr/bin/python3 ~/demo/backup.py"
expect cron-redirect "$c" "-- /bin/sh -c '/usr/local/bin/make-report --out ~/out/report.csv >> ~/logs/report.log 2>&1'"
expect cron-name-skips-cd "$c" "--name sync-sh"
refute cron-comment-skipped "$c" "MAILTO"
p=$(python3 scripts/wrap_plan.py $F/demo.plist --watch /w/watch.sh)
expect plist-label "$p" "<string>com.example.demo-report</string>"
expect plist-orig "$p" "<string>/usr/local/bin/claude</string>"
expect plist-notice "$p" "This script changed nothing"
before=$(shasum $F/crontab.txt $F/demo.plist | shasum)
python3 scripts/wrap_plan.py $F/crontab.txt >/dev/null; python3 scripts/wrap_plan.py $F/demo.plist >/dev/null
check wrap-inputs-untouched "$before" "$(shasum $F/crontab.txt $F/demo.plist | shasum)"

rm -rf "$T"
[ $fail -eq 0 ] && echo "ALL PASS" || { echo "FAILED"; exit 1; }
