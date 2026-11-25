#!/usr/bin/env python3
"""run-watchdog wrap plan. Reads a crontab text file or a launchd plist and PRINTS how to wrap each job.
It never edits anything. Usage: wrap_plan.py FILE [--watch PATH_TO_watch.sh] [--timeout 1800]
"""
import argparse
import os
import plistlib
import re
import shlex
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPECIALS = ("@reboot", "@yearly", "@annually", "@monthly", "@weekly", "@daily", "@midnight", "@hourly")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "job"


def wrapped(cmd, watch, name, timeout):
    """Return the wrapped command string for a cron command line."""
    head = "%s --name %s --expect REPLACE_WITH_OUTPUT_PATH --timeout %d -- " % (watch, name, timeout)
    if re.search(r"[|;&`<>]|\$\(", cmd):
        return head + "/bin/sh -c " + shlex.quote(cmd)
    return head + cmd


def cron_plan(text, watch, timeout):
    out, n = [], 0
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", line):
            continue
        parts = line.split(None, 1 if line.split()[0] in SPECIALS else 5)
        if line.split()[0] in SPECIALS:
            if len(parts) < 2:
                continue
            sched, cmd = parts[0], parts[1]
        else:
            if len(parts) < 6:
                continue
            sched, cmd = " ".join(parts[:5]), parts[5]
        n += 1
        core = re.sub(r"^\s*cd\s+\S+\s*(?:&&|;)\s*", "", cmd)
        try:
            first = [t for t in shlex.split(core) if "=" not in t.split("/")[0]][0]
        except (ValueError, IndexError):
            first = cmd.split()[0]
        name = slug(os.path.basename(first))
        name = "%s-%d" % (name, n) if name in ("sh", "bash", "python3", "python", "node") else name
        out.append("Job %d (line %d)\n  now:      %s\n  proposed: %s %s\n" % (n, lineno, line, sched, wrapped(cmd, watch, name, timeout)))
    return out, n


def plist_plan(data, watch, timeout):
    label = data.get("Label", "job")
    args = data.get("ProgramArguments") or ([data["Program"]] if data.get("Program") else [])
    new = [watch, "--name", label, "--expect", "REPLACE_WITH_OUTPUT_PATH", "--timeout", str(timeout), "--"] + list(args)
    lines = ["Job 1 (launchd label %s)" % label, "  now ProgramArguments:      " + " ".join(shlex.quote(a) for a in args),
             "  proposed ProgramArguments:", "    <key>ProgramArguments</key>", "    <array>"]
    for a in new:
        lines.append("      <string>%s</string>" % a.replace("&", "&amp;").replace("<", "&lt;"))
    lines.append("    </array>")
    lines.append("  Edit the plist yourself, then reload it with launchctl. This script changed nothing.")
    return ["\n".join(lines) + "\n"], 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Print how to wrap cron or launchd jobs with watch.sh (proposal only).")
    ap.add_argument("file")
    ap.add_argument("--watch", default=os.path.join(HERE, "watch.sh"), help="absolute path to watch.sh to put in the plan")
    ap.add_argument("--timeout", type=int, default=1800)
    a = ap.parse_args(argv)
    with open(os.path.expanduser(a.file), "rb") as f:
        raw = f.read()
    print("Wrap plan for %s (proposal only, nothing was edited)" % a.file)
    print("Replace REPLACE_WITH_OUTPUT_PATH with the file each job is supposed to write (comma separate several).")
    print("")
    if raw.lstrip().startswith(b"<?xml") or b"<plist" in raw[:500]:
        items, n = plist_plan(plistlib.loads(raw), a.watch, a.timeout)
    else:
        items, n = cron_plan(raw.decode("utf-8", "replace"), a.watch, a.timeout)
    for it in items:
        print(it)
    print("Jobs found: %d" % n)
    return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main())
