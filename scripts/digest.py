#!/usr/bin/env python3
"""run-watchdog digest: which jobs ran, which failed, which stayed silent.

jobs.json: {"jobs": [{"name": "nightly", "every": "daily"}, ...]} (a bare list also works).
every: hourly, daily, weekly, monthly, or Nm / Nh / Nd (minutes, hours, days).
A job is SILENT when its last run is older than 1.25 x its interval (or it never ran).
Times are UTC unless --utc-offset is given (hours, e.g. 5).
"""
import argparse
import datetime
import json
import os
import re
import sys

UTC = datetime.timezone.utc


def parse_every(s):
    s = str(s).strip().lower()
    fixed = {"hourly": 3600, "daily": 86400, "weekly": 7 * 86400, "monthly": 30 * 86400}
    if s in fixed:
        return fixed[s]
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([mhd])$", s)
    if not m:
        raise ValueError("bad frequency %r (use hourly, daily, weekly, monthly, 30m, 6h, 2d)" % s)
    return float(m.group(1)) * {"m": 60, "h": 3600, "d": 86400}[m.group(2)]


def parse_ts(s):
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def human(sec):
    if sec >= 86400:
        return "%.1f days" % (sec / 86400.0)
    if sec >= 3600:
        return "%.1f hours" % (sec / 3600.0)
    return "%d minutes" % (sec // 60)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Daily digest of watched job runs.")
    ap.add_argument("--jobs", required=True, help="jobs.json")
    ap.add_argument("--log-dir", default="~/.run-watchdog", help="folder holding runs.jsonl")
    ap.add_argument("--date", help="day to report, YYYY-MM-DD (default: day of --now)")
    ap.add_argument("--now", help="override the current time, e.g. 2026-11-26T12:00:00Z (for tests)")
    ap.add_argument("--utc-offset", type=float, default=0.0, help="hours to add to UTC when bucketing days and printing times")
    a = ap.parse_args(argv)

    with open(os.path.expanduser(a.jobs), encoding="utf-8") as f:
        spec = json.load(f)
    jobs = spec["jobs"] if isinstance(spec, dict) else spec
    now = parse_ts(a.now) if a.now else datetime.datetime.now(UTC).replace(microsecond=0)
    off = datetime.timedelta(hours=a.utc_offset)
    day = a.date or (now + off).strftime("%Y-%m-%d")

    runs = []
    path = os.path.join(os.path.expanduser(a.log_dir), "runs.jsonl")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                    r["_t"] = parse_ts(r["start"])
                    runs.append(r)
                except (ValueError, KeyError):
                    continue
    by_job = {}
    for r in runs:
        by_job.setdefault(r["name"], []).append(r)

    ok_lines, fail_lines, silent_lines = [], [], []
    for j in jobs:
        name = j["name"]
        interval = parse_every(j["every"])
        mine = sorted(by_job.get(name, []), key=lambda r: r["_t"])
        today = [r for r in mine if (r["_t"] + off).strftime("%Y-%m-%d") == day]
        good = [r for r in today if r["status"] == "ok"]
        bad = [r for r in today if r["status"] != "ok"]
        if good:
            ok_lines.append("%s (%d run%s)" % (name, len(good), "" if len(good) == 1 else "s"))
        for r in bad:
            at = (r["_t"] + off).strftime("%H:%M")
            what = r["status"].upper().replace("_", " ")
            ex = [e for e in r.get("expect", []) if not e.get("ok")]
            extra = ""
            if ex:
                extra = ", missing: " + ", ".join("%s (%s)" % (e["path"], e["reason"]) for e in ex)
            fail_lines.append("%s at %s: %s, exit code %s%s" % (name, at, what, r["exit_code"], extra))
        last = mine[-1]["_t"] if mine else None
        window = interval * 1.25
        if last is None:
            silent_lines.append("%s: never ran (expected %s)" % (name, j["every"]))
        elif (now - last).total_seconds() > window:
            silent_lines.append("%s: no run for %s (expected %s)" % (name, human((now - last).total_seconds()), j["every"]))
    listed = {j["name"] for j in jobs}
    unlisted = sorted(set(by_job) - listed)

    print("Run-watchdog digest for %s (as of %s)" % (day, now.strftime("%Y-%m-%dT%H:%M:%SZ")))
    print("")
    print("RAN: %d" % len(ok_lines))
    for l in ok_lines:
        print("  " + l)
    print("FAILED: %d" % len(fail_lines))
    for l in fail_lines:
        print("  " + l)
    print("SILENT: %d" % len(silent_lines))
    for l in silent_lines:
        print("  " + l)
    if unlisted:
        print("")
        print("In the log but not in jobs.json: " + ", ".join(unlisted))
    return 1 if (fail_lines or silent_lines) else 0


if __name__ == "__main__":
    sys.exit(main())
