#!/usr/bin/env python3
"""bin/gzcoord-compose: a message skeleton with its header filled, its id
minted and the whole validated before it is written; never sent.

Run through the real command, reached by a link as bootstrap links it, in
a minimal environment: a scratch state directory whose binding names the
role and project, a scratch git repository for origin, no relay. What is
proved: each type's sections (the tool's convention) and that each, filled,
passes `gzmsg validate`; toward a role, REQUEST: is left out and a REQUEST
is refused with the validator's reason; retired and unknown types and a
bad address are refused (exit 2); a line break in a value is a usage error
(exit 1) and writes nothing; -o creates a 0600 file and never replaces or
follows one; REPOSITORY is origin's <org>/<repo>, given, or left out with
the reason; an unknown ROLE is refused, never guessed. Plain script: prints
ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import pwd
import re
import stat
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
from gzcoord import gzmsg  # noqa: E402

BIN = os.path.join(ROOT, "bin", "gzcoord-compose")
RUN_PY = os.path.join(ROOT, "tools", "fabric", "gzcoord", "run.py")
ME = pwd.getpwuid(os.geteuid()).pw_name
EN = gzmsg.en()
TABLE = {
    "INFO": ["CONTEXT", "NOTES"],
    "OBSERVATION": ["OBSERVATION", "VERIFIED", "NOT-VERIFIED", "IMPACT", "REQUEST"],
    "QUESTION": ["CONTEXT", "QUESTION"],
    "REQUEST": ["REQUEST", "ACCEPTANCE", "DELIVER-TO"],
    "REVIEW": ["CONTEXT", "REQUEST", "IMPACT"],
    "DECISION": ["DECISION", "RATIONALE"],
    "HANDOFF": ["CONTEXT", "REQUEST"],
    "REPLY": ["REPLY"],
    "X-PING": [],
}
SECTION = re.compile(r"^([A-Z][A-Z0-9-]*):$")


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with tempfile.TemporaryDirectory() as sandbox:
        home, state, repo, bindir = (os.path.join(sandbox, n) for n in ("home", "state", "repo", "bin"))
        for d in (home, os.path.join(state, "agents", ME), repo, bindir):
            os.makedirs(d)
        with open(os.path.join(state, "agents", ME, "binding.json"), "w", encoding="utf-8") as fh:
            json.dump({"role": "python-dev", "project": "agent-fabric"}, fh)
        link = os.path.join(bindir, "gzcoord-compose")
        os.symlink(BIN, link)
        env = {"PATH": "/usr/bin:/bin", "HOME": home, "LANG": "C.UTF-8", "GIT_CONFIG_NOSYSTEM": "1",
               "AGENT_FABRIC_ROOT": ROOT, "AGENT_FABRIC_STATE_DIR": state,
               "AGENT_FABRIC_PYTHON": sys.executable}

        def git(*a: str) -> None:
            subprocess.run(["git", "-C", repo, *a], env=env, check=True, capture_output=True, timeout=30)

        git("init", "-q")

        def compose(*argv: str | bytes, cwd: str = repo, run_env: dict | None = None) -> tuple[int, str, str]:
            r = subprocess.run([link, *argv], cwd=cwd, env=run_env or env, capture_output=True,
                               timeout=60, stdin=subprocess.DEVNULL)
            return r.returncode, r.stdout.decode("utf-8", "surrogateescape"), r.stderr.decode("utf-8", "surrogateescape")

        def sections(text: str) -> list[str]:
            return [m.group(1) for m in map(SECTION.match, text.split("\n")[1:]) if m]

        def header(text: str) -> dict[str, str]:
            return gzmsg.parse(text)["metadata"]

        def validate(text: str) -> tuple[int, str]:
            path = os.path.join(sandbox, "filled.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            r = subprocess.run([sys.executable, "-I", RUN_PY, "gzmsg", "validate", path], env=env,
                               capture_output=True, text=True, timeout=60)
            os.unlink(path)
            return r.returncode, r.stdout + r.stderr

        def filled(text: str) -> str:
            return "\n".join(line + "\nx" if SECTION.match(line) and i else line
                             for i, line in enumerate(text.split("\n")))

        print("each type: its sections, then REFERENCES:; filled, it validates")
        git("remote", "add", "origin", "https://github.com/acme-org/widgets.git")
        for mtype, names in TABLE.items():
            rc, out, err = compose(mtype, "--to", "develop-qzapp/user", "--subject", f"a {mtype}")
            check(f"{mtype}: composes", rc == 0 and out.startswith(f"[GZCOORD/1] {mtype}\n"), f"rc={rc}\n{err}")
            check(f"{mtype}: sections {' '.join(names + ['REFERENCES'])}", sections(out) == names + ["REFERENCES"],
                  out)
            vrc, vout = validate(filled(out))
            check(f"{mtype}: filled, gzmsg validate accepts it", vrc == 0, vout)

        print("the header")
        rc, out, err = compose("REPLY", "--to", "develop-qzapp/user", "--subject", "the subject",
                               "--in-reply-to", "01a114e1-1e0f-7aa3-8d0c-57b519a35533", "--reply-expected", "no")
        h = header(out)
        check("FROM is this login's address", h.get("FROM", "").endswith("/" + ME), json.dumps(h))
        check("ROLE and PROJECT are the binding's", h.get("ROLE") == "python-dev" and h.get("PROJECT") == "agent-fabric",
              json.dumps(h))
        check("REPOSITORY is origin's <org>/<repo>", h.get("REPOSITORY") == "acme-org/widgets", json.dumps(h))
        check("TO, IN-REPLY-TO, REPLY-EXPECTED and SUBJECT as given",
              h.get("TO") == "develop-qzapp/user" and h.get("IN-REPLY-TO") == "01a114e1-1e0f-7aa3-8d0c-57b519a35533"
              and h.get("REPLY-EXPECTED") == "no" and h.get("SUBJECT") == "the subject", json.dumps(h))
        check("MESSAGE-ID is minted, id-shaped", gzmsg.id_complaint("MESSAGE-ID", h.get("MESSAGE-ID", "")) is None
              and bool(h.get("MESSAGE-ID")), json.dumps(h))
        _, again, _ = compose("REPLY", "--to", "develop-qzapp/user", "--subject", "the subject")
        check("…and a new one each time", header(again).get("MESSAGE-ID") != h.get("MESSAGE-ID"))
        check("nothing on stderr for a clean compose", err == "", err)
        _, out, _ = compose("INFO", "--broadcast", "--subject", "s")
        check("--broadcast is BROADCAST: true", header(out).get("BROADCAST") == "true", out)

        print("toward a role")
        for mtype in ("OBSERVATION", "REVIEW", "HANDOFF"):
            rc, out, err = compose(mtype, "--to-role", "python-dev", "--subject", "s")
            want = [n for n in TABLE[mtype] if n != "REQUEST"] + ["REFERENCES"]
            check(f"{mtype}: REQUEST: left out, and it validates filled",
                  rc == 0 and sections(out) == want and validate(filled(out))[0] == 0, f"rc={rc}\n{out}{err}")
        rc, out, err = compose("REQUEST", "--to-role", "python-dev", "--subject", "s")
        reason = EN("validate.request-to-role")
        check("a REQUEST toward a role: exit 2, the validator's reason, nothing on stdout",
              rc == 2 and reason in err and out == "", f"rc={rc}\nout={out}\nerr={err}\nwant={reason}")

        print("refused: the message would be invalid (exit 2)")
        for argv, key, args in ((["HELLO", "--broadcast"], "validate.retired-type", {"type": "HELLO"}),
                                (["GOODBYE", "--broadcast"], "validate.retired-type", {"type": "GOODBYE"}),
                                (["NOTICE", "--broadcast"], "validate.unknown-type", {"type": "NOTICE"}),
                                (["INFO", "--to", "no-slash"], "validate.to-shape", {}),
                                (["INFO", "--broadcast", "--reply-expected", "maybe"], "validate.reply-expected", {})):
            rc, out, err = compose(*argv, "--subject", "s")
            check(f"{' '.join(argv)}: exit 2 with the validator's reason", rc == 2 and EN(key, args) in err
                  and out == "", f"rc={rc}\nerr={err}")

        print("usage (exit 1), nothing written")
        for label, argv in (("a line break in --subject", ["INFO", "--broadcast", "--subject", "s\nFROM: x/y"]),
                            ("a carriage return in --in-reply-to", ["INFO", "--broadcast", "--subject", "s",
                                                                   "--in-reply-to", "a\rTO: x/y"]),
                            ("a line separator in TYPE", ["INFO\u2028FROM: x/y", "--broadcast", "--subject", "s"]),
                            ("no addressing", ["INFO", "--subject", "s"]),
                            ("two addressings", ["INFO", "--to", "a/b", "--broadcast", "--subject", "s"]),
                            ("no --subject", ["INFO", "--broadcast"]),
                            ("an empty --subject", ["INFO", "--broadcast", "--subject", " "]),
                            ("a --subject of nothing but U+FEFF", ["INFO", "--broadcast", "--subject", "\ufeff"]),
                            ("bytes that are not UTF-8 in --subject", ["INFO", "--broadcast", "--subject", b"caf\xe9"]),
                            ("--to given twice", ["INFO", "--to", "a/b", "--to", "c/d", "--subject", "s"]),
                            ("--subject given twice", ["INFO", "--broadcast", "--subject", "s", "--subject", "t"]),
                            ("an abbreviated option", ["INFO", "--broadcast", "--subj", "s"])):
            rc, out, err = compose(*argv)
            check(f"{label}: exit 1, stdout empty", rc == 1 and out == "" and "usage:" in err, f"rc={rc}\n{out}{err}")
        for value in ("junk", "$ID"):
            rc, out, err = compose("INFO", "--broadcast", "--subject", "s", "--in-reply-to", value)
            check(f"--in-reply-to {value}: exit 2, as send refuses it, said once",
                  rc == 2 and out == "" and err.count(gzmsg.id_complaint("IN-REPLY-TO", value, EN)) == 1,
                  f"rc={rc}\nerr={err}")
        rc, out, _ = compose("--help")
        check("--help: exit 0, the table, said to be the tool's convention",
              rc == 0 and "OBSERVATION: VERIFIED: NOT-VERIFIED: IMPACT: REQUEST:" in out
              and "not a" in out and "protocol rule" in out, out)

        print("-o FILE")
        target = os.path.join(sandbox, "msg.txt")
        rc, out, err = compose("INFO", "--broadcast", "--subject", "s", "-o", target)
        mode = stat.S_IMODE(os.stat(target).st_mode) if os.path.exists(target) else None
        check("written, mode 0600, stdout empty, stderr names it",
              rc == 0 and mode == 0o600 and out == "" and target in err, f"rc={rc} mode={mode}\n{err}")
        with open(target, encoding="utf-8") as fh:
            first = fh.read()
        rc, _, err = compose("INFO", "--broadcast", "--subject", "s", "-o", target)
        with open(target, encoding="utf-8") as fh:
            check("an existing file is refused (exit 1) and left as it was", rc == 1 and fh.read() == first, err)
        victim = os.path.join(sandbox, "victim")
        with open(victim, "w", encoding="utf-8") as fh:
            fh.write("keep\n")
        os.symlink(victim, os.path.join(sandbox, "via-link"))
        rc, _, err = compose("INFO", "--broadcast", "--subject", "s", "-o", os.path.join(sandbox, "via-link"))
        with open(victim, encoding="utf-8") as fh:
            check("a link there is refused, its target untouched", rc == 1 and fh.read() == "keep\n", err)
        dangling = os.path.join(sandbox, "dangling")
        os.symlink(os.path.join(sandbox, "made-through-link"), dangling)
        rc, _, err = compose("INFO", "--broadcast", "--subject", "s", "-o", dangling)
        check("a dangling link is refused, its target never created",
              rc == 1 and not os.path.exists(os.path.join(sandbox, "made-through-link")), err)
        rc, _, err = compose("REQUEST", "--to-role", "python-dev", "--subject", "s",
                             "-o", os.path.join(sandbox, "refused.txt"))
        check("an invalid message writes no file", rc == 2 and not os.path.exists(os.path.join(sandbox, "refused.txt")),
              err)

        print("REPOSITORY")
        for url in ("git@github.com:acme-org/widgets.git", "ssh://git@github.com/acme-org/widgets",
                    "https://github.com/acme-org/widgets/"):
            git("remote", "set-url", "origin", url)
            _, out, _ = compose("INFO", "--broadcast", "--subject", "s")
            check(f"from {url}", header(out).get("REPOSITORY") == "acme-org/widgets", out)
        _, out, _ = compose("INFO", "--broadcast", "--subject", "s", "--repository", "other-org/thing")
        check("--repository wins over origin", header(out).get("REPOSITORY") == "other-org/thing", out)
        git("remote", "set-url", "origin", "https://x-access-token:s3cr3t-t0ken@gitlab.example/group/sub/widgets.git")
        rc, out, err = compose("INFO", "--broadcast", "--subject", "s")
        check("a URL that is not <org>/<repo>: left out, its user part never printed",
              rc == 0 and "REPOSITORY" not in header(out) and "s3cr3t-t0ken" not in err
              and "x-access-token" not in err and "origin's URL is not <host>/<org>/<repo>" in err, f"rc={rc}\n{err}")
        # Never echoed at all: an scp-style user part and a query-string token
        # are credentials no redaction pattern named (review of #107).
        for url in ("HTTPS://u:s3cr3t-t0ken@gitlab.example/g/s/r.git", "git+https://u:s3cr3t-t0ken@host.example/g/s/r",
                    "s3cr3t-t0ken@gitlab.example:group/sub/repo.git", "https://gitlab.example/g/s/r.git?private_token=s3cr3t-t0ken"):
            git("remote", "set-url", "origin", url)
            rc, out, err = compose("INFO", "--broadcast", "--subject", "s")
            check(f"{url.split(':')[0]}: the user part never printed",
                  rc == 0 and "s3cr3t-t0ken" not in err and "REPOSITORY left out" in err, f"rc={rc}\n{err}")
        other = os.path.join(sandbox, "other")
        subprocess.run(["git", "init", "-q", other], env=env, check=True, capture_output=True, timeout=30)
        subprocess.run(["git", "-C", other, "remote", "add", "origin", "https://github.com/wrong-org/wrong.git"],
                       env=env, check=True, capture_output=True, timeout=30)
        git("remote", "set-url", "origin", "https://github.com/acme-org/widgets.git")
        _, out, _ = compose("INFO", "--broadcast", "--subject", "s",
                            run_env={**env, "GIT_DIR": os.path.join(other, ".git")})
        check("origin is the working copy's, not a GIT_DIR the session set",
              header(out).get("REPOSITORY") == "acme-org/widgets", out)
        git("remote", "set-url", "origin", "/srv/git/widgets.git")
        rc, out, err = compose("INFO", "--broadcast", "--subject", "s")
        check("a local path: left out, stderr says why, still composed",
              rc == 0 and "REPOSITORY" not in header(out) and "REPOSITORY left out" in err
              and "/srv/git/widgets.git" not in err and "git remote get-url origin" in err, f"rc={rc}\n{err}")
        git("remote", "remove", "origin")
        rc, out, err = compose("INFO", "--broadcast", "--subject", "s")
        check("no origin: left out, stderr says why", rc == 0 and "REPOSITORY" not in header(out)
              and "REPOSITORY left out" in err, f"rc={rc}\n{err}")
        rc, out, err = compose("INFO", "--broadcast", "--subject", "s", cwd=home)
        check("not a repository: left out, stderr says why", rc == 0 and "REPOSITORY" not in header(out)
              and "REPOSITORY left out" in err, f"rc={rc}\n{err}")

        print("an unknown ROLE is refused, never guessed")
        # A root with a catalogue this login carries no slug of and no
        # identity.py: whoami is the login plus a binding with no role.
        bare = os.path.join(sandbox, "bare-root")
        os.makedirs(os.path.join(bare, "identities", "roles"))
        with open(os.path.join(bare, "identities", "roles", "catalog.json"), "w", encoding="utf-8") as fh:
            json.dump({"roles": [{"id": "zz-only-role", "title": "Only"}]}, fh)
        bare_state = os.path.join(sandbox, "bare-state")
        os.makedirs(os.path.join(bare_state, "agents", ME))
        with open(os.path.join(bare_state, "agents", ME, "binding.json"), "w", encoding="utf-8") as fh:
            json.dump({"project": "agent-fabric"}, fh)
        rc, out, err = compose("INFO", "--broadcast", "--subject", "s",
                               run_env={**env, "AGENT_FABRIC_ROOT": bare, "AGENT_FABRIC_STATE_DIR": bare_state})
        check("exit 2, the validator's missing-ROLE reason, nothing on stdout",
              rc == 2 and EN("validate.missing", {"key": "ROLE"}) in err and out == "", f"rc={rc}\n{out}{err}")

    print(f"\ntest_gzcoord_compose: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
