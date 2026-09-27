#!/usr/bin/env bash
# tests/test_fabric-lease.sh — bin/fabric-lease holds one lease per name
# across processes: a second caller is refused fast and told who holds
# it, or waits when asked; the lease outlives nothing the command leaves
# behind and is gone when the holder exits; --need-mem refuses under a
# forged /proc/meminfo; the missing directory is a refusal that names the
# fix. Against a scratch lease directory.
set -uo pipefail
HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"; ROOT="$(dirname "$HERE")"
PASS=0; FAIL=0
ok() { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ✗ $1"; [[ -n "${2:-}" ]] && echo "$2" | sed 's/^/      /'; }
SANDBOX="$(mktemp -d)"; HOLDER=""; trap '[[ -n "$HOLDER" ]] && kill "$HOLDER" 2>/dev/null; rm -rf "$SANDBOX"' EXIT
D="$SANDBOX/leases"; mkdir -m 1777 "$D"
lease() { AGENT_FABRIC_LEASES="$D" bash "$ROOT/bin/fabric-lease" "$@"; }

echo "fabric-lease: usage"
out="$(lease 2>&1 >/dev/null)"; rc=$?; [[ $rc -eq 2 ]] && grep -q "^usage:" <<<"$out" && ok "no name: exit 2, usage on stderr" || bad "no name" "rc=$rc $out"
[[ -z "$(lease 2>/dev/null)" ]] && ok "…and nothing on stdout" || bad "usage leaked to stdout"
lease "bad name" -- true 2>/dev/null; [[ $? -eq 2 ]] && ok "a name with a space is refused" || bad "bad name accepted"
lease x --wait abc -- true 2>/dev/null; [[ $? -eq 2 ]] && ok "--wait must be a number" || bad "--wait abc"
out="$(AGENT_FABRIC_LEASES="$SANDBOX/absent" bash "$ROOT/bin/fabric-lease" x -- true 2>&1)"; rc=$?
[[ $rc -eq 2 ]] && grep -q "operator" <<<"$out" && ! grep -q "sudo" <<<"$out" && ok "no lease directory: refused; the operator's action named, nothing the agent cannot run" || bad "absent dir" "$out"

echo "fabric-lease: a free lease runs the command and returns its status"
out="$(lease backend-test -- sh -c 'echo ran; exit 3' 2>&1)"; rc=$?
[[ $rc -eq 3 && "$out" == "ran" ]] && ok "command ran, exit status passed through" || bad "run" "rc=$rc $out"
[[ "$(stat -c %a "$D/backend-test")" == 666 ]] && ok "the lease file is 0666 (any login may record itself)" || bad "mode" "$(stat -c %a "$D/backend-test")"
lease backend-test --who >/dev/null; [[ $? -eq 0 ]] && ok "--who: free after the holder exited" || bad "not free after exit"
lease backend-test -- sh -c 'sleep 30 & exit 0' >/dev/null 2>&1
lease backend-test --who >/dev/null; [[ $? -eq 0 ]] && ok "a process the command left behind does not keep the lease" || bad "orphan kept the lease"

echo "fabric-lease: a held lease"
AGENT_FABRIC_LEASES="$D" bash "$ROOT/bin/fabric-lease" backend-test -- sh -c 'echo started; sleep 20' > "$SANDBOX/holder.out" 2>&1 &
HOLDER=$!
for _ in $(seq 50); do grep -q started "$SANDBOX/holder.out" 2>/dev/null && break; sleep 0.1; done
out="$(lease backend-test -- echo second 2>&1)"; rc=$?
[[ $rc -eq 75 ]] && ! grep -q second <<<"$out" && ok "a second caller is refused fast, exit 75, command not run" || bad "second caller" "rc=$rc $out"
grep -q "held by $(id -un) " <<<"$out" && grep -q "backend-test" <<<"$out" && ok "…told who holds it (login, pid, since, name)" || bad "holder not named" "$out"
out="$(lease backend-test --who 2>&1)"; rc=$?
[[ $rc -eq 1 ]] && grep -q "^held: $(id -un) " <<<"$out" && ok "--who: held, exit 1, the record" || bad "--who held" "rc=$rc $out"
out="$(lease backend-test --wait 1 -- echo second 2>&1)"; rc=$?
[[ $rc -eq 75 ]] && grep -q "still held" <<<"$out" && ok "--wait 1: waits, then says it is still held" || bad "wait" "rc=$rc $out"
out="$(lease other-thing -- echo other 2>&1)"; [[ "$out" == "other" ]] && ok "another name is another lease" || bad "names not independent" "$out"
kill "$HOLDER" 2>/dev/null; wait "$HOLDER" 2>/dev/null; HOLDER=""
lease backend-test --who >/dev/null; [[ $? -eq 0 ]] && ok "the holder killed: the lease is free (the kernel released it)" || bad "stale after kill"
# waiting caller gets it when the holder finishes
AGENT_FABRIC_LEASES="$D" bash "$ROOT/bin/fabric-lease" backend-test -- sh -c 'echo started; sleep 1.5' > "$SANDBOX/holder.out" 2>&1 &
HOLDER=$!; for _ in $(seq 50); do grep -q started "$SANDBOX/holder.out" 2>/dev/null && break; sleep 0.1; done
out="$(lease backend-test --wait 10 -- echo got-it 2>/dev/null)"; [[ "$out" == "got-it" ]] && ok "--wait: runs once the holder finishes" || bad "wait did not acquire" "$out"
wait "$HOLDER" 2>/dev/null; HOLDER=""

echo "fabric-lease: --need-mem"
printf 'MemTotal:       18152000 kB\nMemAvailable:    2048000 kB\n' > "$SANDBOX/meminfo"
out="$(AGENT_FABRIC_MEMINFO="$SANDBOX/meminfo" lease backend-test --need-mem 4096 -- echo ran 2>&1)"; rc=$?
[[ $rc -eq 75 ]] && ! grep -q '^ran$' <<<"$out" && grep -q "needs 4096 MB" <<<"$out" && grep -q "2000 MB available" <<<"$out" && ok "short of memory: refused, exit 75, the numbers said" || bad "need-mem refuse" "rc=$rc $out"
lease backend-test --who >/dev/null; [[ $? -eq 0 ]] && ok "…and the lease released" || bad "lease kept after memory refusal"
out="$(AGENT_FABRIC_MEMINFO="$SANDBOX/meminfo" lease backend-test --need-mem 1024 -- echo ran 2>&1)"
[[ "$out" == "ran" ]] && ok "enough memory: runs" || bad "need-mem pass" "$out"
out="$(AGENT_FABRIC_MEMINFO="$SANDBOX/absent" lease backend-test --need-mem 1024 -- echo ran 2>&1)"; rc=$?
[[ $rc -eq 2 ]] && ! grep -q '^ran$' <<<"$out" && grep -q "MemAvailable cannot be read" <<<"$out" && ok "MemAvailable unreadable: refused, exit 2, never skipped" || bad "unreadable meminfo" "rc=$rc $out"
printf 'MemTotal:       18152000 kB\n' > "$SANDBOX/meminfo-noavail"
out="$(AGENT_FABRIC_MEMINFO="$SANDBOX/meminfo-noavail" lease backend-test --need-mem 1024 -- echo ran 2>&1)"; rc=$?
[[ $rc -eq 2 ]] && ! grep -q '^ran$' <<<"$out" && ok "no MemAvailable line: the same refusal" || bad "missing MemAvailable" "rc=$rc $out"

echo "fabric-lease: a probe is not an acquisition"
# --who holds a shared lock for its lifetime; a caller landing in that window
# must still acquire. Run 40 probes in a burst and a caller in the middle.
for _ in $(seq 40); do lease backend-test --who >/dev/null 2>&1 & done
out="$(lease backend-test -- echo got-through 2>&1)"; rc=$?; wait
[[ $rc -eq 0 && "$out" == "got-through" ]] && ok "a caller is not refused by a burst of --who probes" || bad "probe refused a caller" "rc=$rc $out"
# two probes at once both say free (shared locks coexist)
( lease backend-test --who & lease backend-test --who; wait ) 2>/dev/null | sort | uniq -c | grep -q "2 free: backend-test" && ok "two simultaneous probes both read free" || bad "probes saw each other as a holder"
# a shared lock held by an observer never reads as "held": --who says free
# while a flock -s is open on the file (the deterministic pin for the
# shared-probe design; the burst above is the same fact, timing-dependent)
( exec 8<"$D/backend-test"; flock -s 8; lease backend-test --who; echo "who-rc=$?" ) 2>/dev/null | grep -q "who-rc=0" && ok "--who reads free under another observer's shared lock" || bad "a shared lock read as held"
# the record is written before the memory check: a caller refused WHILE a
# --need-mem evaluation is running is told THIS holder. The check is made
# observable by pointing MEMINFO at a fifo: awk blocks on it until the test
# writes, and in that window the record must already be the new holder's.
lease backend-test -- true >/dev/null 2>&1   # a previous holder's record
prev="$(head -1 "$D/backend-test")"
mkfifo "$SANDBOX/meminfo.fifo"
AGENT_FABRIC_LEASES="$D" AGENT_FABRIC_MEMINFO="$SANDBOX/meminfo.fifo" bash "$ROOT/bin/fabric-lease" backend-test --need-mem 1024 -- sh -c 'echo started' > "$SANDBOX/holder.out" 2>&1 &
HOLDER=$!
# Wait for the NEW holder's line, not merely for a change: the record is
# truncated and rewritten in place (the file is the lock, so it cannot be
# replaced by rename), and a read in that instant is empty — which is a
# change, and made this case flake under load.
for _ in $(seq 50); do [[ "$(head -1 "$D/backend-test" 2>/dev/null)" == "$(id -un) $HOLDER "* ]] && break; sleep 0.1; done
now="$(head -1 "$D/backend-test")"
refused="$(lease backend-test -- echo second 2>&1)"
[[ "$now" == "$(id -un) $HOLDER "* ]] && ok "the record names the new holder while its memory check is still running" || bad "record during the memory check" "prev=$prev now=$now holder=$HOLDER"
grep -q "held by $(id -un) $HOLDER " <<<"$refused" && ok "…and a caller refused in that window is told the new holder" || bad "refused caller told the wrong holder" "$refused"
# Opening a fifo for writing blocks until a reader opens it: bounded, so a
# regression that made the holder exit before its awk ever read the fifo
# fails the suite instead of hanging it.
timeout 5 sh -c 'printf "MemTotal:       18152000 kB\nMemAvailable:   12000000 kB\n" > "$1"' _ "$SANDBOX/meminfo.fifo" || bad "the holder never opened the fifo (exited before its memory check)"
wait "$HOLDER"; rc=$?; HOLDER=""
[[ $rc -eq 0 ]] && grep -q started "$SANDBOX/holder.out" && ok "…the holder then ran once the meminfo arrived" || bad "holder after fifo" "rc=$rc $(cat "$SANDBOX/holder.out")"

echo "fabric-lease: signals and names"
AGENT_FABRIC_LEASES="$D" bash "$ROOT/bin/fabric-lease" backend-test -- sh -c 'echo started; trap "echo child-got-term; exit 0" TERM; while :; do sleep 0.2; done' > "$SANDBOX/holder.out" 2>&1 &
HOLDER=$!; for _ in $(seq 50); do grep -q started "$SANDBOX/holder.out" 2>/dev/null && break; sleep 0.1; done
kill -TERM "$HOLDER"; wait "$HOLDER" 2>/dev/null; HOLDER=""
for _ in $(seq 30); do grep -q child-got-term "$SANDBOX/holder.out" 2>/dev/null && break; sleep 0.1; done
grep -q child-got-term "$SANDBOX/holder.out" && ok "TERM to the wrapper reaches the command" || bad "TERM not forwarded" "$(cat "$SANDBOX/holder.out")"
lease backend-test --who >/dev/null; [[ $? -eq 0 ]] && ok "…and the lease is free afterwards" || bad "lease held after TERM"
out="$(lease backend-test -- record 2>&1)"; rc=$?; [[ $rc -eq 127 ]] && ok "a function of the script is not a command (exit 127)" || bad "function ran as command" "rc=$rc $out"
out="$(lease backend-test -- -v ls 2>&1)"; rc=$?; [[ $rc -eq 127 ]] && ok "a first word of -v is not an option of command (exit 127)" || bad "-v taken as command's option" "rc=$rc $out"
out="$(echo hello-from-stdin | lease backend-test -- cat)"; [[ "$out" == "hello-from-stdin" ]] && ok "the command inherits the wrapper's stdin" || bad "stdin lost" "$out"
# INT (2) and QUIT (3) — bits 0x6 — must not be ignored in the command: a
# plain `&` in a script sets both to SIG_IGN. Other bits are the caller's
# own inheritance (a CI runner ignores PIPE, 0x1000) and pass through.
mask="$(lease backend-test -- grep SigIgn /proc/self/status | awk '{print $2}')"; (( (16#$mask & 16#6) == 0 )) && ok "INT and QUIT are not ignored in the command (SigIgn $mask)" || bad "INT/QUIT ignored in the command" "SigIgn $mask"
# The teardown: a child whose TERM handler takes time and exits 7. The
# lease must stay held while it runs, and the wrapper must return 7.
AGENT_FABRIC_LEASES="$D" bash "$ROOT/bin/fabric-lease" backend-test -- sh -c 'echo started; trap "sleep 1.5; echo child-done; exit 7" TERM; while :; do sleep 0.2; done' > "$SANDBOX/holder.out" 2>&1 &
HOLDER=$!; for _ in $(seq 50); do grep -q started "$SANDBOX/holder.out" 2>/dev/null && break; sleep 0.1; done
kill -TERM "$HOLDER"; sleep 0.6
lease backend-test --who >/dev/null 2>&1; [[ $? -eq 1 ]] && ok "TERM: the lease stays held while the command tears down" || bad "lease released before the command exited"
wait "$HOLDER"; rc=$?; HOLDER=""
[[ $rc -eq 7 ]] && grep -q child-done "$SANDBOX/holder.out" && ok "…the wrapper's status is the command's (7), after its teardown" || bad "wrapper status after TERM" "rc=$rc $(cat "$SANDBOX/holder.out")"
lease backend-test --who >/dev/null; [[ $? -eq 0 ]] && ok "…and the lease is free once it is gone" || bad "lease held after teardown"
# HUP is forwarded like TERM.
AGENT_FABRIC_LEASES="$D" bash "$ROOT/bin/fabric-lease" backend-test -- sh -c 'echo started; trap "echo child-got-hup; exit 0" HUP; while :; do sleep 0.2; done' > "$SANDBOX/holder.out" 2>&1 &
HOLDER=$!; for _ in $(seq 50); do grep -q started "$SANDBOX/holder.out" 2>/dev/null && break; sleep 0.1; done
kill -HUP "$HOLDER"; wait "$HOLDER" 2>/dev/null; HOLDER=""
grep -q child-got-hup "$SANDBOX/holder.out" && ok "HUP to the wrapper reaches the command" || bad "HUP not forwarded" "$(cat "$SANDBOX/holder.out")"

echo "fabric-lease: every refusal ends with one stable reason line; --label names the job"
# The contract callers match (ADR-010): the LAST stderr line, whatever the prose above it says.
last() { tail -1 <<<"$1"; }
out="$(AGENT_FABRIC_LEASES="$SANDBOX/absent" bash "$ROOT/bin/fabric-lease" x -- true 2>&1)"
[[ "$(last "$out")" == "fabric-lease: reason=nodir" ]] && ok "no lease directory: reason=nodir, last" || bad "nodir reason" "$out"
out="$(AGENT_FABRIC_MEMINFO="$SANDBOX/meminfo" lease heavy --need-mem 4096 -- true 2>&1)"
[[ "$(last "$out")" == "fabric-lease: reason=memory" ]] && ok "short of memory: reason=memory, last" || bad "memory reason" "$out"
AGENT_FABRIC_LEASES="$D" bash "$ROOT/bin/fabric-lease" heavy --label backend-test -- sh -c 'echo started; sleep 20' > "$SANDBOX/holder.out" 2>&1 &
HOLDER=$!
for _ in $(seq 50); do grep -q started "$SANDBOX/holder.out" 2>/dev/null && break; sleep 0.1; done
out="$(lease heavy --label stack-up -- true 2>&1)"; rc=$?
[[ $rc -eq 75 && "$(last "$out")" == "fabric-lease: reason=held" ]] && ok "held, no wait: exit 75, reason=held, last" || bad "held reason" "rc=$rc $out"
grep -q "held by $(id -un) .* heavy (backend-test)" <<<"$out" && ok "…and the holder's job is named: heavy (backend-test)" || bad "label not in the holder record" "$out"
out="$(lease heavy --wait 1 -- true 2>&1)"; rc=$?
[[ $rc -eq 75 && "$(last "$out")" == "fabric-lease: reason=timeout" ]] && ok "the wait ran out: exit 75, reason=timeout, last" || bad "timeout reason" "rc=$rc $out"
out="$(lease heavy --who 2>&1)"; grep -q "^held: .* heavy (backend-test)$" <<<"$out" && ok "--who shows the label too" || bad "--who label" "$out"
kill "$HOLDER" 2>/dev/null; wait "$HOLDER" 2>/dev/null; HOLDER=""
lease heavy --label 'two words' -- true 2>/dev/null; [[ $? -eq 2 ]] && ok "a label with a space is refused (it is written into a shared file)" || bad "bad label accepted"
lease heavy --label "$(printf 'x\033]0;y')" -- true 2>/dev/null; [[ $? -eq 2 ]] && ok "a label with a control character is refused" || bad "control label accepted"
out="$(lease heavy -- sh -c 'echo ran' 2>&1)"; [[ "$out" == "ran" ]] && ok "a run that is not refused prints no reason line" || bad "reason on success" "$out"
out="$(AGENT_FABRIC_MEMINFO=/dev/null lease heavy --need-mem 1024 -- true 2>&1)"; rc=$?
[[ $rc -eq 2 && "$(last "$out")" == "fabric-lease: reason=memory-unknown" ]] && ok "MemAvailable unreadable: exit 2, reason=memory-unknown, last" || bad "memory-unknown reason" "rc=$rc $out"
# A holder record another login wrote by hand reaches a refused caller's terminal: control characters never do.
printf 'x 1 T heavy \033]0;PWNED\007\302\233(bad)\n' > "$D/rogue"; chmod 666 "$D/rogue"
exec 8<"$D/rogue"; flock 8
out="$(lease rogue -- true 2>&1)"; flock -u 8; exec 8<&-
! grep -q $'\033' <<<"$out" && ! grep -q $'\007' <<<"$out" && ! LC_ALL=C grep -q $'\302\233' <<<"$out" && grep -q "held by x 1 T heavy" <<<"$out" && ok "the holder record is printed as printable ASCII only (C0, DEL and C1 dropped)" || bad "control characters reached the caller" "$(cat -v <<<"$out")"
# A lease file in the sandbox that its owner cannot read. Not a file of
# the host's: /proc/kcore is absent here, readable under a container's
# default mask, and the case passed or failed with the machine (the
# review of #39). Root reads a mode-000 file, so the case is skipped there.
: > "$D/sealed"; chmod 000 "$D/sealed"
if (( EUID == 0 )); then ok "unopenable: skipped under root, which opens a mode-000 file"
else
out="$(lease sealed -- true 2>&1)"; rc=$?
[[ $rc -eq 2 && "$(last "$out")" == "fabric-lease: reason=unopenable" ]] && ok "a lease file that cannot be opened: exit 2, reason=unopenable, last" || bad "unopenable reason" "rc=$rc $out"
fi
chmod 600 "$D/sealed"

echo
if (( FAIL )); then echo "fabric-lease: $FAIL failure(s), $PASS passed"; exit 1; fi
echo "fabric-lease: $PASS passed"
