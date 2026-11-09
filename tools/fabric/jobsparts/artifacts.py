"""tools/fabric/jobsparts/artifacts.py — what a job's artifacts name: the one reader of them (ADR-037 rule 14, rows R7, R8, R9, R10).

`done` (switch's step 1 and the verb), `deliver` and `sweep` all ask whether an artifact is open or landed, and used to read the
artifact two ways: settle took "<project> #N" as a number in the job's own repository and a sha from any word, sweep resolved the
project through the registry and read a sha only beside the job's project (findings F7 and F8 of j100). A job sweep closed on
"other-proj #4" could then not be left by switch. There is one reader now; what differs between callers is the one thing the
caller knows and the reader cannot: `bare_repo`, the repository a bare "#N" or "PR #N" means.

- a pull request URL, "<owner>/<repo>#N", and "<project> #N" or "<project> PR #N" (the project's first github.com remote in
  projects/registry.json) always name their repository;
- a bare "#N" or "PR #N" is in `bare_repo` when the caller has one (a person at the job's checkout does; the hourly sweep does
  not, and guessing the job's own would close it on another project's number);
- a number nothing above resolves, or a shape (an "MR 3", a "!3") no one reads, is `unresolved`: never a guess;
- a commit is any 7-40 hex word. A word that is no commit here is not evidence and not a failure (the caller probes it); a
  reply is `reply:<MESSAGE-ID>`.
"""
from __future__ import annotations

import os
import re
from fabric_jobs.base import FABRIC_ROOT, MESSAGE_ID, _load

_REPO = r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9_.-]+"
PR_FULL = re.compile(rf"(?<![\w/.-])({_REPO})#([1-9][0-9]{{0,8}})\b", re.ASCII)
PR_URL = re.compile(rf"github\.com/({_REPO})/pull/([1-9][0-9]{{0,8}})", re.ASCII)
PR_BARE = re.compile(r"(?:\bPR\s*#?|(?<![\w/.-])#)([1-9][0-9]{0,8})\b", re.ASCII | re.IGNORECASE)
REPLY = re.compile(rf"\breply:({MESSAGE_ID.pattern})", re.ASCII)
# Any 7-40 hex word: an abbreviated sha can be all digits (one in 27 at seven characters) or all letters. A word that is no commit here
# is "not evidence" when probed, never a failure, so the loose reading costs a probe.
SHA = re.compile(r"(?<![0-9a-zA-Z])[0-9a-f]{7,40}(?![0-9a-zA-Z])", re.ASCII)
LEFTOVER = re.compile(r"[#＃!]\s*\d+|\b(?:PR|MR|pull[\s_-]*(?:request)?|merge[\s_-]*request)s?(?![a-z])[\W_]{0,3}(?:(?:no\.?|number)\s*)?\d+", re.IGNORECASE)
# "branch:<name>" is the explicit form; the same word without the prefix is read as a branch artifact is.
BRANCH_PREFIX = re.compile(r"\bbranch:\s*(?=[A-Za-z0-9])", re.ASCII | re.IGNORECASE)


def registry_repos() -> tuple[dict[str, str], str | None]:
    """({project: owner/repo}, why the registry could not be read). The repository is the project's first github.com remote: a
    project with remotes in two organisations is the first one's, which the registry lists as the primary."""
    wc = _load("fabric_workingcopy", os.path.join(FABRIC_ROOT, "tools", "fabric", "workingcopy.py"))
    roots = _load("fabric_roots", os.path.join(FABRIC_ROOT, "tools", "fabric", "roots.py"))
    path = roots.projects_registry(engine=FABRIC_ROOT)
    try:
        registry = wc.load_registry(path)
        projects = registry.get("projects") or {}
        out = {}
        for name, entry in projects.items():
            for remote in entry.get("remotes") or []:
                parsed = wc.parse_remote(remote)
                if parsed and parsed["host"] == "github.com" and parsed["path"].count("/") == 1:
                    out[name] = parsed["path"]
                    break
        return out, None
    except (OSError, ValueError, AttributeError) as e:
        return {}, f"{path} could not be read ({type(e).__name__}: {e})"


def project_pattern(names: list[str]) -> re.Pattern | None:
    if not names:
        return None
    alt = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    return re.compile(rf"(?<![\w./-])({alt})(?:\s+PR\s*#?\s*|\s*#\s*)([1-9][0-9]{{0,8}})\b", re.ASCII | re.IGNORECASE)


def read(job: dict, repos: dict[str, str], named: re.Pattern | None, bare_repo: str | None) -> tuple[dict, list[str]]:
    """({"prs": [(repo, n)], "shas": [...], "replies": [...]}, [the references that name no repository]) for one job."""
    prs: list[tuple[str, str]] = []
    unresolved: list[str] = []
    shas: list[str] = []
    replies: list[str] = []
    for art in job.get("artifacts") or []:
        replies += [m.group(1).lower() for m in REPLY.finditer(str(art))]
        text = MESSAGE_ID.sub(" ", str(art))
        here = [(m.group(1), m.group(2)) for m in PR_URL.finditer(text)]
        text = PR_URL.sub(" ", text)
        shas += [m.group(0) for m in SHA.finditer(text)]
        here += [(m.group(1), m.group(2)) for m in PR_FULL.finditer(text)]
        text = PR_FULL.sub(" ", text)
        if named:
            for m in named.finditer(text):
                project = next(p for p in repos if p.lower() == m.group(1).lower())
                here.append((repos[project], m.group(2)))
            text = named.sub(" ", text)
        if bare_repo:
            taken = {n for _, n in here}
            here += [(bare_repo, m.group(1)) for m in PR_BARE.finditer(text) if m.group(1) not in taken]
            text = PR_BARE.sub(" ", text)
        # A number no pattern above consumed names no repository: guessing the job's own would close it on another project's PR
        # whenever an artifact says "gzcoord#3", "#3 in other" or "fixes #3 upstream". It stays until written as <project> #N.
        for m in LEFTOVER.finditer(text):
            unresolved.append(f"{m.group(0).strip()} names no repository (write it as <project> #N or owner/repo#N)")
        prs += here
    return {"prs": list(dict.fromkeys(prs)), "shas": list(dict.fromkeys(shas)), "replies": list(dict.fromkeys(replies))}, unresolved
