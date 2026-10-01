#!/usr/bin/env bash
# Install moveto from this directory to /usr/local. Needs root. (Bash, like
# every script here: one dialect the static checks prove, not two.)
#
#     sudo runtime/provisioning/moveto/install.sh
#
# This directory is the SOURCE; /usr/local holds a copy. The installer
# records what it installed in /usr/local/share/moveto/installed.sha256
# (sha256sum format), and `bin/fabric-status` compares the repository, the
# manifest and the installed files on every call: the source moved on and
# this was not re-run, or a copy was edited in place, is one line there
# rather than nothing (review, 2026-09-16). $MOVETO_PREFIX overrides
# /usr/local for a test.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
prefix="${MOVETO_PREFIX:-/usr/local}"

install -d -m 755 "$prefix/bin" "$prefix/share/moveto"
install -m 755 "$here/moveto" "$prefix/bin/moveto"
install -m 755 "$here/enter"  "$prefix/share/moveto/enter"
# The work is Python (ADR-040 Wave 5); the shim in bin/ finds it here,
# beside enter and rc, when no checkout is behind the copy.
install -m 644 "$here/moveto.py" "$prefix/share/moveto/moveto.py"
install -m 644 "$here/rc"     "$prefix/share/moveto/rc"
# Tab completion, where bash-completion loads it on first use (XDG_DATA_DIRS
# lists /usr/local/share before /usr/share): accounts from the host
# registry, clones from `moveto <account> --list`.
install -d -m 755 "$prefix/share/bash-completion/completions"
install -m 644 "$here/completion.bash" "$prefix/share/bash-completion/completions/moveto"
# The manifest names the installed paths relative to the prefix, so the
# same sha256sum line checks the copy wherever the prefix is.
( cd "$prefix" && sha256sum bin/moveto share/moveto/moveto.py share/moveto/enter share/moveto/rc share/bash-completion/completions/moveto ) > "$prefix/share/moveto/installed.sha256.tmp"
mv "$prefix/share/moveto/installed.sha256.tmp" "$prefix/share/moveto/installed.sha256"
chmod 644 "$prefix/share/moveto/installed.sha256"

echo "moveto installed to $prefix (manifest: $prefix/share/moveto/installed.sha256). Try: moveto --list"
