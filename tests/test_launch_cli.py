#!/usr/bin/env python3
"""runtime/openrouter/launch, run end to end. The launcher execs a
session, so the cases run it in SANDBOXES: a fake agent-fabric root (the
real routing files minus the committed roles/agents layers, the real
resolver), a fake state directory holding this agent's binding, a fake
`ori` and `claude` on PATH, and HOME pointed at a scratch dir. Every
refusal, the merge order, the shim derivation and the review-grade gate
are exercised without spawning a real claude; model-audit.sh with them.
Ported from runtime/openrouter/test_launch.sh (ADR-040 Wave 6), case for
case. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
import time
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "runtime", "openrouter")
LAUNCHER = os.path.join(HERE, "launch")
LOGIN = pwd.getpwuid(os.geteuid()).pw_name
AUTH_OK = '{"ok":true,"data":{"authenticated":true,"source":{"kind":"environment","location":"OPENROUTER_API_KEY"}}}'

# A fake ori whose auth --json reports environment-sourced auth and which
# records its argv and the child's ENVIRONMENT, not only its argv: a pin
# that lost its export would still print under --print and be absent here.
FAKE_ORI = r'''#!/usr/bin/env bash
if [[ "${1:-}" == auth ]]; then
    echo '{"ok":true,"data":{"authenticated":true,"source":{"kind":"environment","location":"OPENROUTER_API_KEY"}}}'
    exit 0
fi
echo "ORI-EXECCED:$*"
for v in ANTHROPIC_DEFAULT_HAIKU_MODEL ANTHROPIC_DEFAULT_SONNET_MODEL ANTHROPIC_DEFAULT_OPUS_MODEL ANTHROPIC_DEFAULT_FABLE_MODEL AGENT_FABRIC_LAUNCH_SESSION_MODEL AGENT_FABRIC_LAUNCH_EFFORT AGENT_FABRIC_LAUNCH_PROFILE AGENT_FABRIC_LAUNCH_AGENT AGENT_FABRIC_LAUNCH_ROLE AGENT_FABRIC_LAUNCH_PROMPT_DIGEST AGENT_FABRIC_LAUNCH_CLAUDE_VERSION CLAUDE_CODE_DISABLE_TERMINAL_TITLE TMPDIR; do
    echo "ORI-ENV:$v=${!v:-}"
done
# Presence only, never a value: a template token must not reach the broker.
echo "ORI-HAS-OAUTH-TOKEN:${CLAUDE_CODE_OAUTH_TOKEN+yes}"
for v in OPENROUTER_API_KEY GH_TOKEN CLAUDE_BRIDGE_AUTH_TOKEN OPENAI_API_KEY DEMO_PORT_OFFSET; do
    echo "ORI-HAS:$v=${!v+yes}"
done
'''
# A fake claude that records its argv, the tuning and the tier variables,
# and credentials by SHAPE, never by value.
FAKE_CLAUDE = r'''#!/usr/bin/env bash
echo "CLAUDE-EXECCED:$*"
for v in CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT CLAUDE_CODE_MAX_CONTEXT_TOKENS ANTHROPIC_MODEL DISABLE_TELEMETRY; do
    echo "CLAUDE-TUNE:$v=${!v-<unset>}"
done
for v in ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_CUSTOM_HEADERS; do
    if [[ -z "${!v+x}" ]]; then shape=unset; elif [[ -z "${!v}" ]]; then shape=empty
    elif [[ "${!v}" == sk-or-* ]]; then shape=sk-or; elif [[ "${!v}" == sk-ant-* ]]; then shape=sk-ant; else shape=other; fi
    echo "CLAUDE-CRED:$v=$shape"
done
for v in OPENROUTER_API_KEY GH_TOKEN CLAUDE_BRIDGE_AUTH_TOKEN OPENAI_API_KEY CLAUDE_CODE_OAUTH_TOKEN DEMO_PORT_OFFSET; do
    echo "CLAUDE-HAS:$v=${!v+yes}"
done
for v in ANTHROPIC_DEFAULT_HAIKU_MODEL ANTHROPIC_DEFAULT_SONNET_MODEL ANTHROPIC_DEFAULT_OPUS_MODEL ANTHROPIC_DEFAULT_FABLE_MODEL ANTHROPIC_BASE_URL AGENT_FABRIC_LAUNCH_SESSION_MODEL AGENT_FABRIC_LAUNCH_EFFORT AGENT_FABRIC_LAUNCH_PROVIDER AGENT_FABRIC_LAUNCH_PROFILE AGENT_FABRIC_LAUNCH_ROLE AGENT_FABRIC_LAUNCH_PROMPT_DIGEST AGENT_FABRIC_LAUNCH_CLAUDE_VERSION CLAUDE_CODE_DISABLE_TERMINAL_TITLE TMPDIR; do
    echo "CLAUDE-ENV:$v=${!v:-}"
done
'''
SESSION_START = "Session start: arm your GZCoord inbox watch now, exactly as the session-start context's NO INBOX WATCH line gives it"


def utc(seconds_from_now: float = 0) -> str:
    return (datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(seconds=seconds_from_now)).strftime("%Y-%m-%dT%H:%M:%SZ")


def fp(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:12]


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + "\n      ".join(detail.split("\n")[:6]))
        fails += not good

    def has(pattern: str, text: str) -> bool:
        return re.search(pattern, text, re.M) is not None

    def grep(pattern: str, text: str) -> str:
        return "\n".join(ln for ln in text.split("\n") if re.search(pattern, ln))

    host = subprocess.run(["hostname", "-s"], stdout=subprocess.PIPE, text=True, check=True, timeout=10).stdout.strip()
    # The credential family, CLAUDE_CONFIG_DIR and every AGENT_FABRIC_,
    # CLAUDE_ and ANTHROPIC_ variable are CLEARED for every case and set
    # again only by the case: one that asserts about a base URL or a key
    # fixes it itself, or its answer depends on where the suite runs (an
    # inherited broker URL once turned a case red; an inherited
    # CLAUDE_CONFIG_DIR pointed the launcher at the runner's LIVE config).
    base = {k: v for k, v in os.environ.items()
            if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_"))
            and k not in ("GIT_DIR", "OPENROUTER_API_KEY", "GH_TOKEN", "OPENAI_API_KEY", "REPO_ROOT", "USER", "LOGNAME")}
    base.update(USER=LOGIN, LOGNAME=LOGIN)

    with tempfile.TemporaryDirectory() as sandbox:
        home, fabric, state, repo = f"{sandbox}/home", f"{sandbox}/fabric", f"{sandbox}/state", f"{sandbox}/repo"
        agent_dir = f"{state}/agents/{LOGIN}"
        prompt_file = f"{agent_dir}/launch-prompt.md"
        os.makedirs(home)
        # Every plain-claude launch needs a long-lived sign-in in the login's
        # synced record; the fixture holds one of the right shape.
        sec = f"{home}/.config/agent-fabric/secrets.env"

        def put(path: str, text: str, mode: int | None = None) -> None:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            if mode is not None:
                os.chmod(path, mode)

        def read(path: str) -> str:
            try:
                with open(path, encoding="utf-8") as fh:
                    return fh.read()
            except OSError:
                return ""

        def rm(*paths: str) -> None:
            for p in paths:
                if os.path.isdir(p) and not os.path.islink(p):
                    shutil.rmtree(p)
                elif os.path.lexists(p):
                    os.remove(p)

        put(sec, "export CLAUDE_CODE_OAUTH_TOKEN='sk-ant-oat01-SUITE-FIXTURE'\n")
        bin_ = f"{sandbox}/bin"
        os.makedirs(bin_)
        path_export = f"{bin_}:{base.get('PATH', '')}"

        def write_fake_ori() -> None:
            put(f"{bin_}/ori", FAKE_ORI, 0o755)
        write_fake_ori()

        def git(*args: str, cwd: str | None = None) -> str:
            r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
                               cwd=cwd, env=base, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=60)
            return r.stdout.strip()

        def binding(role: str | None = "backend-dev", **extra: str) -> None:
            put(f"{agent_dir}/binding.json", json.dumps({"agent": LOGIN, "host": host, "role": role, **extra,
                                                         "updated_at": "x"}) + "\n")

        def mkfabric() -> None:
            """A fixture agent-fabric root: the real routing files (minus the
            committed roles/agents layers, which may name the login running
            this suite) and resolver, a state dir with this agent's binding
            (role backend-dev), and a launch working copy with a git toplevel."""
            rm(fabric, state, repo)
            for d in ("runtime/openrouter", "runtime/claude-code", "tools/fabric", "projects", "runtime/mcp"):
                os.makedirs(f"{fabric}/{d}")
            # The engine's routing (capabilities, shims, schemas); the
            # operator's half — the profile overlay and the review grade —
            # from the frozen fixture, never the live files (ADR-045 §5 rule 2).
            shutil.copytree(f"{ROOT}/routing", f"{fabric}/routing",
                            ignore=lambda d, names: {"profiles.json", "policies"} & set(names) if d == f"{ROOT}/routing" else set())
            shutil.copy(f"{ROOT}/tests/fixtures/routing-distinct/profiles.json", f"{fabric}/routing/")
            shutil.copytree(f"{ROOT}/tests/fixtures/routing-distinct/policies", f"{fabric}/routing/policies")
            # Classes that differ, so a case can tell which one an export or
            # an agent file came from.
            for f in ("capabilities.json", "effort.json"):
                shutil.copy(f"{ROOT}/tests/fixtures/routing-distinct/{f}", f"{fabric}/routing/")
            for f in ("aliases.json", "install-agent-files.sh"):
                shutil.copy2(f"{ROOT}/runtime/claude-code/{f}", f"{fabric}/runtime/claude-code/")
            shutil.copytree(f"{ROOT}/runtime/claude-code/agents", f"{fabric}/runtime/claude-code/agents")
            # The installer's MCP step reads its helper from the fabric.
            shutil.copytree(f"{ROOT}/runtime/mcp/websearch-locale", f"{fabric}/runtime/mcp/websearch-locale")
            shutil.copy(f"{ROOT}/runtime/identity.py", f"{fabric}/runtime/")
            # install-agent-files.sh is a shim for its module, which imports
            # fabric_writes (ADR-040 §5 rule 5).
            for f in ("routing.py", "workingcopy.py", "jobs.py", "layout.py", "launch_prompt.py",
                      "install_agent_files.py", "fabric_writes.py", "roots.py"):
                shutil.copy2(f"{ROOT}/tools/fabric/{f}", f"{fabric}/tools/fabric/")
            shutil.copytree(f"{ROOT}/tools/fabric/jobsparts", f"{fabric}/tools/fabric/jobsparts", ignore=shutil.ignore_patterns("__pycache__"))   # jobs.py's parts
            # The role's system prompt: the assembler, the shared sections and
            # a fixture charter for the bound role (no brief: the placeholder).
            shutil.copytree(f"{ROOT}/identities/prompt", f"{fabric}/identities/prompt")
            put(f"{fabric}/identities/roles/backend-dev/charter.md",
                '---\nrole: backend-dev\nclass: charter\ndescription: "x"\ntier: 1\ndistilled_at: 2026-09-15\n---\n\n'
                "# backend-dev — charter\n\nFIXTURE-CHARTER-LINE: the backend that owns meaning.\n")
            put(f"{fabric}/projects/registry.json", json.dumps({"projects": {}}))   # its own, never the live one
            binding()
            os.makedirs(repo)
            subprocess.run(["git", "init", "-q", repo], env=base, check=True, timeout=30)

        def profile(layer: str, *args: str) -> None:
            """profile('defaults', json) | profile('roles'|'agents', key, json)"""
            p = f"{fabric}/routing/profiles.json"
            d = json.loads(read(p))
            if layer == "defaults":
                d["defaults"].update(json.loads(args[0]))
            else:
                d.setdefault(layer, {})[args[0]] = json.loads(args[1])
            put(p, json.dumps(d, indent=1))

        def local(text: str) -> None:
            put(f"{agent_dir}/model-profile.local.json", text + "\n")

        def run(*args: str, plant: dict | None = None, keep_tmpdir: str | None = None, cwd: str | None = None,
                launcher: str = LAUNCHER, **env: str) -> tuple[int, str]:
            """TMPDIR is UNSET for the launcher unless a case keeps one: what
            is asserted is the launcher's default, and a TMPDIR the caller set
            wins over it by design."""
            e = {**base, "HOME": home, "PATH": path_export, "AGENT_FABRIC_ROOT": fabric, "AGENT_FABRIC_STATE_DIR": state,
                 **(plant or {}), **env}
            e.pop("TMPDIR", None)
            if keep_tmpdir is not None:
                e["TMPDIR"] = keep_tmpdir
            r = subprocess.run(["bash", launcher, *args], cwd=cwd or repo, env=e, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", timeout=300)
            return r.returncode, r.stdout

        def out_of(*args: str, **kw) -> str:
            return run(*args, **kw)[1]

        print("launch: --print resolves the capability classes through model -> family shim")
        mkfabric()
        rc, out = run("--print")
        check("exits 0", rc == 0, out)
        check("the label is role/agent, agent = login",
              f"resolved profile for backend-dev/{LOGIN} (agent {LOGIN}, role backend-dev, provider openrouter)" in out, out)
        check("the hint to see every choice names fabric-model bare",
              "; fabric-model list --provider openrouter shows every choice" in out and "bin/fabric-model" not in out, out)
        check("default session (the top tier, with its family shim)",
              "session : deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim" in out, out)
        check("code-low -> glm-5.3-flash + shim -> haiku alias",
              "export ANTHROPIC_DEFAULT_HAIKU_MODEL=z-ai/glm-5.3-flash@preset/glm2claude-shim" in out, out)
        check("code-medium -> glm-5.2 + shim -> sonnet alias",
              "export ANTHROPIC_DEFAULT_SONNET_MODEL=z-ai/glm-5.2@preset/glm2claude-shim" in out, out)
        check("code-high -> deepseek v4 pro + its shim -> opus alias",
              "export ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim" in out, out)
        check("code-plan -> deepseek v4 pro + its shim -> fable alias, its own export",
              has(r"export ANTHROPIC_DEFAULT_FABLE_MODEL=deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim$", out), out)
        check("four aliases, four exports: the review class never shares code-high's",
              len(re.findall(r"export ANTHROPIC_DEFAULT_", out)) == 4, out)
        # The class lines and the effort beside them, and nothing on stderr:
        # the launcher has no `set -e`, so a traceback there costs the caller
        # nothing but the output it came for.
        e = {**base, "HOME": home, "PATH": path_export, "AGENT_FABRIC_ROOT": fabric, "AGENT_FABRIC_STATE_DIR": state}
        r = subprocess.run(["bash", LAUNCHER, "--print"], cwd=repo, env=e, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=300)
        check("a line per capability class, from the python block",
              len(re.findall(r"^  code-[a-z]*  *:", r.stdout, re.M)) == 5, r.stdout)
        check("…and --print writes nothing to stderr", r.stderr == "", r.stderr)
        check("each class line carries its routed effort (routing/effort.json)",
              len(re.findall(r"^  code-[a-z]*  *:.* effort ", r.stdout, re.M)) == 5, r.stdout)
        check("a level the model does not admit prints asked -> served, never served alone",
              has(r"code-medium .* effort high \(asked medium\)", r.stdout), r.stdout)

        print("launch: a non-GLM override receives no shim; a GLM override keeps it")
        mkfabric()
        profile("roles", "backend-dev", '{"capabilities":{"code-high":"anthropic/claude-sonnet-5"}}')
        out = out_of("--print")
        check("a role override to a non-GLM model gets no shim",
              has(r"export ANTHROPIC_DEFAULT_OPUS_MODEL=anthropic/claude-sonnet-5$", out), out)
        check("the untouched GLM class keeps its shim",
              "export ANTHROPIC_DEFAULT_HAIKU_MODEL=z-ai/glm-5.3-flash@preset/glm2claude-shim" in out, out)
        mkfabric()
        profile("agents", LOGIN, '{"capabilities":{"code-low":"z-ai/glm-5.2"},"session":"z-ai/glm-5.3"}')
        out = out_of("--print")
        check("an agent (login-keyed) override to another GLM model keeps the family shim",
              "export ANTHROPIC_DEFAULT_HAIKU_MODEL=z-ai/glm-5.2@preset/glm2claude-shim" in out, out)
        check("the session (main agent) gets the family shim too, separately from the classes",
              "session : z-ai/glm-5.3@preset/glm2claude-shim" in out, out)

        print("launch: merge order — defaults <- role <- agent <- local, later wins")
        mkfabric()
        profile("defaults", '{"capabilities":{"code-low":"vendor/default-low"}}')
        profile("roles", "backend-dev", '{"capabilities":{"code-low":"vendor/role-low","code-medium":"vendor/role-medium"}}')
        profile("agents", LOGIN, '{"capabilities":{"code-medium":"vendor/agent-medium"},"session":"vendor/agent-session"}')
        local('{"session":"vendor/local-session"}')
        out = out_of("--print")
        check("role row wins over defaults", "ANTHROPIC_DEFAULT_HAIKU_MODEL=vendor/role-low" in out, out)
        check("agent row wins over role", "ANTHROPIC_DEFAULT_SONNET_MODEL=vendor/agent-medium" in out, out)
        check("the local override wins over the agent row", "session : vendor/local-session" in out, out)

        print("launch: the review gate")
        mkfabric()
        local('{"capabilities":{"code-review":"anthropic/claude-opus-5"}}')
        rc, out = run("--print")
        check("another review-grade model in the local override is allowed; it reaches the reviewer file, never the "
              "fable export (code-plan's)",
              rc == 0 and "code-review : anthropic/claude-opus-5  shim -  => anthropic/claude-opus-5  (pinned in the agent file"
              in out and "ANTHROPIC_DEFAULT_FABLE_MODEL=anthropic/claude-opus-5" not in out, out)
        check("the fable export is code-plan's",
              "export ANTHROPIC_DEFAULT_FABLE_MODEL=deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim" in out, out)
        mkfabric()
        local('{"capabilities":{"code-review":"z-ai/glm-5.3-flash"}}')
        check("a review model outside review-grade.json in the local override is REFUSED", run("--print")[0] != 0)
        mkfabric()
        local('{"capabilities":{"code-high":"z-ai/glm-5.3-flash"}}')
        rc, out = run("--print")
        check("the coding classes are NOT review-gated: a cheap code-high is allowed",
              rc == 0 and "ANTHROPIC_DEFAULT_OPUS_MODEL=z-ai/glm-5.3-flash@preset/glm2claude-shim" in out, out)

        print("launch: the refusals")
        mkfabric()
        rm(f"{agent_dir}/binding.json")
        rc, out = run("--print")
        check("no binding: refused, names fabric-role by its bare name",
              rc == 1 and "no active role binding" in out and "fabric-role bind" in out and "bin/fabric-role" not in out, out)
        mkfabric()
        binding(None)
        check("binding with no role: refused", run("--print")[0] == 1)
        mkfabric()
        rm(f"{fabric}/routing/capabilities.json")
        check("no capabilities.json: refused", run("--print")[0] == 1)
        mkfabric()
        check("--settings passthrough refused", run("--settings", "foo.json")[0] != 0)
        mkfabric()
        check("--setting-sources passthrough refused", run("--setting-sources", "user,project")[0] != 0)
        for flag in ("--system-prompt", "--system-prompt-file", "--append-system-prompt", "--append-system-prompt-file"):
            mkfabric()
            rc, out = run(flag, "x.md")
            check(f"{flag} passthrough refused: the role's prompt is the launcher's",
                  rc != 0 and "role's system prompt is the" in out, out)
            mkfabric()
            check(f"{flag}=… refused too", run(f"{flag}=x.md")[0] != 0)
        mkfabric()
        put(f"{home}/.claude/settings.json", '{"env":{"ANTHROPIC_DEFAULT_OPUS_MODEL":"vendor/sneaky"}}\n')
        check("user-scope ANTHROPIC_DEFAULT pin: refused", run("--print")[0] == 1)
        rm(f"{home}/.claude/settings.json")

        # EVERY settings scope is fenced, and the refusal names the file and
        # key.
        def pin_in(path: str, text: str, **kw) -> tuple[int, str]:
            mkfabric()
            put(path, text + "\n")
            rc, out = run("--print", **kw)
            rm(path)
            return rc, out
        rc, out = pin_in(f"{home}/.claude/settings.local.json", '{"env":{"ANTHROPIC_DEFAULT_HAIKU_MODEL":"vendor/sneaky"}}')
        check("user LOCAL scope pin: refused", rc == 1, out)
        rc, out = pin_in(f"{repo}/.claude/settings.json", '{"modelOverrides":{"claude-opus-5":"vendor/sneaky"}}')
        check("project scope modelOverrides: refused", rc == 1, out)
        rc, out = pin_in(f"{repo}/.claude/settings.local.json", '{"env":{"CLAUDE_CODE_SUBAGENT_MODEL":"vendor/sneaky"}}')
        check("project LOCAL scope subagent pin: refused", rc == 1, out)
        check("…naming the file and the key",
              "settings.local.json carries model pins (env.CLAUDE_CODE_SUBAGENT_MODEL)" in out, out)
        mkfabric()
        put(f"{sandbox}/cfgdir/settings.json", '{"env":{"ANTHROPIC_MODEL":"vendor/sneaky"}}\n')
        rc, out = run("--print", plant={"CLAUDE_CONFIG_DIR": f"{sandbox}/cfgdir"})
        check("CLAUDE_CONFIG_DIR scope, ANTHROPIC_MODEL (not only _DEFAULT_): refused", rc == 1, out)
        rm(f"{sandbox}/cfgdir")
        rc, out = pin_in(f"{repo}/.claude/settings.local.json",
                         '{"env":{"CLAUDE_BRIDGE_AUTH_TOKEN":"not-a-pin"},"model":"opus"}')
        check("a non-pin env entry and a top-level model preference are not refused", rc == 0, out)
        mkfabric()
        rc, out = run("--print", CLAUDE_CODE_SUBAGENT_MODEL="vendor/sneaky")
        check("CLAUDE_CODE_SUBAGENT_MODEL in the caller's environment: refused", rc == 1, out)
        mkfabric()
        rc, out = run("--print", CLAUDE_CODE_SUBAGENT_MODEL_FORCE="1")
        check("CLAUDE_CODE_SUBAGENT_MODEL_FORCE: refused", rc == 1 and "SUBAGENT_MODEL_FORCE" in out, out)
        # The fence is on the LAUNCH directory, never an inherited REPO_ROOT.
        mkfabric()
        shutil.copytree(repo, f"{sandbox}/other")
        put(f"{repo}/.claude/settings.local.json", '{"env":{"ANTHROPIC_DEFAULT_OPUS_MODEL":"vendor/sneaky"}}\n')
        rc, out = run("--print", REPO_ROOT=f"{sandbox}/other")
        check("an inherited REPO_ROOT does not move the fence off the launch directory",
              rc == 1 and "repo/.claude/settings.local.json carries model pins" in out, out)
        rm(f"{sandbox}/other")

        print("launch: identity comes from the OS, not from the directory or the environment")
        mkfabric()
        rm(repo)
        os.makedirs(f"{sandbox}/architect-cto-01")
        subprocess.run(["git", "init", "-q", f"{sandbox}/architect-cto-01"], env=base, check=True, timeout=30)
        out = out_of("--print", cwd=f"{sandbox}/architect-cto-01", USER="architect-cto-01", LOGNAME="architect-cto-01")
        check(f"launched from a directory named for another agent, with USER forged: still agent {LOGIN}",
              f"(agent {LOGIN}, role backend-dev, provider openrouter)" in out, out)
        os.makedirs(repo)
        subprocess.run(["git", "init", "-q", repo], env=base, check=True, timeout=30)

        # A malformed LOCAL override is refused, not exported as "None".
        def override(text: str) -> tuple[int, str]:
            mkfabric()
            local(text)
            return run("--print")
        rc, out = override('{"session": null}')
        check("session: null refused, named", rc == 1 and "session is None" in out, out)
        check("capabilities.code-low: null refused", override('{"capabilities": {"code-low": null}}')[0] == 1)
        check("a class that is not a model id refused", override('{"capabilities": {"code-low": "Not A Model"}}')[0] == 1)
        check("an empty class refused (ori would silently substitute its own default)",
              override('{"capabilities": {"code-low": ""}}')[0] == 1)
        check("a COMPOSITE in a profile layer is refused: the shim is derived, never configured",
              override('{"capabilities": {"code-low": "z-ai/glm-5.3@preset/glm2claude-shim"}}')[0] == 1)
        check("variant and [1m] spellings accepted", override('{"session": "anthropic/claude-opus-5:floor[1m]"}')[0] == 0)
        rc, out = override('{"session": "vendor/model\\n"}')
        check("a trailing newline is not a model id", rc == 1 and "session is 'vendor/model\\n'" in out, out)

        # --print anywhere in the arguments, not only first.
        mkfabric()
        out = out_of("--verbose", "--print")
        check("--print after another flag still prints, never execs",
              "resolved profile" in out and "ORI-EXECCED" not in out, out)

        # Auth is a CONJUNCTION — authenticated AND source.kind == environment.
        def fake_auth(answer: str, status: int = 0) -> None:
            put(f"{bin_}/ori", f"#!/usr/bin/env bash\necho '{answer}'\nexit {status}\n", 0o755)
        for answer, status, label in (
                ('{"ok":false,"data":{"authenticated":false}}', 1, "unauthenticated ori: refused"),
                ('{"ok":true,"data":{"authenticated":false,"source":{"kind":"environment","location":"OPENROUTER_API_KEY"}}}', 0,
                 "unauthenticated but environment-sourced: refused"),
                ('{"ok":true,"data":{"authenticated":true,"source":{"kind":"workspace"}}}', 0,
                 "authenticated from a stored credential: refused"),
                ('{"ok":true,"data":{"authenticated":true,"source":{"kind":"environment"}}}', 3, "ori auth exit status is kept")):
            mkfabric()
            fake_auth(answer, status)
            check(label, run("--print")[0] == 1)
        write_fake_ori()

        print("launch: --provider anthropic execs plain claude with only the pinned tiers exported")
        put(f"{bin_}/claude", FAKE_CLAUDE, 0o755)
        mkfabric()
        rc, out = run("--provider", "anthropic", "--print")
        check("--print exits 0", rc == 0, out)
        check("the header names the provider", "provider anthropic)" in out, out)
        check("the session is the anthropic default, Opus 5.5 (its own, not the broker's spelled natively)",
              has(r"session : claude-opus-5-5$", out), out)
        check("the review class is pinned to claude-opus-5[1m] (the column's native id), through the agent file",
              "code-review : claude-opus-5[1m]  (pinned in the agent file; the dispatch guard applies it; from "
              "capabilities.providers.anthropic)" in out, out)
        check("a coding class pinned by the column is exported for the tier it rides (the top of each class)",
              "code-high   : claude-opus-5-5  (exported for its tier; from capabilities.providers.anthropic)" in out
              and has(r"export ANTHROPIC_DEFAULT_OPUS_MODEL=claude-opus-5-5$", out), out)
        check("the fable export is code-plan's pin; the reviewer never rides it",
              has(r"export ANTHROPIC_DEFAULT_FABLE_MODEL=claude-fable-5-1$", out), out)

        print("launch: the session's effort — resolved, stamped, overridable, and never from the environment")
        mkfabric()
        out = out_of("--provider", "anthropic", "--print")
        check("--print names the session level and where it came from",
              has(r"^  effort  : high  \(routing/effort\.json\)", out), out)
        out = out_of("--provider", "anthropic", "--version")
        check("…and it reaches claude as --effort", has(r"CLAUDE-EXECCED:.*--effort high", out), out)
        check("…and is stamped, so fabric-status can compare it with the read-back",
              "CLAUDE-ENV:AGENT_FABRIC_LAUNCH_EFFORT=high" in out, out)
        # The stamp says what the CHILD applies, never what the fabric wanted.
        out = out_of("--provider", "anthropic", "--effort", "low", "--version")
        check("a caller's --effort is what gets stamped", "CLAUDE-ENV:AGENT_FABRIC_LAUNCH_EFFORT=low" in out, out)
        check("…and only one --effort reaches the child", grep("CLAUDE-EXECCED", out).count("--effort") == 1, out)
        rc, out = run("--provider", "anthropic", "--version", CLAUDE_CODE_EFFORT_LEVEL="max")
        check("CLAUDE_CODE_EFFORT_LEVEL in the environment: REFUSED, never launched", rc != 0 and "EXECCED" not in out, out)
        rc, out = run("--provider", "anthropic", "--version", CLAUDE_CODE_EFFORT_LEVEL="auto")
        check("…'auto' too: it is a value meaning 'use the model default', not an absence", rc != 0, out)
        # Every scope fenced for models is fenced for effort: a settings key
        # is merged into the CHILD, past the process-environment refusal.
        mkfabric()
        put(f"{home}/.claude/settings.json", '{"maxEffortLevel":"low"}\n')
        rc, out = run("--provider", "anthropic", "--version")
        check("a settings scope capping effort: REFUSED", rc != 0 and "EXECCED" not in out, out)
        put(f"{home}/.claude/settings.json", '{"env":{"CLAUDE_CODE_EFFORT_LEVEL":"max"}}\n')
        check("…and one carrying the variable in its env block", run("--provider", "anthropic", "--version")[0] != 0)
        # …but NOT the two the harness writes itself: /effort persists
        # modelSettings into the user scope, and --effort outranks both.
        put(f"{home}/.claude/settings.json",
            '{"modelSettings":{"claude-opus-5":{"effortLevel":"high"}},"effortLevel":"high"}\n')
        rc, out = run("--provider", "anthropic", "--version")
        check("a user scope carrying modelSettings/effortLevel still launches: --effort outranks them",
              rc == 0 and "EXECCED" in out, out)
        rm(f"{home}/.claude/settings.json")
        check("exported but EMPTY is still set, and still refused",
              run("--provider", "anthropic", "--version", CLAUDE_CODE_EFFORT_LEVEL="")[0] != 0)
        # A trailing bare --effort is the caller's; adding ours makes the
        # child read "--effort" as the level.
        mkfabric()
        out = out_of("--provider", "anthropic", "--version", "--effort")
        check("a trailing bare --effort is not doubled", grep("CLAUDE-EXECCED", out).count("--effort") == 1, out)
        # A session on a model with no effort control gets no flag at all.
        mkfabric()
        profile("defaults", '{"providers":{"anthropic":{"session":"claude-haiku-4-5-20251001"}}}')
        out = out_of("--provider", "anthropic", "--print")
        check("a session model with no effort control says so",
              has(r"^  effort  : -  \(this session's model expresses none", out), out)
        # Planted: a launch from inside another fabric session arrives carrying
        # that session's stamp, and must clear it rather than pass it on.
        out = out_of("--provider", "anthropic", "--version", AGENT_FABRIC_LAUNCH_EFFORT="high")
        check("…and passes no --effort and stamps nothing, even over an inherited stamp",
              "--effort" not in out and not has(r"AGENT_FABRIC_LAUNCH_EFFORT=.", out), out)
        caps = json.loads(read(f"{fabric}/routing/capabilities.json"))
        caps["providers"]["anthropic"]["models"]["code-high"] = None
        put(f"{fabric}/routing/capabilities.json", json.dumps(caps))
        out = out_of("--provider", "anthropic", "--print")
        check("a null in the column is the harness's own tier: nothing exported for it",
              "code-high   : opus  (harness default for its tier)" in out and "export ANTHROPIC_DEFAULT_OPUS_MODEL" not in out, out)
        # --print only shows the plan; the CHILD's environment is what runs.
        out = out_of("--provider", "anthropic", "--version", ANTHROPIC_DEFAULT_OPUS_MODEL="claude-parent-leftover")
        check("…and an alias export inherited from a parent session is cleared, not passed on",
              has(r"CLAUDE-ENV:ANTHROPIC_DEFAULT_OPUS_MODEL=$", out), grep("OPUS", out))
        mkfabric()
        out = out_of("--provider=anthropic", "--version")
        check("execs plain claude with the native session model and the role's prompt file",
              f"CLAUDE-EXECCED:--model claude-opus-5-5 --effort high --append-system-prompt-file {prompt_file} --version" in out,
              out)
        check("role stamped on plain claude", has(r"CLAUDE-ENV:AGENT_FABRIC_LAUNCH_ROLE=backend-dev$", out), out)
        check("no tool removed from a login that is not language-culture", "--disallowedTools" not in out, out)
        plain = out
        # THE WATCH STARTS WITH THE SESSION: a bare interactive launch opens
        # with a prompt that arms it, after `--` and last; print mode, the
        # caller's own prompt, --version and a caller's own `--` add none.
        out = out_of("--provider", "anthropic")
        check("a bare launch opens with the prompt that arms the watch, after --",
              has(rf"CLAUDE-EXECCED:.*launch-prompt\.md -- {re.escape(SESSION_START)}", out), out)
        # The prompt stays in claude's argv; a kill by the watch's command
        # pattern once matched it and ended the session.
        check("…and names no command a process pattern could match", "gzcoord-inbox" not in grep("CLAUDE-EXECCED:", out), out)
        out = out_of("--provider", "anthropic", "--resume", "abc123")
        check("…and a resume, after the session id",
              has(r"CLAUDE-EXECCED:.*--resume abc123 -- Session start: arm your GZCoord inbox watch", out), out)
        out = out_of("--provider", "anthropic", "--resume")
        check("…a bare --resume keeps its picker: the prompt is not its value",
              has(r"CLAUDE-EXECCED:.*--resume -- Session start: arm", out), out)
        out = out_of("--provider", "anthropic", "--add-dir", "/x")
        check("…and a variadic option does not swallow it", has(r"CLAUDE-EXECCED:.*--add-dir /x -- Session start: arm", out), out)
        for args in (["-p"], ["do-the-thing"], ["--version"], ["--", "do-it"], ["--"]):
            out = out_of("--provider", "anthropic", *args)
            check(f"…none with: {' '.join(args)}", "Session start: arm" not in out, out)
        out = out_of("--provider", "anthropic", AGENT_FABRIC_NO_OPENING="1")
        check("…and none when AGENT_FABRIC_NO_OPENING is set", "Session start: arm" not in out, out)
        # A language-culture login whose locale has a search: the harness's
        # WebSearch is removed at exec.
        suffix = LOGIN.rsplit("-", 1)[-1]
        lc = f"{fabric}/identities/roles/language-culture"
        shutil.copytree(f"{fabric}/identities/roles/backend-dev", lc)   # a charter to render
        put(f"{lc}/locale/{suffix}/locale.json", '{"timezone":"Asia/Tbilisi","brave":{"country":"ALL","tool_description":"ძიება"}}')
        binding("language-culture")
        outlc = out_of("--provider", "anthropic", "--", "--version")
        check("a language-culture login with a locale search execs claude without WebSearch — the variadic flag last, "
              "after the caller's arguments", has(r"CLAUDE-EXECCED:.*--version --disallowedTools WebSearch$", outlc), outlc)
        outlc = out_of("--provider", "anthropic")
        check("…and a bare launch there: the opening after the variadic flag, behind --",
              has(r"CLAUDE-EXECCED:.*--disallowedTools WebSearch -- Session start: arm", outlc), outlc)
        check("…with the prompt still appended and no build stamp: the locale carries no harness text",
              has(rf"CLAUDE-EXECCED:.*--append-system-prompt-file {re.escape(prompt_file)}", outlc)
              and has(r"CLAUDE-ENV:AGENT_FABRIC_LAUNCH_CLAUDE_VERSION=$", outlc), outlc)
        # The build stamp means "the prompt is replaced": inherited from a
        # replaced session, it would say so of this child. Planted.
        outlc = out_of("--provider", "anthropic", "--", "--version", AGENT_FABRIC_LAUNCH_CLAUDE_VERSION="9.9.9 (Claude Code)")
        check("…and a build stamp inherited from a replaced session is cleared",
              has(r"CLAUDE-ENV:AGENT_FABRIC_LAUNCH_CLAUDE_VERSION=$", outlc), grep("CLAUDE_VERSION", outlc))
        # The locale carries the harness text: the whole prompt is replaced,
        # the build stamped, on both providers.
        put(f"{lc}/locale/{suffix}/harness.md", "---\nclass: harness-translation\ntranslates: runtime/claude-code/harness/en.md\n"
            "translates_digest: sha256:x\n---\nშენ ხარ Claude Code. მეხსიერება: `{memory_dir}`.\n")
        outlc = out_of("--provider", "anthropic", "--", "--version")
        check("a locale with the harness text execs claude with the whole prompt replaced",
              has(rf"CLAUDE-EXECCED:.*--system-prompt-file {re.escape(prompt_file)}", outlc)
              and "--append-system-prompt-file" not in outlc, outlc)
        check("…and the build it ran is stamped", has(r"CLAUDE-ENV:AGENT_FABRIC_LAUNCH_CLAUDE_VERSION=.", outlc), outlc)
        rendered = read(prompt_file)
        check("the rendered file ends with the harness text, its memory directory filled",
              f"შენ ხარ Claude Code. მეხსიერება: `{home}/.claude/projects/" in rendered and "{memory_dir}" not in rendered,
              rendered[-300:])
        outp = out_of("--provider", "anthropic", "--print")
        check("--print names the flag and the build",
              "bytes; --system-prompt-file)" in outp and "AGENT_FABRIC_LAUNCH_CLAUDE_VERSION=" in outp, outp)
        outori = out_of("--", "--version")
        check("the broker path carries the same flag",
              has(rf"ORI-EXECCED:claude .*--system-prompt-file {re.escape(prompt_file)}", outori), outori)
        rm(f"{lc}/locale/{suffix}")
        outlc = out_of("--provider", "anthropic", "--", "--version")
        check("…and not when its locale has no search authored", "--disallowedTools" not in outlc, outlc)
        rm(lc)
        binding()
        out = plain
        check("tab-title writer off on plain claude too", "CLAUDE-ENV:CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1" in out, out)
        tmp_default = f"/var/tmp/agent-fabric-{LOGIN}"
        check("TMPDIR is a per-login directory under /var/tmp, created 700",
              f"CLAUDE-ENV:TMPDIR={tmp_default}" in out and os.path.isdir(tmp_default)
              and oct(os.stat(tmp_default).st_mode & 0o777) == "0o700", out)
        os.makedirs(f"{sandbox}/own-tmp")
        out2 = out_of("--provider=anthropic", "--version", keep_tmpdir=f"{sandbox}/own-tmp")
        check("a TMPDIR the account set wins", f"CLAUDE-ENV:TMPDIR={sandbox}/own-tmp" in out2, out2)
        # /tmp is root's: the account's own choice is never held to the
        # per-login directory's owner check (review of #87).
        # Under root /tmp is this account's own, and the case proves nothing.
        if os.geteuid() != 0:
            out3 = out_of("--provider=anthropic", "--version", keep_tmpdir="/tmp")
            check("…even one another account owns, as /tmp is root's",
                  "CLAUDE-ENV:TMPDIR=/tmp\n" in out3 + "\n" and "launch: TMPDIR" not in out3, out3)
        check("…not ori", "ORI-EXECCED" not in out, out)
        check("FABLE exported as code-plan's pin, the native id",
              has(r"CLAUDE-ENV:ANTHROPIC_DEFAULT_FABLE_MODEL=claude-fable-5-1$", out), out)
        check("OPUS exported as code-high's pin", has(r"CLAUDE-ENV:ANTHROPIC_DEFAULT_OPUS_MODEL=claude-opus-5-5$", out), out)
        check("the exec installed the reviewer file for plain claude: claude-opus-5[1m]",
              has(r"^model: claude-opus-5\[1m\]$", read(f"{home}/.claude/agents/code-review.md")),
              read(f"{home}/.claude/agents/code-review.md")[:300])
        out_of("--version")
        check("…and a broker launch rewrites it with the composite: one file, one launch at a time",
              has(r"^model: deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim$", read(f"{home}/.claude/agents/code-review.md")),
              read(f"{home}/.claude/agents/code-review.md")[:300])
        out_of("--provider=anthropic", "--help")
        check("…but a help read on the other provider rewrites nothing (2026-10-02: it broke the review guard)",
              has(r"^model: deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim$", read(f"{home}/.claude/agents/code-review.md")),
              read(f"{home}/.claude/agents/code-review.md")[:300])
        check("code-plan keeps its alias line: its pin is the export",
              has(r"^model: fable$", read(f"{home}/.claude/agents/code-plan.md")), read(f"{home}/.claude/agents/code-plan.md")[:300])
        out = out_of("--provider=anthropic", "--version")
        check("no base URL: Anthropic direct", has(r"CLAUDE-ENV:ANTHROPIC_BASE_URL=$", out), out)
        # Over a base URL the CALLER carries: a launch from inside a broker
        # session would otherwise run and bill on the broker while every
        # stamp says "anthropic". Planted.
        out = out_of("--provider", "anthropic", "--version", plant={"ANTHROPIC_BASE_URL": "https://openrouter.ai/api"})
        check("an inherited broker base URL is cleared on the anthropic path",
              has(r"CLAUDE-ENV:ANTHROPIC_BASE_URL=$", out), grep("BASE_URL|PROVIDER", out))
        # …and ONLY the broker's: any other base URL is someone's choice.
        out = out_of("--provider", "anthropic", "--version", plant={"ANTHROPIC_BASE_URL": "https://gateway.example.com"})
        check("a base URL naming anything else is left alone",
              has(r"CLAUDE-ENV:ANTHROPIC_BASE_URL=https://gateway\.example\.com$", out), grep("BASE_URL", out))
        out = out_of("--provider", "anthropic", "--version", plant={"ANTHROPIC_BASE_URL": "https://example.com/openrouter.ai"})
        check("…including a look-alike with openrouter.ai in its path: the host decides",
              has(r"CLAUDE-ENV:ANTHROPIC_BASE_URL=https://example\.com/openrouter\.ai$", out), grep("BASE_URL", out))
        # The CREDENTIALS, which the base URL alone missed: the environment
        # `ori claude` gives its child, planted whole.
        fake_or = "sk-or-v1-fixture-not-a-real-key"
        out = out_of("--provider", "anthropic", "--version", OPENROUTER_API_KEY=fake_or,
                     plant={"ANTHROPIC_BASE_URL": "https://openrouter.ai/api", "ANTHROPIC_AUTH_TOKEN": "",
                            "ANTHROPIC_API_KEY": fake_or, "ANTHROPIC_CUSTOM_HEADERS": "X-Session-Id: s1"})
        check("the broker's key never reaches a plain-claude child", "CLAUDE-CRED:ANTHROPIC_API_KEY=unset" in out,
              grep("CLAUDE-CRED", out))
        check("…nor its headers, nor its (empty) token",
              "CLAUDE-CRED:ANTHROPIC_CUSTOM_HEADERS=unset" in out and "CLAUDE-CRED:ANTHROPIC_AUTH_TOKEN=unset" in out,
              grep("CLAUDE-CRED", out))
        # The broker branch must clear the key BY ITSELF: this one is neither
        # sk-or shaped nor equal to OPENROUTER_API_KEY.
        out = out_of("--provider", "anthropic", "--version", OPENROUTER_API_KEY="a-different-value",
                     plant={"ANTHROPIC_BASE_URL": "https://openrouter.ai/api", "ANTHROPIC_API_KEY": "opaque-fixture-token"})
        check("…the branch clears the key whatever its shape, with no second check to lean on",
              "CLAUDE-CRED:ANTHROPIC_API_KEY=unset" in out, grep("CLAUDE-CRED", out))
        # Not only credentials: ori tunes its child for the BROKER'S model;
        # the privacy opt-outs are left.
        out = out_of("--provider", "anthropic", "--version", plant={"ANTHROPIC_BASE_URL": "https://openrouter.ai/api"},
                     CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT="1", CLAUDE_CODE_MAX_CONTEXT_TOKENS="163840",
                     ANTHROPIC_MODEL="deepseek/deepseek-v4-pro", DISABLE_TELEMETRY="1")
        check("the broker's model tuning does not follow onto plain claude",
              "CLAUDE-TUNE:CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT=<unset>" in out
              and "CLAUDE-TUNE:CLAUDE_CODE_MAX_CONTEXT_TOKENS=<unset>" in out and "CLAUDE-TUNE:ANTHROPIC_MODEL=<unset>" in out,
              grep("CLAUDE-TUNE", out))
        check("…but a privacy opt-out is left as it was", "CLAUDE-TUNE:DISABLE_TELEMETRY=1" in out, grep("CLAUDE-TUNE", out))
        check("…and what was dropped is said, by name",
              has(r"^launch: plain claude goes to Anthropic direct — dropped .*ANTHROPIC_BASE_URL.*CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT",
                  out), grep("^launch:", out))
        check("…names only, never values",
              not re.search(r"openrouter\.ai/api|163840|deepseek/deepseek-v4-pro", grep("^launch:", out)), grep("^launch:", out))
        # Without a broker base URL, the same variables are someone's own.
        out = out_of("--provider", "anthropic", "--version", CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT="1")
        check("with no broker base URL the tuning is a person's own: kept, and nothing said",
              "CLAUDE-TUNE:CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT=1" in out and not has(r"^launch: plain claude goes", out),
              grep("CLAUDE-TUNE|^launch:", out))
        # The secret check stands on its own, without the base URL beside it.
        out = out_of("--provider", "anthropic", "--version", OPENROUTER_API_KEY=fake_or, plant={"ANTHROPIC_API_KEY": fake_or})
        check("an OpenRouter key in ANTHROPIC_API_KEY is dropped even with no broker base URL",
              "CLAUDE-CRED:ANTHROPIC_API_KEY=unset" in out, grep("CLAUDE-CRED", out))
        out = out_of("--provider", "anthropic", "--version", OPENROUTER_API_KEY="a-different-value",
                     plant={"ANTHROPIC_API_KEY": fake_or})
        check("…recognised by its shape alone, when it matches no known key", "CLAUDE-CRED:ANTHROPIC_API_KEY=unset" in out,
              grep("CLAUDE-CRED", out))
        # And ONLY that: a real Anthropic key is the person's own.
        out = out_of("--provider", "anthropic", "--version", plant={"ANTHROPIC_API_KEY": "sk-ant-fixture-not-a-real-key"})
        check("an Anthropic key is left alone", "CLAUDE-CRED:ANTHROPIC_API_KEY=sk-ant" in out, grep("CLAUDE-CRED", out))
        out = out_of("--provider", "anthropic", "--version", plant={"ANTHROPIC_BASE_URL": "https://gateway.example.com",
                                                                   "ANTHROPIC_API_KEY": "sk-ant-fixture-not-a-real-key"})
        check("…including beside a non-broker base URL", "CLAUDE-CRED:ANTHROPIC_API_KEY=sk-ant" in out, grep("CLAUDE-CRED", out))
        check("provider stamped", "CLAUDE-ENV:AGENT_FABRIC_LAUNCH_PROVIDER=anthropic" in out, out)
        check("profile stamped on vanilla too", f"CLAUDE-ENV:AGENT_FABRIC_LAUNCH_PROFILE=backend-dev/{LOGIN}" in out, out)
        mkfabric()
        rm(f"{agent_dir}/binding.json")
        rc, out = run("--provider", "anthropic", "--print")
        check("vanilla through the launcher still needs a bound role", rc != 0 and "no active role binding" in out, out)
        mkfabric()
        profile("defaults", '{"session": "z-ai/glm-5.3", "providers": {}}')
        rc, out = run("--provider", "anthropic", "--print")
        check("a non-Anthropic session with no Anthropic layer is refused on vanilla, not mistranslated",
              rc != 0 and "not an Anthropic model and no profile layer names one" in out, out)
        # A layer is per provider: plain claude's session and pins are named
        # in its own vocabulary and never leak to the broker.
        mkfabric()
        local('{"providers":{"openrouter":{"session":"z-ai/glm-5.3"},"anthropic":{"session":"code-plan","capabilities":'
              '{"code-high":"claude-opus-5[1m]","code-low":"claude-haiku-4-5"}}}}')
        rc, out = run("--provider", "anthropic", "--print")
        check("plain claude's session is providers.anthropic.session, a class, resolved on this provider, with no skip to "
              "report", rc == 0 and "session : claude-fable-5-1  (the code-plan class)" in out
              and "is not an Anthropic model" not in out, out)
        check("a local pin of a coding class is exported for the tier it rides and says where it came from",
              "code-high   : claude-opus-5[1m]  (exported for its tier; from local)" in out
              and "export ANTHROPIC_DEFAULT_OPUS_MODEL=claude-opus-5[1m]" in out, out)
        check("the other tiers keep the column's pins",
              has(r"export ANTHROPIC_DEFAULT_HAIKU_MODEL=claude-haiku-4-5$", out)
              and has(r"export ANTHROPIC_DEFAULT_SONNET_MODEL=claude-sonnet-5$", out), out)
        rc, out = run("--print")
        check("the same file on the broker: its own session, and the native pins do not reach the broker's exports",
              rc == 0 and "session : z-ai/glm-5.3@preset/glm2claude-shim" in out
              and "export ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim" in out, out)
        local('{"session":"code-high"}')
        rc, out = run("--print")
        check("a flat class-named session is that class's composite on the broker",
              rc == 0 and "session : deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim  (the code-high class)" in out,
              out)
        rc, out = run("--provider", "anthropic", "--print")
        check("…and that class's native pin on plain claude",
              rc == 0 and "session : claude-opus-5-5  (the code-high class)" in out, out)
        local('{"providers":{"anthropic":{"capabilities":{"code-review":"claude-haiku-4-5"}}}}')
        rc, out = run("--provider", "anthropic", "--print")
        check("a local review pin outside the grade is refused on vanilla",
              rc != 0 and "not in routing/policies/review-grade.json" in out, out)
        local('{"providers":{"anthropic":{"capabilities":{"code-high":"z-ai/glm-5.3"}}}}')
        rc, out = run("--provider", "anthropic", "--print")
        check("a class pinned to a broker id on plain claude is refused by name",
              rc != 0 and "providers.anthropic.capabilities.code-high is 'z-ai/glm-5.3', not a native Claude id" in out, out)
        check("…on the broker path too: one malformed layer refuses every launch", run("--print")[0] != 0)
        local('{"providers":{"anthropic":{"capabilities":{"code-high":"opus"}}}}')
        rc, out = run("--provider", "anthropic", "--print")
        check("a tier alias is not a model: the class is the vocabulary, the alias is the adapter's",
              rc != 0 and "not a native Claude id" in out, out)
        mkfabric()
        caps = json.loads(read(f"{fabric}/routing/capabilities.json"))
        caps["providers"]["anthropic"]["models"]["code-review"] = "claude-haiku-4-5"
        put(f"{fabric}/routing/capabilities.json", json.dumps(caps))
        rc, out = run("--provider", "anthropic", "--print")
        check("a pinned review model outside the grade is refused on vanilla too",
              rc != 0 and "not in routing/policies/review-grade.json" in out, out)
        rc, out = run("--provider", "nowhere", "--print")
        check("an unknown provider is refused", rc != 0 and "must be openrouter, anthropic or gateway" in out, out)
        rm(f"{bin_}/claude")

        print("launch: the exec carries the pins to the child")
        mkfabric()
        out = out_of("--version")
        check("execs via ori claude", "ORI-EXECCED:" in out, out)
        check("session model passed as --model", "--model deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim" in out, out)
        check("HAIKU pin (code-low composite) is in the child's environment",
              "ORI-ENV:ANTHROPIC_DEFAULT_HAIKU_MODEL=z-ai/glm-5.3-flash@preset/glm2claude-shim" in out, out)
        check("SONNET pin (code-medium composite) is in the child's environment",
              "ORI-ENV:ANTHROPIC_DEFAULT_SONNET_MODEL=z-ai/glm-5.2@preset/glm2claude-shim" in out, out)
        check("OPUS pin (code-high composite) is in the child's environment",
              "ORI-ENV:ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim" in out, out)
        check("FABLE pin (code-plan composite) is in the child's environment, separate from OPUS",
              has(r"ORI-ENV:ANTHROPIC_DEFAULT_FABLE_MODEL=deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim$", out), out)
        check("session model stamped in the child env",
              "ORI-ENV:AGENT_FABRIC_LAUNCH_SESSION_MODEL=deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim" in out, out)
        check("profile stamped as role/agent", f"ORI-ENV:AGENT_FABRIC_LAUNCH_PROFILE=backend-dev/{LOGIN}" in out, out)
        check("agent stamped", f"ORI-ENV:AGENT_FABRIC_LAUNCH_AGENT={LOGIN}" in out, out)
        check("the harness's tab-title writer is off in the child: the hook is the only writer",
              "ORI-ENV:CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1" in out, out)
        mkfabric()
        out = out_of("--model", "vendor/override", "--version")
        check("a caller's --model is what gets stamped", "ORI-ENV:AGENT_FABRIC_LAUNCH_SESSION_MODEL=vendor/override" in out, out)
        check("…and the launcher's own --model is omitted, so the child sees one; the prompt file still rides",
              f"ORI-EXECCED:claude --effort high --append-system-prompt-file {prompt_file} --model vendor/override --version" in out
              and "--model anthropic/claude-sonnet-5" not in out, out)
        mkfabric()
        out = out_of("--print", "--model=vendor/override2")
        check("--print shows the override", "overridden by --model on the command line: vendor/override2" in out, out)
        mkfabric()
        out = out_of("-p", "hi")
        check("-p passes through to claude untouched, after the prompt file",
              f"ORI-EXECCED:claude --model deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim --effort high "
              f"--append-system-prompt-file {prompt_file} -p hi" in out, out)

        print("launch: a Claude-account template's token never reaches a broker session")
        mkfabric()
        out = out_of("--version", CLAUDE_CODE_OAUTH_TOKEN="sk-ant-oat01-TEMPLATE-FIXTURE")
        check("broker path: the template token is dropped before the session, and that is said",
              has(r"^ORI-HAS-OAUTH-TOKEN:$", out) and "dropped CLAUDE_CODE_OAUTH_TOKEN" in out, grep("(?i)oauth", out))
        check("…by name, never by value", "sk-ant-oat01-TEMPLATE-FIXTURE" not in out)
        # On plain claude the login's synced record decides, not the
        # inherited shell: a fake that reports its token by fingerprint only.
        put(f"{bin_}/claude", '#!/usr/bin/env bash\nv="${CLAUDE_CODE_OAUTH_TOKEN:-}"; if [ -n "$v" ]; then echo '
            '"CLAUDE-OAUTH-SHA:$(printf %s "$v" | sha256sum | cut -c1-12)"; else echo "CLAUDE-OAUTH-SHA:none"; fi\n', 0o755)
        put(sec, "export CLAUDE_CODE_OAUTH_TOKEN='sk-ant-oat01-NEW-TEMPLATE'\n")
        out = out_of("--provider", "anthropic", "--version", CLAUDE_CODE_OAUTH_TOKEN="sk-ant-oat01-OLD-TEMPLATE")
        check("plain claude: the synced record's token, not the older one the shell inherited, and that is said",
              has(rf"^CLAUDE-OAUTH-SHA:{fp('sk-ant-oat01-NEW-TEMPLATE')}$", out) and "taken from the login's synced record" in out,
              grep("(?i)oauth|synced", out))
        check("…by name, never by value", "sk-ant-oat01-" not in out)
        put(sec, "")
        rc, out = run("--provider", "anthropic", "--version", CLAUDE_CODE_OAUTH_TOKEN="sk-ant-oat01-OLD-TEMPLATE")
        check("no template in the record: an inherited one is dropped, by name",
              "the login's synced record has none" in out, grep("(?i)oauth|synced", out))
        check("…and the launch is refused: no session on a login's own /login",
              rc == 1 and "no long-lived Claude sign-in" in out and not has(r"^CLAUDE-OAUTH-SHA:", out), f"rc={rc}\n{out}")
        check("…its hint naming the commands on PATH, not a checkout's bin/",
              "(fabric-accounts assign " in out and "then fabric-secrets sync here" in out and "bin/fabric-" not in out,
              grep("fabric-", out))
        put(sec, "export CLAUDE_CODE_OAUTH_TOKEN='a-login-access-token'\n")
        rc, out = run("--provider", "anthropic", "--version")
        check("a token not of a setup-token's shape is refused too", rc == 1 and "no long-lived Claude sign-in" in out,
              f"rc={rc}")
        print("launch: the session holds its own credential and no other synced secret (ADR-038 rule 9)")
        put(sec, "export CLAUDE_CODE_OAUTH_TOKEN='sk-ant-oat01-SUITE-FIXTURE'\nexport OPENROUTER_API_KEY=sk-or-FILE\n"
                 "export GH_TOKEN=gh-FILE\nexport OPENAI_API_KEY=oa-FILE\nexport DEMO_PORT_OFFSET=640\n"
                 "export CLAUDE_BRIDGE_AUTH_TOKEN=br-FILE\n")
        put(f"{home}/.config/agent-fabric/env.sh", "export DEMO_PORT_OFFSET=640\n")
        inherited = {"GH_TOKEN": "gh-SHELL", "CLAUDE_BRIDGE_AUTH_TOKEN": "br-SHELL", "OPENAI_API_KEY": "oa-SHELL",
                     "DEMO_PORT_OFFSET": "640"}
        put(f"{bin_}/claude", FAKE_CLAUDE, 0o755)
        out = out_of("--provider", "anthropic", "--version", OPENROUTER_API_KEY="sk-or-SHELL", **inherited)
        got = dict(re.findall(r"^CLAUDE-HAS:(\w+)=(\w*)$", out, re.M))
        check("plain claude: only the OAuth token and the plain value reach the session",
              got == {"OPENROUTER_API_KEY": "", "GH_TOKEN": "", "CLAUDE_BRIDGE_AUTH_TOKEN": "yes", "OPENAI_API_KEY": "",
                      "CLAUDE_CODE_OAUTH_TOKEN": "yes", "DEMO_PORT_OFFSET": "yes"}, got)
        check("…the drop is said by name, never by value",
              "dropped what this shell inherited: GH_TOKEN OPENAI_API_KEY OPENROUTER_API_KEY" in out
              and "-SHELL" not in out and "-FILE" not in out, grep("(?i)dropped", out))
        mkfabric()
        out = out_of("--version", **inherited)
        got = dict(re.findall(r"^ORI-HAS:(\w+)=(\w*)$", out, re.M))
        check("broker: the OpenRouter key from the file reaches ori, though no shell exported it; nothing else",
              got == {"OPENROUTER_API_KEY": "yes", "GH_TOKEN": "", "CLAUDE_BRIDGE_AUTH_TOKEN": "yes", "OPENAI_API_KEY": "",
                      "DEMO_PORT_OFFSET": "yes"} and has(r"^ORI-HAS-OAUTH-TOKEN:$", out), got)
        put(sec, "export CLAUDE_CODE_OAUTH_TOKEN='sk-ant-oat01-SUITE-FIXTURE'\n")
        rm(f"{home}/.config/agent-fabric/env.sh")
        out = out_of("--provider", "anthropic", "--version", GH_TOKEN="gh-SHELL", CLAUDE_BRIDGE_AUTH_TOKEN="br-SHELL")
        check("a fixed secret name is dropped even when the file no longer lists it (the stale shell)",
              has(r"^CLAUDE-HAS:GH_TOKEN=$", out), grep("CLAUDE-HAS", out))
        check("…the relay token too: the harness holds the file's or none, never a stale shell's",
              has(r"^CLAUDE-HAS:CLAUDE_BRIDGE_AUTH_TOKEN=$", out), grep("CLAUDE-HAS", out))
        put(f"{home}/.claude.json", '{"hasCompletedOnboarding": false, "theme": "dark"}\n')
        out = out_of("--provider", "anthropic", "--help")
        check("a help read leaves onboarding alone: no session follows it (#91's review)",
              "marked the harness's onboarding done" not in out
              and json.loads(read(f"{home}/.claude.json")).get("hasCompletedOnboarding") is False,
              read(f"{home}/.claude.json"))
        out = out_of("--provider", "anthropic", "--version")
        try:
            d = json.loads(read(f"{home}/.claude.json"))
            onboarded = d.get("hasCompletedOnboarding") is True and d.get("theme") == "dark"
        except ValueError:
            onboarded = False
        check("a template login's unfinished onboarding is marked done before the session — the wizard would ask for a /login",
              onboarded and "marked the harness's onboarding done" in out, read(f"{home}/.claude.json"))
        out = out_of("--provider", "anthropic", "--version")
        check("…once: an onboarded login's file is not rewritten", "marked the harness's onboarding done" not in out)
        rm(f"{home}/.claude.json")
        put(sec, "")
        rc, out = run("--provider", "anthropic", "--print")
        check("--print needs no sign-in: a prompt read-back still works", rc == 0, f"rc={rc}\n{out[-300:]}")
        put(sec, "export CLAUDE_CODE_OAUTH_TOKEN='sk-ant-oat01-SUITE-FIXTURE'\n")
        rm(f"{bin_}/claude")

        print("launch: announces nothing — presence is the control plane's; the session's exit status is still the launcher's")
        # A tripwire: a stub announce.py that records any call, where the
        # launcher used to call it from; the binding names a project, which
        # is what once made it announce.
        mkfabric()
        binding(project="gzapp")
        put(f"{fabric}/tools/fabric/announce.py", 'import os, sys, time\nwith open(os.environ["ANNOUNCE_LOG"], "a") as fh:\n'
            '    fh.write(" ".join(sys.argv[1:]) + f" @{time.time():.3f}\\n")\n')
        alog = f"{sandbox}/announce.log"

        def runa(*args: str, **env: str) -> tuple[int, str]:
            return run(*args, ANNOUNCE_LOG=alog, **env)
        rc, out = runa("--version")
        check("the launcher's exit status is the session's (0)", rc == 0, out)
        check("nothing announced before the session or after it (HELLO and GOODBYE are retired)", not read(alog), read(alog))
        # A plain-claude launch refused for want of a sign-in starts nothing
        # and announces nothing.
        put(f"{bin_}/claude", '#!/usr/bin/env bash\necho "CLAUDE-RAN"\n', 0o755)
        put(sec, "")
        rm(alog)
        rc, out = runa("--provider", "anthropic", "--version")
        check("a launch refused for want of a long-lived sign-in starts nothing and announces nothing",
              rc == 1 and "no long-lived Claude sign-in" in out and "CLAUDE-RAN" not in out and not read(alog), f"rc={rc}\n{out}")
        put(sec, "export CLAUDE_CODE_OAUTH_TOKEN='sk-ant-oat01-SUITE-FIXTURE'\n")
        rm(alog, f"{bin_}/claude")
        # The session's failure is the launcher's failure.
        put(f"{bin_}/ori", f"#!/usr/bin/env bash\nif [[ \"${{1:-}}\" == auth ]]; then echo '{AUTH_OK}'; exit 0; fi\n"
            'echo "ORI-EXECCED:$*"; exit 3\n', 0o755)
        rc, out = runa("--version")
        check("a session exiting 3 makes the launcher exit 3", rc == 3, out)
        check("…and announces nothing", not read(alog), read(alog))
        # A session killed by a signal is the launcher's status too.
        put(f"{bin_}/ori", f"#!/usr/bin/env bash\nif [[ \"${{1:-}}\" == auth ]]; then echo '{AUTH_OK}'; exit 0; fi\n"
            'echo "ORI-EXECCED:$*"; kill -TERM $$\n', 0o755)
        rm(alog)
        rc, out = runa("--version")
        check("a session ended by SIGTERM: the launcher reports 143", rc == 143, out)
        check("…and announces nothing", not read(alog), read(alog))
        write_fake_ori()

        print("launch: a session stopped for an upgrade comes back, resumed, on the new version")
        # The fake session plays the control agent's part: on its first run
        # it writes the restart marker as upgrade.mjs does and ends as SIGTERM
        # leaves it (143); on the second it records its arguments. The binding
        # names the session id the restart must resume.
        binding(project="gzapp", session="sess-123")
        runs = f"{sandbox}/runs"

        def upgrade_session(status: str, requested_at: str) -> None:
            marker = json.dumps({"request_id": "r1", "requested_at": requested_at, "piece": "claude", "from": "2.1.280",
                                 "to": "2.1.281", "installed": "2.1.281", "status": status, "reason": "network"})
            put(f"{bin_}/ori", f"#!/usr/bin/env bash\nif [[ \"${{1:-}}\" == auth ]]; then echo '{AUTH_OK}'; exit 0; fi\n"
                f'n="$(cat "{runs}" 2>/dev/null || echo 0)"; echo $((n+1)) > "{runs}"\n'
                f'if [[ "$n" == 0 ]]; then\n  printf \'%s\\n\' \'{marker}\' > "{agent_dir}/restart.json"\n'
                '  echo "RUN1:$*"; exit 143\nfi\necho "RUN2:$*"; exit 0\n', 0o755)
            rm(runs, alog)
        time.sleep(1)
        upgrade_session("done", utc(1))
        rc, out = runa("--resume", "old-id", "--model", "x")
        check("the upgrade is said, and the launcher does not exit with the stopped session",
              rc == 0 and "claude upgraded 2.1.280 → 2.1.281; resuming the session on it" in out, f"rc={rc}\n{out}")
        check("…resumed by the stopped session's id; the caller's own --resume replaced, the rest passed on",
              has(r"^RUN2:.*--model x", out) and has(r"^RUN2:.*--resume sess-123", out) and not has(r"^RUN2:.*old-id", out),
              grep("RUN2", out))
        check("…and the marker is consumed", not os.path.exists(f"{agent_dir}/restart.json"))
        check("…and a stop and resume announce nothing either", not read(alog), read(alog))
        upgrade_session("failed", utc(5))
        rc, out = runa()
        check("a failed upgrade still brings the session back, and says why",
              rc == 0 and "FAILED (network); resuming the session on what is installed" in out
              and has(r"^RUN2:.*--resume sess-123", out), out)
        upgrade_session("pending", utc(5))
        rc, out = runa(AGENT_FABRIC_RESTART_WAIT_S="1")
        check("an upgrade that never finishes: the wait is bounded, the session comes back",
              "waiting for it" in out and "did not finish within 1 s; resuming" in out and has(r"^RUN2:", out), out)
        upgrade_session("done", "2026-01-01T00:00:00Z")
        rc, out = runa()
        check("a marker older than the launch is another session's: removed, not obeyed",
              rc == 143 and not has(r"^RUN2:", out) and not os.path.exists(f"{agent_dir}/restart.json"), f"rc={rc}\n{out}")
        write_fake_ori()

        print("launch: a session that ends its own job comes back fresh, not resumed")
        # The fake session plays bin/fabric-fresh: a fresh marker with a
        # note, then the stop; the relaunch names no session and says the note.
        put(f"{bin_}/ori", f"#!/usr/bin/env bash\nif [[ \"${{1:-}}\" == auth ]]; then echo '{AUTH_OK}'; exit 0; fi\n"
            f'n="$(cat "{runs}" 2>/dev/null || echo 0)"; echo $((n+1)) > "{runs}"\n'
            'if [[ "$n" == 0 ]]; then\n'
            '  printf \'{"requested_at":"%s","piece":"a fresh session","status":"done","fresh":true,"note":"PR 981 merged"}\\n\' '
            f'"$(date -u -d \'+2 seconds\' +%Y-%m-%dT%H:%M:%SZ)" > "{agent_dir}/restart.json"\n'
            '  echo "RUN1:opening=${AGENT_FABRIC_LAUNCH_OPENING:-unset}:$*"; exit 143\nfi\necho "RUN2:$*"; exit 0\n', 0o755)
        rm(runs)
        rc, out = runa("--resume", "old-id")
        check("the session is told the launcher wrote its opening (fabric-fresh reads it)", has(r"^RUN1:opening=1:", out),
              grep("RUN1", out))
        check("a fresh marker is said, and the launcher brings a session back",
              rc == 0 and "the session finished its job: PR 981 merged; starting a fresh one" in out, f"rc={rc}\n{out}")
        check("…with no --resume and no --continue: a new conversation",
              has(r"^RUN2:", out) and not has(r"^RUN2:.*--resume", out) and not has(r"^RUN2:.*--continue", out), grep("RUN2", out))
        check("…and the opening prompt carries the note",
              has(r"^RUN2:.*finished its job and started this one fresh: PR 981 merged", out), grep("RUN2", out))
        check("…and the marker is consumed", not os.path.exists(f"{agent_dir}/restart.json"))
        # A launch with its own prompt would be relaunched with that prompt
        # and no note: the finished job again. Not relaunched, and said.
        rm(runs)
        rc, out = runa("do the job")
        check("a launch with its own prompt tells the session so", has(r"^RUN1:opening=0:", out), grep("RUN1", out))
        check("…and a fresh marker under it is not a relaunch of that prompt",
              rc == 143 and not has(r"^RUN2:", out) and "carried its own prompt; not relaunching" in out
              and not os.path.exists(f"{agent_dir}/restart.json"), f"rc={rc}\n{out}")
        write_fake_ori()

        print("launch: a fresh session for a job starts in that job's working copy, with the job in its opening")

        def fresh_job_session(job: str) -> None:
            put(f"{bin_}/ori", f"#!/usr/bin/env bash\nif [[ \"${{1:-}}\" == auth ]]; then echo '{AUTH_OK}'; exit 0; fi\n"
                f'n="$(cat "{runs}" 2>/dev/null || echo 0)"; echo $((n+1)) > "{runs}"\n'
                'if [[ "$n" == 0 ]]; then\n'
                '  printf \'{"requested_at":"%s","piece":"a fresh session","status":"done","fresh":true,"note":"","job":"'
                f'{job}"}}\\n\' "$(date -u -d \'+2 seconds\' +%Y-%m-%dT%H:%M:%SZ)" > "{agent_dir}/restart.json"\n'
                '  exit 143\nfi\necho "RUN2:pwd=$PWD:$*"; exit 0\n', 0o755)
            rm(runs)

        def jobs_cmd(*args: str) -> None:
            subprocess.run([sys.executable, f"{fabric}/tools/fabric/jobs.py", *args],
                           env={**base, "AGENT_FABRIC_ROOT": fabric, "AGENT_FABRIC_STATE_DIR": state},
                           stdout=subprocess.DEVNULL, check=True, timeout=60)
        other = f"{sandbox}/other"
        rm(other)
        os.makedirs(other)
        subprocess.run(["git", "init", "-q", other], env=base, check=True, timeout=30)
        jobs_cmd("add", "ship the other thing", "--working-copy", other, "--topic", "routing")
        jobs_cmd("add", "a job whose copy is gone", "--working-copy", f"{sandbox}/gone")
        fresh_job_session("j1")
        rc, out = runa()
        check("the relaunch starts in the job's working copy, and says so",
              rc == 0 and has(rf"^RUN2:pwd={re.escape(other)}:", out) and f"starting job j1 in {other}" in out, f"rc={rc}\n{out}")
        check("…and the opening prompt carries the job in place of waiting for instructions",
              has(r"^RUN2:.*It is for your job j1, ship the other thing \([^)]*topic routing\): read it in full with fabric-jobs show j1",
                  out) and not has(r"^RUN2:.*Then wait for instructions", out), grep("RUN2", out))
        # Started by a relative path, as the README runs it from projects/:
        # the relaunch changes directory first, and must still find itself —
        # and a relative path argument must still name its file.
        rel = os.path.relpath(LAUNCHER, repo)
        os.makedirs(f"{repo}/extra")
        fresh_job_session("j1")
        rc, out = run("--add-dir", "extra", "--mcp-config=m.json", "--model", "extra", launcher=rel, ANNOUNCE_LOG=alog)
        check("…started by a relative path: it finds itself after the move, and only path options' values are made absolute "
              "(both forms, existing or not; a model named like a file is left alone)",
              rc == 0 and has(rf"^RUN2:pwd={re.escape(other)}:", out)
              and has(rf"^RUN2:.*--add-dir {re.escape(repo)}/extra --mcp-config={re.escape(repo)}/m\.json", out)
              and has(r"^RUN2:.* --model extra", out), f"rc={rc}\n{out}")
        os.rmdir(f"{repo}/extra")
        put(f"{other}/f", "dirty\n")
        fresh_job_session("j1")
        rc, out = runa()
        check("a job's copy with uncommitted changes: the old directory, and why",
              has(rf"^RUN2:pwd={re.escape(repo)}:", out)
              and f"job j1's working copy {other} has uncommitted changes; starting in {repo}" in out, out)
        fresh_job_session("j2")
        rc, out = runa()
        check("a job's copy that is gone: the old directory, and why — the job is still said",
              has(rf"^RUN2:pwd={re.escape(repo)}:", out) and f"job j2's working copy {sandbox}/gone is not there" in out
              and has(r"^RUN2:.*It is for your job j2", out), out)
        write_fake_ori()

        print("launch: a fabric checkout behind origin/main is pulled and the launcher re-executes on it")
        # The fixture fabric becomes a git checkout with a bare origin one
        # commit ahead.
        mkfabric()
        git("init", "-q", "-b", "main", cwd=fabric)
        git("add", "-A", cwd=fabric)
        git("commit", "-q", "-m", "base", cwd=fabric)
        origin = f"{sandbox}/origin.git"
        rm(origin)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", origin], env=base, check=True, timeout=30)
        git("remote", "add", "origin", origin, cwd=fabric)
        git("push", "-q", "origin", "main", cwd=fabric)
        rc, out = run("--print")
        check("current: the fetch finds nothing behind, launch proceeds", rc == 0, out)
        rm(other)
        subprocess.run(["git", "clone", "-q", origin, other], env=base, check=True, timeout=60, stderr=subprocess.DEVNULL)

        def origin_ahead(msg: str) -> None:
            git("commit", "-q", "--allow-empty", "-m", msg, cwd=other)
            git("push", "-q", "origin", "main", cwd=other)
        origin_ahead("newer")
        rc, out = run("--print")
        check("behind: pulled, said so, relaunched",
              rc == 0 and "was 1 commit(s) behind origin/main; pulled to" in out and "relaunching on it" in out, out)
        check("…the checkout is at origin/main", git("rev-parse", "HEAD", cwd=fabric) == git("rev-parse", "HEAD", cwd=other))
        check("…and the relaunch resolved the profile (one pull, one relaunch)", "resolved profile" in out, out)
        # Behind again, with a local commit that cannot fast-forward.
        origin_ahead("newer2")
        git("commit", "-q", "--allow-empty", "-m", "local-divergence", cwd=fabric)
        rc, out = run("--print")
        check("diverged: refused with the reason, before resolving anything",
              rc == 1 and "cannot fast-forward" in out and "resolved profile" not in out, out)
        git("reset", "-q", "--hard", "origin/main", cwd=fabric)
        origin_ahead("newer3")
        rc, out = run("--print", AGENT_FABRIC_ALLOW_STALE="1")
        check("AGENT_FABRIC_ALLOW_STALE=1: launches without pulling, loudly",
              rc == 0 and "WARNING — agent-fabric is 1 commit(s) behind" in out
              and git("rev-parse", "HEAD", cwd=fabric) != git("rev-parse", "HEAD", cwd=other), out)
        # A relaunch that is still behind does not loop.
        rc, out = run("--print", AGENT_FABRIC_PULLED="1")
        check("a second relaunch is refused: no loop",
              rc == 1 and "still 1 commit(s) behind origin/main after a pull; not relaunching again" in out, out)
        git("pull", "-q", "--ff-only", "origin", "main", cwd=fabric)
        git("remote", "set-url", "origin", "/nonexistent/origin.git", cwd=fabric)
        rc, out = run("--print")
        check("origin unreachable: launches on what is checked out, and says so",
              rc == 0 and "could not fetch origin/main" in out, out)

        print("launch: the working copy the session starts in is brought up to date, or its gap is said")
        mkfabric()
        git("symbolic-ref", "HEAD", "refs/heads/main", cwd=repo)
        git("commit", "-q", "--allow-empty", "-m", "base", cwd=repo)
        wc_origin, wc_other = f"{sandbox}/wc-origin.git", f"{sandbox}/wc-other"
        rm(wc_origin, wc_other)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", wc_origin], env=base, check=True, timeout=30)
        git("remote", "add", "origin", wc_origin, cwd=repo)
        git("push", "-q", "origin", "main", cwd=repo)
        subprocess.run(["git", "clone", "-q", wc_origin, wc_other], env=base, check=True, timeout=60, stderr=subprocess.DEVNULL)

        def wc_ahead(msg: str) -> None:
            git("commit", "-q", "--allow-empty", "-m", msg, cwd=wc_other)
            git("push", "-q", "origin", "main", cwd=wc_other)
        wc_ahead("newer")
        rc, out = run("--print")
        check("on a clean main: fast-forwarded before the session loads its CLAUDE.md",
              rc == 0 and "was 1 commit(s) behind origin/main; fast-forwarded to" in out
              and git("rev-parse", "HEAD", cwd=repo) == git("rev-parse", "HEAD", cwd=wc_other), out)
        wc_ahead("newer2")
        git("checkout", "-q", "-b", "feature", cwd=repo)
        rc, out = run("--print")
        check("on another branch: the gap is said and nothing moves",
              rc == 0 and "(feature) lacks 1 commit(s) of origin/main" in out
              and git("rev-parse", "HEAD", cwd=repo) != git("rev-parse", "HEAD", cwd=wc_other), out)
        git("checkout", "-q", "main", cwd=repo)
        put(f"{repo}/tracked", "change\n")
        git("add", "tracked", cwd=repo)
        rc, out = run("--print")
        staged = subprocess.run(["git", "diff", "--cached", "--quiet", "--", "tracked"], cwd=repo, env=base,
                                timeout=30).returncode != 0
        check("on a main with staged changes: the gap is said and nothing moves",
              rc == 0 and "(main) lacks 1 commit(s) of origin/main" in out and staged, out)
        git("reset", "-q", "--hard", cwd=repo)
        git("remote", "remove", "origin", cwd=repo)
        rm(wc_origin, wc_other)

        print("launch: the role rides in the system prompt file")
        mkfabric()
        out = out_of("--version")
        prompt = read(prompt_file)
        check("the prompt file is written under the agent's state dir", os.path.isfile(prompt_file))
        check("…and carries the bound role's charter body", "FIXTURE-CHARTER-LINE" in prompt, prompt[:400])
        check("…the identity header names agent and role",
              has(rf"^You are agent `{re.escape(LOGIN)}` on host", prompt) and "the role **backend-dev**" in prompt, prompt[:300])
        check("…a missing brief is a placeholder, not a refusal", "No brief has been distilled" in prompt)
        check("…the team and memory sections are rendered for the role",
              "REPLY-EXPECTED: yes" in prompt and "memory/domains/backend-dev/" in prompt)
        check("…without frontmatter", "class: charter" not in prompt)
        digest = "sha256:" + hashlib.sha256(prompt.encode()).hexdigest()
        check("role stamped in the child env", has(r"ORI-ENV:AGENT_FABRIC_LAUNCH_ROLE=backend-dev$", out), out)
        check("the prompt's sha256 stamped, and it is the file's",
              has(rf"ORI-ENV:AGENT_FABRIC_LAUNCH_PROMPT_DIGEST={digest}$", out), out)
        mkfabric()
        out = out_of("--print")
        check("--print shows the role, the digest and the prompt path",
              "export AGENT_FABRIC_LAUNCH_ROLE=backend-dev" in out and "export AGENT_FABRIC_LAUNCH_PROMPT_DIGEST=sha256:" in out
              and f"prompt  : {prompt_file} (" in out, out)
        check("…and execs nothing", "EXECCED" not in out, out)
        mkfabric()
        rm(f"{fabric}/identities/roles/backend-dev/charter.md")
        rc, out = run("--version")
        check("a role with no charter cannot launch: refused before exec",
              rc != 0 and "could not render the role's system prompt" in out and "EXECCED" not in out, out)

        print("launch: --provider gateway — the harness talks to the gateway, holding a local key and no upstream credential")
        FAKE_GATEWAY = r"""#!/usr/bin/env python3
import ctypes, hashlib, json, os, signal, socket, stat, sys, time
mode = os.environ.get("FAKE_GW_MODE", "ok")
log = os.environ["FAKE_GW_LOG"]
def note(**rec):
    with open(log, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
if sys.argv[1:] == ["--version", "--json"]:
    if mode == "badjson":
        print("not json"); sys.exit(0)
    print(json.dumps({"gateway_version": "0.1.0-fake", "runtime_contract": 2 if mode == "contract2" else 1,
                      "plan_schemas": [1] if mode == "schema1" else [0]}))
    sys.exit(0)
args = dict(zip(sys.argv[2::2], sys.argv[3::2]))
plan = open(args["--plan"], "rb").read()
key = os.read(int(args["--local-key-fd"]), 200).decode()
libc = ctypes.CDLL(None)
sig = ctypes.c_int()
libc.prctl(2, ctypes.byref(sig))   # PR_GET_PDEATHSIG
control = os.fstat(int(args["--control-fd"]))
note(event="serve", argv=sys.argv[1:], key_sha=hashlib.sha256(key.encode()).hexdigest(), key_is_64_hex=len(key) == 64 and all(c in "0123456789abcdef" for c in key),
     pdeathsig=sig.value, own_session=os.getsid(0) == os.getpid(), control_is_socket=stat.S_ISSOCK(control.st_mode),
     plan_sha="sha256:" + hashlib.sha256(plan).hexdigest(), pid=os.getpid(), stdout_is_null=os.path.samestat(os.fstat(1), os.stat(os.devnull)))
if mode == "exit4":
    sys.exit(4)
if mode == "hang":
    time.sleep(60)
ready = {"event": "ready", "gateway_version": "0.1.0-fake", "runtime_contract": 1, "plan_schema": 0,
         "listener": "http://0.0.0.0:54321" if mode == "publiclistener" else "http://127.0.0.1:54321",
         "plan_digest": "sha256:" + "0" * 64 if mode == "baddigest" else "sha256:" + hashlib.sha256(plan).hexdigest()}
if mode == "contract2ready":
    ready["runtime_contract"] = 2
os.write(int(args["--ready-fd"]), (json.dumps(ready) + "\n").encode())
os.close(int(args["--ready-fd"]))
signal.signal(signal.SIGTERM, lambda *a: (note(event="term"), sys.exit(0)))
while True:
    time.sleep(0.1)
"""
        FAKE_CLAUDE_GW = r"""#!/usr/bin/env bash
echo "CLAUDE-EXECCED:$*"
echo "CLAUDE-BASE:${ANTHROPIC_BASE_URL-<unset>}"
echo "CLAUDE-KEYSHA:$(printf %s "${ANTHROPIC_API_KEY-}" | sha256sum | cut -d' ' -f1)"
for v in CLAUDE_CODE_OAUTH_TOKEN ANTHROPIC_AUTH_TOKEN OPENROUTER_API_KEY ANTHROPIC_CUSTOM_HEADERS; do echo "CLAUDE-HAS:$v=${!v+yes}"; done
echo "CLAUDE-GATEWAY-LINES-ALREADY:$(wc -l < "$FAKE_GW_LOG")"
echo "CLAUDE-STATE:$(cat "$AGENT_FABRIC_STATE_DIR/agents/$LOGNAME/gateway.json" 2>/dev/null || echo none)"
echo "CLAUDE-PROVIDER:${AGENT_FABRIC_LAUNCH_PROVIDER-}"
"""
        gw_log = f"{sandbox}/gateway.log"
        gw_env = {"AGENT_FABRIC_GATEWAY_BIN": f"{bin_}/fake-gateway", "FAKE_GW_LOG": gw_log,
                  "CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat01-LEAK-CHECK", "OPENROUTER_API_KEY": "sk-or-LEAK-CHECK",
                  "ANTHROPIC_AUTH_TOKEN": "leak-auth-token", "ANTHROPIC_CUSTOM_HEADERS": "x-leak: 1",
                  "ANTHROPIC_API_KEY": "sk-ant-api03-LEAK-CHECK"}
        put(f"{bin_}/fake-gateway", FAKE_GATEWAY, 0o755)
        put(f"{bin_}/claude", FAKE_CLAUDE_GW, 0o755)
        def put_generator() -> None:
          put(f"{fabric}/tools/fabric/gateway_plan.py", (
              "import json, os\n"
              "class Plan:\n    pass\n"
              "def build(login, provider='anthropic', role=None, port=0, session=None):\n"
              "    p = Plan()\n"
              "    models = [v for k, v in os.environ.items() if k.startswith('ANTHROPIC_DEFAULT_') and k.endswith('_MODEL')]\n"
              "    models.append(os.environ['AGENT_FABRIC_LAUNCH_SESSION_MODEL'])\n"
              "    drop = os.environ.get('FAKE_PLAN_DROP')\n"
              "    p.selectors = [{'selector': m, 'model': m, 'route_id': 'r'} for m in models if m != drop]\n"
              "    p.skipped = ['code-plan: rides a harness alias'] if drop else []\n"
              "    p.bytes = json.dumps({'login': login, 'provider': provider, 'role': role, 'session': session}).encode() + b'\\n'\n"
              "    return p\n"
              "def write(plan, path):\n    open(path, 'wb').write(plan.bytes)\n    return path\n"))

        def gw_records() -> list[dict]:
            return [json.loads(l) for l in read(gw_log).splitlines() if l.strip()]

        def alive(pid: int) -> bool:
            try:
                os.kill(pid, 0)
            except OSError:
                return False
            try:
                with open(f"/proc/{pid}/stat") as fh:
                    return fh.read().rsplit(") ", 1)[1].split()[0] != "Z"
            except OSError:
                return False
        state_file = f"{agent_dir}/gateway.json"
        mkfabric()
        put_generator()
        rm(gw_log, state_file)
        rc, out = run("--provider", "gateway", plant=gw_env)
        recs = gw_records()
        serve = next((r for r in recs if r.get("event") == "serve"), {})
        check("a launch with a fake gateway runs the harness: exit 0", rc == 0 and "CLAUDE-EXECCED:" in out, out)
        check("the gateway got a 64-hex key on --local-key-fd, a ready fd and a control fd that is a socket",
              serve.get("key_is_64_hex") and "--local-key-fd" in serve.get("argv", []) and "--ready-fd" in serve.get("argv", [])
              and serve.get("control_is_socket") is True and "--control-fd" in serve.get("argv", []), serve)
        check("…and was already running when the harness started (READY awaited)", has(r"CLAUDE-GATEWAY-LINES-ALREADY:1$", out), out)
        check("the harness gets ANTHROPIC_BASE_URL = the listener READY reported", has(r"CLAUDE-BASE:http://127\.0\.0\.1:54321$", out), out)
        check("…and ANTHROPIC_API_KEY = the key the gateway was given, not the one the shell had",
              has(rf"CLAUDE-KEYSHA:{re.escape(serve.get('key_sha', 'x'))}$", out)
              and serve.get("key_sha") != hashlib.sha256(b"sk-ant-api03-LEAK-CHECK").hexdigest(), (out, serve))
        check("the harness holds no upstream credential: no OAuth token, auth token, OpenRouter key or custom headers",
              all(has(rf"CLAUDE-HAS:{v}=$", out) for v in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN", "OPENROUTER_API_KEY",
                                                           "ANTHROPIC_CUSTOM_HEADERS")), out)
        check("the plan the gateway served is the file written, digest and all",
              serve.get("plan_sha") == "sha256:" + hashlib.sha256(open(f"{agent_dir}/gateway-plan.json", "rb").read()).hexdigest(), serve)
        check("the plan was built for the login, as anthropic, with a per-launch session id",
              '"provider": "anthropic"' in read(f"{agent_dir}/gateway-plan.json") and f'"login": "{LOGIN}"' in read(f"{agent_dir}/gateway-plan.json"))
        check("the gateway is a child in a session of its own, with the parent-death signal SIGTERM",
              serve.get("own_session") is True and serve.get("pdeathsig") == 15, serve)
        check("its stdout is /dev/null (READY goes by the descriptor, never by prose)", serve.get("stdout_is_null") is True, serve)
        state_during = next(iter(re.findall(r"CLAUDE-STATE:(.*)$", out, re.M)), "")
        check("the state record the harness could read has pid, version, listener and plan digest, and no key",
              all(k in state_during for k in ('"pid"', '"gateway_version": "0.1.0-fake"', '"listener": "http://127.0.0.1:54321"',
                                              '"plan_digest": "sha256:'))
              and not re.search(r"[0-9a-f]{64}", state_during.replace(serve.get("plan_sha", "")[7:], "")), state_during)
        check("when the session ends the gateway is stopped (SIGTERM), its pid gone, its record removed",
              any(r.get("event") == "term" for r in gw_records()) and not alive(serve.get("pid", 0)) and not os.path.exists(state_file), gw_records())
        check("the launch is stamped as the gateway's", has(r"CLAUDE-PROVIDER:gateway$", out), out)
        check("…and recorded as the gateway's, so a resume comes back through it; the agent files were installed for anthropic",
              json.loads(read(f"{agent_dir}/launch-provider.json")).get("provider") == "gateway", read(f"{agent_dir}/launch-provider.json"))
        for mode, why, wants in (("contract2", "a gateway whose runtime contract it does not support", "speaks runtime contract 2"),
                                 ("schema1", "a gateway that does not accept the plan schema", "accepts plan schemas [1]"),
                                 ("badjson", "a --version --json that is not JSON", "did not answer")):
            rm(gw_log)
            rc, out = run("--provider", "gateway", plant={**gw_env, "FAKE_GW_MODE": mode})
            check(f"{why}: refused before the harness starts, and before serve", rc == 1 and wants in out and "CLAUDE-EXECCED" not in out
                  and not any(r.get("event") == "serve" for r in gw_records()), (rc, out))
        for mode, wants in (("exit4", "credential source or the local key was unavailable"), ("baddigest", "not the sha256:"),
                            ("publiclistener", "not loopback http"), ("contract2ready", "READY names runtime contract 2"),
                            ("hang", "did not report READY within")):
            rm(gw_log)
            rc, out = run("--provider", "gateway", plant={**gw_env, "FAKE_GW_MODE": mode, "AGENT_FABRIC_GATEWAY_READY_TIMEOUT_S": "2"})
            serve = next((r for r in gw_records() if r.get("event") == "serve"), {})
            check(f"READY failure ({mode}): refused before the harness, the gateway not left running", rc == 1 and wants in out
                  and "CLAUDE-EXECCED" not in out and not alive(serve.get("pid", 0)) and not os.path.exists(state_file), (rc, out))
        rm(gw_log)
        rc, out = run("--provider", "gateway", plant={**gw_env, "FAKE_PLAN_DROP": "x"})
        rc2, out2 = run("--provider", "gateway", plant=gw_env)
        check("a model the harness would send but the plan has no route for: refused, naming it, the gateway not started",
              rc2 == 0, out2)
        # the dropped selector must be a real pin: take the session model from a normal run
        session_model = next(iter(re.findall(r"CLAUDE-EXECCED:.*--model (\S+)", out2)), "")
        rm(gw_log)
        rc, out = run("--provider", "gateway", plant={**gw_env, "FAKE_PLAN_DROP": session_model})
        check("…the same with the session model dropped from the plan",
              rc == 1 and f"the plan has no route for {session_model}" in out and "skipped: code-plan" in out
              and "CLAUDE-EXECCED" not in out and not os.path.exists(gw_log), (rc, out))
        rc, out = run("--provider", "gateway", plant={**gw_env, "AGENT_FABRIC_GATEWAY_BIN": f"{bin_}/nope"})
        check("no installed gateway: refused, nothing started", rc == 1 and "cannot run" in out and "CLAUDE-EXECCED" not in out, out)
        rm(f"{fabric}/tools/fabric/gateway_plan.py")
        rm(gw_log)
        rc, out = run("--provider", "gateway", plant=gw_env)
        check("no plan generator in the checkout: refused before the gateway starts",
              rc == 1 and "gateway plan generator" in out and not os.path.exists(gw_log) and "CLAUDE-EXECCED" not in out, out)
        rc, out = run("--provider", "gateway", "--print", plant=gw_env)
        check("--print on the gateway path resolves as anthropic, says so, and starts nothing",
              rc == 0 and "provider anthropic)" in out and "launched through agent-fabric-gateway" in out and not os.path.exists(gw_log)
              and "EXECCED" not in out, out)
        rc, out = run("--provider", "gateway", "--help", plant=gw_env)
        check("claude's own --help on the gateway path starts no gateway", not os.path.exists(gw_log), out)
        put(f"{bin_}/claude", FAKE_CLAUDE, 0o755)
        rm(f"{bin_}/fake-gateway")

        print("model-audit: provider values are allowlisted, never echoed by default")

        def audit(**env: str) -> str:
            r = subprocess.run(["bash", os.path.join(HERE, "model-audit.sh")],
                               env={"PATH": base.get("PATH", ""), "HOME": home, **env},
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
            return r.stdout
        out = audit(ANTHROPIC_CUSTOM_HEADERS="Authorization: Bearer test-secret",
                    ANTHROPIC_BASE_URL="https://key-secret@proxy.example/api", ANTHROPIC_DEFAULT_OPUS_MODEL="anthropic/claude-opus-5")
        check("a non-allowlisted provider variable is reported set, not printed",
              "test-secret" not in out and "ANTHROPIC_CUSTOM_HEADERS = <set, " in out, out)
        check("the base URL prints scheme+host, no userinfo",
              "key-secret" not in out and has(r"ANTHROPIC_BASE_URL = https://proxy\.example$", out), out)
        check("an allowlisted pin prints its value", "ANTHROPIC_DEFAULT_OPUS_MODEL = anthropic/claude-opus-5" in out, out)
        check("no stamp: says the session model is not visible", "not launched via runtime/openrouter/launch" in out, out)
        out = audit(ANTHROPIC_BASE_URL="HTTPS://key@proxy.example:8443?api_key=qs-secret#frag-secret")
        check("uppercase scheme, no path, query+fragment: scheme://host:port only",
              not re.search(r"key@|qs-secret|frag-secret", out) and has(r"ANTHROPIC_BASE_URL = https://proxy\.example:8443$", out), out)
        out = audit(ANTHROPIC_BASE_URL="sk-or-v1-notaurl")
        check("a non-URL base value is reported set, never echoed",
              "sk-or" not in out and "ANTHROPIC_BASE_URL = <set, 16 chars>" in out, out)
        out = audit(AGENT_FABRIC_LAUNCH_SESSION_MODEL="vendor/s", AGENT_FABRIC_LAUNCH_PROFILE="r/a", AGENT_FABRIC_LAUNCH_AGENT="a")
        check("the launcher's stamp is reported, agent included",
              "session : vendor/s" in out and "profile : r/a" in out and "agent   : a" in out, out)
        out = audit(ANTHROPIC_CUSTOM_HEADERS="Authorization: Bearer first-secret\nANTHROPIC_MODEL=second-secret")
        check("a newline inside a redacted value neither splits the entry nor truncates the count",
              not re.search(r"first-secret|second-secret", out) and "ANTHROPIC_CUSTOM_HEADERS = <set, 64 chars>" in out
              and "ANTHROPIC_MODEL = " not in out, out)
        out = audit(ANTHROPIC_BASE_URL="HTTPS://OPENROUTER.AI/api")
        check("an uppercase openrouter.ai host classifies as OpenRouter", "routed through OpenRouter" in out, out)
        out = audit(ANTHROPIC_BASE_URL="https://notopenrouter.example/openrouter")
        check("a look-alike host with openrouter in the path is not OpenRouter", "does not name OpenRouter" in out, out)

    print(f"\ntest_launch_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
