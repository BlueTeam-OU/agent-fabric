#!/usr/bin/env python3
"""runtime/github/actions-health.sh, through the shim with gh and curl
mocked on PATH. Ported case for case from a managed project's
tools/gh/test_actions-health.sh (its script the oracle, ADR-040 §5): the
value of the tool is a decision — spend minutes, or don't — so each state
must produce the RIGHT exit, and "I could not find out" (2) must never be
mistaken for "GitHub is broken" (1). Then what the port adds: --json, the
setting a project's forwarder names, and the parse failures the bash read
as plausible numbers. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "runtime", "github", "actions-health.sh")

# githubstatus.com, from a fixture. status_unreachable: curl fails.
CURL = r'''#!/usr/bin/env bash
set -uo pipefail
[[ -f "$MOCK_STATE/status_unreachable" ]] && exit 7
if [[ -f "$MOCK_STATE/status_malformed" ]]; then
  cat "$MOCK_STATE/status_malformed"; exit 0
fi
status="$(cat "$MOCK_STATE/actions_status" 2>/dev/null || echo operational)"
incident="$(cat "$MOCK_STATE/incident" 2>/dev/null || true)"
printf '{"components":[{"name":"Actions","status":"%s"}],"incidents":[' "$status"
[[ -n "$incident" ]] && printf '{"name":"%s"}' "$incident"
printf ']}\n'
'''

# gh: the working copy (owner, name, visibility), one repository's
# visibility, and the billing usage — the transport the port speaks.
GH = r'''#!/usr/bin/env bash
set -uo pipefail
if [[ "${1:-}" == "repo" ]]; then
  if [[ " $* " == *" name "* ]]; then
    if [[ -f "$MOCK_STATE/this_repo_name" ]]; then cat "$MOCK_STATE/this_repo_name"; else echo "openrepo"; fi; exit 0
  fi
  if [[ " $* " == *" isPrivate "* ]]; then
    [[ -f "$MOCK_STATE/this_repo_unreadable" ]] && exit 1
    [[ -f "$MOCK_STATE/this_repo_public" ]] && { echo false; exit 0; }
    echo true; exit 0
  fi
  echo "testorg"; exit 0
fi
if [[ "${1:-}" == "api" && "${2:-}" == repos/* ]]; then
  name="${2#repos/testorg/}"
  [[ "$name" == "$2" || "$name" == */* ]] && { echo '{"message":"Not Found","status":"404"}'; exit 1; }
  if grep -qx "$name" "$MOCK_STATE/public_repos" 2>/dev/null; then echo false; exit 0; fi
  if grep -qx "$name" "$MOCK_STATE/unknown_repos" 2>/dev/null; then echo '{"message":"Not Found","status":"404"}'; exit 1; fi
  if grep -qx "$name" "$MOCK_STATE/silent_repos" 2>/dev/null; then exit 1; fi
  echo true; exit 0
fi
if [[ "${1:-}" == "api" ]]; then
  [[ -f "$MOCK_STATE/billing_unreadable" ]] && exit 1
  # Refused with an error body on stdout, as gh does for a 403 or 404.
  [[ -f "$MOCK_STATE/billing_error_body" ]] && { echo '{"message":"Not Found","status":"404"}'; exit 1; }
  printf '%s\n' "${2:-}" > "$MOCK_STATE/last_request"
  if [[ -f "$MOCK_STATE/billing_raw" ]]; then cat "$MOCK_STATE/billing_raw"; exit 0; fi
  net="$(cat "$MOCK_STATE/billing_net" 2>/dev/null || echo 0)"
  mins="$(cat "$MOCK_STATE/billing_mins" 2>/dev/null || echo 100)"
  storage_net="$(cat "$MOCK_STATE/billing_storage_net" 2>/dev/null || echo 0)"
  this_month="$(date -u +%Y-%m)-01"
  prev_month="$(date -u -d "$(date -u +%Y-%m-01) -1 day" +%Y-%m)-01"
  prev_mins="$(cat "$MOCK_STATE/billing_prev_mins" 2>/dev/null || echo 0)"
  public_mins="$(cat "$MOCK_STATE/billing_public_mins" 2>/dev/null || echo 0)"
  bare_mins="$(cat "$MOCK_STATE/billing_bare_mins" 2>/dev/null || echo 0)"
  qpub_mins="$(cat "$MOCK_STATE/qualified_public_mins" 2>/dev/null || echo 0)"
  self_net="$(cat "$MOCK_STATE/self_net" 2>/dev/null || echo 0)"
  self_mins="$( [[ -f "$MOCK_STATE/self_net" ]] && echo 5 || echo 0 )"
  self_row_name="$(cat "$MOCK_STATE/self_row_name" 2>/dev/null || echo openrepo)"
  printf '{"usageItems":[{"product":"actions","sku":"Actions Linux","unitType":"Minutes","quantity":%s,"netAmount":%s,"date":"%s","repositoryName":"app"},{"product":"actions","sku":"Actions Linux","unitType":"Minutes","quantity":%s,"netAmount":0,"date":"%s","repositoryName":"app"},{"product":"actions","sku":"Actions Linux","unitType":"Minutes","quantity":%s,"netAmount":0,"date":"%s","repositoryName":"openrepo"},{"product":"actions","sku":"Actions Linux","unitType":"Minutes","quantity":'"$bare_mins"',"netAmount":0},{"product":"actions","sku":"Actions Linux","unitType":"Minutes","quantity":'"$qpub_mins"',"netAmount":0,"date":"'"$this_month"'","repositoryName":"testorg/openrepo"},{"product":"actions","sku":"Actions Linux 16-core","unitType":"Minutes","quantity":'"$self_mins"',"netAmount":'"$self_net"',"date":"'"$this_month"'","repositoryName":"'"$self_row_name"'"},{"product":"actions","sku":"Actions Storage","unitType":"GigabyteHours","quantity":5,"netAmount":%s,"date":"%s","repositoryName":"app"}]}\n' \
    "$mins" "$net" "$this_month" "$prev_mins" "$prev_month" "$public_mins" "$this_month" "$storage_net" "$this_month"
  exit 0
fi
exit 1
'''


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with tempfile.TemporaryDirectory() as sandbox:
        bin_, state = os.path.join(sandbox, "bin"), os.path.join(sandbox, "state")
        os.makedirs(bin_)
        os.makedirs(state)
        for name, text in (("curl", CURL), ("gh", GH)):
            with open(os.path.join(bin_, name), "w", encoding="utf-8") as fh:
                fh.write(text)
            os.chmod(os.path.join(bin_, name), 0o755)
        # Every invocation states its allowance: an ambient one would make
        # these pass or fail with the shell that launched them.
        base = {k: v for k, v in os.environ.items()
                if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_", "GH_")) and k != "GIT_DIR"}
        base.update(PATH=bin_ + os.pathsep + os.environ.get("PATH", ""), MOCK_STATE=state)
        if os.environ.get("AGENT_FABRIC_PYTHON"):
            base["AGENT_FABRIC_PYTHON"] = os.environ["AGENT_FABRIC_PYTHON"]
        out = {"text": "", "rc": -1}

        def put(name: str, text: str = "") -> None:
            with open(os.path.join(state, name), "w", encoding="utf-8") as fh:
                fh.write(text)

        def reset() -> None:
            for name in os.listdir(state):
                os.remove(os.path.join(state, name))
            put("actions_status", "operational\n")
            put("billing_net", "0\n")
            put("billing_mins", "100\n")

        def invoke(*args: str, allowance: str | None = None, **env: str) -> None:
            e = dict(base, **env)
            if allowance is not None:
                e["AGENT_FABRIC_ACTIONS_INCLUDED_MINUTES"] = allowance
            r = subprocess.run([TOOL, *args], env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, timeout=120)
            out["text"], out["rc"] = r.stdout, r.returncode

        def rc(label: str, want: int) -> None:
            check(label, out["rc"] == want, f"expected exit {want}, got {out['rc']}\n{out['text']}")

        def has(label: str, text: str) -> None:
            check(label, text in out["text"], f"output lacked {text!r}\n{out['text']}")

        def lacks(label: str, text: str) -> None:
            check(label, text not in out["text"], f"output unexpectedly contained {text!r}\n{out['text']}")

        def requested(label: str, text: str) -> None:
            try:
                with open(os.path.join(state, "last_request"), encoding="utf-8") as fh:
                    req = fh.read()
            except OSError:
                req = ""
            check(label, text in req, f"request lacked {text!r}: {req!r}")

        now = datetime.datetime.now(datetime.timezone.utc)

        print("actions-health: a healthy platform says go")
        reset()
        invoke()
        rc("exits 0", 0)
        has("says OK", "OK — Actions operational")
        has("quotes the minutes", "100 minutes used")

        print("actions-health: the previous month's minutes are not this period's")
        reset()
        put("billing_mins", "3000\n")
        put("billing_prev_mins", "900\n")
        invoke(allowance="3500")
        rc("exits 0 — this month alone is under the allowance", 0)
        has("quotes this month only", "3000 of 3500 minutes used")
        lacks("never adds the previous month", "3900 of")
        requested("names the year on the request", f"year={now.year}")
        requested("names the month on the request", f"month={now.month}")

        print("actions-health: a PUBLIC repository's minutes do not count toward the allowance")
        reset()
        put("billing_mins", "42406\n")
        put("billing_public_mins", "8613\n")
        put("public_repos", "openrepo\n")
        invoke(allowance="50000")
        rc("exits 0 — the private repositories are under the allowance", 0)
        has("quotes the private sum only", "42406 of 50000 minutes used")
        lacks("never adds the public repository", "51019 of")
        reset()
        put("billing_mins", "42406\n")
        put("billing_public_mins", "8613\n")
        invoke(allowance="50000")
        rc("the same minutes on a private repository exit 1", 1)
        has("and the sum includes them", "51019 of 50000")
        reset()
        put("billing_mins", "42406\n")
        put("billing_public_mins", "8613\n")
        put("unknown_repos", "openrepo\n")
        invoke(allowance="50000")
        rc("a repository the lookup cannot read (404) is counted", 1)
        has("and the sum includes it", "51019 of 50000")
        reset()
        put("billing_mins", "42406\n")
        put("billing_public_mins", "8613\n")
        put("silent_repos", "openrepo\n")
        invoke(allowance="50000")
        rc("a lookup that fails with no output is counted too", 1)

        print("actions-health: billed minutes are named even with allowance to spare")
        reset()
        put("billing_net", "7.50\n")
        put("billing_mins", "100\n")
        invoke(allowance="3000")
        rc("billed under the allowance is still degraded", 1)
        has("  and says money is moving", "is billing")
        has("  while naming the room that remains", "100 of 3000")
        lacks("  and does not report plain OK", "remaining.")

        print("actions-health: --org naming another owner is not answered for this working copy")
        reset()
        put("this_repo_public")
        put("billing_net", "87.384\n")
        invoke("--org", "otherorg")
        rc("a public working copy, --org otherorg billing: exits 1", 1)
        lacks("  not the public-repository answer", "this repository is public")
        invoke("--org", "testorg")
        rc("  …while --org naming its own owner keeps the public answer", 0)

        print("actions-health: run from a PUBLIC repository, billing cannot hold a run")
        reset()
        put("this_repo_public")
        put("billing_net", "87.384\n")
        put("billing_mins", "60000\n")
        invoke()
        rc("billed overage elsewhere, no allowance configured: exits 0", 0)
        has("says the repository is public", "this repository is public and none of its minutes bill")
        has("quotes the private usage as context", "60000 minutes this period, $87.384 billing as overage")
        lacks("never DEGRADED", "DEGRADED")
        invoke(allowance="50000")
        rc("past the allowance and billed: still exits 0", 0)
        put("billing_net", "0\n")
        invoke(allowance="50000")
        rc("past the allowance and NOT billed: still exits 0", 0)
        put("actions_status", "major_outage\n")
        invoke()
        rc("a degraded platform still stops the work", 1)
        reset()
        put("this_repo_public")
        put("billing_unreadable")
        invoke()
        rc("billing unreadable: still answers, exits 0", 0)
        has("and says why it can", "(Billing API unreadable: a larger runner")
        reset()
        put("this_repo_unreadable")
        put("billing_net", "87.384\n")
        invoke()
        rc("a visibility that cannot be read is private: billed exits 1", 1)

        print("actions-health: a row with no date and no repositoryName is counted")
        reset()
        put("billing_mins", "100\n")
        put("billing_bare_mins", "500\n")
        invoke(allowance="3000")
        rc("exits 0", 0)
        has("and the sum includes it", "600 of 3000 minutes used")

        print("actions-health: --help prints the whole header")
        reset()
        invoke("--help")
        rc("exits 0", 0)
        has("down to the exit codes", "2  invocation problem")
        has("and the header's last line", "would stop work for no reason.")
        lacks("and no code after it", "from __future__")
        has("names the --json fields", "own_net, included, remaining}")

        print("actions-health: a bad allowance is exit 2 before any network answer")
        for st in ("this_repo_public", "billing_unreadable", "major_outage"):
            reset()
            if st == "major_outage":
                put("actions_status", "major_outage\n")
            else:
                put(st)
            invoke(allowance="abc")
            rc(f"{st}: exits 2", 2)
            has("  and names the setting", "must be a positive number")

        print("actions-health: an owner-qualified repositoryName is looked up once, unprefixed")
        reset()
        put("billing_mins", "42406\n")
        put("qualified_public_mins", "8613\n")
        put("public_repos", "openrepo\n")
        invoke(allowance="50000")
        rc("a public repository named org/name is not counted: exits 0", 0)
        has("quotes the private sum only", "42406 of 50000 minutes used")

        print("actions-health: a public repository's OWN billed minutes are a cost")
        reset()
        put("this_repo_public")
        put("self_net", "0.75\n")
        invoke()
        rc("its own billed minutes: exits 1", 1)
        has("names the cost", "$0.75 of its own minutes bill this period")
        lacks("never the free-runs line", "cost nothing")
        put("self_row_name", "testorg/openrepo\n")
        invoke()
        rc("…also when its row names it owner-qualified: exits 1", 1)
        os.remove(os.path.join(state, "self_row_name"))
        put("this_repo_name", "otherrepo\n")
        invoke()
        rc("another repository's billed row is not this one's: exits 0", 0)
        put("this_repo_name", "")
        invoke()
        rc("its name unread: exits 0", 0)
        has("and says its own billing was not checked", "its own billing could not be checked")

        print("actions-health: a degraded Actions component stops the work")
        reset()
        put("actions_status", "major_outage\n")
        put("incident", "Incident with Actions\n")
        invoke()
        rc("exits 1", 1)
        has("names the status", "major_outage")
        has("names the incident", "Incident with Actions")
        has("says not to spend", "do not spend minutes")

        print("actions-health: only BILLED MINUTES count as paid overage")
        reset()
        put("billing_net", "0\n")
        put("billing_storage_net", "9.99\n")
        put("billing_mins", "3200\n")
        invoke(allowance="3000")
        rc("storage billing does not clear a spent allowance", 1)
        has("still names the allowance", "allowance is spent")
        has("and says runners stop", "stop getting runners")
        lacks("and claims no overage", "billing as overage")

        print("actions-health: billed minutes with no configured allowance is degraded")
        reset()
        put("billing_net", "13.35\n")
        put("billing_mins", "3200\n")
        invoke()
        rc("exits 1, not 0", 1)
        has("names the overage", "billing as overage")
        has("says it blocks nothing", "blocks nothing")
        has("still flags the unknown", "Allowance size unknown")

        print("actions-health: billed overage is a cost, not a block")
        reset()
        put("billing_net", "13.35\n")
        put("billing_mins", "3200\n")
        invoke(allowance="3000")
        rc("exits 1", 1)
        has("says it blocks nothing", "blocks nothing")
        has("quotes usage AND limit", "3200 of 3000 minutes used")
        lacks("does not claim runners stop", "stop getting runners")

        print("actions-health: a spent allowance stops the work")
        reset()
        put("billing_net", "0\n")
        put("billing_mins", "3200\n")
        invoke(allowance="3000")
        rc("exits 1", 1)
        has("names the allowance", "allowance is spent")
        has("says runners stop", "stop getting runners")

        print("actions-health: a spent allowance is caught even when NOTHING is billed")
        reset()
        put("billing_net", "0\n")
        put("billing_mins", "3025\n")
        invoke(allowance="3000")
        rc("exits 1 despite $0 billed", 1)
        has("names the allowance", "allowance is spent")
        has("quotes usage AND limit", "3025 of 3000 minutes used")

        print("actions-health: room left reports the EXACT remainder")
        reset()
        put("billing_mins", "3025\n")
        invoke(allowance="50000")
        rc("exits 0", 0)
        has("quotes usage and limit", "3025 of 50000 minutes used")
        has("quotes what is left", "46975 remaining")

        print("actions-health: --included overrides the environment")
        reset()
        put("billing_mins", "3025\n")
        invoke("--included", "3000", allowance="50000")
        rc("flag wins, exits 1", 1)
        has("uses the flag's limit", "3025 of 3000 minutes used")

        print("actions-health: with no allowance configured, it declines to guess")
        reset()
        put("billing_mins", "3025\n")
        invoke()
        rc("exits 0, not 1", 0)
        has("says the remainder is unknown", "Remaining unknown")
        has("names the setting", "AGENT_FABRIC_ACTIONS_INCLUDED_MINUTES")
        invoke(AGENT_FABRIC_ACTIONS_INCLUDED_SETTING="PROJ_ACTIONS_INCLUDED_MINUTES")
        has("…or the one a project's forwarder names", "set PROJ_ACTIONS_INCLUDED_MINUTES in .claude/settings.json")

        print("actions-health: a non-numeric allowance is an invocation error")
        reset()
        invoke(allowance="abc")
        rc("exits 2, not 0 or 1", 2)
        invoke(allowance="3000abc")
        rc("a number with a tail is refused too, never read as its prefix", 2)
        invoke(allowance="-5")
        rc("a negative one: exits 2", 2)
        invoke(allowance="0")
        rc("zero is no allowance: exits 2", 2)
        invoke(allowance="\u0663\u0660\u0660\u0660")
        rc("digits that are not ASCII are no number: exits 2", 2)
        for big in ("9" * 400 + ".0", "2" * 309):
            invoke(allowance=big)
            rc(f"a number past a double's range ({'decimal' if '.' in big else 'integer'}): exits 2", 2)
            has("  refused, naming the setting", "must be a positive number")
        invoke("--json", allowance="2" * 309)
        lines = out["text"].splitlines()
        check("  …and --json calls it invalid", out["rc"] == 2 and bool(lines)
              and json.loads(lines[-1]).get("verdict") == "invalid", out["text"])
        invoke(allowance="3000.5")
        rc("a decimal one is a number: exits 0", 0)

        print("actions-health: unknown is NOT the same as broken")
        reset()
        put("status_unreachable")
        put("billing_unreadable")
        invoke()
        rc("exits 2, not 1", 2)
        has("says health is unknown", "health unknown")

        print("actions-health: a status body it cannot parse is not a status it read")
        reset()
        put("status_malformed", "<html>proxy error</html>\n")
        put("billing_unreadable")
        invoke()
        rc("exits 2, not 0", 2)
        has("says health is unknown", "health unknown")
        reset()
        put("status_malformed", '{"components":[{"name":"Pages","status":"operational"}],"incidents":[]}\n')
        put("billing_unreadable")
        invoke()
        rc("a summary without the component is unknown too", 2)

        print("actions-health: a billing answer it cannot parse is not a billing it read")
        reset()
        put("status_unreachable")
        put("billing_raw", "<html>proxy error</html>\n")
        invoke(allowance="3000")
        rc("not JSON, and no status: exits 2, never '0 minutes used'", 2)
        has("says health is unknown", "health unknown")
        reset()
        put("billing_raw", '{"usageItems":[{"product":"actions","unitType":"Minutes","quantity":"many","netAmount":0}]}\n')
        invoke(allowance="3000")
        rc("a quantity that is no number: the allowance is not checked, exit 0 on the status", 0)
        has("  and says so", "Allowance not checked")

        reset()
        put("billing_error_body")
        invoke(allowance="3000")
        rc("a billing call refused with an error body: exit 0 on the status", 0)
        has("  and the allowance not claimed checked", "Allowance not checked")
        lacks("  never read as no usage", "0 of 3000 minutes used")
        put("status_unreachable")
        invoke(allowance="3000")
        rc("  …and with no status either: exits 2", 2)
        reset()
        put("billing_raw", '{"usageItems":[{"product":"actions","unitType":"Minutes","quantity":NaN,"netAmount":0}]}\n')
        invoke("--json", allowance="3000")
        rc("NaN in a minute row: the allowance not checked, exit 0 on the status, no traceback", 0)
        has("  and said", "Allowance not checked")
        for label, rows in (
                ("an integer past a double's range in a minute row",
                 '[{"product":"actions","unitType":"Minutes","quantity":' + "2" * 309 + ',"netAmount":0}]'),
                ("rows past a double's range whose sum is not",
                 '[{"product":"actions","unitType":"Minutes","quantity":' + "2" * 309 + ',"netAmount":0},'
                 '{"product":"actions","unitType":"Minutes","quantity":-' + "2" * 309 + ',"netAmount":0}]'),
                ("finite rows whose sum is not",
                 '[{"product":"actions","unitType":"Minutes","quantity":1,"netAmount":1e308},'
                 '{"product":"actions","unitType":"Minutes","quantity":1,"netAmount":1e308}]')):
            reset()
            put("billing_raw", '{"usageItems":' + rows + '}\n')
            invoke("--json", allowance="3000")
            try:
                doc = json.loads(out["text"])
            except ValueError:
                doc = {}
            check(f"{label}: the allowance not checked, exit 0 on the status, valid JSON",
                  out["rc"] == 0 and "Allowance not checked" in doc.get("reason", ""), out["text"][:300])
        reset()
        put("billing_raw", '[]\n')
        invoke(allowance="3000")
        rc("a billing answer that is a JSON array is unreadable too", 0)
        has("  and said", "Allowance not checked")
        reset()
        put("billing_raw", '{"usageItems":[{"product":"actions","unitType":"Minutes","quantity":40,"netAmount":0,"date":false}]}\n')
        invoke(allowance="3000")
        rc("a row dated false is counted, as jq's // reads it", 0)
        has("  in the sum", "40 of 3000 minutes used")

        print("actions-health: an error nothing foresaw is unknown, never degraded")
        reset()
        put("billing_raw", "[" * 200000 + "\n")
        invoke(allowance="3000")
        rc("a billing body too deep to parse: exits 2, not 1", 2)
        has("  and says why", "could not decide (RecursionError")

        print("actions-health: billing alone never claims the platform is up")
        reset()
        put("status_malformed", "<html>proxy error</html>\n")
        put("billing_mins", "3025\n")
        invoke(allowance="50000")
        rc("still answers on the allowance", 0)
        has("quotes the usage", "3025 of 50000 minutes used")
        has("admits the status is unverified", "Actions status unverified")

        print("actions-health: a readable status with unreadable billing still answers")
        reset()
        put("billing_unreadable")
        invoke()
        rc("exits 0", 0)
        has("flags what it skipped", "Allowance not checked")

        print("actions-health: --quiet prints nothing and still decides")
        reset()
        put("actions_status", "major_outage\n")
        invoke("--quiet")
        rc("exits 1", 1)
        check("prints nothing", out["text"] == "", out["text"])

        print("actions-health: --json, one object for a program")
        reset()
        put("billing_mins", "3025\n")
        put("billing_net", "0\n")
        invoke("--json", "--quiet", allowance="50000")
        try:
            doc = json.loads(out["text"])
        except ValueError:
            doc = {}
        check("one object, whatever --quiet says, with every field",
              out["rc"] == 0 and list(doc) == ["exit", "verdict", "reason", "public", "period", "private_minutes",
                                               "private_net", "own_net", "included", "remaining"], out["text"])
        check("…the values the line is made of",
              doc.get("exit") == 0 and doc.get("verdict") == "ok" and doc.get("public") is False
              and doc.get("period") == now.strftime("%Y-%m") and doc.get("private_minutes") == 3025
              and doc.get("private_net") == 0 and doc.get("own_net") is None and doc.get("included") == 50000
              and doc.get("remaining") == 46975 and "3025 of 50000 minutes used" in doc.get("reason", ""), out["text"])
        reset()
        put("this_repo_public")
        put("self_net", "0.75\n")
        invoke("--json")
        doc = json.loads(out["text"] or "{}")
        check("a public repository's own cost: degraded, own_net, no remainder",
              out["rc"] == 1 and doc.get("verdict") == "degraded" and doc.get("public") is True
              and doc.get("own_net") == 0.75 and doc.get("remaining") is None, out["text"])
        reset()
        put("status_unreachable")
        put("billing_unreadable")
        invoke("--json")
        lines = out["text"].splitlines()
        doc = json.loads(lines[-1]) if lines else {}
        check("neither source read: exit 2, verdict unknown, the reason said on stderr too",
              out["rc"] == 2 and doc.get("verdict") == "unknown" and "health unknown" in doc.get("reason", "")
              and any(ln.startswith("actions-health: ") for ln in lines) and doc.get("private_minutes") is None,
              out["text"])
        invoke("--json", allowance="abc")
        lines = out["text"].splitlines()
        doc = json.loads(lines[-1]) if lines else {}
        check("a bad allowance: exit 2, verdict invalid", out["rc"] == 2 and doc.get("verdict") == "invalid", out["text"])
        reset()
        put("actions_status", "major_outage\n")
        invoke("--json")
        doc = json.loads(out["text"] or "{}")
        check("a degraded platform: exit 1 before billing, its fields null",
              out["rc"] == 1 and doc.get("verdict") == "degraded" and doc.get("period") is None
              and doc.get("private_minutes") is None, out["text"])

        print("actions-health: invocation errors")
        reset()
        invoke("--nope")
        rc("unknown option exits 2", 2)
        invoke("--org")
        rc("--org needs a value", 2)
        r = subprocess.run([TOOL, "--json", "--nope"], env=base, capture_output=True, text=True, timeout=120)
        check("a usage error is stderr alone, even with --json",
              r.returncode == 2 and r.stdout == "" and "unknown option" in r.stderr, f"{r.stdout!r} {r.stderr!r}")

    print(f"\ntest_actions_health_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
