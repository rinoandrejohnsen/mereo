#!/usr/bin/env python3
"""Every `assembly "syscall"` number in linux.mereo, against the kernel's own
table in <asm/unistd_64.h>.

A wrong number is the one mistake in that file that no amount of reading
catches and no test necessarily catches either -- the neighbouring call often
exists, takes arguments in the same registers, and fails in a way that looks
like something else. So it is checked mechanically, against the header the
kernel installs rather than against a copy kept here.

Skipped: a declaration whose name is not a syscall name (`exit` is exit_group,
231, which is deliberate and documented where it is declared).

Usage: python3 tools/check_syscalls.py [linux.mereo]   -> exit 0 if all agree
"""
import re
import sys
import pathlib

HEADER = "/usr/include/asm/unistd_64.h"
# declarations whose mereo name is deliberately not the syscall's name
ALIASES = {"exit": "exit_group"}


def kernel_numbers(path):
    text = pathlib.Path(path).read_text()
    return {m.group(1): int(m.group(2))
            for m in re.finditer(r"^#define __NR_(\w+)\s+(\d+)", text, re.M)}


def declared(path):
    text = pathlib.Path(path).read_text()
    # The declarations sit inside `linux contains`, so the header carries
    # one level of indentation and its body two. Matched loosely on purpose --
    # this gate has gone vacuous twice by pinning the layout too tightly, and a
    # gate that matches nothing passes everything.
    for m in re.finditer(r"^[ ]*(\w+) is (?:final )?assembly \"syscall\"[ ]*$\n"
                         r"((?:[ ]+\S.*\n)+)", text, re.M):
        num = re.search(r"^\s*number is (\d+) in rax$", m.group(2), re.M)
        if num:
            yield m.group(1), int(num.group(1))


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "linux.mereo"
    if not pathlib.Path(HEADER).exists():
        print(f"check_syscalls: {HEADER} not present -- skipped")
        return 0
    table = kernel_numbers(HEADER)
    checked = wrong = unknown = 0
    for name, got in declared(src):
        want = table.get(ALIASES.get(name, name))
        if want is None:
            print(f"  {name}: no __NR_{name} in the header -- not checked")
            unknown += 1
            continue
        checked += 1
        if got != want:
            print(f"  {name}: declares {got}, the kernel says {want}")
            wrong += 1
    if wrong:
        print(f"check_syscalls: {wrong} wrong of {checked}")
        return 1
    if checked == 0:
        # a gate that checks nothing passes everything. This one went vacuous
        # once already, when the declaration syntax changed under its regex.
        print("check_syscalls: no declarations matched -- the gate is vacuous")
        return 1
    tail = f", {unknown} unknown" if unknown else ""
    print(f"  syscall numbers: {checked} checked against {HEADER}{tail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
