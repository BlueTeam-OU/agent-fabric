#!/usr/bin/env python3
"""bin/fabric-status says what this session was launched as, and says
DRIFT when the binding, the session default or the prompt file moved
under it. Runs the real script against a throwaway state dir; the stamps
a launch exports are forged in the environment. Ported from
tests/test_fabric-status.sh (ADR-040 Wave 6), case for case. Plain
script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import hashlib
import json
import os
import pwd
import re
import subprocess
import sys
import tempfile
from git_env import git_env, scrub_process_env  # noqa: E402 — tests/, the script's own directory

# Every git this suite starts, fixture or under test, reads none of the
# caller's ~/.gitconfig: set here, it reaches the calls that pass no env.
os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CMD = os.path.abspath(os.environ.get("FABRIC_STATUS") or os.path.join(ROOT, "bin", "fabric-status"))
if not os.path.isfile(CMD):
    sys.exit(f"test: script under test not found at {CMD}")
LOGIN = pwd.getpwuid(os.geteuid()).pw_name


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    def has(pattern: str, text: str) -> bool:
        return re.search(pattern, text, re.M) is not None

    def put(path: str, text: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    host = subprocess.run(["hostname", "-s"], stdout=subprocess.PIPE, text=True, check=True, timeout=10).stdout.strip()

    with tempfile.TemporaryDirectory() as sandbox:
        state = f"{sandbox}/state"
        agent = f"{state}/agents/{LOGIN}"
        put(f"{agent}/binding.json",
            json.dumps({"agent": LOGIN, "host": host, "role": "db-admin", "updated_at": "x"}) + "\n")
        put(f"{agent}/launch-prompt.md", "prompt text\n")
        digest = "sha256:" + hashlib.sha256(b"prompt text\n").hexdigest()

        # Nothing a real session exported may leak into the forged one, and
        # the login is placed on this host in a fixture registry (the real one
        # need not know a CI runner's login) unless a case names another.
        # The scrub is CI's: AGENT_FABRIC_*, CLAUDE_* and ANTHROPIC_* —
        # CLAUDE_EFFORT is the RUNNING session's own read-back (set in every
        # real agent's environment, in none on CI, and it moves mid-session),
        # CLAUDE_CODE_OAUTH_TOKEN and CLAUDE_CONFIG_DIR change the sign-in
        # line. HOME too: fabric-status reads the login's synced record from
        # it, and every holder saw a sign-in DRIFT CI never did.
        placed = f"{sandbox}/placed.json"
        put(placed, json.dumps({"version": 1, "hosts": {host: {"platform": "fedora-qubes", "ssh": None,
                                                               "operator": LOGIN, "fabric": "x"}},
                                "placement": {LOGIN: host}}) + "\n")
        os.makedirs(f"{sandbox}/home")
        base = {k: v for k, v in os.environ.items()
                if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_")) and k not in ("GIT_DIR", "CLAUDECODE")}
        base.update(HOME=f"{sandbox}/home", AGENT_FABRIC_STATE_DIR=state, AGENT_FABRIC_HOSTS_REGISTRY=placed)

        def status(*mode: str, cwd: str | None = None, **env: str) -> str:
            r = subprocess.run(["bash", CMD, *mode], env={**base, **env}, cwd=cwd, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, errors="replace", timeout=120)
            return r.stdout

        def json_of(text: str) -> dict:
            try:
                d = json.loads(text)
                return d if isinstance(d, dict) else {}
            except ValueError:
                return {}

        print("fabric-status: unlaunched — nothing to drift from")
        out = status()
        check("the bound role", has(r"^role         db-admin", out), out)
        check("no launch stamp: no drift line, no 'launched as'", "DRIFT" not in out and "launched as" not in out, out)

        print("fabric-status: launched as the bound role, prompt intact")
        out = status(AGENT_FABRIC_LAUNCH_ROLE="db-admin", AGENT_FABRIC_LAUNCH_PROMPT_DIGEST=digest,
                     AGENT_FABRIC_LAUNCH_PROVIDER="anthropic")
        check("says what it was launched as, with the prompt digest",
              has(rf"^launched as  db-admin    prompt {digest}", out), out)
        check("…and no drift", "DRIFT" not in out, out)

        print("fabric-status: the binding moved under the session")
        out = status(AGENT_FABRIC_LAUNCH_ROLE="backend-dev", AGENT_FABRIC_LAUNCH_PROMPT_DIGEST=digest)
        check("role drift is one DRIFT line naming both and the fix",
              has(r"^DRIFT        launched as backend-dev, binding now db-admin", out)
              and "relaunch to hold db-admin" in out, out)
        d = json_of(status("--json", AGENT_FABRIC_LAUNCH_ROLE="backend-dev"))
        check("…and in the JSON report", d.get("launched_role") == "backend-dev"
              and any("binding now db-admin" in x for x in d.get("drift", [])), json.dumps(d)[:400])

        print("fabric-status: the prompt file moved under the session")
        out = status(AGENT_FABRIC_LAUNCH_ROLE="db-admin", AGENT_FABRIC_LAUNCH_PROMPT_DIGEST="sha256:0000")
        check("a digest mismatch is said", has(r"^DRIFT        the prompt file was rewritten since launch", out), out)
        os.remove(f"{agent}/launch-prompt.md")
        out = status(AGENT_FABRIC_LAUNCH_ROLE="db-admin", AGENT_FABRIC_LAUNCH_PROMPT_DIGEST=digest)
        check("a missing file is said, not a crash", has(r"^DRIFT        the launched prompt file is gone", out), out)

        print("fabric-status: the session default moved under the session")
        out = status(AGENT_FABRIC_LAUNCH_ROLE="db-admin", AGENT_FABRIC_LAUNCH_PROVIDER="anthropic",
                     AGENT_FABRIC_LAUNCH_SESSION_MODEL="claude-sonnet-5")
        check("a changed session default is said with the current resolution",
              has(r"^DRIFT        launched on claude-sonnet-5, the anthropic session now resolves to", out)
              and "relaunch to apply" in out, out)
        m = re.search(r"the anthropic session now resolves to ([^ ]*) ", out)
        current = m.group(1) if m else ""
        out = status(AGENT_FABRIC_LAUNCH_ROLE="db-admin", AGENT_FABRIC_LAUNCH_PROVIDER="anthropic",
                     AGENT_FABRIC_LAUNCH_SESSION_MODEL=current)
        check("launched on what now resolves: no drift", bool(current) and "launched on" not in out, out)

        print("fabric-status: effort — the intent is shown, the drift waits for a stamp")
        launched = {"AGENT_FABRIC_LAUNCH_ROLE": "db-admin", "AGENT_FABRIC_LAUNCH_PROVIDER": "anthropic"}
        out = status(**launched, CLAUDE_EFFORT="xhigh")
        check("unpinned: the asked-for level and the running one, side by side",
              has(r"^session effort .* \(asked; not pinned at launch\) \(running xhigh\)", out), out)
        check("…and no DRIFT: nothing pinned it, so nothing drifted from it", not has(r"DRIFT.*effort", out), out)
        out = status(**launched, AGENT_FABRIC_LAUNCH_EFFORT="max", CLAUDE_EFFORT="high")
        check("pinned and clamped: one DRIFT line naming both levels",
              has(r"^DRIFT        launched at effort max, the session is running at high", out), out)
        out = status(**launched, AGENT_FABRIC_LAUNCH_EFFORT="high", CLAUDE_EFFORT="high")
        check("pinned and honoured: confirmed, no drift", not has(r"DRIFT.*effort", out) and "(confirmed)" in out, out)
        # The STAMP is the headline once there is one: it is what this
        # session was started with. The resolved intent only says what a
        # relaunch would do, and printing it first described a different
        # session.
        out = status(**launched, AGENT_FABRIC_LAUNCH_EFFORT="low", CLAUDE_EFFORT="low")
        check("launched at a level below the routed one: the stamp is the headline",
              has(r"^session effort low \(confirmed\)", out), out)
        # A session whose model expresses no effort has no level to report
        # at all, and must not be given the code-high class's by
        # recomputation.
        put(f"{agent}/model-profile.local.json",
            '{"providers":{"anthropic":{"session":"claude-haiku-4-5-20251001"}}}\n')
        out = status(**launched)
        check("a session model with no effort control reports none, not the class's",
              not has(r"^session effort", out), out)
        os.remove(f"{agent}/model-profile.local.json")
        out = status(**launched, AGENT_FABRIC_LAUNCH_EFFORT="max")
        check("no read-back at all: nothing to compare, nothing said", not has(r"DRIFT.*effort", out), out)

        print("fabric-status: the account's placement")
        hosts = f"{sandbox}/hosts.json"
        two = {host: {"platform": "fedora-qubes", "ssh": None, "operator": LOGIN, "fabric": "x"},
               "other-host": {"platform": "debian", "ssh": "op@other", "operator": "op", "fabric": "x"}}
        put(hosts, json.dumps({"version": 1, "hosts": two, "placement": {LOGIN: host}}) + "\n")
        out = status(AGENT_FABRIC_HOSTS_REGISTRY=hosts)
        check("placed on this host: no drift", "registered on" not in out and "not placed" not in out, out)
        put(hosts, json.dumps({"version": 1, "hosts": two, "placement": {LOGIN: "other-host"}}) + "\n")
        out = status(AGENT_FABRIC_HOSTS_REGISTRY=hosts)
        check("placed elsewhere: one DRIFT line naming both hosts",
              has(rf"^DRIFT        registered on other-host, running on {re.escape(host)}", out), out)
        d = json_of(status("--json", AGENT_FABRIC_HOSTS_REGISTRY=hosts))
        check("…and in the JSON report", d.get("placement") == "other-host"
              and any("registered on other-host" in x for x in d.get("drift", [])), json.dumps(d)[:400])
        put(hosts, json.dumps({"version": 1, "hosts": {host: two[host]}, "placement": {}}) + "\n")
        out = status(AGENT_FABRIC_HOSTS_REGISTRY=hosts)
        check("not placed at all: said", has(r"^DRIFT        not placed in runtime/hosts/registry\.json", out), out)

        print("fabric-status: moveto installed from this repository, or behind it")
        prefix = f"{sandbox}/usr-local"
        r = subprocess.run(["sh", os.path.join(ROOT, "runtime", "provisioning", "moveto", "install.sh")],
                           env={**base, "MOVETO_PREFIX": prefix}, stdout=subprocess.DEVNULL, timeout=60)
        check("install.sh installs under $MOVETO_PREFIX", r.returncode == 0)
        manifest = f"{prefix}/share/moveto/installed.sha256"
        good = os.path.isfile(manifest) and os.path.getsize(manifest) > 0 and subprocess.run(
            ["sha256sum", "-c", "--quiet", "share/moveto/installed.sha256"], cwd=prefix, timeout=60).returncode == 0
        check("…and records a manifest that checks out", good)
        out = status(MOVETO_PREFIX=prefix)
        check("a fresh install is in sync", has(r"^moveto       in sync", out), out)
        with open(f"{prefix}/share/moveto/enter", "a", encoding="utf-8") as fh:
            fh.write("\n# local edit\n")
        out = status(MOVETO_PREFIX=prefix)
        check("an installed copy that differs is said, with the file, the cause and the fix",
              has(r"^moveto       drift: behind the repository: share/moveto/enter", out)
              and "edited in place since install: share/moveto/enter" in out and "install.sh" in out, out)
        d = json_of(status("--json", MOVETO_PREFIX=prefix))
        check("…and in the JSON report", d.get("host_tools", {}).get("moveto", {}).get("status") == "drift",
              json.dumps(d)[:400])
        out = status(MOVETO_PREFIX=f"{sandbox}/nowhere")
        check("no moveto under the prefix: no line", not has(r"^moveto", out), out)

        print("fabric-status: memories written and not yet drained")
        wc = f"{sandbox}/gzapp"
        subprocess.run(["git", "init", "-q", wc], check=True, timeout=30, env=git_env())
        subprocess.run(["git", "-C", wc, "remote", "add", "origin", "git@github.com:gzapi-org/gzapp.git"],
                       check=True, timeout=30, env=git_env())
        # The harness's spelling: every non-alphanumeric is a dash.
        mem = f"{sandbox}/home/.claude/projects/{re.sub(r'[^A-Za-z0-9]', '-', wc)}/memory"
        report = f"{wc}/.agent-fabric/memory/last-drain-report.json"
        put(report, json.dumps({"watermarks": {f"{LOGIN}@{host}": 1000}}) + "\n")
        put(f"{mem}/a.md", "---\nname: a\ndescription: d\nmetadata:\n  type: project\n  roles_class: solution\n---\nfact\n")
        put(f"{mem}/b.md", "---\nname: b\ndescription: d\nmetadata:\n  type: user\n---\nmine\n")
        put(f"{mem}/MEMORY.md", "# index\n")
        out = status(cwd=wc)
        check("counts drainable and private memories newer than the watermark; MEMORY.md is not a memory",
              has(r"^memory       1 drainable \(roles_class set\) and 1 private \(none\) written since the last drain",
                  out), out)
        os.remove(report)
        out = status(cwd=wc)
        check("no report: counted since ever, said so", "written since ever (no drain report)" in out, out)
        out = status(cwd=sandbox)
        check("outside a working copy: no memory line", not has(r"^memory ", out), out)

        print("fabric-status: the job list")
        out = status(cwd=sandbox)
        jobs_line = "\n".join(line for line in out.split("\n") if line.startswith("jobs"))
        check("an empty list: none active, zero counts",
              has(r"^jobs         none active; 0 queued, 0 blocked, 0 delivered", out), jobs_line)
        jobs_env = {**base, "AGENT_FABRIC_ROOT": ROOT}
        for args in (["add", "first"], ["add", "second"], ["start", "j2"]):
            subprocess.run([os.path.join(ROOT, "bin", "fabric-jobs"), *args], cwd=wc, env=jobs_env,
                           stdout=subprocess.DEVNULL, check=True, timeout=60)
        out = status(cwd=sandbox)
        jobs_line = "\n".join(line for line in out.split("\n") if line.startswith("jobs"))
        check("the active job and the counts",
              has(r"^jobs         active j2 \(second\); 1 queued, 0 blocked, 0 delivered", out), jobs_line)
        j = json_of(status("--json", cwd=sandbox)).get("jobs", {})
        check("…and in --json", isinstance(j, dict) and (j.get("active") or {}).get("id") == "j2"
              and j.get("queued") == 1, str(j))

        print("fabric-status: which Claude sign-in plain claude uses")
        h = f"{sandbox}/signin-home"
        put(f"{h}/.claude.json", '{"oauthAccount":{"emailAddress":"someone@example.org"}}\n')

        def signin(text: str) -> str:
            return "\n".join(line for line in text.split("\n") if re.search(r"sign-in|DRIFT", line, re.I))
        out = status(HOME=h)
        check("no template token: the login's own sign-in, by its email",
              has(r"^claude sign-in own /login \(someone@example\.org\)$", out), signin(out))
        tpl = "sk-ant-oat01-TEMPLATE-FIXTURE"
        fp = hashlib.sha256(tpl.encode()).hexdigest()[:12]
        out = status(HOME=h, CLAUDE_CODE_OAUTH_TOKEN=tpl)
        check("a template token outranks the own sign-in and is named by fingerprint, not by the old account",
              has(rf"^claude sign-in setup-token {fp} \(CLAUDE_CODE_OAUTH_TOKEN", out)
              and "someone@example.org" not in out, signin(out))
        check("the token itself is never printed", tpl not in out)
        # The shape that occurs: the launcher removed the variable from a
        # broker session, so only the login's synced record says which
        # account it is on.
        put(f"{h}/.config/agent-fabric/secrets.env", f"export CLAUDE_CODE_OAUTH_TOKEN='{tpl}'\n")
        out = status(HOME=h, ANTHROPIC_BASE_URL="https://openrouter.ai/api")
        check("a broker session on a template login names the template from the synced record, not the old account",
              has(rf"^claude sign-in setup-token {fp} .*\(plain claude's; this session goes to broker \(ori\) "
                  r"and uses neither\)$", out) and "someone@example.org" not in out, signin(out))
        check("…the token itself never printed, and no drift: the launcher removing it on the broker is the design",
              tpl not in out and not has(r"^DRIFT.*setup-token", out), out)
        # A direct-path session launched before the sync that moved the
        # login: its environment has no token, the record has one. The line
        # says which it reports, and the disagreement is drift, not the
        # template claimed as in use.
        out = status(HOME=h)
        check("direct path, record but no variable: named as the record, and said as drift",
              has(rf"^claude sign-in setup-token {fp} \(the login's synced record;", out)
              and has(rf"^DRIFT .*this session runs on no token, the login's synced record names setup-token {fp}",
                      out), signin(out))
        out = status(HOME=h, CLAUDE_CODE_OAUTH_TOKEN=tpl)
        check("variable and record agree: this session's, no drift",
              has(rf"^claude sign-in setup-token {fp} \(CLAUDE_CODE_OAUTH_TOKEN in this session;", out)
              and not has(r"^DRIFT.*setup-token", out), signin(out))

    print(f"\ntest_fabric_status_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    scrub_process_env()
    sys.exit(main())
