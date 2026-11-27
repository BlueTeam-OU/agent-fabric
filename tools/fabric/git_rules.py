#!/usr/bin/env python3
"""tools/fabric/git_rules.py — how a session works with git in a repository, rendered (agent-fabric ADR-019 §5 rule 9).

CONTRACT (bin/fabric-git-rules is the command; session-start.py and freshness.py call render()):
  fabric-git-rules [--repo <owner>/<name> | <path>]     default: the working directory
  stdout   the header line, then one line per note (the repository's git.md unreadable, no usable copy of its
           policy), a blank line, the rendered text; nothing else, exit 0.
  stderr   one `fabric-git-rules: <reason>` line on failure, nothing on stdout, exit 1; a usage error exits 2.
  No API call and no write: the account's copy of the policy and of the repository's git.md is read as
  arm_policy.load left it (write_threshold_cache).

THE TEXT is the first of three layers found, whole, never merged: the repository's repos/<repo>.git.md as the account's
copy holds it, operator/prompt/git.md, identities/prompt/git.md. A `{dotted.name}` in it is filled: no prefix from the
repository's merged arming policy, `repo.*` from projects/registry.json (plus `id`, the project's), `signing.*` from
policies/signing.json's default with the repository's entry over it, `integration.*` from the project's
integration/gh/arm.json. A list renders ", "-joined. A name with no value — absent, null, an empty list, a mapping — is
a GitRulesError naming it: a blank would read as a rule that says nothing.

WHAT THE HEADER SAYS: the layer used and where the policy came from (the account's copy as read at a time, or the
fleet's value and why). Two situations are given a line of their own, because the session would otherwise take the
operator's text for the repository's: the repository's git.md could not be read, and there is no usable copy.
Unknown stays unknown: nothing here turns an unreadable copy into a default the contract did not define; the
fleet's value is the contract's own answer for "no copy" (rule 9), said as such.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import NamedTuple
from typing import Any

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "guards"))
import roots  # noqa: E402
import workingcopy  # noqa: E402
import branch_size  # noqa: E402  the account's copy has one path (cache_path) and one writer (arm_policy)
identity = branch_size.identity  # the state dir and its atomic write have one owner (ADR-003 rule 1)
from github import arm_policy  # noqa: E402

PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*)\}")
REPO_NAME = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
TEXT_LIMIT = arm_policy.GIT_MD_LIMIT
GIT_MD_STATES = ("present", "absent", "unreadable")


class GitRulesError(Exception):
    """Rendering failed; the message is one line for a person."""


# NamedTuple, not a dataclass: the hooks load this module by path without registering it in sys.modules, and a
# dataclass looks its own module up there (an AttributeError at import on 3.14).
class Rendered(NamedTuple):
    header: str
    notes: tuple[str, ...]
    body: str

    def text(self) -> str:
        return "\n".join([self.header, *self.notes, "", self.body.strip("\n")])


def _read_json(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        raise GitRulesError(f"{path} cannot be read ({e})") from None


def _read_layer(path: str) -> str | None:
    """The text of a layer file, None when it is not there. One that is there and cannot be read is an error, not a
    layer that is absent: the next layer would give the session rules its owner did not choose."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read(TEXT_LIMIT + 1)
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as e:
        raise GitRulesError(f"{path} cannot be read ({e.strerror or e})") from None
    if len(raw) > TEXT_LIMIT:
        raise GitRulesError(f"{path} is over {TEXT_LIMIT} bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise GitRulesError(f"{path} is not UTF-8") from None
    if not text.strip():
        raise GitRulesError(f"{path} is empty")
    return text


def _repo_of(top: str, timeout: float | None = None) -> str | None:
    """<owner>/<name> of the working copy's origin when it is a GitHub remote, in the spelling the account's copy is
    keyed by (branch_size.repository_of's, without its unbounded git call)."""
    url = workingcopy.remote_url(top, **_bound(timeout))
    parsed = workingcopy.parse_remote(url) if url else None
    if not parsed or parsed["host"] != "github.com" or not REPO_NAME.fullmatch(parsed["path"]):
        return None
    return parsed["path"]


def _bound(timeout: float | None) -> dict:
    return {} if timeout is None else {"timeout": timeout}


class Target(NamedTuple):
    repo: str | None
    project: str | None
    spec: dict | None


def target_of(working_copy: str | None, repo: str | None, registry: dict, timeout: float | None = None) -> Target:
    """Which repository and registered project the text is for: the working copy's (its marker or its origin), or
    `repo`'s. No repository, or one no project has, is a Target without a project: the operator layer on the fleet
    policy."""
    projects = registry.get("projects") if isinstance(registry, dict) else None
    if not isinstance(projects, dict):
        raise GitRulesError("projects/registry.json has no projects map")
    for pid, spec in projects.items():
        # null remotes is empty, as every other registry reader takes it (`or []`); a remote that is no string would
        # reach workingcopy.parse_remote's .strip() on the working-copy route and leave a traceback.
        remotes = spec.get("remotes") or [] if isinstance(spec, dict) else None
        if not isinstance(remotes, list) or not all(isinstance(r, str) for r in remotes):
            raise GitRulesError(f"projects/registry.json: project {pid!r} is not a mapping with a list of remote strings")
    if repo:
        try:
            found = arm_policy.project_of(registry, repo)
        except arm_policy.PolicyUnavailable as e:
            raise GitRulesError(str(e)) from None
        return Target(repo, found[0], found[1]) if found else Target(repo, None, None)
    top = workingcopy.toplevel(working_copy, **_bound(timeout)) if working_copy else None
    if not top:
        return Target(None, None, None)
    try:
        got = workingcopy.resolve(top, registry, timeout)
    except SystemExit as e:
        raise GitRulesError(str(e.code)) from None
    project = got["project"]
    spec = projects.get(project) if project else None
    return Target(_repo_of(top, timeout), project, spec if isinstance(spec, dict) else None)


def _valid_copy(doc: Any, repo: str) -> bool:
    if not isinstance(doc, dict) or doc.get("repository") != repo:
        return False
    policy, md = doc.get("policy"), doc.get("git_md")
    return (isinstance(policy, dict) and isinstance(policy.get("commits"), dict)
            and isinstance(md, dict) and md.get("state") in GIT_MD_STATES
            and (md["state"] != "present" or isinstance(md.get("text"), str) and bool(md["text"].strip())
                 and len(md["text"].encode("utf-8")) <= TEXT_LIMIT))


def _copy_of(repo: str) -> tuple[dict | None, str | None]:
    """(the account's copy, None) or (None, why there is none usable). A copy written before it held the whole policy
    is no copy: the next read of the policy replaces it."""
    try:
        path = branch_size.cache_path(repo)
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        return None, f"no copy of {repo}'s policy has been read by this account yet"
    except (OSError, ValueError, RuntimeError) as e:
        return None, f"the copy of {repo}'s policy cannot be read ({e})"
    md = doc.get("git_md") if isinstance(doc, dict) else None
    if isinstance(md, dict) and isinstance(md.get("text"), str) and len(md["text"].encode("utf-8")) > TEXT_LIMIT:
        return None, f"the copy of {repo}'s git.md is over {TEXT_LIMIT} bytes (the next read of the policy replaces it)"
    if not _valid_copy(doc, repo):
        return None, f"the copy of {repo}'s policy is not in the current shape (the next read of the policy replaces it)"
    return doc, None


def _signing(repo: str | None, operator: str | None) -> dict | None:
    doc = _read_json(roots.policy("signing.json", root=operator))
    if not isinstance(doc, dict) or not isinstance(doc.get("default"), dict):
        return None
    repositories = doc.get("repositories", {})
    if not isinstance(repositories, dict):
        raise GitRulesError("policies/signing.json: `repositories` is not a mapping")
    entry = repositories.get(repo) if repo else None
    if entry is not None and not isinstance(entry, dict):
        raise GitRulesError(f"policies/signing.json: the entry for {repo} is not a mapping")
    return arm_policy.merge(doc["default"], entry) if isinstance(entry, dict) else dict(doc["default"])


def scopes(target: Target, policy: dict, operator: str | None) -> dict[str, Any]:
    """The documents a placeholder's first segment selects; the policy answers a name with no prefix."""
    out: dict[str, Any] = {"": policy}
    if target.spec is not None:
        out["repo"] = {**target.spec, "id": target.project}
        integration = _read_json(roots.project_integration(target.project, "gh", "arm.json", root=operator))
        if integration is not None and not isinstance(integration, dict):
            raise GitRulesError(f"integration/gh/arm.json of project {target.project} is not a mapping")
        if integration is not None:
            out["integration"] = integration
    signing = _signing(target.repo, operator)
    if signing is not None:
        out["signing"] = signing
    return out


def _value(name: str, scoped: dict[str, Any]) -> str:
    head, _, rest = name.partition(".")
    if rest and head in ("repo", "signing", "integration"):
        cur: Any = scoped.get(head)
        path = rest
    else:
        cur, path = scoped[""], name
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            cur = None
            break
        cur = cur[part]
    if isinstance(cur, bool):
        return "true" if cur else "false"
    if isinstance(cur, (str, int, float)) and cur != "":
        return str(cur)
    if isinstance(cur, list) and cur and all(isinstance(v, (str, int, float)) and not isinstance(v, bool) and v != "" for v in cur):
        return ", ".join(str(v) for v in cur)
    raise GitRulesError(f"the placeholder {{{name}}} has no value here")


def fill(text: str, scoped: dict[str, Any]) -> str:
    return PLACEHOLDER.sub(lambda m: _value(m.group(1), scoped), text)


def render(working_copy: str | None = None, *, repo: str | None = None, operator: str | None = None,
           engine: str | None = None, timeout: float | None = None) -> Rendered:
    """The git rules for the working copy (or `repo`): see the module's header. GitRulesError, never a traceback, for
    what cannot be rendered: the readers of the policy, the registry and the signing file each have their own error
    types, and the command prints one line for all of them. `timeout` bounds each git call (a hook's budget)."""
    try:
        return _render(working_copy, repo, operator, engine, timeout)
    except GitRulesError:
        raise
    except workingcopy.GitTimeout as e:
        raise GitRulesError(f"a git call did not answer within {timeout:g} s ({e})") from None
    except (arm_policy.PolicyError, arm_policy.PolicyUnavailable, OSError, ValueError) as e:
        raise GitRulesError(f"{type(e).__name__}: {e}") from None


def _render(working_copy: str | None, repo: str | None, operator: str | None, engine: str | None,
            timeout: float | None) -> Rendered:
    path = roots.projects_registry(root=operator, engine=engine)
    registry = _read_json(path)
    if registry is None:
        # An operator without a registry (none written yet, or a stripped checkout) registers no project: the
        # working copy matches none and the engine's text renders. A registry that is there and unreadable stays an
        # error (_read_json); only absence is empty.
        registry = {"projects": {}}
    target = target_of(working_copy, repo, registry, timeout)
    notes: list[str] = []
    copy: dict | None = None
    if target.repo and target.project:
        copy, why = _copy_of(target.repo)
        if copy is None:
            notes.append(f"agent-fabric: {why}; no repository layer is available, so the operator's text (else the engine's) is given, "
                         f"on the fleet's policy values.")
    if copy is not None:
        policy = copy["policy"]
        source = f"the account's copy as read {copy.get('read_at', 'at an unknown time')}"
    else:
        policy = arm_policy.fleet_policy(operator)
        source = "the fleet's value" if target.project else "the fleet's value (no registered repository here)"
    layer, text = None, None
    if copy is not None and copy["git_md"]["state"] == "present":
        layer, text = "the repository's git.md", copy["git_md"]["text"]
    elif copy is not None and copy["git_md"]["state"] == "unreadable":
        notes.append(f"agent-fabric: the repository's git.md could not be read ({copy['git_md'].get('why', 'no reason recorded')}); "
                     f"the operator's text (else the engine's) is given in its place.")
    if text is None:
        opr = roots.operator_root(engine=engine) if operator is None else operator
        for name, file in (("the operator's git.md", os.path.join(opr, "prompt", "git.md")),
                           ("the engine's git.md", os.path.join(roots.engine_root() if engine is None else engine,
                                                                "identities", "prompt", "git.md"))):
            text = _read_layer(file)
            if text is not None:
                layer = name
                break
    if text is None or layer is None:
        raise GitRulesError("no git.md found: not the repository's copy, operator/prompt/git.md or identities/prompt/git.md")
    body = fill(text, scopes(target, policy, operator))
    return Rendered(f"agent-fabric: git rules for {target.repo or 'no repository'} — text: {layer}; policy: {source}",
                    tuple(notes), body)


SESSION_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


FAILURE_PREFIX = "agent-fabric: the git rules could not be rendered ("


def for_hook(working_copy: str | None, timeout: float | None = None) -> str:
    """The text a hook gives a session, or one line saying why it cannot. Rendering never stops a session (rule 9): a
    failure is a line and the hook goes on. Nothing is raised."""
    try:
        return render(working_copy, timeout=timeout).text()
    except GitRulesError as e:
        reason = str(e)
    except (Exception, SystemExit) as e:  # noqa: BLE001 — a state or tree oddity must not cost the session its start
        reason = f"{type(e).__name__}: {e.code if isinstance(e, SystemExit) else e}"
    return f"{FAILURE_PREFIX}{reason}); run `fabric-git-rules` and read what it says."


def _given_path(session: str, state: str | None) -> str | None:
    if not SESSION_RE.fullmatch(session or ""):
        return None
    return os.path.join(state or identity.agent_state_dir(), f"git-rules-{session}.json")


def given(session: str, state: str | None = None) -> str | None:
    """The working copy ("" for none) the session was last given the rules for; None when it was given none, or the note
    cannot be read: asked again then, because unknown is not "already told"."""
    path = _given_path(session, state)
    try:
        with open(path or os.devnull, encoding="utf-8") as fh:
            value = json.load(fh).get("working_copy")
    except (OSError, ValueError, AttributeError):
        return None
    return value if isinstance(value, str) else None


def record_given(session: str, working_copy: str | None, state: str | None = None) -> None:
    """Note that the session was given the rules for `working_copy`; a failure to note it is only a repeat later."""
    path = _given_path(session, state)
    if path is None:
        return
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        identity.atomic_write(path, json.dumps({"working_copy": os.path.realpath(working_copy) if working_copy else ""}), 0o600)
    except OSError as e:
        print(f"git_rules: the note of the rules given to {session} was not written: {e}", file=sys.stderr)


def changed(session: str, working_copy: str | None, state: str | None = None) -> bool:
    """Whether `working_copy` is another than the one the session was last given the rules for."""
    last = given(session, state)
    return last is None or last != (os.path.realpath(working_copy) if working_copy else "")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fabric-git-rules", description="Print the git rules for a working copy: the repository's "
                                 "git.md copy, else operator/prompt/git.md, else identities/prompt/git.md, its {placeholders} "
                                 "filled from the repository's policy (agent-fabric ADR-019 section 5 rule 9). No API call.")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--repo", metavar="OWNER/NAME", help="a repository by name, not a working copy")
    group.add_argument("path", nargs="?", help="a working copy (default: the current directory)")
    args = ap.parse_args(argv)
    if args.repo is not None and not REPO_NAME.fullmatch(args.repo):
        ap.error(f"--repo wants <owner>/<name>, not {args.repo!r}")
    try:
        if args.path is not None and not os.path.isdir(args.path):
            raise GitRulesError(f"{args.path!r} is not a directory")
        done = render(args.path if args.path is not None else os.getcwd(), repo=args.repo)
    except GitRulesError as e:
        print(f"fabric-git-rules: {e}", file=sys.stderr)
        return 1
    print(done.text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
