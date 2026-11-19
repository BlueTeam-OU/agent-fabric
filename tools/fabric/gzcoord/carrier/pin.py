"""tools/fabric/gzcoord/carrier/pin.py — what runtime/interweave/release.json pins for an installed InterWeave
program, read the one way for every caller (admit.py's transportctl, control_link.py's interweave-human).

CONTRACT.
  release_entry(release_path, machine)   the current release's entry for this machine; PinError otherwise.
  pinned_version(release_path, program, machine)   `reports[program]`.
  pinned_digest(release_path, program, machine)    `program_sha256[program]`, lowercase hex SHA-256 or PinError.
  file_sha256(path)                      PinError when the file cannot be read.
  verify_program(path, release_path, program)      None when path is the pinned program, else the one-line reason.
A missing, malformed or unreadable value is a PinError, never a default: an unknown digest must not read as a match.
"""
from __future__ import annotations

import hashlib
import json
import platform
import re


class PinError(Exception):
    """The pin or the program cannot be read, or says something else; the message names the fact that fixes it."""


def release_entry(release_path: str, machine: str | None = None) -> dict:
    arch = machine or platform.machine()
    try:
        with open(release_path, encoding="utf-8") as fh:
            doc = json.load(fh)
        return doc["releases"][doc["current"]][arch]
    except (OSError, ValueError) as e:
        raise PinError(f"{release_path}: {e}") from e
    except (KeyError, TypeError) as e:
        raise PinError(f"{release_path} pins no release for {arch}") from e


def pinned_version(release_path: str, program: str, machine: str | None = None) -> str:
    try:
        return release_entry(release_path, machine)["reports"][program]
    except (KeyError, TypeError) as e:
        raise PinError(f"{release_path} pins no {program} version") from e


def pinned_digest(release_path: str, program: str, machine: str | None = None) -> str:
    try:
        digest = release_entry(release_path, machine)["program_sha256"][program]
    except (KeyError, TypeError) as e:
        raise PinError(f"{release_path} pins no program_sha256 for {program}") from e
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise PinError(f"{release_path}: program_sha256 for {program} is not lowercase hex SHA-256")
    return digest


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except OSError as e:
        raise PinError(f"{path} cannot be read: {e.strerror or type(e).__name__}") from e
    return h.hexdigest()


def verify_program(path: str, release_path: str, program: str) -> str | None:
    """None when the file at `path` is the current release's `program`; otherwise why not, in one line."""
    try:
        want = pinned_digest(release_path, program)
        have = file_sha256(path)
    except PinError as e:
        return str(e)
    if have != want:
        return f"{path} is not the pinned release's {program} (SHA-256 differs from release.json): reinstall it"
    return None
