---
name: flutter-client-capture
description: See what a running Flutter client actually shows — capture its window, read the image, and know which capture tools depend on the app rather than the tooling. Use when a UI change must be checked against the screen rather than the widget tree, when a capture tool answers that visual capture is unsupported, or when a screenshot comes back showing the wrong thing.
---

# Seeing a running Flutter client

What a Flutter app draws is evidence the widget tree is not. These are
the ways that evidence goes wrong, each learned by a holder of this
role on a Linux desktop build (one holder, one project,
two apps); the ones marked *one place* have not been seen elsewhere yet.
Where the app runs, what its windows are called, which ports and
binaries the host has and how the launcher is driven are the project's
facts: the project's remit for this role names them, and its own skill
carries them.

1. **The MCP visual-capture tools may not work, and the answer says
   so badly.** `fmt_capture_ui_snapshot` and `fmt_get_view_details` are
   served by app-side service extensions that the `mcp_toolkit` package
   registers. An app that does not depend on it answers
   `visual_capture_unsupported` ("visual capture is app-owned on this
   target and requires the optional app permission bridge"), which reads
   like something to retry or reconnect. It is not. Adding the package
   links a debug tool into the app: a decision to raise, never a fix made
   in passing. Check the pubspec before reaching for these tools. The
   VM-service tools — hot reload, isolate inspection, the widget tree —
   do not depend on it. *One place.*
2. **Capture the app's window, never the root.** On a developer
   workstation the root window is the terminal, and the screenshot is
   of your own session.
3. **`xdotool --name` takes a POSIX extended regex.** Alternation is
   `|`, not `\|`; a backslashed pipe matches nothing, which looks exactly
   like xdotool not being installed.
4. **Read the image.** A blank frame is a result — the app drew nothing,
   or the wrong window was captured — not a failed capture to retry.
5. **A desktop debug build may render inside a DevicePreview phone
   frame.** The app is the inner rectangle; the settings panel beside it
   is the wrapper, not the app. *One place.*
6. **Some launcher inputs are read at launch time.** A stale process
   shows a stale world: when the data behind those inputs changed,
   relaunch rather than hot reload.

What to report: the capture, what it shows against what the change
claimed, and which of the above applied. A capture you could not take
is reported as that, with the tool's answer verbatim, never as "the UI
is fine".
