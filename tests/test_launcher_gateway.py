#!/usr/bin/env python3
"""tools/fabric/launcher/gateway.py and what makes `--provider gateway` a provider
the rest of the tools understand: the version check, READY parsing, the harness's
environment, the state record, and the mapping of "gateway" to the anthropic column.
The launch end to end, with a fake gateway, is tests/test_launch_cli.py's. Plain script:
prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import launch  # noqa: E402,F401  (loads the fabric_launcher package)
from fabric_launcher import gateway  # noqa: E402
from fabric_launcher.base import Refused  # noqa: E402
import resume  # noqa: E402


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail!r}"))
        fails += not good

    def refused(fn, *a, **kw) -> str:
        try:
            fn(*a, **kw)
        except Refused as e:
            return str(e)
        return ""

    with tempfile.TemporaryDirectory(prefix="test_launcher_gateway.") as tmp:
        def script(name: str, body: str) -> str:
            path = os.path.join(tmp, name)
            with open(path, "w") as fh:
                fh.write("#!/usr/bin/env python3\n" + body)
            os.chmod(path, 0o755)
            return path

        ok_json = '{"gateway_version": "1.2.3", "runtime_contract": 1, "plan_schemas": [0, 1]}'
        print("the version check")
        v = gateway.check_version(script("ok", f"print('''{ok_json}''')"))
        check("a supported contract and a plan schema it accepts: returned", v["gateway_version"] == "1.2.3", v)
        for label, body, wants in (
                ("an unsupported runtime contract", "print('{\"gateway_version\":\"1.2.3\",\"runtime_contract\":2,\"plan_schemas\":[0]}')", "speaks runtime contract 2"),
                ("a gateway that does not accept plan schema 0", "print('{\"gateway_version\":\"1.2.3\",\"runtime_contract\":1,\"plan_schemas\":[1]}')", "accepts plan schemas [1]"),
                ("a contract that is a string", "print('{\"gateway_version\":\"1\",\"runtime_contract\":\"1\",\"plan_schemas\":[0]}')", "did not answer"),
                ("a plan_schemas of [false], which is not 0", "print('{\"gateway_version\":\"1\",\"runtime_contract\":1,\"plan_schemas\":[false]}')", "accepts plan schemas [False]"),
                ("a bool contract", "print('{\"gateway_version\":\"1\",\"runtime_contract\":true,\"plan_schemas\":[0]}')", "did not answer"),
                ("not JSON", "print('hello')", "did not answer"),
                ("a JSON array", "print('[]')", "did not answer"),
                ("a non-zero exit", "import sys\nprint('{}')\nsys.exit(3)", "exited 3")):
            msg = refused(gateway.check_version, script("bad", body))
            check(f"{label}: refused, nothing started", wants in msg and "Nothing started" in msg, msg)
        check("a missing binary: refused", "cannot run" in refused(gateway.check_version, os.path.join(tmp, "absent")))
        check("a hung --version: refused at the bound", "did not answer within" in refused(
            gateway.check_version, script("hang", "import time\ntime.sleep(30)"), 1))

        print("READY")
        digest = "sha256:" + "a" * 64
        good = {"event": "ready", "gateway_version": "1", "runtime_contract": 1, "plan_schema": 0,
                "listener": "http://127.0.0.1:54321", "plan_digest": digest}

        def parse_raises(**over) -> str:
            try:
                gateway._parse_ready((json.dumps({**good, **over}) + "\n").encode(), digest)
            except gateway._Refuse as e:
                return str(e)
            return ""
        check("a good READY parses", parse_raises() == "")
        for label, over, wants in (("an unsupported contract", {"runtime_contract": 2}, "runtime contract 2"),
                                   ("a plan schema other than 0", {"plan_schema": 1}, "plan schema 1"),
                                   ("a bool for the contract", {"runtime_contract": True}, "runtime contract True"),
                                   ("a float for the contract", {"runtime_contract": 1.0}, "runtime contract 1.0"),
                                   ("a bool for the schema", {"plan_schema": False}, "plan schema False"),
                                   ("a float for the schema", {"plan_schema": 0.0}, "plan schema 0.0"),
                                   ("a public listener", {"listener": "http://0.0.0.0:54321"}, "not loopback"),
                                   ("an https listener", {"listener": "https://127.0.0.1:54321"}, "not loopback"),
                                   ("a listener port above 65535", {"listener": "http://127.0.0.1:99999"}, "not loopback"),
                                   ("a listener with a path", {"listener": "http://127.0.0.1:54321/x"}, "not loopback"),
                                   ("a digest of another plan", {"plan_digest": "sha256:" + "b" * 64}, "not the sha256"),
                                   ("a malformed digest", {"plan_digest": "nope"}, "no plan digest"),
                                   ("another event", {"event": "starting"}, "not a READY record")):
            check(f"{label}: refused", wants in parse_raises(**over), parse_raises(**over))
        try:
            gateway._parse_ready(b"not json\n", digest)
            got = ""
        except gateway._Refuse as e:
            got = str(e)
        check("a first line that is not JSON: refused", "not a READY record" in got, got)

        print("the harness's environment, the state record")
        class Fake:
            pid, listener, plan_digest, version, runtime_contract, key = 4242, "http://127.0.0.1:1", digest, "1", 1, "k" * 64
            started_at = "2026-10-10T00:00:00Z"
        env = {"CLAUDE_CODE_OAUTH_TOKEN": "t", "ANTHROPIC_AUTH_TOKEN": "t", "ANTHROPIC_API_KEY": "old", "OPENROUTER_API_KEY": "o",
               "ANTHROPIC_CUSTOM_HEADERS": "h", "ANTHROPIC_MODEL": "m", "PATH": "/bin", "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-x"}
        gateway.harness_env(Fake, env)
        check("the base URL and the local key are set; every upstream credential and broker variable is gone",
              env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:1" and env["ANTHROPIC_API_KEY"] == "k" * 64
              and not any(k in env for k in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN", "OPENROUTER_API_KEY",
                                              "ANTHROPIC_CUSTOM_HEADERS", "ANTHROPIC_MODEL")), env)
        check("…and what is not a credential is left", env["PATH"] == "/bin" and env["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "claude-x", env)
        state = os.path.join(tmp, "state")
        gateway.record_state(state, Fake)
        rec = open(os.path.join(state, "gateway.json")).read()
        check("the record holds pid, version, listener, plan digest, started_at and not the key",
              json.loads(rec) == {"pid": 4242, "gateway_version": "1", "runtime_contract": 1, "listener": "http://127.0.0.1:1",
                                  "plan_digest": digest, "started_at": "2026-10-10T00:00:00Z"} and "k" * 8 not in rec, rec)
        gateway.forget_state(state, 1)
        check("a record another gateway wrote over this login's is left alone", os.path.exists(os.path.join(state, "gateway.json")))
        gateway.forget_state(state, 4242)
        check("forgotten at the end, when it is this gateway's", not os.path.exists(os.path.join(state, "gateway.json")))
        gateway.forget_state(state, 4242)
        check("forgetting what is not there is not an error", True)
        env3 = {"ANTHROPIC_BASE_URL": Fake.listener, "ANTHROPIC_API_KEY": Fake.key}
        gateway.clear_harness_env(Fake, env3)
        check("after the session this launcher's listener and key leave its environment", env3 == {}, env3)
        env4 = {"ANTHROPIC_BASE_URL": "http://elsewhere", "ANTHROPIC_API_KEY": "another"}
        gateway.clear_harness_env(Fake, env4)
        check("…and a value that is not ours stays", env4 == {"ANTHROPIC_BASE_URL": "http://elsewhere", "ANTHROPIC_API_KEY": "another"})
        try:
            gateway.plan_digest(os.path.join(tmp, "no-plan"))
            got = ""
        except Refused as e:
            got = str(e)
        check("a plan that cannot be read: refused, nothing started", "cannot be read" in got and "Nothing started" in got, got)
        env2 = {}
        os.environ.pop("AGENT_FABRIC_GATEWAY_READY_TIMEOUT_S", None)
        check("the READY wait defaults", gateway.ready_timeout(env2) == gateway.READY_TIMEOUT_S)
        check("…is overridable", gateway.ready_timeout({"AGENT_FABRIC_GW_READY_TIMEOUT_S": "7"}) == 7.0)
        check("…and a bad override falls back", gateway.ready_timeout({"AGENT_FABRIC_GW_READY_TIMEOUT_S": "-1"}) == gateway.READY_TIMEOUT_S)
        fab = os.path.join(tmp, "fabric")
        os.makedirs(os.path.join(fab, "runtime"))
        with open(os.path.join(fab, "runtime", "gateway.json"), "w") as fh:
            json.dump({"releases": {"9.9.9": {"x86_64": {"member": "dir-9.9.9/gw-bin"}}}}, fh)
        check("the executable's name is the pin's: the basename of a release's member", gateway.pinned_name(fab) == "gw-bin")
        os.makedirs(os.path.join(tmp, "home", ".local", "bin"))
        installed = script("home/.local/bin/gw-bin", "pass")
        elsewhere = os.path.join(tmp, "path")
        os.makedirs(elsewhere)
        on_path = script("path/gw-bin", "pass")
        check("AGENT_FABRIC_GW_BIN wins; else ~/.local/bin, where the install action puts it; else PATH",
              gateway.binary_path({"AGENT_FABRIC_GW_BIN": "/x/gw", "HOME": os.path.join(tmp, "home")}, fab) == "/x/gw"
              and gateway.binary_path({"HOME": os.path.join(tmp, "home"), "PATH": elsewhere}, fab) == installed
              and gateway.binary_path({"HOME": os.path.join(tmp, "nohome"), "PATH": elsewhere}, fab) == on_path,
              (installed, on_path))
        check("not installed anywhere: refused, nothing started",
              "gw-bin is not installed" in refused(gateway.binary_path, {"HOME": os.path.join(tmp, "nohome"), "PATH": "/nonexistent"}, fab))
        with open(os.path.join(fab, "runtime", "gateway.json"), "w") as fh:
            fh.write("{")
        check("a pin that names no executable: refused", "names no gateway executable" in refused(gateway.pinned_name, fab))

    print("the parent guard")
    with tempfile.TemporaryDirectory(prefix="test_launcher_gateway.") as tmp:
        fake = os.path.join(tmp, "gw")
        with open(fake, "w") as fh:
            fh.write("#!/usr/bin/env python3\nimport os, sys\nopen(sys.argv[sys.argv.index('--plan') + 1] + '.ran', 'w').close()\n")
        os.chmod(fake, 0o755)
        plan = os.path.join(tmp, "plan.json")
        with open(plan, "w") as fh:
            fh.write("{}\n")
        why = refused(gateway.start, fake, plan, os.path.join(tmp, "log"), {"gateway_version": "1"}, ready_timeout=5,
                      launcher_pid=os.getpid() + 1)
        check("a parent that is not the recorded launcher: the child exits before exec (127), the gateway never runs",
              "stopped before READY" in why and "exit 127" in why and not os.path.exists(plan + ".ran"), why)
        why = refused(gateway.start, fake, plan, os.path.join(tmp, "log"), {"gateway_version": "1"}, ready_timeout=5)
        check("the recorded parent: the gateway runs (here it exits without READY, which is its own refusal)",
              os.path.exists(plan + ".ran") and "stopped before READY" in why and "exit 127" not in why, why)

    print("approving the gateway-local key for the harness")
    with tempfile.TemporaryDirectory(prefix="test_launcher_gateway.") as tmp:
        path = os.path.join(tmp, ".claude.json")
        key = "0123456789abcdef" * 4
        gateway.approve_key(path, key)
        d = json.load(open(path))
        check("a new file: the last 20 characters approved, onboarding done, mode 0600",
              d == {"customApiKeyResponses": {"approved": [key[-20:]], "rejected": []}, "hasCompletedOnboarding": True}
              and (os.stat(path).st_mode & 0o777) == 0o600, d)
        with open(path, "w") as fh:
            json.dump({"theme": "dark", "projects": {"/x": {"a": 1}},
                       "customApiKeyResponses": {"approved": ["old1", "old2", 7], "rejected": [key[-20:], "keep"], "other": 1}}, fh)
        gateway.approve_key(path, key)
        d = json.load(open(path))
        check("an existing file: its other keys and approvals kept, the key's tail added, a rejection of it removed",
              d["theme"] == "dark" and d["projects"] == {"/x": {"a": 1}} and d["customApiKeyResponses"]["approved"] == ["old1", "old2", key[-20:]]
              and d["customApiKeyResponses"]["rejected"] == ["keep"] and d["customApiKeyResponses"]["other"] == 1, d)
        gateway.approve_key(path, key)
        check("approving it again adds no second entry", json.load(open(path))["customApiKeyResponses"]["approved"].count(key[-20:]) == 1)
        with open(path, "w") as fh:
            json.dump({"customApiKeyResponses": {"approved": [f"k{i}" for i in range(150)]}}, fh)
        gateway.approve_key(path, key)
        got = json.load(open(path))["customApiKeyResponses"]["approved"]
        check("the list is bounded: the latest entries kept, the new one last", len(got) == gateway.APPROVED_KEEP and got[-1] == key[-20:] and got[0] == "k51", (len(got), got[:2]))
        for label, content in (("not JSON", "{"), ("a JSON array", "[]")):
            with open(path, "w") as fh:
                fh.write(content)
            try:
                gateway.approve_key(path, key)
                why = ""
            except gateway._Refuse as e:
                why = str(e)
            check(f"{label}: refused, the file left as it was", "could not approve" in why and open(path).read() == content, why)

    print("a gateway session resumes through the gateway")
    with tempfile.TemporaryDirectory(prefix="test_launcher_gateway.") as tmp:
        def record(doc) -> str:
            path = os.path.join(tmp, "launch-provider.json")
            with open(path, "w") as fh:
                fh.write(doc if isinstance(doc, str) else json.dumps(doc))
            return path
        check("a record with transport gateway: gateway", resume.last_launch_transport(record({"provider": "anthropic", "transport": "gateway"})) == "gateway")
        check("a record without a transport: none", resume.last_launch_transport(record({"provider": "anthropic"})) == "")
        check("a transport it does not know: none", resume.last_launch_transport(record({"provider": "anthropic", "transport": "x"})) == "")
        check("an unreadable or non-object record: none", resume.last_launch_transport(record("{")) == "" and resume.last_launch_transport(record("[]")) == ""
              and resume.last_launch_transport(os.path.join(tmp, "absent")) == "")
        saved = (resume.last_launch_transport, resume.install_agent_files.last_launch_provider)
        try:
            resume.last_launch_transport = lambda record=None: "gateway"
            resume.install_agent_files.last_launch_provider = lambda: "anthropic"
            check("fabric-resume launches --provider gateway after a gateway session", resume.provider_args([]) == ["--provider", "gateway"], resume.provider_args([]))
            check("…unless the caller names a provider", resume.provider_args(["--provider", "openrouter"]) == [])
            resume.install_agent_files.last_launch_provider = lambda: "openrouter"
            check("…and a gateway record beside an openrouter provider is not read as the gateway", resume.provider_args([]) == ["--provider", "openrouter"])
        finally:
            resume.last_launch_transport, resume.install_agent_files.last_launch_provider = saved
        prof = os.path.join(tmp, "profiles.json")
        with open(prof, "w") as fh:
            json.dump({"agents": {"alice": {"launch_provider": "gateway"}}, "roles": {"r": {"launch_provider": "openrouter"}},
                       "defaults": {"launch_provider": "anthropic"}}, fh)
        os.environ["AGENT_FABRIC_RESUME_PROFILES"] = prof
        try:
            check("a profile's launch_provider of gateway is taken for the agent that names it",
                  resume.profile_provider("alice", "r") == "gateway" and resume.profile_provider("bob", "r") == "openrouter", (
                      resume.profile_provider("alice", "r"), resume.profile_provider("bob", "r")))
        finally:
            del os.environ["AGENT_FABRIC_RESUME_PROFILES"]

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
