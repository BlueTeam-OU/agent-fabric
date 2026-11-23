#!/usr/bin/env python3
"""projects/gzapp/integration/provisioning/host_check.py — what a host must carry for an account that works on
gzapp, beyond the fabric's own contract (Wave 9 batch 9, ADR-040 §5). Run by tools/fabric/provisioning/worker.py
finish on the account's host for each --project it clones, with the fleet's pinned Python; prints one line per item
on stderr, nothing on stdout, and exits 0 whatever is missing — a missing item is named for the person, never a stop
(the fabric provisions the account; the project's toolchain is its own). Pinned by tests/test_host_check.py.

Commit signing goes through the OpenTimestamps gpg wrapper that devex-tooling installs (gzapp
infra/signing/install-shim.sh); the local stack runs rootless podman; the decks and site tooling render with
ImageMagick. The wrapper is tested as bash -x did (a directory with the bit counts); the tools are found on PATH only.
"""
import os
import shutil
import sys

WRAPPER = "/usr/local/bin/ots-git-gpg-wrapper.sh"


def report() -> list[str]:
    wrapper = (f"gpg wrapper: {WRAPPER}" if os.access(WRAPPER, os.X_OK)
               else "gpg wrapper: MISSING — commit signing needs it; devex-tooling installs it (infra/signing/install-shim.sh)")
    tools = [f"{tool}: present" if shutil.which(tool) else f"{tool}: MISSING (a TemplateVM package on Qubes)" for tool in ("podman", "magick")]
    return [f"host-check gzapp: {item}" for item in (wrapper, *tools)]


def main() -> int:
    for line in report():
        print(line, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
