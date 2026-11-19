---
role: "python-dev"
class: workflow
topic: "j216-binding-readers-and-syntaxwarning-merged-525"
description: "j216 (#525): bare ast.parse under -W error turns an invalid escape into \"unparseable, clean\"; BindingRecord.updated_at came as coordinator patch; supply branch binding-readers; job done needs a reply: artifact"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0169e7f67725391f
---

## j216 (#525): bare ast.parse under -W error turns an invalid escape into "unparseable, clean"; BindingRecord.updated_at came as coordinator patch; supply branch binding-readers; job done needs a reply: artifact

#525 merged 2026-11-09 (3 work, 1 fix; armed on the owner's word "arm 525" under the minimum, local suite never ran: the host's one-suite lease was held 25+ min and CI ran it).

- **Class**: a checker that catches SyntaxError and returns [] reads an invalid escape as a clean module when warnings are errors. Fix = `warnings.catch_warnings(); simplefilter("ignore", SyntaxWarning)` around the parse (as context_reads does). Test = scan a fixture holding backslash-space beside a real violation under `simplefilter("error")`, with a positive control that bare `ast.parse` raises there. Escaping trap: in the test source `"\\ "` inside a `'...'` literal is a valid escape; the fixture needs exactly one backslash after the Python layer.
- **runtime/identity.py is outside the python-dev entry**: adding `BindingRecord.updated_at` went as a diff in a REPLY; the coordinator committed it on `develop-qzapp/user/for/python-dev-01/j216-binding-updated-at` (not on my branch, which was unpushed) and I merged that unrebased. Push the branch first if you want a commit on it.
- **Raw-read tests**: `read_binding` is called by `binding_record`/`resolve_context` themselves, so a booby-trap that raises breaks the record; count calls instead, or record the caller name (`sys._getframe(1).f_code.co_name` == "binding_record"). A review caught that `ctx["role"]` is the raw value, so a mutation test needs a non-string role (5) to separate it from `binding.role`.
- **Supply tier from a job checkout**: a commit in a sibling worktree is refused by the job hook; save the diff, remove the worktree, `git switch` the for/ branch in the job checkout, apply, commit, push (gh credential helper), switch back.
- **Closing**: `fabric-jobs deliver` with a merged PR says "done, not delivered"; `done` wants evidence; `deliver <job> reply:<MESSAGE-ID>` then `sweep` closed it. `switch` also wants both queued REQUESTs acknowledged and a memory written.
- **Review brief**: I abridged the previous report in the re-review prompt; keep it verbatim.

*Anchors: `tools/fabric/state_writes.py::scan`, `runtime/identity.py::BindingRecord`, `tools/fabric/status.py::build_report`*

*Observed 2026-11-09 (python-dev)*
