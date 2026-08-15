#!/usr/bin/env python3
"""mereoraii -- verify RAII cleanup and error records on a mereo BINARY.

mereo is function-free, no libc, no heap: the entire resource lifecycle is in
the syscall stream -- fds are acquired by open/socket/accept, released by close,
and the error record is a write to fd 2. So a syscall tracer is the right
Valgrind-analog (Valgrind watches malloc/free; here we watch acquire/close).

Two audits, both on the real binary via strace:

  HAPPY   run once; every fd the program OPENED is closed exactly once (no leak,
          no double-close).

  FAULT   inject a failure at each fallible syscall in turn; on every one the
          release tower must (a) close every fd that was open at the fault,
          (b) write a record to fd 2, (c) exit non-zero. A -EINTR/-EPIPE
          injection instead must be graceful: no record, exit 0. Any fd left
          open on a fault path is a LEAK ON ERROR -- the bug this exists to catch.

Usage:
    python3 mereoraii.py [--stdin DATA] [--] BINARY [args...]
"""

import re
import subprocess
import sys

# syscalls that hand back a fresh fd the program then owns
FD_ACQUIRE = ("openat", "open", "socket", "accept4", "accept", "dup3", "dup2",
              "dup", "pipe2", "pipe", "memfd_create", "eventfd2", "timerfd_create")
# fallible operations worth injecting a fault into (not close/exit/rt_sig*)
INJECTABLE = ("openat", "open", "read", "write", "socket", "connect", "bind",
              "listen", "accept4", "accept", "sendmsg", "recvmsg", "sendto",
              "recvfrom", "setsockopt", "lseek", "getrandom")

LINE = re.compile(r"^(\w+)\((.*)\)\s*=\s*(-?\d+|0x[0-9a-f]+)(?:\s+(\w+))?")


def run(binary, args, stdin, inject=None):
    """Trace one run (optionally injecting `SYS:error=ERRNO:when=N`); return the
    strace lines."""
    cmd = ["strace", "-f", "-qq", "-e",
           "trace=" + ",".join(sorted(set(FD_ACQUIRE + INJECTABLE
                                          + ("close", "rt_sigaction")))),
           "-e", "signal=none"]
    if inject:
        cmd += ["-e", "inject=" + inject]
    cmd += [binary, *args]
    p = subprocess.run(cmd, input=stdin, stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE, timeout=20)
    # strace -f exits with the tracee's own exit code, so it is the program's
    return p.stderr.decode("latin1").splitlines(), p.returncode


# A returning handler for SIGINT/SIGTERM -- as opposed to SIG_IGN or SIG_DFL --
# is the only way -EINTR can reach a program: a signal whose disposition is
# default or ignore never interrupts a syscall and hands it back. So whether the
# graceful-EINTR contract APPLIES is visible in the trace, and asking for it
# from a program that installed no such handler is asking it to handle something
# that cannot happen. mereo installs the stub exactly when it owns something,
# and correspondingly tests for -EINTR only then; this used to report every
# correct fd-less program as broken.
CATCHES_INTERRUPT = re.compile(
    r"rt_sigaction\(SIG(?:INT|TERM), \{sa_handler=0x")


def catches_interrupt(lines):
    return any(CATCHES_INTERRUPT.search(l) for l in lines)


def parse(traced):
    """-> (events, exit_code, stderr_record_bytes). events is a list of
    ('acq', fd) / ('rel', fd) / ('call', name, ret, errname) in order."""
    lines, exit_code = traced
    events, record = [], 0
    for ln in lines:
        m = LINE.match(ln)
        if not m:
            continue
        name, argstr, ret, err = m.group(1), m.group(2), m.group(3), m.group(4)
        rv = int(ret, 0) if not ret.startswith("0x") else int(ret, 16)
        events.append(("call", name, rv, err))
        if name == "close":
            # record EVERY close attempt (even one returning EBADF), so a
            # double-close -- whose second close fails -- is still seen
            fd = int(argstr.split(",")[0].split(")")[0])
            events.append(("rel", fd))
        elif name in FD_ACQUIRE and rv >= 0:
            events.append(("acq", rv))
        if name == "write" and argstr.startswith("2,") and rv > 0:
            record += rv                       # bytes written to stderr
    return events, exit_code, record


def fd_audit(events):
    """-> (leaks:list, doubles:list) by modelling each fd's LIFECYCLE, so fd
    reuse (open->close->open again reuses the same number) is not mistaken for a
    double-close. acquire -> live; close of a live fd -> clean (dead); close of
    an already-dead fd we opened -> double-free; still-live at the end -> leak.
    A close of an fd we never opened is an adopted fd -- ignored."""
    live = {}
    doubles = []
    for ev in events:
        if ev[0] == "acq":
            live[ev[1]] = True                 # (re)open
        elif ev[0] == "rel":
            fd = ev[1]
            if fd not in live:
                continue                       # adopted fd
            if live[fd]:
                live[fd] = False               # clean close
            else:
                doubles.append(fd)             # closing an already-closed fd
    leaks = sorted(fd for fd, isopen in live.items() if isopen)
    return leaks, sorted(set(doubles))


def occurrences(events):
    """Fallible syscalls in the happy trace as (name, when) 1-based per name."""
    counter, out = {}, []
    for ev in events:
        if ev[0] == "call" and ev[1] in INJECTABLE:
            counter[ev[1]] = counter.get(ev[1], 0) + 1
            out.append((ev[1], counter[ev[1]]))
    return out


def open_fds_before(events, name, when):
    """The set of our fds open at the moment of the `when`-th call to `name`."""
    seen, opened = 0, {}
    for ev in events:
        if ev[0] == "acq":
            opened[ev[1]] = True
        elif ev[0] == "rel":
            opened[ev[1]] = False
        elif ev[0] == "call" and ev[1] == name:
            seen += 1
            if seen == when:
                return {fd for fd, live in opened.items() if live}
    return set()


def main():
    argv = sys.argv[1:]
    stdin = b""
    if argv and argv[0] == "--stdin":
        stdin = argv[1].encode() if len(argv) > 1 else b""
        argv = argv[2:]
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        sys.exit("usage: mereoraii.py [--stdin DATA] [--] BINARY [args...]")
    binary, args = argv[0], argv[1:]

    print(f"mereoraii {binary}:")
    fails = 0

    # ---- happy-path audit -------------------------------------------------
    _happy = run(binary, args, stdin)
    interruptible = catches_interrupt(_happy[0])
    events, code, record = parse(_happy)
    leaks, doubles = fd_audit(events)
    acquired = [ev[1] for ev in events if ev[0] == "acq"]
    if leaks:
        print(f"  HAPPY  LEAK: opened fds never closed: {sorted(leaks)}")
        fails += 1
    if doubles:
        print(f"  HAPPY  DOUBLE-CLOSE: {sorted(doubles)}")
        fails += 1
    if not leaks and not doubles:
        print(f"  HAPPY  ok  ({len(acquired)} fd(s) acquired, all closed once, "
              f"exit {code})")
    if code != 0:
        print(f"  HAPPY  baseline exited {code} (not a success path) -- give "
              "valid input/args; the fault audit assumes a happy baseline")
        fails += 1

    # ---- fault audit: inject at each fallible syscall ---------------------
    sites = occurrences(events)
    if not sites:
        print("  FAULT  (no fallible syscalls in this run to inject)")
    for name, when in sites:
        expect_open = open_fds_before(events, name, when)
        # a real error (EIO) must clean up + record + exit non-zero
        fe, fcode, frecord = parse(
            run(binary, args, stdin, inject=f"{name}:error=EIO:when={when}"))
        fleaks, fdoubles = fd_audit(fe)
        tag = f"{name}#{when}"
        if fleaks:
            print(f"  FAULT  {tag:<16} LEAK ON ERROR: {sorted(fleaks)} not "
                  "closed by the tower")
            fails += 1
        elif fdoubles:
            print(f"  FAULT  {tag:<16} DOUBLE-CLOSE on error: {sorted(fdoubles)}")
            fails += 1
        elif fcode == 0:
            print(f"  FAULT  {tag:<16} exited 0 on a real error (should be "
                  "non-zero)")
            fails += 1
        elif frecord == 0:
            print(f"  FAULT  {tag:<16} no stderr record written on error out")
            fails += 1
        elif not interruptible:
            # No returning handler for SIGINT/SIGTERM, so -EINTR cannot reach
            # this program and there is no graceful contract to hold it to.
            print(f"  FAULT  {tag:<16} ok  (err: closed {len(expect_open)} "
                  f"fd + {frecord}B record, exit {fcode}; no interrupt handler)")
        else:
            # graceful contract: a -EINTR (Ctrl-C) / -EPIPE injection must still
            # clean up, but write NO record and exit 0
            ge, gcode, grecord = parse(
                run(binary, args, stdin, inject=f"{name}:error=EINTR:when={when}"))
            gleaks, gdoubles = fd_audit(ge)
            if gleaks or gdoubles:
                print(f"  FAULT  {tag:<16} graceful path leaks/double-closes "
                      f"{sorted(gleaks + gdoubles)}")
                fails += 1
            elif grecord or gcode != 0:
                print(f"  FAULT  {tag:<16} -EINTR not graceful (record {grecord}B, "
                      f"exit {gcode}; want 0B, exit 0)")
                fails += 1
            else:
                print(f"  FAULT  {tag:<16} ok  (err: closed {len(expect_open)} "
                      f"fd + {frecord}B record, exit {fcode}; -EINTR: graceful)")

    print("  RAII verified" if fails == 0 else f"  {fails} PROBLEM(S)")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
