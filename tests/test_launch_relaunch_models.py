#!/usr/bin/env python3
"""tests/test_launch_relaunch_models.py — a relaunch in the SAME routing column
replays the original launch's --model and --fallback-model only when the target
provider can run them (launch.relaunch_args, j179). language-culture-ru was
declared anthropic after broker days; its fresh relaunch replayed the original
--model z-ai/glm-5.2@preset/glm2claude-shim, the launcher refused it and the
pane fell to a shell. The declared provider is stubbed as the identity (the
column move is the integration suite's, tests/test_launch_cli.py); routing is
the repository's own. Plain script: ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("fabric_launch_under_test", os.path.join(HERE, "tools", "fabric", "launch.py"))
launch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(launch)

GLM = "z-ai/glm-5.2@preset/glm2claude-shim"


def relaunch(args: list[str], root: str = HERE) -> tuple[list[str], str]:
    err = io.StringIO()
    real = launch.declared_provider_args
    launch.declared_provider_args = lambda a: list(a)
    try:
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(err):
            return launch.relaunch_args(args, root), err.getvalue()
    finally:
        launch.declared_provider_args = real


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + str(detail).replace("\n", "\n      "))
        fails += not good

    for provider in ("anthropic", "gateway"):
        print(f"same column, {provider}")
        out, said = relaunch(["--provider", provider, "--model", GLM, "--effort", "max", "--x"])
        check("a broker --model is dropped, the rest kept in order",
              out == ["--provider", provider, "--effort", "max", "--x"], out)
        check("…and said in one line naming it", said.count("\n") == 1 and GLM in said and "cannot run" in said, said)
        out, said = relaunch([f"--provider={provider}", f"--model={GLM}", "--fallback-model", GLM])
        check("the = spelling and --fallback-model go too", out == [f"--provider={provider}"], out)
        out, said = relaunch(["--provider", provider, "--model", "claude-sonnet-5", "--fallback-model", "opus"])
        check("a model valid for the target stays (a person's choice), nothing said",
              out == ["--provider", provider, "--model", "claude-sonnet-5", "--fallback-model", "opus"] and said == "", (out, said))
        out, said = relaunch(["--provider", provider, "--model", "claude-sonnet-5", "--fallback-model", GLM])
        check("each flag is judged alone: the valid one stays, the foreign one goes",
              out == ["--provider", provider, "--model", "claude-sonnet-5"], out)

    print("same column, openrouter")
    out, said = relaunch(["--provider", "openrouter", "--model", GLM])
    check("a broker model stays on the broker", out == ["--provider", "openrouter", "--model", GLM] and said == "", (out, said))
    out, said = relaunch(["--provider", "openrouter", "--model", "claude-opus-5-5"])
    check("a native Claude id there is what the broker refuses: dropped", out == ["--provider", "openrouter"], out)

    print("what cannot be judged")
    out, said = relaunch(["--provider", "anthropic", "--model"])
    check("a trailing bare --model is left to the launch's own parse", out == ["--provider", "anthropic", "--model"], out)
    out, said = relaunch(["--provider", "anthropic", "--model", GLM], root="/nonexistent-root")
    check("routing that cannot be loaded leaves the arguments as they were", out == ["--provider", "anthropic", "--model", GLM], out)
    out, said = relaunch(["--provider", "anthropic", "--", "--model", GLM])
    check("nothing after -- is an option", out == ["--provider", "anthropic", "--", "--model", GLM], out)

    out, said = relaunch(["--provider", "anthropic", "--model", "claude-sonnet-5", "--", "--model", GLM])
    check("a valid --model before -- is not judged by a foreign one after it",
          out == ["--provider", "anthropic", "--model", "claude-sonnet-5", "--", "--model", GLM] and said == "", (out, said))
    out, said = relaunch(["--provider", "anthropic", "--model", GLM, "--model", "opus"])
    check("each occurrence on its own value: the foreign one goes, the valid one stays",
          out == ["--provider", "anthropic", "--model", "opus"], out)
    real_load, launch.load_routing = launch.load_routing, lambda path, root: object()
    try:
        out, said = relaunch(["--provider", "anthropic", "--model", "claude-sonnet-5"])
    finally:
        launch.load_routing = real_load
    check("a routing module of another shape leaves the arguments as they were",
          out == ["--provider", "anthropic", "--model", "claude-sonnet-5"], out)

    print(f"\ntest_launch_relaunch_models: {'OK' if not fails else f'{fails} FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
