#!/usr/bin/env python3
"""mereocheck -- verify the hot/cold layout of a mereo binary against the source
intent, on the ACTUAL assembly. A guarantee, not a hint: __builtin_expect and
the road pins ask GCC for the layout; this proves it delivered, and fails the
build if it ever silently regresses.

    python3 mereocheck.py BINARY [SOURCE.c]      (binary built with -g)

SOURCE.c is the transpiler's own output -- it holds the definitive
`LABEL_road_k:` labels, so the check knows which roads MUST exist. Without it,
a crossroad that GCC dissolved entirely (full if-conversion into cmovs, every
branch on the spine, no road labels left) would look like "no crossroads"; with
it, that dissolution is the loudest failure of all.

For every crossroad (a `LABEL likely goes` + `LABEL when ... goes` set, seen in
DWARF as the merge label `LABEL` and road labels `LABEL_road_k`):

  1. INLINE   the dispatch decision is on the hot path -- a conditional jump
              to each `when` road sits BEFORE the noreturn `exit`, so the
              fall-through (the likely road) is what runs hot. (Robust to GCC
              tail-duplicating the merge into every road's rejoin.)
  2. COLD     every `when` road sits AFTER `exit`, in the cold tail.
  3. NO LEAK  no data a `when` road uses is referenced on the hot path -- the
              regression case, where a cold road's selection (`&"nothing\n"`)
              got speculated onto the spine, is caught here even though the
              road LABEL was still cold.

Exit 0 and "OK" if every crossroad holds; exit 1 with the violation otherwise.
"""

import re
import sys

import mereodis


def rodata_refs(ops, comment, ro_base, ro_len):
    """The set of .rodata addresses an instruction references -- rip-relative
    (objdump resolves these in its comment) or a direct immediate."""
    addrs = set()
    for m in re.finditer(r"0x([0-9a-f]+)", ops + " " + comment):
        v = int(m.group(1), 16)
        if ro_base is not None and ro_base <= v < ro_base + ro_len:
            addrs.add(v)
    return addrs


def expected_roads(source):
    """The crossroads the transpiler emitted, from its C: {merge: {road_names}},
    plus the NESTED road names -- the ones whose crossroad sits inside a cold
    road, which the emitter marks `/* nested: NAME */`. Their dispatch is cold
    by construction, so they are held to the cold-region rule rather than the
    spine rule. This is the contract the binary must honor."""
    text = open(source).read()
    want = {}
    for m in re.finditer(r"\b(\w+)_road_(\d+)\b", text):
        want.setdefault(m.group(1), set()).add(f"{m.group(1)}_road_{m.group(2)}")
    nested = set(re.findall(r"/\* nested: (\w+) \*/", text))
    return want, nested


# the labels the emitter appends AFTER the program's steps -- the cold tail
COLD_LABEL = re.compile(r"^(?:error_|recover_|attempt_|release_)|^exit$"
                        r"|_road_\d+$")


def check(binary, source=None):
    _vars, labels, label_pairs = mereodis.dwarf_names(binary)
    insns, syms = mereodis.instructions(binary)
    ro_base, ro_data = mereodis.rodata(binary)
    ro_len = len(ro_data)

    # both dwarf `labels` and `syms` are {addr: name}; invert to name -> addr
    named = {name: addr for addr, name in labels.items()}
    for addr, name in syms.items():
        named.setdefault(name, addr)
    if "exit" not in named:
        print("mereocheck: no `exit` label -- not a mereo binary?", file=sys.stderr)
        return 1
    exit_addr = named["exit"]

    # crossroads that SURVIVED in the binary: merge M with roads M_road_k
    # over `label_pairs`, not `labels`: a road whose first statement is itself a
    # label shares that address, and the one-name-per-address map would hide it
    roads = {}
    for addr, name in label_pairs:
        m = re.match(r"^(\w+)_road_(\d+)$", name)
        if m:
            roads.setdefault(m.group(1), []).append((int(m.group(2)), addr, name))

    # the roads the source SAYS must exist. Any expected road missing from the
    # binary was dissolved onto the spine (if-converted) -- the worst violation.
    want, nested = expected_roads(source) if source else (None, set())
    if want is not None:
        found = {n for rs in roads.values() for _, _, n in rs}
        missing = {n for names in want.values() for n in names} - found
        if missing:
            for n in sorted(missing):
                print(f"  FAIL {n}: not in the binary -- the road was dissolved "
                      "onto the hot path (if-converted), every branch is on the "
                      "spine")
            return 1
    elif not roads:
        print(f"{binary}: no road labels found (pass the generated .c to require "
              "the source's crossroads) -- nothing to check")
        return 0

    road_addrs = {addr for rs in roads.values() for _, addr, _ in rs}

    # THE HOT REGION is the spine: the entry up to the first cold block. Cold
    # blocks are the roads themselves, the error records, the recovery and retry
    # blocks, and the release tower ending in `exit` -- everything the emitter
    # appends once the program's steps are done.
    #
    # `exit` alone is NOT the boundary, which is what this used to test. The
    # tower's floors are emitted BEFORE the exit label, so a program that faults
    # out of a loop can have a perfectly cold road sitting between `release_o`
    # and `release_keep` -- past every instruction that runs on the spine, and
    # still "not after exit". Widening the cold region also stops the tower's
    # own rodata from counting as a hot reference, which rule 3 reads.
    cold_starts = [a for a, n in label_pairs
                   if COLD_LABEL.search(n)] + [exit_addr]
    hot_end = min(cold_starts)

    # a first hot-region pass: the rodata each hot instruction references, and
    # which roads are reached by a conditional jump taken from the hot path
    hot_refs = set()
    hot_jumps = set()
    all_jumps = set()       # ...and every jump anywhere, for a NESTED road,
    for addr, mnem, ops, comment in insns:   # whose dispatch is cold itself
        if mnem.startswith("j"):
            m = re.match(r"\s*([0-9a-f]+)", ops)
            if m:
                all_jumps.add(int(m.group(1), 16))
                if addr < hot_end:
                    hot_jumps.add(int(m.group(1), 16))
        if addr < hot_end:
            hot_refs |= rodata_refs(ops, comment, ro_base, ro_len)

    # block ranges, so a road's own instructions can be isolated
    starts = sorted(named.values())

    def block_start(road_addr):
        """The road's first instruction, which is not always its label. GCC may
        hoist part of the block above the label -- a `mov` of the road's own
        constant -- and the dispatch then jumps a few bytes short of it. The
        block begins after the previous label, so anything in between is the
        road's."""
        prev = [a for a in starts if a < road_addr]
        return max(prev) + 1 if prev else 0

    def block_end(start):
        for a in starts:
            if a > start:
                return a
        return 1 << 62

    ok = True
    for merge, rs in sorted(roads.items()):
        good = True
        for _, raddr, rname in sorted(rs):
            # 2. COLD: the when road is outside the hot region
            if not raddr > hot_end:
                print(f"  FAIL {rname}: at {raddr:x} it is not past the "
                      f"spine -- no cold block starts before it (exit is at "
                      f"{exit_addr:x}), so this when road runs on the hot path")
                good = False
                continue
            # 1. INLINE: the road is reached by a dispatch jump, so the
            #    fall-through (the likely road) runs first. For a road on the
            #    spine that jump must come FROM the hot path; for a NESTED one
            #    the dispatch is cold by construction, so any jump proves the
            #    same thing -- that the road is still a road and was not merged
            #    into what precedes it.
            _from = all_jumps if rname in nested else hot_jumps
            if not any(block_start(raddr) <= t <= raddr for t in _from):
                _where = ("anywhere" if rname in nested else "on the hot path")
                print(f"  FAIL {rname}: no dispatch jump to it {_where} "
                      "-- the likely road may not be inline")
                good = False
            # 3. NO LEAK: nothing the road references appears on the hot path
            end = block_end(raddr)
            road_refs = set()
            for addr, mnem, ops, comment in insns:
                if raddr <= addr < end:
                    road_refs |= rodata_refs(ops, comment, ro_base, ro_len)
            for a in sorted(road_refs & hot_refs):
                s = ro_data[a - ro_base:].split(b"\0", 1)[0]
                shown = s.decode("latin1").replace("\n", "\\n")
                print(f'  FAIL {rname}: its data "{shown}" is also loaded on '
                      "the hot path -- a cold road's work leaked onto the spine")
                good = False
        if good:
            _kind = ("dispatch cold (nested)"
                     if any(n in nested for _, _, n in rs) else "dispatch hot")
            print(f"  OK   {merge}: {_kind}, {len(rs)} when road(s) cold "
                  f"(past the spine, which ends at {hot_end:x}), no leak")
        ok = ok and good
    return 0 if ok else 1


def main():
    if not 2 <= len(sys.argv) <= 3:
        sys.exit("usage: mereocheck.py BINARY [SOURCE.c]   (built with -g)")
    binary = sys.argv[1]
    source = sys.argv[2] if len(sys.argv) > 2 else None
    print(f"mereocheck {binary}:")
    rc = check(binary, source)
    print("  layout guarantee holds" if rc == 0 else "  LAYOUT VIOLATION")
    sys.exit(rc)


if __name__ == "__main__":
    main()
