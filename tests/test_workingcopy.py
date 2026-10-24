#!/usr/bin/env python3
"""tests/test_workingcopy.py — the remote parser behind project matching.

A project is matched by its remote, so what counts as "the same remote"
decides which project a working copy belongs to. parse_remote reads the
two shapes git accepts (a URL with a scheme; scp-like `[user@]host:path`
when no slash precedes the first colon) and nothing else; canonical_remote
compares host (case-insensitive, IPv6 kept in brackets), a non-default
port, and the path — lowercased only on hosts that treat it so."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from git_env import git_env, scrub_process_env  # noqa: E402 — tests/, the script's own directory
scrub_process_env()

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
spec = importlib.util.spec_from_file_location("fabric_workingcopy", os.path.join(ROOT, "tools", "fabric", "workingcopy.py"))
wc = importlib.util.module_from_spec(spec); spec.loader.exec_module(wc)


def test_the_shapes_git_accepts_parse_to_one_structure() -> None:
    cases = {
        "git@github.com:org/repo.git": ("ssh", "git", "github.com", None, "org/repo"),
        "ssh://git@github.com/org/repo.git": ("ssh", "git", "github.com", None, "org/repo"),
        "https://github.com/org/repo/": ("https", None, "github.com", None, "org/repo"),
        "https://user:token@forge.example:8443/Org/Repo.git": ("https", "user:token", "forge.example", 8443, "Org/Repo"),
        "ssh://git@forge.example:2222/Org/Repo.git": ("ssh", "git", "forge.example", 2222, "Org/Repo"),
        "ssh://git@forge.example:22/Org/Repo": ("ssh", "git", "forge.example", None, "Org/Repo"),   # the scheme's default port
        "ssh://git@[::1]:2222/org/repo.git": ("ssh", "git", "[::1]", 2222, "org/repo"),
        "git@[fe80::1%eth0]:org/repo": ("ssh", "git", "[fe80::1%eth0]", None, "org/repo"),
        "git://forge.example/org/repo": ("git", None, "forge.example", None, "org/repo"),
        "github.com/org/repo": (None, None, "github.com", None, "org/repo"),        # the registry's shorthand
        "GitHub.COM/org/repo": (None, None, "github.com", None, "org/repo"),
    }
    for url, want in cases.items():
        r = wc.parse_remote(url)
        assert r is not None, url
        assert (r["scheme"], r["user"], r["host"], r["port"], r["path"]) == want, (url, r)


def test_what_is_not_a_network_remote_parses_to_nothing() -> None:
    for url in ("/home/x/repo", "./repo", "file:///home/x/repo", "https:///nohost/x", "foo", "", "   ",
                "host:", "host:/", "https://host", "https://host/"):
        assert wc.parse_remote(url) is None, url
        assert wc.canonical_remote(url) is None, url


def test_scp_syntax_follows_gits_own_rule() -> None:
    # No slash before the first colon: scp-like, and what follows the colon
    # is the path — git reads `host:2222/org/repo` exactly so.
    assert wc.parse_remote("host:2222/org/repo")["path"] == "2222/org/repo"
    assert wc.parse_remote("host:2222/org/repo")["port"] is None
    # A slash before the first colon: not scp-like; without a scheme it is a
    # local path git would open, never a remote to match.
    assert wc.parse_remote("./host:org/repo") is None


def test_canonical_ignores_scheme_and_user_keeps_port_and_host_case_folds() -> None:
    same = ["git@github.com:org/repo.git", "https://github.com/org/repo", "ssh://git@github.com:22/org/repo/",
            "GITHUB.com/org/repo", "https://oauth2:tok@github.com/org/repo.git"]
    assert len({wc.canonical_remote(u) for u in same}) == 1, [wc.canonical_remote(u) for u in same]
    assert wc.canonical_remote("ssh://git@forge.example:2222/org/repo") != wc.canonical_remote("ssh://git@forge.example/org/repo"), \
        "a non-default port is another server"
    assert wc.canonical_remote("ssh://git@forge.example:22/org/repo") == wc.canonical_remote("git@forge.example:org/repo")
    assert wc.canonical_remote("ssh://git@[::1]:2222/org/repo") == "[::1]:2222/org/repo"


def test_path_case_is_host_specific() -> None:
    # GitHub, GitLab and Bitbucket route Org/Repo and org/repo to one repository.
    assert wc.canonical_remote("git@github.com:Org/Repo.git") == wc.canonical_remote("https://github.com/org/repo")
    assert wc.canonical_remote("git@gitlab.com:Org/Repo.git") == wc.canonical_remote("https://gitlab.com/org/repo")
    # A self-hosted forge may not: the path is compared as written.
    assert wc.canonical_remote("git@forge.example:Org/Repo.git") != wc.canonical_remote("git@forge.example:org/repo.git")
    assert wc.canonical_remote("git@FORGE.example:Org/Repo.git") == wc.canonical_remote("git@forge.example:Org/Repo.git"), \
        "the host is DNS: case never matters there"


def test_project_matching_uses_the_canonical_form() -> None:
    registry = {"projects": {"demo": {"remotes": ["git@example.com:org/demo.git"]},
                             "gh": {"remotes": ["github.com/org/gh"]},
                             "ported": {"remotes": ["ssh://git@forge.example:2222/org/x.git"]}}}
    assert wc.project_for_remote("https://example.com/org/demo/", registry) == "demo"
    assert wc.project_for_remote("EXAMPLE.com/org/demo", registry) == "demo"
    assert wc.project_for_remote("example.com/Org/Demo", registry) is None, "path case on a non-GitHub host"
    assert wc.project_for_remote("git@GitHub.com:Org/GH.git", registry) == "gh"
    assert wc.project_for_remote("ssh://forge.example:2222/org/x", registry) == "ported"
    assert wc.project_for_remote("ssh://forge.example/org/x", registry) is None, "the port is part of the remote"
    assert wc.project_for_remote("/home/x/org/demo", registry) is None
    assert wc.project_for_remote(None, registry) is None
    assert wc.project_for_remote("demo", registry) is None, "a bare word matches nothing"


def test_blueteam_projects_resolve_under_both_github_orgs() -> None:
    """The move from gzapi-org to BlueTeam-OU: a clone keeps its project
    whichever name its origin carries. Since the move (2026-10-09) the new
    name is first, which new_agent.py (the first git@ remote) and results.py
    (the first GitHub one) take, and the old ones are listed as moved_from,
    which bootstrap re-points.
    The operator's own registry on purpose: the fact is about its data."""
    import json
    roots_spec = importlib.util.spec_from_file_location("fabric_roots", os.path.join(ROOT, "tools", "fabric", "roots.py"))
    roots = importlib.util.module_from_spec(roots_spec); roots_spec.loader.exec_module(roots)
    path = roots.projects_registry(engine=ROOT)
    if not os.path.exists(path):
        print(f"  skip test_blueteam_projects_resolve_under_both_github_orgs: no projects registry at {path} (an operator exported to a tree without one)")
        return
    with open(path, encoding="utf-8") as fh:
        registry = json.load(fh)
    for pid, repo in (("agent-fabric", "agent-fabric"), ("agent-fabric-gateway", "agent-fabric-gateway"),
                      ("herdr", "agent-fabric-herdr"), ("radicle-spike", "radicle-spike"),
                      ("interweave", "InterWeave")):
        for url in (f"git@github.com:gzapi-org/{repo}.git", f"https://github.com/BlueTeam-OU/{repo}",
                    f"git@github.com:blueteam-ou/{repo}.git"):
            assert wc.project_for_remote(url, registry) == pid, (url, pid)
        entry = registry["projects"][pid]
        assert entry["remotes"][0].startswith("git@github.com:BlueTeam-OU/"), pid
        assert all(u in entry["remotes"] for u in entry["moved_from"]), pid


def test_kutaisi_shop_transit_resolves_under_both_owners() -> None:
    """The move from andreabenetton to gzapi-org (the owner, 2026-10-24): an
    unmoved clone still resolves, the new name is first and the client is
    gzapi's, whose settings repository then holds the arming policy."""
    import json
    roots_spec = importlib.util.spec_from_file_location("fabric_roots", os.path.join(ROOT, "tools", "fabric", "roots.py"))
    roots = importlib.util.module_from_spec(roots_spec); roots_spec.loader.exec_module(roots)
    path = roots.projects_registry(engine=ROOT)
    if not os.path.exists(path):
        print(f"  skip test_kutaisi_shop_transit_resolves_under_both_owners: no projects registry at {path}")
        return
    with open(path, encoding="utf-8") as fh:
        registry = json.load(fh)
    for owner in ("andreabenetton", "gzapi-org"):
        for url in (f"git@github.com:{owner}/kutaisi-shop-transit.git", f"https://github.com/{owner}/kutaisi-shop-transit"):
            assert wc.project_for_remote(url, registry) == "kutaisi-shop-transit", url
    entry = registry["projects"]["kutaisi-shop-transit"]
    assert entry["remotes"][0] == "git@github.com:gzapi-org/kutaisi-shop-transit.git"
    assert entry["client"] == "gzapi"
    assert all(u in entry["remotes"] for u in entry["moved_from"])


def test_a_hanging_git_reads_as_no_repository_within_the_bound() -> None:
    """A git that never answers is cut at GIT_TIMEOUT_S and _git says None,
    so a stalled filesystem cannot hold a session start or a scan."""
    import tempfile
    import time
    with tempfile.TemporaryDirectory() as tmp:
        fake = os.path.join(tmp, "git")
        with open(fake, "w") as fh:
            fh.write("#!/bin/sh\nexec sleep 30\n")
        os.chmod(fake, 0o755)
        saved_path, saved_bound = os.environ.get("PATH", ""), wc.GIT_TIMEOUT_S
        os.environ["PATH"] = tmp + os.pathsep + saved_path
        wc.GIT_TIMEOUT_S = 1
        try:
            started = time.monotonic()
            got = wc._git(["rev-parse", "--show-toplevel"], tmp)
            took = time.monotonic() - started
        finally:
            os.environ["PATH"], wc.GIT_TIMEOUT_S = saved_path, saved_bound
        assert got is None, got
        assert took < 10, f"took {took:.1f} s"


REGISTRY = {"projects": {
    "acme-app": {"remotes": ["git@github.com:some-other-org/acme-app.git"], "client": "acme"},
    "loose": {"remotes": ["git@github.com:some-other-org/loose.git"]},
    "stray": {"remotes": ["git@github.com:some-other-org/stray.git"], "client": "ghost"}}}
CLIENTS = {"clients": {"acme": {"title": "Acme", "engagement": "acme/rules", "secrets_store": "acme/secrets",
                                "channel": "acme:chan", "settings_repo": "acme/settings"},
                       "bare": {}}}


def test_a_project_resolves_to_its_registered_client() -> None:
    assert wc.client_for_project(None, REGISTRY, CLIENTS) is None
    assert wc.client_for_project("loose", REGISTRY, CLIENTS) is None, "a project with no client field has none"
    assert wc.client_for_project("unregistered", REGISTRY, CLIENTS) is None
    assert wc.client_for_project("acme-app", REGISTRY, CLIENTS) == {
        "id": "acme", "title": "Acme", "engagement": "acme/rules", "secrets_store": "acme/secrets",
        "channel": "acme:chan", "settings_repo": "acme/settings"}
    bare = {"projects": {"p": {"client": "bare"}}}
    assert wc.client_for_project("p", bare, CLIENTS) == {
        "id": "bare", "title": None, "engagement": None, "secrets_store": None, "channel": None, "settings_repo": None}


def test_an_unknown_client_refuses_naming_the_project_and_the_files() -> None:
    try:
        wc.client_for_project("stray", REGISTRY, CLIENTS)
    except SystemExit as exc:
        msg = str(exc.code)
        assert "stray" in msg and "ghost" in msg and "projects/clients.json" in msg, msg
    else:
        raise AssertionError("an unlisted client must refuse")


def _repo(tmp: str, remote: str) -> str:
    top = os.path.join(tmp, "wc")
    os.makedirs(top)
    subprocess.run(["git", "-C", top, "init", "-q"], env=git_env(), check=True)
    subprocess.run(["git", "-C", top, "remote", "add", "origin", remote], env=git_env(), check=True)
    return top


def test_resolve_names_the_client_from_the_project_never_the_organisation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        top = _repo(tmp, "git@github.com:some-other-org/acme-app.git")
        got = wc.resolve(top, REGISTRY)
        assert got["project"] == "acme-app" and got["client"] == "acme", got
        assert got["operator"] == wc.roots.operator_root(engine=wc.FABRIC_ROOT), got
        triple = wc.resolve_client(top, REGISTRY, CLIENTS)
        assert triple["project"] == "acme-app" and triple["client"]["id"] == "acme", triple
        assert triple["operator"] == got["operator"] and triple["working_copy"] == got["path"], triple
    with tempfile.TemporaryDirectory() as tmp:
        top = _repo(tmp, "git@github.com:nobody/unregistered.git")
        got = wc.resolve(top, REGISTRY)
        assert got["project"] is None and got["client"] is None, got
        assert wc.resolve_client(top, REGISTRY, CLIENTS)["client"] is None
    with tempfile.TemporaryDirectory() as tmp:
        got = wc.resolve(tmp, REGISTRY)
        assert got["client"] is None and got["operator"] is None, got


def test_resolve_never_refuses_over_a_client() -> None:
    """An unknown client is client_for_project's refusal, not resolve's:
    resolve answers the registry's word and keeps the project."""
    with tempfile.TemporaryDirectory() as tmp:
        top = _repo(tmp, "git@github.com:some-other-org/stray.git")
        got = wc.resolve(top, REGISTRY)
        assert got["project"] == "stray" and got["client"] == "ghost", got


def main() -> int:
    cases = [test_resolve_never_refuses_over_a_client, test_a_project_resolves_to_its_registered_client, test_an_unknown_client_refuses_naming_the_project_and_the_files,
             test_resolve_names_the_client_from_the_project_never_the_organisation, test_blueteam_projects_resolve_under_both_github_orgs, test_kutaisi_shop_transit_resolves_under_both_owners, test_the_shapes_git_accepts_parse_to_one_structure, test_what_is_not_a_network_remote_parses_to_nothing,
             test_scp_syntax_follows_gits_own_rule, test_canonical_ignores_scheme_and_user_keeps_port_and_host_case_folds,
             test_path_case_is_host_specific, test_project_matching_uses_the_canonical_form,
             test_a_hanging_git_reads_as_no_repository_within_the_bound]
    failures = 0
    for case in cases:
        try:
            case()
            print(f"  ok   {case.__name__}")
        except Exception as exc:  # noqa: BLE001 — a case that raises fails alone; the rest still run
            failures += 1
            print(f"  FAIL {case.__name__}: {exc.__class__.__name__ + ': ' if not isinstance(exc, AssertionError) else ''}{exc}")
    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
