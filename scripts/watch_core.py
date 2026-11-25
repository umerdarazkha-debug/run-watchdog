#!/usr/bin/env python3
"""run-watchdog core. Stdlib only, Python 3.8+. Called by watch.sh."""
import argparse
import datetime
import glob
import json
import os
import shutil
import signal
import subprocess
import sys
import time

EXIT_SILENT = 3
EXIT_TIMEOUT = 124
EXIT_NOTFOUND = 127


def iso(t):
    return datetime.datetime.fromtimestamp(t, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def check_path(spec, start):
    """Return dict describing one expected output."""
    p = os.path.expanduser(spec)
    res = {"path": spec, "exists": False, "size": 0, "updated": False, "ok": False, "reason": ""}
    if any(c in p for c in "*?["):
        matches = sorted(glob.glob(p))
        if not matches:
            res["reason"] = "no file matches"
            return res
        subs = [check_path(m, start) for m in matches]
        best = next((s for s in subs if s["ok"]), subs[0])
        res.update({"exists": True, "size": best["size"], "updated": best["updated"], "ok": best["ok"], "reason": best["reason"]})
        return res
    if os.path.isdir(p):
        files = [os.path.join(d, f) for d, _, fs in os.walk(p) for f in fs]
        subs = [check_path(f, start) for f in files]
        res["exists"] = True
        good = next((s for s in subs if s["ok"]), None)
        if good:
            res.update({"size": good["size"], "updated": True, "ok": True})
        else:
            res["reason"] = "no file in the folder was updated" if files else "folder is empty"
        return res
    if not os.path.exists(p):
        res["reason"] = "file does not exist"
        return res
    st = os.stat(p)
    res["exists"] = True
    res["size"] = st.st_size
    res["updated"] = st.st_mtime >= start
    if not res["updated"]:
        res["reason"] = "not modified during the run"
    elif st.st_size == 0:
        res["reason"] = "file is empty"
    else:
        res["ok"] = True
    return res


def run_with_timeout(cmd, timeout):
    """Run cmd in its own process group. Returns (exit_code, timed_out)."""
    proc = subprocess.Popen(cmd, start_new_session=True)
    try:
        return proc.wait(timeout=timeout), False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            proc.wait()
        return EXIT_TIMEOUT, True


def notify(name, status, message, notify_cmd, no_notify):
    if no_notify:
        return
    if notify_cmd:
        env = dict(os.environ, WATCHDOG_JOB=name, WATCHDOG_STATUS=status, WATCHDOG_MESSAGE=message)
        subprocess.call(notify_cmd, shell=True, env=env)
        return
    osa = shutil.which("osascript")
    if osa:
        text = ("%s: %s" % (name, message)).replace("\\", "\\\\").replace('"', '\\"')
        subprocess.call([osa, "-e", 'display notification "%s" with title "run-watchdog"' % text],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main(argv):
    if "--" not in argv:
        print("usage: watch.sh --name JOB [--expect PATH,PATH] [--timeout SECS] -- command ...", file=sys.stderr)
        return 2
    i = argv.index("--")
    opts, cmd = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(prog="watch.sh")
    ap.add_argument("--name", required=True)
    ap.add_argument("--expect", action="append", default=[], help="comma separated paths; repeatable")
    ap.add_argument("--timeout", type=float, default=1800)
    ap.add_argument("--log-dir", default="~/.run-watchdog")
    ap.add_argument("--notify-cmd", help="shell command run on failure; sees WATCHDOG_JOB, WATCHDOG_STATUS, WATCHDOG_MESSAGE")
    ap.add_argument("--no-notify", action="store_true")
    a = ap.parse_args(opts)
    if not cmd:
        print("run-watchdog: no command after --", file=sys.stderr)
        return 2
    expects = [e.strip() for chunk in a.expect for e in chunk.split(",") if e.strip()]

    start = time.time()
    found = shutil.which(cmd[0]) if os.sep not in cmd[0] else (cmd[0] if os.access(cmd[0], os.X_OK) and os.path.isfile(cmd[0]) else None)
    if not found:
        code, timed_out, status = EXIT_NOTFOUND, False, "command_not_found"
        print("run-watchdog: command not found: %s (PATH=%s)" % (cmd[0], os.environ.get("PATH")), file=sys.stderr)
    else:
        code, timed_out = run_with_timeout(cmd, a.timeout)
        status = "timeout" if timed_out else ("failed" if code != 0 else "ok")
    end = time.time()

    results = [check_path(e, start) for e in expects]
    bad = [r for r in results if not r["ok"]]
    if status == "ok" and bad:
        status = "silent_failure"
    msg = {
        "ok": "exit 0, expected outputs updated" if expects else "exit 0",
        "failed": "exited with code %d" % code,
        "timeout": "timed out after %g s and was killed" % a.timeout,
        "command_not_found": "command not found: %s" % cmd[0],
        "silent_failure": "SILENT FAILURE: exit 0 but expected output not updated: " + "; ".join("%s (%s)" % (r["path"], r["reason"]) for r in bad),
    }[status]
    record = {"name": a.name, "start": iso(start), "end": iso(end), "duration_s": round(end - start, 2),
              "exit_code": code, "status": status, "timeout_s": a.timeout,
              "command": os.path.basename(cmd[0]), "expect": results}
    logdir = os.path.expanduser(a.log_dir)
    os.makedirs(logdir, exist_ok=True)
    with open(os.path.join(logdir, "runs.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    print("run-watchdog: %s status=%s %s" % (a.name, status, msg), file=sys.stderr if status != "ok" else sys.stdout)
    if status != "ok":
        notify(a.name, status, msg, a.notify_cmd, a.no_notify)
    if status == "silent_failure":
        return EXIT_SILENT
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
