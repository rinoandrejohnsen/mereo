#!/usr/bin/env python3
"""Suite 6 -- what a program owes the system around it.

The other suites ask whether a program is CORRECT (1, 2), what its
abstractions COST (3, 4) and what the compiler CATCHES (5). This one asks the
question the shell asks: does the program behave like a Unix program when the
system does something to it -- a signal, a closed descriptor, a short read.

Every claim here is observed from OUTSIDE the process, the way a parent sees
it: wait status, the file the program wrote, the terminal it was driving.
"""
import os, signal, subprocess, sys, termios, fcntl, time, select

DIR  = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(DIR))
B    = os.environ.get("OUT", "/tmp/mbuild/citizen")

CFLAGS = ("-O2 -fwrapv -nostdlib -static -fno-stack-protector"
          " -fno-tree-loop-distribute-patterns -fwhole-program"
          " -fno-strict-aliasing -fno-asynchronous-unwind-tables -fno-ident").split()
LDFLAGS = [f"-Wl,-T,{ROOT}/mereo.lds", "-Wl,-z,noseparate-code",
           "-Wl,--build-id=none", "-s"]

fails = []


def ok(name, passed, detail=""):
    """One claim. The detail is what was actually seen, and it is printed only
    when the claim fails -- a passing line that carries the failure wording
    reads like a failure, which is the wrong thing for a suite to teach."""
    print(f"  {'ok  ' if passed else 'FAIL'}  {name}"
          + ("" if passed else f"   {detail}" if detail else ""))
    if not passed:
        fails.append(name)


def build(src):
    """Transpile + compile one program, exactly as build.sh ships it."""
    name = os.path.basename(src)[:-len(".mereo")]
    c, out = f"{B}/{name}.c", f"{B}/{name}"
    with open(c, "w") as fh:
        r = subprocess.run([sys.executable, f"{ROOT}/mereoc.py", src],
                           stdout=fh, stderr=subprocess.PIPE)
    if r.returncode:
        sys.exit(f"transpile failed for {src}:\n{r.stderr.decode()}")
    r = subprocess.run(["gcc", *CFLAGS, *LDFLAGS, "-o", out, c],
                       stderr=subprocess.PIPE)
    if r.returncode:
        sys.exit(f"compile failed for {src}:\n{r.stderr.decode()}")
    return out


def wait_state(pid):
    """(kind, number) for a finished child: ('signal', n) or ('exit', n)."""
    _, st = os.waitpid(pid, 0)
    return ("signal", os.WTERMSIG(st)) if os.WIFSIGNALED(st) else ("exit", os.WEXITSTATUS(st))


def run_closed(prog, shut, stdin=b"", args=()):
    """Run prog with the descriptors in `shut` CLOSED. Returns (state, stdout)."""
    rin, win = os.pipe()
    rout, wout = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.dup2(rin, 0); os.dup2(wout, 1)
        for fd in (rin, win, rout, wout):
            if fd > 2:
                os.close(fd)
        for fd in shut:
            try: os.close(fd)
            except OSError: pass
        os.execv(prog, [prog, *args])
        os._exit(127)
    os.close(rin); os.close(wout)
    os.write(win, stdin); os.close(win)
    data = b""
    while True:
        chunk = os.read(rout, 4096)
        if not chunk: break
        data += chunk
    os.close(rout)
    return wait_state(pid), data


def signal_holder(prog, sig, ignore=None):
    """Start prog blocked on a pipe, send `sig`, report how it ended.

    `ignore` is a signal the PARENT sets to SIG_IGN before exec -- what nohup
    and a job-control-less shell leave behind, and what the program is supposed
    to honour rather than override."""
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.dup2(r, 0); os.close(w)
        if ignore is not None:
            signal.signal(ignore, signal.SIG_IGN)
        os.execv(prog, [prog])
        os._exit(127)
    os.close(r)
    time.sleep(0.35)
    os.kill(pid, sig)
    time.sleep(0.35)
    done = os.waitpid(pid, os.WNOHANG)
    os.close(w)
    if done == (0, 0):
        os.kill(pid, signal.SIGKILL); os.waitpid(pid, 0)
        return ("running", 0)
    st = done[1]
    return ("signal", os.WTERMSIG(st)) if os.WIFSIGNALED(st) else ("exit", os.WEXITSTATUS(st))


def on_terminal(prog, act):
    """Run prog with a pty as its controlling terminal, in the FOREGROUND process
    group, and hand `act` the master fd and the pid. Returns act's value."""
    master, slave = os.openpty()
    leader = os.fork()
    if leader == 0:
        os.setsid()
        fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
        prog_pid = os.fork()
        if prog_pid == 0:
            os.setpgid(0, 0)
            signal.signal(signal.SIGTTOU, signal.SIG_IGN)
            os.dup2(slave, 0); os.dup2(slave, 1); os.dup2(slave, 2)
            time.sleep(0.25)                    # ...to be made foreground first
            os.execv(prog, [prog])
            os._exit(127)
        os.setpgid(prog_pid, prog_pid)
        signal.signal(signal.SIGTTOU, signal.SIG_IGN)
        os.tcsetpgrp(slave, prog_pid)
        with open(f"{B}/pty.pid", "w") as fh:
            fh.write(str(prog_pid))
        time.sleep(10)
        os._exit(0)
    time.sleep(0.9)
    with open(f"{B}/pty.pid") as fh:
        prog_pid = int(fh.read())
    try:
        return act(master, prog_pid)
    finally:
        for p in (prog_pid, leader):
            try:
                os.kill(p, signal.SIGCONT); os.kill(p, signal.SIGKILL)
            except OSError:
                pass
        try: os.waitpid(leader, 0)
        except OSError: pass
        os.close(master); os.close(slave)


def canonical(fd):
    return bool(termios.tcgetattr(fd)[3] & termios.ICANON)


def stopped(pid):
    out = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                         capture_output=True, text=True).stdout.strip()
    return out.startswith("T")


# --------------------------------------------------------------------------
os.makedirs(B, exist_ok=True)
holder   = build(f"{DIR}/holder.mereo")
stdout_m = build(f"{DIR}/stdout_marker.mereo")
stderr_m = build(f"{DIR}/stderr_marker.mereo")
stdin_r  = build(f"{DIR}/stdin_reader.mereo")
keys     = build(f"{ROOT}/examples/keys.mereo")
upper    = build(f"{ROOT}/examples/upper.mereo")

TARGET = "/tmp/mereo_citizen_target"
SOURCE = "/tmp/mereo_citizen_source"


def target_bytes():
    try:
        with open(TARGET, "rb") as fh: return fh.read()
    except FileNotFoundError:
        return b"<missing>"


print("A. the standard descriptors are the standard descriptors")
# The program opens a file. If descriptor 1 was closed at startup, `open` hands
# it 1 -- and every later write to "standard output" goes into that file.
for fd, prog, want_state in ((1, stdout_m, ("exit", 0)),
                             (2, stderr_m, ("exit", 1))):
    for path in (TARGET,):
        try: os.unlink(path)
        except FileNotFoundError: pass
    state, _ = run_closed(prog, shut=(fd,))
    body = target_bytes()
    ok(f"fd {fd} closed: nothing of the program's own output lands in its file",
       body == b"", f"file holds {body!r}")
    ok(f"fd {fd} closed: the program still ends the way it would have",
       state == want_state, f"got {state}, want {want_state}")

with open(SOURCE, "wb") as fh:
    fh.write(b"FROMFILE\n")
state, out = run_closed(stdin_r, shut=(0,), stdin=b"")
ok("fd 0 closed: a read of standard input does not return the program's own file",
   b"FROMFILE" not in out, f"stdout held {out!r}")

# ...and none of that disturbs the ordinary case.
try: os.unlink(TARGET)
except FileNotFoundError: pass
state, out = run_closed(stdout_m, shut=())
ok("all three open: output goes to standard output, not to the file",
   out == b"MARKER\n" and target_bytes() == b"", f"stdout {out!r}, file {target_bytes()!r}")

print()
print("B. an interrupted program is REPORTED as interrupted")
# A program that catches a fatal signal to clean up owes the parent the truth
# about why it stopped: `for f in *; do prog $f; done` must not walk on past a
# Ctrl-C, and a supervisor must not read a shutdown as a completed job.
for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    got = signal_holder(holder, sig)
    ok(f"{signal.Signals(sig).name}: dies by the signal, not exit 0",
       got == ("signal", sig), f"got {got}")

print()
print("C. an inherited SIG_IGN is left alone")
# What nohup sets, and what a shell without job control leaves on a background
# job so that a terminal Ctrl-C does not reach it.
for sig in (signal.SIGINT, signal.SIGHUP, signal.SIGTERM):
    got = signal_holder(holder, sig, ignore=sig)
    ok(f"{signal.Signals(sig).name} already ignored: the program keeps running",
       got == ("running", 0), f"got {got}")

print()
print("D. the terminal is handed back the way it was found")
for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    def check(master, pid, sig=sig):
        raw = not canonical(master)
        os.kill(pid, sig)
        time.sleep(0.4)
        return raw, canonical(master)
    raw, back = on_terminal(keys, check)
    ok(f"{signal.Signals(sig).name}: the terminal is canonical again",
       raw and back, f"raw while running={raw}, canonical after={back}")


# Ctrl-Z is NOT covered, and the gap is deliberate rather than unnoticed: a
# program stopped by SIGTSTP keeps its terminal settings applied, so the shell
# that gets the terminal back has no echo and no line buffering until the
# program is continued. Restoring across a stop needs a resource to be able to
# say what "suspended" means for it -- a language question, not a runtime one --
# and until it exists there is nothing here to assert. Stopping itself works:
# SIGTSTP keeps its default disposition, so the process does stop.
def suspend_check(master, pid):
    os.killpg(pid, signal.SIGTSTP)
    time.sleep(0.5)
    return stopped(pid)


ok("SIGTSTP: the program stops", on_terminal(keys, suspend_check),
   "process was not in state T")

print()
print("E. a short read does not truncate the stream")
# `write` refuses a short transfer (`ensure written == count`). A read that
# comes back short is the same event on the other side, and a filter that drops
# the tail of its input while exiting 0 is the worst kind of pipeline citizen.
p = subprocess.run(f"( printf aaaa; sleep 0.3; printf bbbb ) | {upper}",
                   shell=True, capture_output=True)
ok("a stream that arrives in two pieces comes out whole",
   p.stdout == b"AAAABBBB", f"got {p.stdout!r}")

p = subprocess.run(f"head -c 200000 /dev/zero | tr '\\0' a | {upper} | wc -c",
                   shell=True, capture_output=True, text=True)
ok("200000 bytes in, 200000 bytes out", p.stdout.strip() == "200000",
   f"got {p.stdout.strip()}")

print()
print("F. and the things that already worked, still work")
p = subprocess.run(f"{stdout_m} | true", shell=True, capture_output=True)
ok("a reader that goes away is not the program's fault (EPIPE -> 0)",
   p.returncode == 0, f"got {p.returncode}")

p = subprocess.run(f"{stdout_m} > /dev/full", shell=True, capture_output=True)
ok("a full disk IS the program's fault (ENOSPC -> record + non-zero)",
   p.returncode != 0 and b"-28" in p.stderr, f"got {p.returncode}, {p.stderr!r}")

uname = build(f"{ROOT}/examples/uname.mereo")
p = subprocess.run(["strace", "-e", "trace=rt_sigaction,poll", uname],
                   capture_output=True, text=True)
ok("a program that owns nothing still installs only the SIGPIPE disposition",
   p.stderr.count("rt_sigaction") == 1 and "poll(" not in p.stderr,
   f"saw {p.stderr.count('rt_sigaction')} rt_sigaction, poll={'poll(' in p.stderr}")

print()
if fails:
    print(f"citizen: {len(fails)} FAILURE(S): " + ", ".join(fails))
    sys.exit(1)
print(f"citizen: all clear")
