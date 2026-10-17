#!/usr/bin/env python3
"""fabric-secrets child roles-put (ADR-060 §5 rule 3): the parent installs a holder's addenda into
the child's store, from its mirror, in one commit it signs, and nothing is committed when a file is refused.

Parent and child are two scratch homes with their own keyrings (outside their HOME, see test_secret_store), a
bare remote and a scratch fabric tree holding the lineage. The install is called in-process with the parent's
environment and a stand-in for addenda_check.validate, so the cases do not move when the validator's rules do
(its own suite is its); one case runs the real command line and the real validator. Plain script: ok/FAIL,
exit 1 on any."""
from __future__ import annotations

import contextlib
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FABRIC = os.path.join(ROOT, "tools", "fabric")
STORE_TOOL = os.path.join(FABRIC, "secret_store.py")
CHILD_TOOL = os.path.join(FABRIC, "secret_child.py")
sys.path.insert(0, FABRIC)
import addenda_check  # noqa: E402
import secret_child  # noqa: E402
import secret_store  # noqa: E402
from secretstore import trust  # noqa: E402
from git_env import scrub_process_env  # noqa: E402 — tests/, the script's own directory
from instance_fixtures import write_secrets_instance  # noqa: E402
scrub_process_env()

ROLE = "legal-expert"
REVIEW = "legal-expert-ee pass-1 " + "a" * 64
REVIEW2 = "language-culture-ge pass-2 " + "b" * 64


def main() -> int:
    real_validate = addenda_check.validate   # before a case swaps it for its stand-in
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail[:500]}"))
        fails += not good

    with tempfile.TemporaryDirectory() as tmp:
        fabric = os.path.join(tmp, "fabric")
        os.makedirs(os.path.join(fabric, "identities", "keys"))
        write_secrets_instance(fabric)

        def role(name: str) -> dict:
            h, g = os.path.join(tmp, name), os.path.join(tmp, f"{name}-gnupg")   # a keyring never at $HOME/.gnupg
            os.makedirs(h)
            os.makedirs(g, mode=0o700)
            return {**{k: v for k, v in os.environ.items() if k != "CLAUDECODE" and not k.startswith("GIT_")},
                    "HOME": h, "GNUPGHOME": g, "AGENT_FABRIC_ROOT": fabric, "AGENT_FABRIC_OPERATOR": fabric,
                    "AGENT_FABRIC_SECRET_STORE": os.path.join(h, "store"),
                    "GIT_CONFIG_GLOBAL": os.path.join(h, ".gitconfig"), "GIT_CONFIG_NOSYSTEM": "1"}

        fixture, parent, child = role("fixture"), role("parent"), role("child")
        fab_git = ["git", "-C", fabric, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
        subprocess.run(["git", "init", "-q", "-b", "main", fabric], check=True, env=fixture)

        def publish() -> None:
            subprocess.run(fab_git + ["add", "-A"], check=True, env=fixture)
            subprocess.run(fab_git + ["commit", "-q", "--allow-empty", "-m", "identities"], check=True, env=fixture)
            subprocess.run(fab_git + ["update-ref", "refs/remotes/origin/main", "HEAD"], check=True, env=fixture)
        remote = os.path.join(tmp, "child-remote.git")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", remote], check=True, env=fixture)

        def tool(env: dict, *args: str) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, STORE_TOOL, *args], env=env, cwd=tmp, capture_output=True, text=True)

        def git(env: dict, repo: str, *args: str) -> str:
            return subprocess.run(["git", "-C", repo, *args], env=env, capture_output=True, text=True, check=True).stdout

        PID = secret_store.mint_agent_id(secret_store.born_ms_of("2026-01-14 21:27:33.247294044 +0100"))
        KID = secret_store.mint_agent_id(secret_store.born_ms_of("now"))
        mirror = os.path.join(parent["HOME"], ".local", "share", "agent-fabric", "children", KID)
        seen: list[tuple] = []

        def fake_validate(role_: str, aid: str, name: str, raw: bytes) -> list[str]:
            seen.append((role_, aid, name, raw))
            return [f"{name} is not allowed here"] if name.startswith("bad") else []

        def fake_validate_set(role_: str, aid: str, files: dict) -> dict:
            return {n: fake_validate(role_, aid, n, raw) for n, raw in files.items()}

        def call(env: dict, *args: str, validate=None) -> tuple[int, str, str]:
            """With no `validate` both the per-file check and the set check are stand-ins, so the cases do not move
            when the validator's rules do; a real `validate` brings the real set rules (they call it)."""
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(addenda_check, "validate", validate or fake_validate), \
                    mock.patch.object(addenda_check, "validate_set", fake_validate_set, create=True) if validate is None \
                    else contextlib.nullcontext(), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = secret_child.main(list(args))
            return rc, out.getvalue(), err.getvalue()

        def addendum(kind: str, digest: str, role_: str = ROLE) -> bytes:
            return (f"---\nclass: {kind}\nrole: {role_}\nagent_id: {KID}\nlang: en\nagainst_digest: {digest}\n---\n"
                    f"# {kind}\nSpecialises {role_} for its holder.\n").encode()

        made = []

        def src(name: str, files: dict[str, bytes]) -> str:
            made.append(name)
            d = os.path.join(tmp, f"src-{len(made)}-{name}")
            os.makedirs(d)
            for n, data in files.items():
                with open(os.path.join(d, n), "wb") as fh:
                    fh.write(data)
            return d

        def install(label: str, name: str, files: dict[str, bytes], *extra: str, env: dict = parent, validate=None):
            return call(env, "roles-put", "--agent", "kid", "--role", ROLE, "--from", src(name, files),
                        "--approval", "ADR-060-2026-10-17", *extra, validate=validate)

        def count() -> int:
            return int(git(parent, mirror, "rev-list", "--count", "HEAD").strip())

        def remote_head() -> str:
            return subprocess.run(["git", "--git-dir", remote, "rev-parse", "main"], env=parent, capture_output=True,
                                  text=True, check=True).stdout.strip()

        try:
            check("the parent makes its key and is the root", tool(parent, "init", "--agent-id", PID).returncode == 0
                  and tool(parent, "certify", "--root").returncode == 0)
            publish()
            check("the child makes its store", tool(child, "init", "--agent-id", KID, "--remote", remote).returncode == 0)
            child_store = child["AGENT_FABRIC_SECRET_STORE"]
            child_fpr = open(os.path.join(child_store, ".gpg-id")).read().split()[0]
            git(child, child_store, "push", "-q", "origin", "HEAD:main")
            exported = os.path.join(tmp, "child.asc")
            with open(exported, "w") as fh:
                subprocess.run(["gpg", "--armor", "--export", child_fpr], env=child, check=True, stdout=fh)
            check("the parent certifies it", tool(parent, "certify", "kid", exported).returncode == 0)
            publish()
            parent_fpr = open(os.path.join(parent["AGENT_FABRIC_SECRET_STORE"], ".gpg-id")).read().split()[0]
            subprocess.run(["git", "clone", "-q", remote, mirror], check=True, env=parent)
            check("the mirror has its trusted base", tool(parent, "trust-base", "--store", mirror).returncode == 0)
            start = count()

            # ── a valid install ───────────────────────────────────────────
            charter, brief = addendum("charter-addendum", "dig-charter-1"), addendum("brief-addendum", "dig-brief-1")
            rc, out, err = install("valid", "v1", {"charter-addendum.md": charter, "brief-addendum.md": brief,
                                                   "holder.json": b'{"locale":"en"}'},
                                   "--reviewed-by", REVIEW, "--reviewed-by", REVIEW2, "--authored-by", "legal-expert-ee")
            check("a valid install is done and says the commit", rc == 0 and "3 file(s) committed as" in out and err == "", out + err)
            check("…each file was judged by the validator, with the role, the child's id, its name and its bytes",
                  sorted(s[:3] for s in seen) == sorted((ROLE, KID, n) for n in ("brief-addendum.md", "charter-addendum.md", "holder.json"))
                  and [s[3] for s in seen if s[2] == "charter-addendum.md"] == [charter], repr([s[:3] for s in seen]))
            check("…ONE commit, pushed: the remote holds the mirror's head", count() == start + 1
                  and remote_head() == git(parent, mirror, "rev-parse", "HEAD").strip())
            check("…with the three files below settings/roles/<role>/ and nothing else",
                  sorted(git(parent, mirror, "show", "--name-only", "--format=", "HEAD").split()) ==
                  [f"settings/roles/{ROLE}/{n}" for n in ("brief-addendum.md", "charter-addendum.md", "holder.json")])
            check("…signed by the parent's key (its primary, by a signing subkey)",
                  git(parent, mirror, "log", "-1", "--format=%G?|%GP").strip() == f"G|{parent_fpr}",
                  git(parent, mirror, "log", "-1", "--format=%G?|%GP"))
            trailers = git(parent, mirror, "log", "-1", "--format=%B").strip().split("\n\n", 1)[1].splitlines()
            check("…its trailers: role, author, each review pass, the approval, each addendum's digest, in that order",
                  trailers == [f"Addendum-Role: {ROLE}", "Authored-By: legal-expert-ee", f"Reviewed-By: {REVIEW}",
                               f"Reviewed-By: {REVIEW2}", "Owner-Approval: ADR-060-2026-10-17",
                               "Against-Digest: charter-addendum.md dig-charter-1", "Against-Digest: brief-addendum.md dig-brief-1"],
                  repr(trailers))
            parsed = subprocess.run(
                ["git", "-C", mirror, "interpret-trailers", "--parse"], input=git(parent, mirror, "log", "-1", "--format=%B"),
                env=parent, capture_output=True, text=True).stdout.strip().splitlines()
            check("…and git reads them as trailers", parsed == trailers, repr(parsed))
            rc, out, err = install("same", "v1b", {"charter-addendum.md": charter, "brief-addendum.md": brief,
                                                   "holder.json": b'{"locale":"en"}'})
            check("the same files again are unchanged: no commit", rc == 0 and "unchanged" in out and count() == start + 1, out + err)

            # ── a refused file: nothing committed, nothing left ───────────
            n0, head0, remote0 = count(), git(parent, mirror, "rev-parse", "HEAD"), remote_head()
            rc, out, err = install("bad", "bad1", {"charter-addendum.md": charter, "bad-extra.md": b"x"})
            check("a file the validator refuses refuses the whole install, naming it, before any commit",
                  rc == 1 and "nothing written" in err and "bad-extra.md is not allowed here" in err and "Traceback" not in err
                  and count() == n0 and git(parent, mirror, "rev-parse", "HEAD") == head0 and remote_head() == remote0
                  and git(parent, mirror, "status", "--porcelain", "--untracked-files=all") == "", out + err)
            check("…and the files of the install before it are still there",
                  os.path.isfile(os.path.join(mirror, "settings", "roles", ROLE, "brief-addendum.md")))
            nested = src("nested", {})
            os.makedirs(os.path.join(nested, "sub"))
            with open(os.path.join(nested, "sub", "x.md"), "w") as fh:
                fh.write("x")
            rc, out, err = call(parent, "roles-put", "--agent", "kid", "--role", ROLE, "--from", nested, "--approval", "A-1")
            check("a file in a subdirectory is refused (rule 1: no subdirectory)", rc == 1 and "directly in" in err
                  and count() == n0, out + err)
            rc, out, err = install("dot", "dot", {".hidden": b"x"})
            check("a name that starts with a dot is refused", rc == 1 and "nothing written" in err and count() == n0, out + err)

            # ── whole: what the directory lacks is removed ────────────────
            rc, out, err = install("whole", "w1", {"charter-addendum.md": addendum("charter-addendum", "dig-charter-2")})
            check("an install writes the role's directory whole: a file the directory lacks is removed",
                  rc == 0 and count() == n0 + 1 and os.listdir(os.path.join(mirror, "settings", "roles", ROLE)) == ["charter-addendum.md"]
                  and f"settings/roles/{ROLE}/brief-addendum.md" in git(parent, mirror, "show", "--name-only", "--format=", "HEAD"),
                  out + err + repr(os.listdir(os.path.join(mirror, "settings", "roles", ROLE))))
            check("…and its trailers carry the one digest left, with no review pass given",
                  "Reviewed-By" not in git(parent, mirror, "log", "-1", "--format=%B")
                  and "Against-Digest: charter-addendum.md dig-charter-2" in git(parent, mirror, "log", "-1", "--format=%B")
                  and "Authored-By: kid" in git(parent, mirror, "log", "-1", "--format=%B"))
            rc, out, err = call(parent, "roles-put", "--agent", "kid", "--role", "other-role", "--from",
                                src("o1", {"charter-addendum.md": addendum("charter-addendum", "dig-o", "other-role")}), "--approval", "A-2")
            rc2, out2, err2 = install("whole2", "w2", {"charter-addendum.md": addendum("charter-addendum", "dig-charter-3")})
            check("another role's directory is another install's: untouched by this role's",
                  rc == 0 and rc2 == 0 and os.path.isfile(os.path.join(mirror, "settings", "roles", "other-role", "charter-addendum.md")),
                  err + err2)

            # ── what the file must carry ──────────────────────────────────
            n1 = count()
            rc, out, err = install("nodigest", "nd", {"charter-addendum.md": b"---\nclass: charter-addendum\n---\nbody\n"})
            check("an addendum with no against_digest in its frontmatter is refused: nothing to record",
                  rc == 1 and "against_digest" in err and "nothing written" in err and count() == n1, out + err)
            rc, out, err = install("nofm", "nf", {"charter-addendum.md": b"no frontmatter\n"})
            check("…nor one with no frontmatter at all", rc == 1 and "frontmatter" in err and count() == n1, out + err)

            # ── arguments ─────────────────────────────────────────────────
            good = {"charter-addendum.md": addendum("charter-addendum", "dig-x")}
            for label, extra, needle in (("a review pass of the wrong shape", ("--reviewed-by", "x pass-1 abc"), "--reviewed-by"),
                                         ("a review pass with a newline", ("--reviewed-by", REVIEW + "\nOwner-Approval: forged"), "--reviewed-by"),
                                         ("an author that is not a login", ("--authored-by", "Not A Login"), "--authored-by")):
                rc, out, err = install(label, "args-" + label[:6], good, *extra)
                check(f"{label} is refused before anything is read", rc == 1 and needle in err and count() == n1, out + err)
            for approval in ("two words", "forged\nAddendum-Role: x", ""):
                rc, out, err = call(parent, "roles-put", "--agent", "kid", "--role", ROLE, "--from", src("ap", good),
                                    "--approval", approval)
                check(f"an approval of {approval!r} is refused", rc == 1 and "--approval" in err and count() == n1, out + err)
            rc, out, err = call(parent, "roles-put", "--agent", "kid", "--role", "Not/A Role", "--from", src("badrole", good), "--approval", "A-3")
            check("a role that is not a slug is refused", rc == 1 and "role slug" in err and count() == n1, out + err)
            with contextlib.redirect_stderr(io.StringIO()):
                try:
                    secret_child.main(["roles-put", "--agent", "kid"])
                    usage = 0
                except SystemExit as e:
                    usage = e.code
            check("missing options are a usage error (2)", usage == 2, repr(usage))

            # ── only the parent ───────────────────────────────────────────
            rc, out, err = install("child", "byc", good, env=child)
            check("the child itself cannot install its own addenda: the lineage names another parent",
                  rc == 1 and "only an agent's parent installs" in err and count() == n1, out + err)
            rc, out, err = call(parent, "roles-put", "--agent", "nobody", "--role", ROLE, "--from", src("nob", good), "--approval", "A-4")
            check("an agent the lineage does not know is refused", rc == 1 and "nobody" in err and "Traceback" not in err, out + err)

            # ── the mirror ────────────────────────────────────────────────
            with open(os.path.join(mirror, "README"), "w") as fh:
                fh.write("x")
            git(parent, mirror, "add", "README")
            rc, out, err = install("dirty", "dirty", good)
            check("a mirror with an uncommitted change is refused", rc == 1 and "uncommitted" in err and count() == n1, out + err)
            git(parent, mirror, "reset", "-q", "--hard", "HEAD")

            # The remote moves on: the child pushes another commit from a second clone.
            other = os.path.join(tmp, "child-clone")
            subprocess.run(["git", "clone", "-q", remote, other], check=True, env=child)
            git(child, other, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                "commit", "-q", "--allow-empty", "-m", "the child moved on")
            git(child, other, "push", "-q", "origin", "HEAD:main")
            remote1 = remote_head()
            rc, out, err = install("behind", "behind", good)
            check("a mirror behind its remote is refused, saying how to bring it up, and nothing is pushed",
                  rc == 1 and "behind its remote" in err and "refresh-mirror" in err and "nothing written" in err
                  and count() == n1 and remote_head() == remote1 and git(parent, mirror, "status", "--porcelain") == "", out + err)
            git(parent, mirror, "fetch", "-q", "origin")
            git(parent, mirror, "merge", "-q", "--ff-only", "origin/main")
            rc, out, err = install("caught", "caught", good)
            check("…the same install on a mirror that caught up is done (the positive control of the refusal)",
                  rc == 0 and "committed as" in out and remote_head() == git(parent, mirror, "rev-parse", "HEAD").strip(), out + err)

            git(parent, mirror, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                "commit", "-q", "--allow-empty", "-m", "a commit of the parent's, not pushed")
            rc, out, err = install("ahead", "ahead", {"charter-addendum.md": addendum("charter-addendum", "dig-ahead")})
            check("a mirror ahead of its remote is refused too, with advice that works on a mirror that is ahead",
                  rc == 1 and "ahead of its remote" in err and "reset --hard origin/main" in err, out + err)
            git(child, other, "pull", "-q", "--ff-only", "origin", "main")
            git(child, other, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                "commit", "-q", "--allow-empty", "-m", "the child moved again")
            git(child, other, "push", "-q", "origin", "HEAD:main")
            rc, out, err = install("diverged", "div", {"charter-addendum.md": addendum("charter-addendum", "dig-div")})
            check("…and one that has diverged from it", rc == 1 and "diverged from its remote" in err and "reset --hard" in err, out + err)
            git(parent, mirror, "fetch", "-q", "origin")
            git(parent, mirror, "reset", "-q", "--hard", "origin/main")
            n1 = count()

            # An ignore rule drops a file from `git add` with exit 0 (the parent's excludes, or a .gitignore the child
            # committed): the commit would hold less than was validated and its trailers would say otherwise.
            exclude = os.path.join(mirror, ".git", "info", "exclude")
            with open(exclude, "a") as fh:
                fh.write("settings/roles/*/charter-addendum.md\n")
            head_i = git(parent, mirror, "rev-parse", "HEAD")
            rc, out, err = install("ignored", "ign", {"charter-addendum.md": addendum("charter-addendum", "dig-ign"),
                                                      "holder.json": b'{"locale":"en"}'})
            check("a file git ignores in the mirror refuses the install: no commit, and the file is not left behind",
                  rc == 1 and "ignore rule" in err and "nothing written" in err and git(parent, mirror, "rev-parse", "HEAD") == head_i
                  and git(parent, mirror, "status", "--porcelain", "--ignored") == "" and remote_head() == head_i.strip(), out + err)
            rc, out, err = install("ignored1", "ign1", {"charter-addendum.md": addendum("charter-addendum", "dig-ign")})
            check("…a first install of only the ignored file is refused too, not reported unchanged",
                  rc == 1 and "ignore rule" in err, out + err)
            rc, out, err = call(parent, "roles-put", "--agent", "kid", "--role", "ignrole", "--from",
                                src("ign2", {"charter-addendum.md": addendum("charter-addendum", "dig-i2", "ignrole")}), "--approval", "A-8")
            check("…and an ignored file that was never tracked is removed from the mirror again, not left for the next run",
                  rc == 1 and not os.path.exists(os.path.join(mirror, "settings", "roles", "ignrole", "charter-addendum.md")), out + err)
            with open(exclude, "w") as fh:
                fh.write("")
            n1 = count()

            # A clean filter changes the bytes on their way into the commit: what is committed is not what was validated.
            rot = "tr 'a-zA-Z' 'n-za-mN-ZA-M'"
            git(parent, mirror, "config", "filter.rot.clean", rot)
            git(parent, mirror, "config", "filter.rot.smudge", rot)
            attrs = os.path.join(mirror, ".git", "info", "attributes")
            with open(attrs, "w") as fh:
                fh.write("settings/roles/*/holder.json filter=rot\n")
            head_f = git(parent, mirror, "rev-parse", "HEAD")
            rc, out, err = install("filter", "flt", {"charter-addendum.md": addendum("charter-addendum", "dig-flt"),
                                                     "holder.json": b'{"locale":"en"}'})
            check("a git filter that changes a file on its way into the commit refuses the install",
                  rc == 1 and "git filter" in err and git(parent, mirror, "rev-parse", "HEAD") == head_f
                  and git(parent, mirror, "status", "--porcelain") == "", out + err)
            os.unlink(attrs)
            git(parent, mirror, "config", "--unset", "filter.rot.clean")
            git(parent, mirror, "config", "--unset", "filter.rot.smudge")

            # SIGTERM while the commit is made: the same undo as Ctrl-C, ending as a one-line refusal, the handler put back.
            import signal as _signal
            before_handler = _signal.getsignal(_signal.SIGTERM)
            head_t = git(parent, mirror, "rev-parse", "HEAD")
            with mock.patch.object(sys.modules["secretstore.roles"], "_commit", side_effect=lambda *a: os.kill(os.getpid(), _signal.SIGTERM)):
                rc, out, err = install("term", "term", {"charter-addendum.md": addendum("charter-addendum", "dig-term")})
            check("SIGTERM during the commit undoes the install like Ctrl-C, and the handler is put back",
                  rc == 1 and "interrupted" in err and git(parent, mirror, "rev-parse", "HEAD") == head_t
                  and git(parent, mirror, "status", "--porcelain", "--ignored") == "" and _signal.getsignal(_signal.SIGTERM) == before_handler,
                  out + err)

            # A regular file where the role's directory belongs: one line, nothing written, nothing left.
            with open(os.path.join(mirror, "settings", "roles", "filerole"), "w") as fh:
                fh.write("x")
            rc, out, err = call(parent, "roles-put", "--agent", "kid", "--role", "filerole", "--from",
                                src("fr", {"charter-addendum.md": addendum("charter-addendum", "dig-f", "filerole")}), "--approval", "A-7")
            check("a file in place of the role's directory is refused in one line, no traceback",
                  rc == 1 and "not a directory" in err and "Traceback" not in err and count() == n1, out + err)
            os.unlink(os.path.join(mirror, "settings", "roles", "filerole"))

            # The undo: a write that fails half way, a push that fails, an interrupt in the push.
            roles_mod = sys.modules["secretstore.roles"]
            real_put_file = roles_mod._put_file
            calls = []

            def second_fails(dest, data):
                calls.append(dest)
                if len(calls) == 2:
                    raise OSError(28, "No space left on device", dest)
                real_put_file(dest, data)
            head_u = git(parent, mirror, "rev-parse", "HEAD")
            tree_u = git(parent, mirror, "ls-files", "-s")
            with mock.patch.object(roles_mod, "_put_file", second_fails):
                rc, out, err = install("half", "half", {"charter-addendum.md": addendum("charter-addendum", "dig-h"),
                                                        "holder.json": b'{"locale":"en"}'})
            check("a write that fails half way puts the mirror back: one line, same head and index, nothing left over",
                  rc == 1 and "No space left" in err and "nothing written" in err and "Traceback" not in err
                  and git(parent, mirror, "rev-parse", "HEAD") == head_u and git(parent, mirror, "ls-files", "-s") == tree_u
                  and git(parent, mirror, "status", "--porcelain", "--ignored") == "", out + err)
            for label, boom, needle in (("a push that fails", secret_store.StoreError("push refused"), "push refused"),
                                        ("an interrupt in the push", KeyboardInterrupt(), "interrupted")):
                with mock.patch.object(roles_mod, "_after_commit", side_effect=boom):
                    rc, out, err = install("push", "push", {"charter-addendum.md": addendum("charter-addendum", "dig-push")})
                check(f"{label} resets the mirror to its remote: no unpushed commit is left",
                      rc == 1 and needle in err and git(parent, mirror, "rev-parse", "HEAD") == head_u
                      and git(parent, mirror, "status", "--porcelain", "--ignored") == "" and remote_head() == head_u.strip(), out + err)
            rc, out, err = install("after", "after", {"charter-addendum.md": addendum("charter-addendum", "dig-after")})
            check("…and the next install is accepted (the mirror is whole)", rc == 0 and "committed as" in out, out + err)
            n1 = count()
            git(parent, mirror, "reset", "-q", "--hard", "HEAD~1")
            git(parent, mirror, "push", "-q", "--force", "origin", "HEAD:main")
            n1 = count()

            keyname = trust.TRUST_KEY
            held = git(parent, mirror, "config", "--local", "--get", keyname).strip()
            git(parent, mirror, "config", "--local", "--unset", keyname)
            n2 = count()
            rc, out, err = install("unverified", "unv", {"charter-addendum.md": addendum("charter-addendum", "dig-unv")})
            check("a mirror with no trusted base is unverified: refused, nothing pushed", rc == 1 and "no trusted base" in err
                  and count() == n2, out + err)
            git(parent, mirror, "config", "--local", keyname, held)
            os.rename(mirror, mirror + ".moved")
            os.makedirs(mirror)
            subprocess.run(["git", "-C", mirror, "init", "-q", "-b", "main"], check=True, env=parent)
            with open(os.path.join(mirror, ".agent-id"), "w") as fh:
                fh.write(PID + "\n")
            rc, out, err = install("nomirror", "nm", good)
            check("a directory that is the mirror of another agent is refused, naming it",
                  rc == 1 and "not the mirror of agent" in err and "nothing written" in err, out + err)
            shutil.rmtree(mirror)
            os.rename(mirror + ".moved", mirror)

            # ── a retirement ──────────────────────────────────────────────
            n3 = count()
            empty = src("empty", {})
            rc, out, err = call(parent, "roles-put", "--agent", "kid", "--role", ROLE, "--from", empty, "--approval", "A-5")
            check("an empty directory without --retire is refused: it may be a mistake", rc == 1 and "--retire" in err and count() == n3, out + err)
            rc, out, err = install("retfiles", "retf", good, "--retire")
            check("--retire with files is refused", rc == 1 and "empty directory" in err and count() == n3, out + err)
            rc, out, err = call(parent, "roles-put", "--agent", "kid", "--role", ROLE, "--from", empty, "--approval", "A-5",
                                "--reviewed-by", REVIEW, "--retire")
            check("a retirement: an empty directory and --retire removes the role's addenda in one signed, pushed commit",
                  rc == 0 and "committed as" in out and count() == n3 + 1 and not os.path.exists(os.path.join(mirror, "settings", "roles", ROLE))
                  and os.path.isfile(os.path.join(mirror, "settings", "roles", "other-role", "charter-addendum.md"))
                  and git(parent, mirror, "log", "-1", "--format=%G?").strip() == "G"
                  and remote_head() == git(parent, mirror, "rev-parse", "HEAD").strip(), out + err)
            msg = git(parent, mirror, "log", "-1", "--format=%B")
            check("…its trailers say whose, who approved, and name no digest",
                  f"Addendum-Role: {ROLE}" in msg and "Owner-Approval: A-5" in msg and f"Reviewed-By: {REVIEW}" in msg
                  and "Against-Digest" not in msg and "roles-retire" in msg.splitlines()[0], msg)
            rc, out, err = call(parent, "roles-put", "--agent", "kid", "--role", ROLE, "--from", empty, "--approval", "A-5", "--retire")
            check("retiring what is already gone is unchanged, no commit", rc == 0 and "unchanged" in out and count() == n3 + 1, out + err)

            # ── a link on the way ─────────────────────────────────────────
            elsewhere = os.path.join(tmp, "elsewhere")
            os.makedirs(elsewhere)
            git(parent, mirror, "rm", "-rq", "--", "settings/roles/other-role")
            git(parent, mirror, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "x")
            git(parent, mirror, "push", "-q", "origin", "HEAD:main")
            os.makedirs(os.path.join(mirror, "settings", "roles"), exist_ok=True)
            os.symlink(elsewhere, os.path.join(mirror, "settings", "roles", ROLE))
            git(parent, mirror, "add", "-A")
            git(parent, mirror, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "a link")
            git(parent, mirror, "push", "-q", "origin", "HEAD:main")
            rc, out, err = install("link", "lnk", good)
            check("a link at settings/roles/<role> in the mirror is refused, never followed", rc == 1 and "link" in err
                  and os.listdir(elsewhere) == [], out + err)
            with open(os.path.join(elsewhere, "keep"), "w") as fh:
                fh.write("k")
            rc, out, err = call(parent, "roles-put", "--agent", "kid", "--role", ROLE, "--from", empty, "--approval", "A-6", "--retire")
            check("…and a retirement of such a link is refused as well: no files to write, so the link itself is what is judged",
                  rc == 1 and "link" in err and "Traceback" not in err and os.listdir(elsewhere) == ["keep"], out + err)

            # ── the set rules, with the real validator (ADR-060 rules 1 and 9) ──
            if hasattr(addenda_check, "validate_set"):
                def real_add(lang: str = "ka", kind: str = "charter-addendum") -> bytes:
                    return (f"---\nclass: {kind}\nrole: {ROLE}\nagent_id: {KID}\nlang: {lang}\n"
                            f"against_digest: sha256:{'a' * 64}\n---\n# {kind}\nSpecialises {ROLE}.\n").encode()

                def gloss_of(add: bytes, digest: str | None = None, kind: str = "charter-addendum") -> bytes:
                    d = digest or addenda_check.body_digest(add.decode())
                    return (f"---\nclass: {kind}-gloss\nrole: {ROLE}\nagent_id: {KID}\nlang: en\n"
                            f"glosses_digest: {d}\n---\n# {kind}\nSpecialises {ROLE}.\n").encode()

                passes = ("--reviewed-by", REVIEW, "--reviewed-by", REVIEW2)
                n_set = count()
                ka = real_add()
                rc, out, err = install("ka-nogloss", "kng", {"charter-addendum.md": ka}, *passes, validate=real_validate)
                check("a non-English addendum with no English gloss is refused at install",
                      rc == 1 and "needs its English gloss" in err and count() == n_set, out + err)
                rc, out, err = install("stale", "stl", {"charter-addendum.md": ka,
                                                        "charter-addendum.gloss.en.md": gloss_of(ka, "sha256:" + "0" * 64)},
                                       *passes, validate=real_validate)
                check("…a stale gloss too", rc == 1 and "stale gloss" in err and count() == n_set, out + err)
                rc, out, err = install("orphan", "orp", {"charter-addendum.md": real_add("en"),
                                                         "brief-addendum.gloss.en.md": gloss_of(ka, kind="brief-addendum")},
                                       *passes, validate=real_validate)
                check("…and a gloss with no addendum", rc == 1 and "not in the set" in err and count() == n_set, out + err)
                rc, out, err = install("ka-ok", "kok", {"charter-addendum.md": ka, "charter-addendum.gloss.en.md": gloss_of(ka)},
                                       *passes, validate=real_validate)
                check("…and the same pair with the gloss in step installs (the positive control)",
                      rc == 0 and count() == n_set + 1, out + err)
                git(parent, mirror, "reset", "-q", "--hard", "HEAD~1")
                git(parent, mirror, "push", "-q", "--force", "origin", "HEAD:main")
            else:
                print("  skip the set rules: addenda_check is still the stub here; they run on the fold")

            # ── the real command line, the real validator ─────────────────
            git(parent, mirror, "reset", "-q", "--hard", "HEAD~1")
            git(parent, mirror, "push", "-q", "--force", "origin", "HEAD:main")
            real = subprocess.run([sys.executable, CHILD_TOOL, "roles-put", "--agent", KID, "--role", ROLE,
                                   "--from", src("real", {"charter-addendum.md": addendum("charter-addendum", "sha256:" + hashlib.sha256(b"the shared charter\n").hexdigest())}),
                                   "--approval", "ADR-060-real"], env=parent, cwd=tmp, capture_output=True, text=True)
            check("the installed command line, with the real validator, installs a conforming addendum",
                  real.returncode == 0 and "committed as" in real.stdout, real.stdout + real.stderr)
            usage = subprocess.run([sys.executable, CHILD_TOOL], env=parent, cwd=tmp, capture_output=True, text=True)
            check("…and without a verb it is a usage error", usage.returncode == 2 and "Traceback" not in usage.stderr, usage.stderr)
        finally:
            for r in (parent, child):
                subprocess.run(["gpgconf", "--homedir", r["GNUPGHOME"], "--kill", "all"], capture_output=True)

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
