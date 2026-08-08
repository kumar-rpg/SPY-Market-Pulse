"""Read/append/push the day's snapshot file.

Each cloud routine firing is a fresh, isolated checkout with no shared disk,
so the git repo itself is the persistence layer: pull before reading, push
after appending. A single pull-rebase-retry covers the (unlikely, at hourly
cadence) case of two firings racing; a second failure is surfaced rather than
retried forever.
"""

import json
import os
import subprocess

SNAPSHOT_DIR = "snapshots"


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, shell=False)


def _path(date_str):
    return os.path.join(SNAPSHOT_DIR, f"{date_str}.json")


def load_today(date_str):
    _run(["git", "pull", "--rebase", "origin", "main"])
    p = _path(date_str)
    if not os.path.exists(p):
        return {"date": date_str, "entries": []}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _commit_and_push(date_str, message):
    _run(["git", "add", _path(date_str)])
    commit = _run(["git", "commit", "-m", message])
    if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr):
        raise RuntimeError(f"git commit failed: {commit.stderr}")
    push = _run(["git", "push", "origin", "main"])
    if push.returncode == 0:
        return True
    # One retry: pull-rebase then push again.
    _run(["git", "pull", "--rebase", "origin", "main"])
    push2 = _run(["git", "push", "origin", "main"])
    if push2.returncode != 0:
        raise RuntimeError(f"git push failed after retry: {push2.stderr}")
    return True


def append_and_push(date_str, entry):
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    data = load_today(date_str)
    data["entries"].append(entry)
    with open(_path(date_str), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    _commit_and_push(date_str, f"snapshot: {date_str} {entry.get('checkpoint_label', '')}")
    return data
