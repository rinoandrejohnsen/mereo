#!/usr/bin/env python3
"""mereoclobber -- verify that narrowing a syscall's memory clobber did not
move memory across the syscall.

A syscall's inline asm carries `"memory"`, which tells GCC the instruction may
touch anything. Narrowing that to the bytes a call really reads or writes lets
values stay in registers across the syscall -- but if the narrowed extent is
wrong, GCC may sink a store past the syscall, hoist a load before it, or kill a
store outright as dead. The kernel then sees bytes the program never intended,
and the failure is silent, intermittent, and load-dependent.

This compares a BASELINE binary (built with the blanket clobber) against a
CANDIDATE (built with the narrowed one) and asserts they agree on the one thing
narrowing must never change: the order of memory writes relative to syscalls.

    python3 mereoclobber.py BASELINE CANDIDATE

Loads may legitimately disappear -- that IS the optimization, and a load that is
gone cannot be read too early. Stores may not move, appear, or vanish: every
store the baseline performed before a syscall must still be performed before it.
Exits 1 and prints the divergence if they disagree.
"""
import re
import subprocess
import sys

# AT&T syntax: the destination is the LAST operand, so an instruction writes
# memory when its final operand is a memory reference. `lea` computes an address
# without touching memory; push/pop/call are frame traffic, not program data.
NOT_A_WRITE = {"lea", "leaq", "leal", "push", "pushq", "pop", "popq",
               "call", "callq", "ret", "retq", "jmp", "endbr64"}
# Multi-byte NOPs are spelled with a memory operand (`nopl 0x0(%rax)`) purely to
# take up space -- they are alignment padding and touch nothing. Counting them
# as writes made the checker report every program that GCC padded differently.
PREFIXES = {"cs", "ds", "es", "ss", "data16", "rep", "repz", "repnz", "lock"}
MEM_OPERAND = re.compile(r"\(%[a-z0-9]+\)|\(%[a-z0-9]+,")


def events(binary):
    """-> [(kind, detail)] for _start: every memory WRITE and every syscall."""
    out = subprocess.run(["objdump", "-d", "--no-show-raw-insn", binary],
                         capture_output=True, text=True, check=True).stdout
    seq, inside = [], False
    for line in out.splitlines():
        if re.match(r"^[0-9a-f]+ <_start>:", line):
            inside = True
            continue
        if inside and re.match(r"^[0-9a-f]+ <", line):
            break                      # the next symbol -- _start is over
        m = re.match(r"^\s+[0-9a-f]+:\s+(\S+)\s*(.*)$", line)
        if not (inside and m):
            continue
        mnem, ops = m.group(1), m.group(2).split("#")[0].strip()
        while mnem in PREFIXES and ops:          # `cs nopw 0x0(%rax,%rax,1)`
            mnem, _, ops = ops.partition(" ")
            ops = ops.strip()
        if mnem.startswith("nop") or mnem == "xchg":
            continue                             # padding, not a memory write
        if mnem == "syscall":
            seq.append(("syscall", ""))
            continue
        if mnem in NOT_A_WRITE or not ops:
            continue
        dest = ops.split(",")[-1].strip()
        if MEM_OPERAND.search(dest):
            # Record the KIND of write, not its operand text. Which register
            # holds the address is register allocation, and GCC is free to
            # choose differently in the two builds; a store moving across a
            # syscall is not.
            seq.append(("write", mnem))
    return seq


def regions(seq):
    """Split the event stream at syscalls -> the writes performed between each
    consecutive pair. This is exactly what a memory clobber constrains: GCC may
    always reorder writes BETWEEN two syscalls, but may not move one ACROSS one.
    Comparing per-region multisets is therefore both sound and stable against
    scheduling and register-allocation noise."""
    out, cur = [], []
    for kind, detail in seq:
        if kind == "syscall":
            out.append(sorted(cur))
            cur = []
        else:
            cur.append(detail)
    out.append(sorted(cur))
    return out


def main():
    if len(sys.argv) != 3:
        print(__doc__.strip())
        return 2
    base, cand = sys.argv[1], sys.argv[2]
    a, b = regions(events(base)), regions(events(cand))
    if len(a) != len(b):
        print(f"mereoclobber: FAIL -- {len(a) - 1} syscalls in the baseline, "
              f"{len(b) - 1} in the candidate")
        return 1
    for i, (ra, rb) in enumerate(zip(a, b)):
        if ra != rb:
            where = ("before the first syscall" if i == 0 else
                     f"between syscall #{i} and #{i + 1}")
            gone = [w for w in ra if ra.count(w) > rb.count(w)]
            new_ = [w for w in rb if rb.count(w) > ra.count(w)]
            print(f"mereoclobber: FAIL -- the writes {where} changed")
            print(f"  baseline  ({len(ra)}): {' '.join(ra) or '<none>'}")
            print(f"  candidate ({len(rb)}): {' '.join(rb) or '<none>'}")
            if gone:
                print(f"  LOST from this region:   {' '.join(sorted(set(gone)))}"
                      "   <- a store the kernel may have needed")
            if new_:
                print(f"  ARRIVED in this region:  {' '.join(sorted(set(new_)))}"
                      "   <- a store that moved across a syscall")
            return 1
    nw = sum(len(r) for r in a)
    print(f"mereoclobber: ok -- {nw} memory writes, {len(a) - 1} syscalls, "
          f"every write in the same inter-syscall region")
    return 0


if __name__ == "__main__":
    sys.exit(main())
