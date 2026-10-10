#!/usr/bin/env python3
"""tools/fabric/install_agent_files.py — install THIS account's
capability-class agent files,
~/.claude/agents/{code-low,code-medium,code-high,code-plan,code-review}.md,
from runtime/claude-code/agents/, with the routed pin and effort applied —
and, on a language-culture login, the locale worker (below). Ported from
runtime/claude-code/install-agent-files.sh (ADR-040 §5), which is now its
shim; its bash test, runtime/claude-code/test_install-agent-files.sh, is the
parity oracle.

CONTRACT, frozen from the bash (ADR-040 §5 rule 1):

  argv         [--provider openrouter|anthropic | --provider=P] [--dry-run]
               anything else: "install-agent-files: unknown argument X" on
               stderr, exit 2 (as does a --provider with no value)
  environment  AGENT_FABRIC_LAUNCH_PROVIDER (the default provider; else
               the provider this account last launched on, from
               <state>/agents/<login>/launch-provider.json, which the
               launcher writes; else anthropic), CLAUDE_CONFIG_DIR (else ~/.claude for the agent
               files and the user settings; else $HOME for .claude.json),
               HOME. AGENT_FABRIC_ROOT is SET for the children, to this
               checkout (the module's own location), never read.
  stdout       one line per file: "  =  dest" (already current),
               "  +  dest" (written; "  +  dest (would write)" on a dry
               run), "     (kept the previous file as ...)", "  -  dest
               (removed: ...)" ("would remove" on a dry run), the lines of
               runtime/mcp/websearch-locale/install.py, and last
               "agent files (P): N written, M already current."
  stderr       the routing and install.py children's own, and the refusals
  exit         0; 1 when routing.py pins or efforts fails (nothing is
               written) or a class source is missing; 2 on a bad argument;
               install.py's own non-zero status when it fails, after the
               class files and the worker were written (as the bash did)
  writes       ~/.claude/agents/<class>.md for the five classes (the repo
               file, `model:` replaced by the routed pin and an `effort:`
               line added after it, where routing resolves one), a
               person's version of a file it replaces, every time it
               differs from the fabric's last write, under the first free
               <file>.before-agent-fabric[.N] with its own mode, the hash of
               each file written or found current in
               <state>/agents/<login>/fabric-written.json (and its .lock),
               ~/.claude/agents/locale-worker.md (language-culture
               login with an authored worker for its locale; removed by the
               agent-fabric marker anywhere else), the locale MCP entry in
               .claude.json and the WebSearch deny in settings.json (both
               through install.py), and the removal of the retired
               blind-reviewer.md. All with mode 644. Nothing under
               --dry-run.
  calls        routing.py pins --me --provider P; routing.py efforts --me
               --provider P; runtime/identity.py --role; install.py
               <claude.json> set|remove, <settings.json>
               deny-websearch|allow-websearch
  relied on    launcher (tools/fabric/launch.py): exit status only, stdout
               discarded; bootstrap.sh: plain and --dry-run, stdout shown;
               bin/fabric-model (tools/fabric/model_profile.py): stdout
               shown or discarded, non-zero status reported.

The notes below are carried from the bash.

WHY A FILE CARRIES THE PIN. The review class rides the same tier alias
as code-plan (fable): the Agent tool's `model` takes only the four
aliases, and one alias carries one export, so through the export the
reviewer would follow code-plan (as it once followed code-high on opus,
2026-09-13). The one route left (verified live on plain claude,
2026-09-15): the agent file's `model:` line decides when the dispatch
leaves `model` unset, and the dispatch guard drops the dispatch's alias
under a fabric launch after checking it was `fable`. The coding classes
ride the exported aliases and keep the repo file's alias line; the pin
here is the review class's alone, from routing, so there is one source.
One file serves one launch at a time: two sessions of one account on
different providers would rewrite it in turn, which the guard catches.
"""
from __future__ import annotations

import json
import os
import pwd
import re
import subprocess
import sys
import tempfile

# The fabric is the one the shim was run from, as the bash found it from its
# own place: abspath keeps the path the shim gave, so a fabric whose tools/
# is a link elsewhere is still itself, not where the link points.
FABRIC_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import fabric_writes  # noqa: E402
import roots  # noqa: E402

CLASS_FILES = ("code-low.md", "code-medium.md", "code-high.md", "code-plan.md", "code-review.md")
MARKER = b"agent-fabric"
MODEL_LINE = re.compile(rb"^model: .*", re.M)


def say(line: str) -> None:
    print(line, flush=True)


class WriteError(Exception):
    """A file that could not be written or removed: one line, exit 1, as
    install(1) and rm(1) said it under the bash (review of #86)."""


def _read(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def marked(path: str) -> bool:
    try:
        return MARKER in _read(path)
    except OSError:
        return False


def home() -> str:
    return os.path.expanduser("~")


def login() -> str:
    return pwd.getpwuid(os.getuid()).pw_name


class Installer:
    def __init__(self, provider: str, dry_run: bool, root: str = FABRIC_ROOT) -> None:
        self.provider, self.dry_run, self.root = provider, dry_run, root
        self.changed = 0
        self.same = 0

    def put(self, dest: str, content: bytes) -> None:
        if os.path.isfile(dest) and _read(dest) == content:
            self.same += 1
            say(f"  =  {dest}")
            if not self.dry_run:
                fabric_writes.record(dest, content)
            return
        if self.dry_run:
            say(f"  +  {dest} (would write)")
            return
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            # A person's version is kept, every time it differs from what the
            # fabric last wrote, under a name of its own. Backing up only once
            # lost a person's later edit; the marker alone re-made the backup
            # on every run and replaced the user's original with the fabric's
            # own previous file (found when effort: started rewriting files
            # that were already the fabric's). fabric_writes has both.
            backup = fabric_writes.keep_person_version(dest)
            if backup:
                say(f"     (kept the previous file as {backup})")
            # install(1) replaces the destination rather than writing through
            # it; a rename does the same, and never leaves a half-written agent
            # file for a session starting at that moment.
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(dest), prefix=".iaf-")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(content)
                os.chmod(tmp, 0o644)
                os.replace(tmp, dest)
            except BaseException:
                os.unlink(tmp)
                raise
        except OSError as e:
            raise WriteError(f"install-agent-files: cannot write {dest}: {e.strerror or e}") from None
        fabric_writes.record(dest, content)
        self.changed += 1
        say(f"  +  {dest}")

    def remove(self, path: str, reason: str) -> None:
        if self.dry_run:
            say(f"  -  {path} (would remove: {reason})")
        else:
            try:
                os.remove(path)
            except OSError as e:
                raise WriteError(f"install-agent-files: cannot remove {path}: {e.strerror or e}") from None
            say(f"  -  {path} (removed: {reason})")
            self.changed += 1

    def route(self, sub: str) -> str:
        r = subprocess.run([sys.executable, os.path.join(self.root, "tools", "fabric", "routing.py"), sub, "--me",
                            "--provider", self.provider], stdout=subprocess.PIPE, text=True,
                           env={**os.environ, "AGENT_FABRIC_ROOT": self.root}, check=False)
        # Captured whole and its status checked, NOT streamed through a
        # reader: a routing.py that raised once left the map empty, every
        # class lost its pin or its level, and the script still printed
        # "N written" and exited 0 (review of 2026-09-23, F8; the pins loop
        # had the same hole since long before effort existed).
        # bootstrap.sh calls this without the launcher's prior validation,
        # so it is the first thing a bad local layer reaches. Each call is
        # its own check.
        if r.returncode != 0:
            print(f"install-agent-files: routing.py {sub} failed; refusing to write agent files with no routing.",
                  file=sys.stderr)
            sys.exit(1)
        return r.stdout

    def run(self) -> int:
        pins: dict[str, str] = {}
        for line in self.route("pins").splitlines():
            parts = line.split(None, 2)
            if parts:
                pins[parts[0]] = parts[2] if len(parts) > 2 else ""
        # ONE LAUNCH OF AN ACCOUNT AT A TIME, now for every class. Before effort,
        # only code-review.md differed between providers, and agent-dispatch-guard.sh
        # catches that one by comparing its `model:` with the launch's resolution.
        # Effort is written into ALL five files per provider, so an openrouter
        # launch leaves GLM's clamp in code-medium.md and an anthropic session
        # dispatching afterwards runs at a level nothing chose for it — and no
        # guard compares that. Extending the guard per dispatched class is the
        # real fix and is deliberately NOT done here: it means buffering the hook's
        # stdin so the class's file can be read before jq sees the call, and a
        # half-made change to that fence is worse than a documented constraint
        # (review of 2026-09-23, F7). Until then: run one launch of an account at a
        # time, or re-run `bin/fabric-model apply` from the session you are in.
        #
        # The agent file is the ONLY per-class channel for effort: the Agent tool
        # takes no effort on a dispatch (2.1.280, read back), and the environment
        # variable would reach every subagent at once and flatten the per-class
        # decision. So the level routing resolves for each class is written into
        # its frontmatter here, exactly as the review class's model is.
        # A class whose model expresses no effort gets NO line — absent is not the
        # same as a default, and writing one would claim a decision nobody made.
        efforts: dict[str, str] = {}
        for line in self.route("efforts").splitlines():
            parts = line.split(None, 2)
            if len(parts) >= 2 and parts[1] != "-":
                efforts[parts[0]] = parts[1]
        claude_home = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(home(), ".claude")
        for f in CLASS_FILES:
            klass = f[:-3]
            pin, effort = pins.get(klass, ""), efforts.get(klass, "")
            src = os.path.join(self.root, "runtime", "claude-code", "agents", f)
            try:
                content = _read(src)
            except OSError as e:
                print(f"install-agent-files: cannot read {src}: {e.strerror}", file=sys.stderr)
                return 1
            if pin:
                content = MODEL_LINE.sub(lambda m: b"model: " + pin.encode(), content, count=1)
            if effort:
                # After `model:`, so the two routed values sit together; the
                # committed sources carry no effort: line, and lint refuses one.
                content = MODEL_LINE.sub(lambda m: m.group(0) + b"\neffort: " + effort.encode(), content, count=1)
            self.put(os.path.join(claude_home, "agents", f), content)
        role = self.role()
        suffix = login().rsplit("-", 1)[-1]
        self.locale_worker(claude_home, role, suffix)
        rc = self.locale_search(claude_home, role, suffix)
        if rc:
            return rc
        # The review class was installed as blind-reviewer.md until 2026-09-15; a
        # copy of ours left there would offer the retired type beside the new one.
        old = os.path.join(claude_home, "agents", "blind-reviewer.md")
        if os.path.isfile(old) and marked(old):
            if self.dry_run:
                say(f"  -  {old} (would remove: retired name of code-review)")
            else:
                # Its own line, not remove()'s "removed: …", which the oracle
                # pins; the failure is remove()'s one line all the same.
                try:
                    os.remove(old)
                except OSError as e:
                    raise WriteError(f"install-agent-files: cannot remove {old}: {e.strerror or e}") from None
                say(f"  -  {old} (retired name of code-review)")
                self.changed += 1
        say(f"agent files ({self.provider}): {self.changed} written, {self.same} already current.")
        return 0

    def role(self) -> str:
        try:
            r = subprocess.run([sys.executable, os.path.join(self.root, "runtime", "identity.py"), "--role"],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                               env={**os.environ, "AGENT_FABRIC_ROOT": self.root}, check=False)
        except OSError:
            return ""
        return r.stdout.rstrip("\n") if r.returncode == 0 else ""

    def locale_worker(self, claude_home: str, role: str, suffix: str) -> None:
        # The locale worker: the language-culture role's subagent, one inert tool, whose
        # system prompt is the locale's language (docs/adr/ADR-027-language-and-culture-shape-the-work-the-bridge.md).
        # Installed as ~/.claude/agents/locale-worker.md on a login of that role
        # whose name ends in a locale the fabric authored
        # (identities/roles/language-culture/locale/<suffix>/worker.md); removed —
        # by the `agent-fabric` marker in its description, as blind-reviewer.md
        # below — from any other login, and from one whose locale has no worker,
        # so a rebind never serves another locale's worker. No per-provider pin:
        # the worker shares no alias with another class, so its model line rides
        # as authored (the reviewer's file pin exists only because fable is
        # code-plan's too). No routed EFFORT either, for the same reason — it is
        # not a capability class, so routing/effort.json has nothing to say about
        # it and it runs at whatever its model does by itself. Lint refuses a
        # hand-written `effort:` in its source (one writer, as for the classes),
        # so a level here would need a routed home first: the absence is a
        # decision, not an oversight (re-review of 2026-09-23).
        src = os.path.join(roots.locale_dir("language-culture", suffix, engine=self.root), "worker.md")
        dest = os.path.join(claude_home, "agents", "locale-worker.md")
        if role == "language-culture" and os.path.isfile(src):
            self.put(dest, _read(src))
        elif os.path.isfile(dest) and marked(dest):
            self.remove(dest, f"role is {role or 'unbound'}, or no worker authored for locale {suffix}")

    def locale_search(self, claude_home: str, role: str, suffix: str) -> int:
        # The locale search tools: an MCP server with one tool per engine the
        # locale file configures — Google's results through SerpAPI, located in
        # the locale, and Brave as a second index (bin/fabric-websearch-locale, entered by runtime/mcp/websearch-locale/install.py), in the login's user-scope
        # configuration (~/.claude.json, or $CLAUDE_CONFIG_DIR/.claude.json) on a
        # language-culture login whose locale has a locale.json; removed — by the
        # server path in its command or args — from any other. The key it needs is synced,
        # never written here (docs/adr/ADR-027-language-and-culture-shape-the-work-the-bridge.md §5 rule 13).
        locale_file = os.path.join(roots.locale_dir("language-culture", suffix, engine=self.root), "locale.json")
        claude_json = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or home(), ".claude.json")
        mcp = os.path.join(self.root, "runtime", "mcp", "websearch-locale")
        flags = ["--dry-run"] if self.dry_run else []
        # …and, on that login, the harness's own WebSearch denied in the user
        # settings (the launcher removes it at exec; this is the fence for a
        # session launched otherwise): a login that searches through its locale
        # searches through that alone (the CEO, 2026-09-17).
        settings = os.path.join(claude_home, "settings.json")
        if role == "language-culture" and os.path.isfile(locale_file):
            calls = [[claude_json, "set", os.path.join(self.root, "bin", "fabric-websearch-locale"), locale_file], [settings, "deny-websearch"]]
        else:
            calls = [[claude_json, "remove"], [settings, "allow-websearch"]]
        outs = []
        for call in calls:
            r = subprocess.run([sys.executable, os.path.join(mcp, "install.py"), *call, *flags],
                               stdout=subprocess.PIPE, text=True, check=False)
            if r.returncode != 0:
                return r.returncode
            outs.append(r.stdout.rstrip("\n"))
        lines = [ln for ln in "\n".join(o for o in outs if o).split("\n") if ln != ""]
        for line in lines:
            say(line)
            if line.startswith("  +  ") and "would write" not in line:
                self.changed += 1
            if line.startswith("  =  "):
                self.same += 1
        return 0


LAUNCH_RECORD = "launch-provider.json"
PROVIDERS = ("anthropic", "openrouter")


def last_launch_provider() -> str | None:
    """The provider this account's last launch installed for. A run with no
    provider of its own — bootstrap from the control agent, fabric-ctl
    upgrade, fabric-model apply — wrote the agent files for anthropic, and a
    session on the broker then had a reviewer file for the other provider,
    which the dispatch guard refused (2026-10-01). Unreadable or unknown is
    None: the default stands."""
    try:
        with open(os.path.join(fabric_writes.state_dir(), LAUNCH_RECORD), encoding="utf-8") as f:
            p = json.load(f).get("provider")
    except (OSError, ValueError, AttributeError):
        return None
    return p if p in PROVIDERS else None


def main(argv: list[str]) -> int:
    dry_run = False
    provider = os.environ.get("AGENT_FABRIC_LAUNCH_PROVIDER") or last_launch_provider() or "anthropic"
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--dry-run":
            dry_run, i = True, i + 1
        elif a == "--provider" and i + 1 < len(argv):
            provider, i = argv[i + 1], i + 2
        elif a.startswith("--provider="):
            provider, i = a[len("--provider="):], i + 1
        else:
            print(f"install-agent-files: unknown argument {a}", file=sys.stderr)
            return 2
    try:
        return Installer(provider, dry_run).run()
    except WriteError as e:
        print(e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
