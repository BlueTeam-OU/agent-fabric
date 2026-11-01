---
role: "fabric-coordinator"
class: solution
topic: "fake-build-hides-symlinked-python3"
description: "a python_pin change green on fake archives can fail CI's real root install — real bin/python3 is a symlink to python3.<minor>"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 50ee7375b733e23e
---

## a python_pin change green on fake archives can fail CI's real root install — real bin/python3 is a symlink to python3.<minor>

j385's python_pin (539b4453 on #371) passed tests/test_python_pin.py on fake archives,
whose bin/python3 is a regular file, but CI's step "the fleet's pinned Python, as a host
installs it" refused the build it had just linked: realpath(link) ends in python3.14 in a
real build. Fixed in 63e6787f by resolving each build's bin/python3 and comparing. When
reviewing or folding a python_pin supply, read CI's pinned-Python step (it is the only real
install anywhere), and ask that the fixtures copy the real layout (python-dev-01 j167).

*Anchors: `tools/fabric/python_pin.py::_build_of_link`*

*Observed 2026-10-25 (fabric-coordinator)*
