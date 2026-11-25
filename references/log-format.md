# runs.jsonl format

One JSON object per line, appended by `watch.sh`. Times are UTC.

```
{"name": "nightly-report", "start": "2026-11-26T03:00:00Z", "end": "2026-11-26T03:05:00Z",
 "duration_s": 300.0, "exit_code": 0, "status": "ok", "timeout_s": 1800.0, "command": "make-report",
 "expect": [{"path": "~/out/report.csv", "exists": true, "size": 120, "updated": true, "ok": true, "reason": ""}]}
```

`status` is one of `ok`, `failed`, `timeout`, `command_not_found`, `silent_failure`. `command` is only the first word of the command line. `expect[].reason` is one of: `file does not exist`, `not modified during the run`, `file is empty`, `no file matches`, `no file in the folder was updated`, `folder is empty`, or empty text when ok.

Not verified on this machine: how `osascript` notifications behave when run from cron (they can need a logged-in GUI session). Test once.
