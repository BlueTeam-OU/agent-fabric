"""tools/fabric/github/pr_in_flight.py — fabric-pr gate --in-flight and
--overlap: every branch on origin as a row, read from git, with the pull
request GitHub knows for it. Split out of pr_gate.py, unchanged; the
contract is that module's header."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gh  # noqa: E402
import git  # noqa: E402
from github.pr_gate_base import INFLIGHT_PATHS_CAP, LIST_CAP, jq_str, note, succeeds  # noqa: E402

def in_flight(repo: str, as_json: bool, overlap: str, prefixes: list[str]) -> int:
    fetch_ok = prs_ok = True
    if not succeeds("fetch", "-q", "--prune", "origin"):
        fetch_ok = False
        seen = "never"
        path = git.run(".", "rev-parse", "--git-path", "FETCH_HEAD", check=False).stdout.strip()
        try:
            seen = dt.datetime.fromtimestamp(os.stat(path).st_mtime, dt.UTC).strftime("%Y-%m-%dT%H:%MZ")
        except OSError:
            pass
        note(f"git fetch origin failed — the rows below are what origin showed this clone at its last fetch ({seen})")
    base = os.environ.get("AGENT_FABRIC_PR_BASE", "")
    if not base:
        base = git.run(".", "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD", check=False).stdout.strip() \
            or "origin/main"
    if not succeeds("rev-parse", "-q", "--verify", f"{base}^{{commit}}"):
        note(f"the base {base} is not in this clone")
        return 2

    try:
        prmap = gh.pr_list(["number", "headRefName"], repo=repo, limit=LIST_CAP)
        if not isinstance(prmap, list):
            raise ValueError
    except (gh.GhError, ValueError):
        prs_ok, prmap = False, []
        note('could not list pull requests — the PR column reads unavailable, never "no PR"')
    if len(prmap) >= LIST_CAP:
        note(f"{LIST_CAP} open pull requests read — the list is capped there.")

    rows = []
    # The full ref name: a short one is ambiguous beside a local branch
    # called origin/<x>, and origin/HEAD shortens to a bare "origin".
    refs = git.run(".", "for-each-ref",
                   "--format=%(refname)\t%(objectname)\t%(committerdate:iso8601-strict)\t%(committerdate:unix)",
                   "refs/remotes/origin/", check=False).stdout
    for line in refs.splitlines():
        ref, sha, when, epoch = (line.split("\t") + ["", "", "", ""])[:4]
        if not ref:
            continue
        name = ref.removeprefix("refs/remotes/origin/")
        if name == "HEAD" or f"origin/{name}" == base:
            continue
        if succeeds("merge-base", "--is-ancestor", sha, base):
            continue   # merged: not in flight
        m = re.match(r"([^/]+/[^/]+)/.+", name, re.S)
        owner = m.group(1) if m else "unattributed"
        if prs_ok:
            pr = next((p.get("number") for p in prmap if isinstance(p, dict) and p.get("headRefName") == name), None)
            pr = "none" if pr is None else pr
        else:
            pr = "unavailable"
        r = git.run(".", "rev-list", "--count", f"{base}..{sha}", check=False)
        ahead = int(r.stdout) if r.returncode == 0 and r.stdout.strip().isdigit() else None
        r = git.run(".", "diff", "--name-only", f"{base}...{sha}", check=False)
        if r.returncode != 0:
            note(f"{name} could not be diffed (deleted meanwhile?) — skipped")
            continue
        rows.append({"branch": name, "owner": owner,
                     "pr": int(pr) if re.fullmatch(r"[0-9]+", str(pr)) else pr,
                     "sha": sha, "last_commit": when, "epoch": int(epoch) if epoch.isdigit() else 0,
                     "ahead": ahead, "paths": [p for p in r.stdout.split("\n") if p]})

    # The target is found among ALL rows, before --path narrows them: a
    # target changing nothing under the prefix is still in flight.
    target = ""
    if overlap:
        if re.fullmatch(r"[0-9]+", overlap):
            if not prs_ok:
                note(f"#{overlap} cannot be resolved to a branch — the PR list is unavailable; name the branch instead")
                return 2
            target = next((r["branch"] for r in rows if r["pr"] == int(overlap)), "")
            if not target:
                note(f"#{overlap} is not an open PR with a branch in flight on origin")
                return 2
        else:
            target = overlap
            if not any(r["branch"] == target for r in rows):
                note(f"{target} is not a branch in flight on origin (merged, deleted, or not pushed)")
                return 2
        theirs = set(next(r["paths"] for r in rows if r["branch"] == target))
        shared_rows = []
        for r in rows:
            if r["branch"] != target:
                r["shared"] = [p for p in r["paths"] if p in theirs]
                if r["shared"]:
                    shared_rows.append(r)
        rows = shared_rows

    if prefixes:
        def under(p: str) -> bool:
            return any(p == x or p.startswith(x.removesuffix("/") + "/") for x in prefixes)
        rows = [r for r in rows if any(under(p) for p in r["paths"])]

    for r in rows:
        r["paths_total"] = len(r["paths"])
        r["paths"] = r["paths"][:INFLIGHT_PATHS_CAP]
        if "shared" in r:
            r["shared_total"] = len(r["shared"])
            r["shared"] = r["shared"][:INFLIGHT_PATHS_CAP]
    rows = sorted(rows, key=lambda r: r["epoch"])[::-1]
    for r in rows:
        del r["epoch"]

    if as_json:
        doc = {"base": base, "fetched_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "fetch_ok": fetch_ok, "prs_ok": prs_ok}
        if target:
            doc["overlap_with"] = target
        doc["rows"] = rows
        print(json.dumps(doc, indent=2, ensure_ascii=False))
    else:
        if target:
            print(f"in flight on {repo} sharing a path with {target} (against {base}): {len(rows)} — no shared path "
                  "is not the same as compatible: two changes can clash in meaning without sharing a file")
        else:
            print(f"in flight on {repo} (not merged into {base}): {len(rows)}")
        for r in rows:
            pr = r["pr"]
            prs = f"#{pr}" if isinstance(pr, int) else ("no PR" if pr == "none" else "PR unavailable")
            line = (f"{r['owner']}  {r['branch']}  {prs}  ahead={jq_str(r['ahead'])}  last={r['last_commit'][0:16]}  "
                    f"paths={r['paths_total']}")
            if "shared" in r:
                line += (f"\n    shares {r['shared_total']}: {', '.join(r['shared'][:8])}"
                         f"{', …' if r['shared_total'] > 8 else ''}")
            print(line)
    return 0 if fetch_ok and prs_ok else 2
