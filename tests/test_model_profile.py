#!/usr/bin/env python3
"""Behavioural tests for tools/fabric/model_profile.py (bin/fabric-model).

The invariant under test: the command writes only the login's own layer
($STATE_DIR/model-profile.local.json) and the account's agent files, in
each provider's vocabulary, gated like the launcher; the repository is
never touched. Runs against the real routing files, minus the committed
roles/agents layers, with a scratch state directory and a scratch
CLAUDE_CONFIG_DIR.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

import instance_fixtures  # noqa: E402 — tests/, this script's own directory

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOL = os.path.join(ROOT, "tools", "fabric", "model_profile.py")


class Fixture:
    def __init__(self, tmp: str) -> None:
        self.state = os.path.join(tmp, "state")
        self.claude = os.path.join(tmp, "claude")
        os.makedirs(self.claude)
        # The real tree, except that the operator half of routing (the
        # profiles overlay and the review grade) is the fixture's, never the
        # live files: its roles/agents layers are empty (one of the live ones
        # may name the login running this suite; the cases assert what the
        # defaults and the local layer resolve to) and a checkout without
        # its instance data (tests/stripped_run.py) passes too.
        # runtime/claude-code is copied, not linked: the installer finds its
        # root by readlink -f on itself, so through a link it would resolve
        # from the real routing. .git is left out, so git at the fixture root
        # finds no repository; the linked subtrees still resolve into the
        # clone, so no case may run git inside them.
        root = os.path.join(tmp, "fabric")
        os.makedirs(os.path.join(root, "runtime"))
        for name in os.listdir(ROOT):
            if name not in ("routing", "runtime", ".git"):
                os.symlink(os.path.join(ROOT, name), os.path.join(root, name))
        for name in os.listdir(os.path.join(ROOT, "runtime")):
            if name != "claude-code":
                os.symlink(os.path.join(ROOT, "runtime", name), os.path.join(root, "runtime", name))
        shutil.copytree(os.path.join(ROOT, "runtime", "claude-code"), os.path.join(root, "runtime", "claude-code"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(os.path.join(ROOT, "routing"), os.path.join(root, "routing"),
                        ignore=shutil.ignore_patterns(*instance_fixtures.ROUTING_OPERATOR_IGNORE))
        # Classes that differ, so a case can tell which one answered: the
        # committed column has two models and one level for five classes.
        for name in ("capabilities.json", "effort.json"):
            shutil.copy2(os.path.join(HERE, "fixtures", "routing-distinct", name), os.path.join(root, "routing", name))
        instance_fixtures.write_routing_overlay(os.path.join(root, "routing"))
        self.env = {**os.environ, "AGENT_FABRIC_ROOT": root, "AGENT_FABRIC_STATE_DIR": self.state,
                    "CLAUDE_CONFIG_DIR": self.claude}
        self.env.pop("AGENT_FABRIC_LAUNCH_PROVIDER", None)  # an unlaunched session, whatever the runner is
        self.login = subprocess.run([sys.executable, os.path.join(ROOT, "runtime", "identity.py")],
                                    capture_output=True, text=True, env=self.env).stdout.strip() or os.getlogin()
        self.local = os.path.join(self.state, "agents", self.login, "model-profile.local.json")

    def run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True, env=self.env)

    def read(self) -> dict:
        return json.load(open(self.local, encoding="utf-8")) if os.path.exists(self.local) else {}

    def reviewer_model(self) -> str | None:
        path = os.path.join(self.claude, "agents", "code-review.md")
        if not os.path.exists(path):
            return None
        for line in open(path, encoding="utf-8"):
            if line.startswith("model: "):
                return line[len("model: "):].strip()
        return None


def test_list_shows_both_providers_with_sources(f: Fixture) -> None:
    p = f.run("list")
    assert p.returncode == 0, p.stderr
    assert "provider openrouter" in p.stdout and "provider anthropic" in p.stdout, p.stdout
    assert "(absent)" in p.stdout, "no local layer yet is said"
    assert "claude-opus-5[1m]" in p.stdout and "via the agent file" in p.stdout, p.stdout
    for word in ("haiku", "sonnet", "opus", "fable"):
        assert f" {word} " not in p.stdout and f"{word}\n" not in p.stdout, f"a tier alias leaked into the listing: {word}"
    j = json.loads(f.run("list", "--json").stdout)
    assert j["providers"]["anthropic"]["code-plan"]["model"] == "claude-fable-5-1"
    assert j["providers"]["openrouter"]["session"]["source"] == "defaults"
    assert not os.path.exists(f.local), "list writes nothing"


def test_set_writes_under_the_provider_and_nothing_else(f: Fixture) -> None:
    p = f.run("set", "--provider", "anthropic", "code-high", "claude-opus-5[1m]")
    assert p.returncode == 0, p.stderr
    assert f.read() == {"providers": {"anthropic": {"capabilities": {"code-high": "claude-opus-5[1m]"}}}}, f.read()
    assert "resolves now to claude-opus-5[1m] (from local)" in p.stdout, p.stdout
    p = f.run("set", "--provider", "openrouter", "code-low", "z-ai/glm-5.2")
    assert p.returncode == 0, p.stderr
    assert f.read()["providers"]["openrouter"] == {"capabilities": {"code-low": "z-ai/glm-5.2"}}
    p = f.run("set", "--provider", "anthropic", "session", "code-plan")
    assert p.returncode == 0 and f.read()["providers"]["anthropic"]["session"] == "code-plan", p.stderr
    j = json.loads(f.run("list", "--json").stdout)
    assert (j["providers"]["anthropic"]["session"]["model"], j["providers"]["anthropic"]["session"]["capability"]) == \
        ("claude-fable-5-1", "code-plan"), "a class-named session is that class's model"
    assert j["providers"]["openrouter"]["session"]["model"] == "deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim", "one provider's session is not the other's"
    assert j["providers"]["openrouter"]["code-low"]["model"] == "z-ai/glm-5.2@preset/glm2claude-shim"
    assert f.local.startswith(f.state), "the write is under the state dir"
    assert not os.path.exists(os.path.join(f.state, "routing")), "nothing shaped like the repo appears in state"


def test_unset_removes_and_prunes(f: Fixture) -> None:
    f.run("set", "--provider", "anthropic", "code-high", "claude-opus-5[1m]")
    p = f.run("unset", "--provider", "anthropic", "code-high")
    assert p.returncode == 0, p.stderr
    assert f.read() == {}, f.read()
    assert "claude-opus-5-5 (from capabilities.providers.anthropic)" in p.stdout, p.stdout


def test_vocabulary_is_the_class_and_the_providers_model(f: Fixture) -> None:
    p = f.run("set", "--provider", "anthropic", "code-high", "z-ai/glm-5.3")
    assert p.returncode == 1 and "not a native Claude id" in p.stderr, p.stderr
    p = f.run("set", "--provider", "anthropic", "code-high", "opus")
    assert p.returncode == 1 and "not a native Claude id" in p.stderr, "a tier alias is not a model"
    p = f.run("set", "--provider", "openrouter", "code-low", "haiku")
    assert p.returncode == 1 and "not an OpenRouter model id" in p.stderr, p.stderr
    p = f.run("set", "--provider", "anthropic", "opus", "claude-opus-5")
    assert p.returncode == 1 and "not a target on anthropic" in p.stderr and "code-plan" in p.stderr, p.stderr
    p = f.run("set", "--provider", "openrouter", "review", "z-ai/glm-5.3")
    assert p.returncode == 1 and "not a target on openrouter" in p.stderr, "the old class name is gone"
    assert not os.path.exists(f.local), "a refused set writes nothing"


def test_review_is_gated_on_both_providers_and_reaches_the_file(f: Fixture) -> None:
    p = f.run("set", "--provider", "openrouter", "code-review", "z-ai/glm-5.3-flash")
    assert p.returncode == 1 and "review-grade.json" in p.stderr, p.stderr
    p = f.run("set", "--provider", "anthropic", "code-review", "claude-haiku-4-5")
    assert p.returncode == 1 and "review-grade.json" in p.stderr, p.stderr
    assert not os.path.exists(f.local)
    p = f.run("set", "--provider", "anthropic", "code-review", "claude-opus-5")
    assert p.returncode == 0, p.stderr
    assert f.reviewer_model() == "claude-opus-5", "an unlaunched session is on anthropic: the pin is installed at once"
    p = f.run("unset", "--provider", "anthropic", "code-review")
    assert p.returncode == 0 and f.reviewer_model() == "claude-opus-5[1m]", "back to the column's pin"
    # Launched on the broker, the file carries that provider's composite.
    f.env["AGENT_FABRIC_LAUNCH_PROVIDER"] = "openrouter"
    p = f.run("set", "--provider", "openrouter", "code-review", "anthropic/claude-opus-5")
    assert p.returncode == 0, p.stderr
    assert f.reviewer_model() == "anthropic/claude-opus-5", f.reviewer_model()
    p = f.run("set", "--provider", "anthropic", "code-review", "claude-opus-5")
    assert p.returncode == 0 and "next launch" in p.stdout and f.reviewer_model() == "anthropic/claude-opus-5", \
        "the other provider's pin does not touch this launch's file"


def test_unlaunched_follows_the_last_launch(f: Fixture) -> None:
    """From a login shell (no launch environment), the files follow the
    provider the account last launched on, not anthropic (review of #91)."""
    os.makedirs(os.path.dirname(f.local), exist_ok=True)
    with open(os.path.join(os.path.dirname(f.local), "launch-provider.json"), "w") as fh:
        json.dump({"provider": "openrouter", "at": "x"}, fh)
    p = f.run("set", "--provider", "openrouter", "code-review", "anthropic/claude-opus-5")
    assert p.returncode == 0, p.stderr
    assert f.reviewer_model() == "anthropic/claude-opus-5", \
        ("the broker's pin reaches the file: the account last launched there", f.reviewer_model())
    p = f.run("set", "--provider", "anthropic", "code-review", "claude-opus-5")
    assert p.returncode == 0 and "next launch" in p.stdout and f.reviewer_model() == "anthropic/claude-opus-5", \
        "anthropic's pin waits for an anthropic launch"


def test_a_flat_local_file_is_migrated_on_first_write(f: Fixture) -> None:
    os.makedirs(os.path.dirname(f.local))
    json.dump({"session": "anthropic/claude-opus-5", "capabilities": {"code-low": "z-ai/glm-5.2"}}, open(f.local, "w"))
    p = f.run("set", "--provider", "anthropic", "code-high", "claude-opus-5[1m]")
    assert p.returncode == 0, p.stderr
    assert f.read() == {"providers": {
        "openrouter": {"session": "anthropic/claude-opus-5", "capabilities": {"code-low": "z-ai/glm-5.2"}},
        "anthropic": {"session": "claude-opus-5", "capabilities": {"code-high": "claude-opus-5[1m]"}}}}, f.read()
    assert "moved:" in p.stdout, p.stdout


def test_a_malformed_local_file_is_refused_not_rewritten(f: Fixture) -> None:
    os.makedirs(os.path.dirname(f.local))
    open(f.local, "w").write('{"session": null}\n')
    p = f.run("set", "--provider", "anthropic", "code-high", "claude-opus-5")
    assert p.returncode == 1 and "session is None" in p.stderr, p.stderr
    assert open(f.local).read() == '{"session": null}\n', "left for the hand"
    p = f.run("list")
    assert p.returncode == 1 and "session is None" in p.stderr


def test_seed_copies_the_merged_defaults_as_pins(f: Fixture) -> None:
    p = f.run("seed", "--provider", "openrouter")
    assert p.returncode == 0, p.stderr
    got = f.read()["providers"]["openrouter"]
    assert got["session"] == "deepseek/deepseek-v4-pro-0813" and "@preset" not in json.dumps(got), "the shim is derived, never seeded"
    assert got["capabilities"] == {"code-low": "z-ai/glm-5.3-flash", "code-medium": "z-ai/glm-5.2", "code-high": "deepseek/deepseek-v4-pro-0813",
                                   "code-plan": "deepseek/deepseek-v4-pro-0813", "code-review": "deepseek/deepseek-v4-pro-0813"}, got
    # The INTENT, not the level today's model happens to admit: on this
    # column code-medium asks `medium` and GLM 5.2 remaps it up to `high`,
    # so the two differ and seeding the wrong one is visible here (it was
    # not on anthropic, where intent == served for every class).
    assert got["effort"]["code-medium"] == "medium", got["effort"]
    # code-plan carries a committed acknowledgement for this column. That
    # is a compensation for one (provider, model) pair, not this agent's
    # choice, and freezing it into a layer that now outranks it would
    # outlive the model it was written for.
    assert "code-plan" not in got["effort"], got["effort"]
    assert "code-review" not in got["effort"], got["effort"]   # acknowledged on this column too
    assert "anthropic" not in f.read()["providers"], "only the provider asked for"
    p = f.run("seed", "--provider", "anthropic")
    assert p.returncode == 0, p.stderr
    got = f.read()["providers"]["anthropic"]
    # Effort is seeded with the model, because it is the same kind of
    # choice — but as the INTENT `seed` would freeze, never the level a
    # model happens to serve. code-low is absent by design: haiku
    # expresses no effort, and a seeded level there would be a decision
    # the model cannot carry out.
    assert got == {"session": "claude-opus-5-5", "capabilities": {
        "code-low": "claude-haiku-4-5-20251001", "code-medium": "claude-sonnet-5", "code-high": "claude-opus-5-5",
        "code-plan": "claude-fable-5-1", "code-review": "claude-opus-5[1m]"},
        "effort": {"code-medium": "medium", "code-high": "high",
                   "code-plan": "xhigh", "code-review": "xhigh"}}, got
    j = json.loads(f.run("list", "--json").stdout)
    assert j["providers"]["openrouter"]["code-low"]["source"] == "local", "a seeded value is now the agent's own"


def test_effort_is_a_target_that_layers_like_a_model(f: Fixture) -> None:
    """The owner's decision: effort layers exactly as a model id does, so
    `<class>-effort` is settable, unsettable and prunes the same way."""
    p = f.run("set", "--provider", "anthropic", "code-high-effort", "max")
    assert p.returncode == 0, p.stderr
    assert f.read()["providers"]["anthropic"]["effort"] == {"code-high": "max"}, f.read()
    j = json.loads(f.run("list", "--provider", "anthropic", "--json").stdout)
    row = j["providers"]["anthropic"]["code-high-effort"]
    assert row["model"] == "max" and row["source"] == "local", row
    # A model whose class expresses no effort still has no level to set on.
    out = f.run("list", "--provider", "anthropic").stdout
    assert "code-low-effort" in out and "expresses none" in out, out
    p = f.run("unset", "--provider", "anthropic", "code-high-effort")
    assert p.returncode == 0, p.stderr
    # It was the only choice in the file, so pruning takes the whole way
    # back out: no effort map, no anthropic layer, no providers at all.
    assert "providers" not in f.read(), f"nothing was pruned: {f.read()}"
    p = f.run("set", "--provider", "anthropic", "code-high-effort", "not-a-level")
    assert p.returncode != 0, "a value outside the vocabulary was accepted"


def test_a_write_waits_for_the_agent_lock(f: Fixture) -> None:
    # Per-agent state is written under agent_lock (agent-fabric ADR-003):
    # while another process holds agents/<login>/.lock, a set writes nothing.
    import fcntl
    lock_dir = os.path.dirname(f.local)
    os.makedirs(lock_dir, exist_ok=True)
    fd = os.open(os.path.join(lock_dir, ".lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        proc = subprocess.Popen([sys.executable, TOOL, "set", "--provider", "anthropic", "code-high", "claude-opus-5[1m]"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=f.env)
        time.sleep(1.5)
        assert proc.poll() is None and not os.path.exists(f.local), "set wrote while another process held the lock"
        fcntl.flock(fd, fcntl.LOCK_UN)
        out, err = proc.communicate(timeout=60)
    finally:
        os.close(fd)
    assert proc.returncode == 0, err
    assert f.read() == {"providers": {"anthropic": {"capabilities": {"code-high": "claude-opus-5[1m]"}}}}, f.read()
    assert [n for n in os.listdir(lock_dir) if n.startswith(".tmp-")] == [], "a temporary was left beside the file"


def main() -> int:
    cases = [
        test_list_shows_both_providers_with_sources,
        test_set_writes_under_the_provider_and_nothing_else,
        test_unset_removes_and_prunes,
        test_a_write_waits_for_the_agent_lock,
        test_vocabulary_is_the_class_and_the_providers_model,
        test_review_is_gated_on_both_providers_and_reaches_the_file,
        test_unlaunched_follows_the_last_launch,
        test_a_flat_local_file_is_migrated_on_first_write,
        test_a_malformed_local_file_is_refused_not_rewritten,
        test_seed_copies_the_merged_defaults_as_pins,
        test_effort_is_a_target_that_layers_like_a_model,
    ]
    failures = 0
    for case in cases:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                case(Fixture(tmp))
                print(f"  ok   {case.__name__}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL {case.__name__}: {exc}")
    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
