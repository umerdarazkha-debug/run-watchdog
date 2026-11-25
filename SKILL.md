---
name: run-watchdog
description: Catch scheduled AI or cron jobs that report success while doing nothing. A wrapper (watch.sh) runs any command with a time limit and a safe PATH, then checks that each expected output file was updated and is not empty. It logs one JSON line per run and sends a macOS notification on failure. A digest script lists what ran, failed or stayed silent, and a plan script shows how to wrap existing crontab or launchd jobs (proposal only). Use when the user says "my cron job runs but nothing happens", "scheduled task silently failed", "claude -p in cron did nothing", "how do I know my automation ran", "wrap my launchd job", "daily digest of my jobs", "job exited 0 but no output".
---

# Run watchdog

A job that exits 0 can still have done nothing: wrong PATH, expired login, empty output. The wrapper checks the output, not just the exit code.

## Steps

1. Ask for each job: a name, the command, and the file(s) it must write. If the user has existing cron lines or a launchd plist, get that file and run the plan script (step 2). Otherwise go to step 3.
2. Show how to wrap existing jobs. This prints a proposal and edits nothing:

```bash
python3 scripts/wrap_plan.py ~/crontab.txt          # save `crontab -l` to a file first
python3 scripts/wrap_plan.py ~/Library/LaunchAgents/com.example.job.plist
```

   Replace `REPLACE_WITH_OUTPUT_PATH` in the output with the real output file. Give the new lines to the user. Do not run `crontab`, `launchctl` or edit any plist yourself.
3. The wrapper form:

```bash
scripts/watch.sh --name nightly-report --expect ~/out/report.csv,~/out/summary.md \
  --timeout 1800 -- /usr/local/bin/make-report --full
```

   - `--expect` takes paths, comma separated or repeated. A path can be a file, a glob (`out/*.csv`, one match must be fresh) or a folder (one file inside must be fresh).
   - A file passes if it was modified after the run started and is not empty.
   - `--timeout` is seconds. The whole process group is stopped (TERM, then KILL after 5 s).
   - `--log-dir` default `~/.run-watchdog`. One line per run goes to `runs.jsonl`.
   - On failure a macOS notification is sent through `osascript` (skipped if missing). `--notify-cmd 'CMD'` runs a command instead and sees `WATCHDOG_JOB`, `WATCHDOG_STATUS`, `WATCHDOG_MESSAGE`. `--no-notify` turns it off.
4. Statuses and exit codes: `ok` 0, `failed` (command's own code), `timeout` 124, `command_not_found` 127, `silent_failure` 3 (exit 0 but an expected file did not change; the output says SILENT FAILURE).
5. Daily digest. Write a `jobs.json` listing each job and how often it should run:

```json
{"jobs": [{"name": "nightly-report", "every": "daily"}, {"name": "sync", "every": "30m"}]}
```

```bash
python3 scripts/digest.py --jobs jobs.json [--utc-offset 5] [--date 2026-11-26]
```

   It prints RAN, FAILED and SILENT. A job is SILENT when its last run is older than 1.25 times its interval, or it never ran. Times are UTC unless `--utc-offset HOURS` is set. Exit code 1 if anything failed or is silent, so it can be wrapped too.
6. Tell the user: pick output files that only a real run would change. Check the notification once with a deliberately failing test job.

## Limits

- A job that writes a stale-looking but valid file every time still passes. Check content in the job itself if that matters.
- The log stores only the command name (first word), never its arguments, so tokens in arguments are not saved.
- If the machine is asleep at the scheduled time, no run happens and the digest reports it as SILENT. That is correct.
- Log format: `references/log-format.md`.
