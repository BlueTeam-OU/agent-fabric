---
role: "rust-ui-dev"
class: domain
topic: "unbounded-reader-remove-not-withhold"
description: "A client action whose library reads untrusted input with no bound (clipboard image decode) -- remove the code path, do not only hide the control; offer the action only on platforms with a bounded read"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0e0c108214332440
---

## A client action whose library reads untrusted input with no bound (clipboard image decode) -- remove the code path, do not only hide the control; offer the action only on platforms with a bounded read

- arboard's get_image reads and decodes the whole clipboard image under the image crate's
  default allocation limit (512 MiB) before the app sees its dimensions. Another local program
  can put a small, highly compressed image with huge dimensions on the clipboard, and one
  paste then allocates hundreds of MiB or gets the client killed.
- Hiding the control (a flag on the view) is not a bound. The reader stays compiled in, and
  only one argument keeps it from a person. Remove the read itself, so the action ends
  harmlessly (here as a cancelled scan) whatever the view flag says. Pin it with a test that
  fails when the arm reads anything.
- Bring the action back only through a bounded read of the encoded bytes (size and time
  limits, then the same bounded decoder an opened file uses), with a regression image whose
  declared size is over the limit. Where a platform has no bounded read (here Windows and
  macOS), do not offer the action there. Say so in the spec, and keep the alternative (Open
  an image...).
- A library dropped from your direct dependencies can stay in the graph through the toolkit
  (arboard through Slint's winit backend). Check `cargo tree -i` before claiming it is gone.
Related: [[type-encode-ui-rules]].

*References: type-encode-ui-rules*

*Observed 2026-10-27 (rust-ui-dev)*
