#!/usr/bin/env python3
"""mereo's C, as Frama-C will accept and can actually check.

Three things need saying differently. None changes what the program does.

A kernel promise is a GCC assume attribute, which Frama-C does not parse. Here
it is an ACSL assertion: Eva reports it unproven and then holds it, which is
what a promise IS.

A syscall wrapper is inline asm with a "memory" clobber, and a clobber says
SOMETHING changed. Eva believes it, loses which object every pointer refers to
-- "garbled mix of &{rbuf; line; obuf; arena}" -- and then cannot check a
single one of those accesses. The absence of an alarm there is not a proof.
What it needs is exactly what mereo already declares: which port is the
buffer, which is the extent, what the call promises about the count. That is
generated below from the wrapper's own parameter names, which ARE the port
names.

And `_start` is sometimes naked asm that jumps to `_run`; the caller picks.
"""
import re
import sys

src = open(sys.argv[1]).read()

# ---- a promise: __attribute__((__assume__(X))); -> /*@ assert X; */
src, n_as = re.subn(r"__attribute__\s*\(\(\s*__assume__\s*\((.*)\)\s*\)\)\s*;",
                    lambda m: "/*@ assert %s; */" % m.group(1).strip(), src)

# ---- GCC-isms the parser does not take
src = re.sub(r"__attribute__\s*\(\(\s*externally_visible\s*\)\)", "", src)
src = re.sub(r"__attribute__\s*\(\(\s*noreturn\s*\)\)", "", src)

# ---- syscall wrappers: replace the asm body with a contract
WRAP = re.compile(
    r"static inline __attribute__\(\(always_inline\)\)\s+"
    r"(long|void)\s+(_assembly_\w+|_write|_sigaction|_exit)\s*\(([^)]*)\)\s*\{"
    r"(?:[^{}]|\{[^{}]*\})*\}", re.S)


def contract(m):
    ret, name, params = m.group(1), m.group(2), m.group(3)
    ps = [q.strip().split()[-1].lstrip("*") for q in params.split(",") if q.strip()]
    L = []
    if "buffer" in ps and "capacity" in ps:          # a read: it FILLS
        L += ["requires capacity >= 0;",
              r"requires \valid(((char *)buffer) + (0 .. capacity - 1));",
              r"assigns ((char *)buffer)[0 .. capacity - 1] \from \nothing;",
              r"assigns \result \from \nothing;",
              r"ensures \result <= capacity;"]
    elif "buffer" in ps and "count" in ps:           # a write: it READS
        L += ["requires count >= 0;",
              r"requires \valid_read(((char *)buffer) + (0 .. count - 1));",
              r"assigns \result \from \nothing;",
              r"ensures \result <= count;"]
    elif ret == "long":
        L += [r"assigns \result \from \nothing;"]
    else:
        L += [r"assigns \nothing;"]
    return ("/*@ " + "\n    ".join(L) + " */\n"
            + ret + " " + name + "(" + params + ");")


src, n_wrap = WRAP.subn(contract, src)

if "int main(" not in src:
    src += "\n\nint main(void) { _start(); return 0; }\n"
sys.stderr.write("  promises -> assertions: %d   wrappers given a contract: %d\n"
                 % (n_as, n_wrap))
open(sys.argv[2], "w").write(src)

# Usage, and what it is for:
#
#   python3 mereoc.py programs/tls/https.mereo > hs.c
#   python3 tools/toframa.py lg.c lg_acsl.c
#   frama-c -eva -eva-precision 3 -main _start lg_acsl.c
#
# A SECOND OPINION, not a replacement. On one measured program they agreed on eight of
# the thirteen accesses neither can prove, which is worth more than either
# verdict alone: those eight are hard, not a mereo weakness. Eva proves four
# that mereo does not -- the hash-table reads. And mereo proves two that Eva
# does not, at precision 3 and with the octagon domain: `line[held]` and
# `arena[used]`, both of the form `offset + length <= capacity`, which is the
# shape `tighten` keeps as `key + others <= rhs` and an interval cannot hold.
#
# `-main _start` for a program that reads stdin; `-main _run` where `_start`
# is naked asm that jumps to it, which is how a program taking arguments is
# emitted. The second needs a driver before it gets past 15% coverage: `_run`
# receives the stack pointer and Eva has no reason to believe anything about
# what it points at.
#
# Ignore the alignment, overflow and initialisation alarms. They come from the
# freestanding style -- `long` holding an address, `asm` writing `_r` -- and
# say nothing about mereo. The bounds alarms are the ones to read.
