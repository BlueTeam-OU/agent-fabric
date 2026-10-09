#!/usr/bin/env python3
"""tools/fabric/tools_check.py — the tools a managed project needs, checked
on this account, behind bin/fabric-tools.

    fabric-tools [--project P | --all] [--role R] [--json]
    fabric-tools --install TOOL [--json]

Each project in projects/registry.json may list `tools`: a name, the
command that proves the tool is there (`proof`), the version it expects,
why the project needs it, where it lives (`host` or `account`), and,
for a tool only some roles need, `roles`. A tool marked `optional` is
reported but never makes the check fail.

The fabric took the Doppler CLI from every account once, believing it
was only the fabric's own, when a project still used it (the owner,
2026-10-07). A project's tools are declared here so that nothing the
fabric does can take one away unsaid, and so an account can be told
what it lacks before a session finds out.

The project is the working copy's (`--project` names one, `--all` every
project); the role is the account's bound role (`--role` names one).
Each proof runs with a timeout, its first output line kept as what was
found; nothing it prints is otherwise reported.

`--install TOOL` installs an `account` tool whose registry entry carries
an `install` pin into this account's ~/.local/bin, only on an account with
a working copy of a project that declares it (tools_install.py has the
whole account). Its exit codes: 0 current, installed or skipped; 1 failed;
2 refused.

Exit codes: 0 every required tool is there; 1 a required tool is
missing or its proof failed; 2 a bad argument or registry.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FABRIC = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(FABRIC, "runtime"))
import workingcopy  # noqa: E402

PROOF_TIMEOUT_S = 15
WHERE = ("host", "account")


def registry() -> dict:
    return workingcopy.load_registry()


def bound_role() -> str | None:
    try:
        import identity
        return identity.read_binding(identity.current_agent()).get("role")
    except (Exception, SystemExit):  # noqa: BLE001 - no binding (or another host's) is no role, not a failure
        return None


def prove(proof: str) -> tuple[str, str]:
    """('ok', first line) or ('missing', why) or ('failed', why)."""
    try:
        argv = shlex.split(proof)
    except ValueError as e:
        return "failed", f"proof is not a command line ({e})"
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=PROOF_TIMEOUT_S, stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        return "missing", f"{argv[0]} not found"
    except subprocess.TimeoutExpired:
        return "failed", f"no answer within {PROOF_TIMEOUT_S} s"
    except OSError as e:
        return "failed", f"{argv[0]}: {e.strerror or e}"
    first = next((ln.strip() for ln in (r.stdout + "\n" + r.stderr).splitlines() if ln.strip()), "")
    if r.returncode != 0:
        return "failed", f"exit {r.returncode}" + (f": {first[:120]}" if first else "")
    return "ok", first[:120]


def check(projects: list[str], role: str | None, reg: dict) -> list[dict]:
    rows = []
    for pid in projects:
        for tool in (reg.get("projects", {}).get(pid, {}).get("tools") or []):
            roles = tool.get("roles")
            if roles and role not in roles:
                continue
            status, found = prove(tool["proof"])
            rows.append({"project": pid, "name": tool["name"], "status": status, "found": found,
                         "version": tool.get("version", ""), "where": tool.get("where", ""),
                         "optional": bool(tool.get("optional")), "why": tool.get("why", "")})
    return rows


def main(argv: list[str]) -> int:
    project, every, role, as_json, install_tool = None, False, None, False, None
    args = list(argv)
    while args:
        a = args.pop(0)
        if a == "--project" and args:
            project = args.pop(0)
        elif a == "--all":
            every = True
        elif a == "--role" and args:
            role = args.pop(0)
        elif a == "--json":
            as_json = True
        elif a == "--install" and args:
            install_tool = args.pop(0)
        elif a in ("-h", "--help"):
            print(__doc__.strip())
            return 0
        else:
            print(f"fabric-tools: unexpected argument: {a}", file=sys.stderr)
            return 2
    reg = registry()
    if install_tool is not None:
        if project or every or role:
            print("fabric-tools: --install goes with --json only", file=sys.stderr)
            return 2
        import tools_install
        try:
            # Armed inside the try, and the verdict printed inside it: a
            # SIGTERM in the gaps around install() is still exit 143.
            tools_install.exit_on_sigterm()
            verdict = tools_install.install(install_tool, reg=reg, home=os.path.expanduser("~"))
            if as_json:
                print(json.dumps(verdict, indent=2))
            else:
                print(f"fabric-tools: {install_tool} {verdict['status']}"
                      + "".join(f"  {verdict[k]}" for k in ("version", "path", "reason") if verdict.get(k)))
        except tools_install.Terminated as t:
            print(f"fabric-tools: {install_tool} install stopped by SIGTERM", file=sys.stderr)
            return t.code
        return {"failed": 1, "refused": 2}.get(verdict["status"], 0)
    known = reg.get("projects", {})
    if every:
        projects = sorted(known)
    elif project:
        if project not in known:
            print(f"fabric-tools: {project} is not a project of projects/registry.json", file=sys.stderr)
            return 2
        projects = [project]
    else:
        here = workingcopy.resolve(os.getcwd(), reg).get("project")
        if not here:
            print("fabric-tools: this directory is no managed project's working copy (--project or --all)",
                  file=sys.stderr)
            return 2
        projects = [here]
    rows = check(projects, role if role is not None else bound_role(), reg)
    bad = [r for r in rows if r["status"] != "ok" and not r["optional"]]
    if as_json:
        print(json.dumps({"projects": projects, "tools": rows, "ok": not bad}, indent=2))
    else:
        if not rows:
            print(f"fabric-tools: {', '.join(projects)} declares no tools")
        for r in rows:
            mark = "ok" if r["status"] == "ok" else ("optional, " if r["optional"] else "") + r["status"]
            print(f"  {r['project']:<14} {r['name']:<16} {mark:<18} {r['found'] or ''}"
                  + ("" if r["status"] == "ok" else f"  (needs {r['version']}, {r['where']}: {r['why']})"))
    return 1 if bad else 0


def entry(argv: list[str]) -> int:
    """main(), with a SIGTERM that lands after its own try (the return, a
    second signal during the stop message) still the exit status 143."""
    import tools_install
    try:
        return main(argv)
    except tools_install.Terminated as t:
        return t.code


if __name__ == "__main__":
    sys.exit(entry(sys.argv[1:]))
