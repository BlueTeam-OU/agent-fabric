---
role: "fabric-coordinator"
class: solution
topic: "moveto-installed-behind-450"
description: "Which moveto is installed on develop-qzapp: /usr/local/share/moveto/moveto.py is #447's 7807cb02; #450's ~^Z stop is on main but not installed"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 417540e236e16418
---

## Which moveto is installed on develop-qzapp: /usr/local/share/moveto/moveto.py is #447's 7807cb02; #450's ~^Z stop is on main but not installed

2026-11-05 (j524, #488): /usr/local/bin/moveto is a wrapper and the code is /usr/local/share/moveto/moveto.py,
installed 2026-11-01 08:34 by root. Its sha256 matches runtime/provisioning/moveto/moveto.py at 7807cb02 (#447),
not origin/main: #450 (60cc83b7: ~^Z stops moveto with ssh, 2c56316e: no second wait on a reaped Popen) is
not installed. To check, compare `sha256sum` of the installed file with `git show <c>:runtime/provisioning/moveto/moveto.py | sha256sum`.
Install is the owner's (sudo runtime/provisioning/moveto/install.sh). The ~^Z stop path gets a live check
after that install. Related: [[attach-hangup-leaves-terminal-modes]].

*References: attach-hangup-leaves-terminal-modes*

*Anchors: `runtime/provisioning/moveto/moveto.py::def attach`*

*Observed 2026-11-04 (fabric-coordinator)*
