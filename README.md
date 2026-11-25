# run-watchdog

Scheduled jobs, including `claude -p` runs from cron or launchd, often report success and do nothing. The login expired, the PATH was empty, the tool wrote an empty file. The exit code is 0, so nobody notices for weeks.

## What it does

- `scripts/watch.sh` wraps a command: safe PATH, command-exists check, time limit (works on macOS, which has no `timeout`), start/end/exit code, and a check that every expected output file was updated and is not empty.
- One JSON line per run goes to `~/.run-watchdog/runs.jsonl`.
- On failure: macOS notification through `osascript`, or your own `--notify-cmd`.
- `scripts/digest.py` prints a daily list: ran, failed, silent (no run in the expected window).
- `scripts/wrap_plan.py` reads a crontab text file or a launchd plist and prints how to wrap each job. It never edits anything.

## Install

```bash
git clone https://github.com/umerdarazkha-debug/run-watchdog ~/.claude/skills/run-watchdog
```

Needs `python3` (the macOS one is fine) and bash. Standard library only.

## Use

```bash
scripts/watch.sh --name nightly-report --expect ~/out/report.csv --timeout 1800 -- /usr/local/bin/make-report
python3 scripts/digest.py --jobs jobs.json
python3 scripts/wrap_plan.py crontab.txt
```

Exit codes: 0 ok, the command's own code on failure, 124 timeout, 127 command not found, 3 silent failure.

## Test

`bash tests/run.sh` runs the wrapper on fake commands: success that writes the file, exit 0 without touching it (must be flagged SILENT FAILURE), exit 0 with an empty file, timeout (child process killed), exit 1, command not found, a stripped environment. It then checks the log fields, the digest text and the wrap plans. Offline. Notifications are replaced by `--notify-cmd` in tests.

## Limits

- A stale but valid file that is rewritten every run still passes.
- Notifications from cron may need a logged-in session. Test once.
- The log keeps the command name only, not its arguments.

## License

MIT
