#!/usr/bin/env python3
"""Attribute every byte of a mereo binary to the SPINE or to the cold tower.

The claim this exists to check is that mereo's extra size over hand-written C
sits in code that never runs -- the error blocks, the release tower, the
per-failure records. That has been asserted and never
measured, which is how the figures there drifted without anyone noticing.

Method: build with `-g`, walk the disassembly with `objdump -dl` so every
instruction carries the generated-C line it came from, and split at the first
`error_*:` label. mereoc emits the whole tower after the spine, in one run, so
that line is an exact boundary rather than a guess. Bytes are summed from the
instruction encodings, so nothing is estimated.

  tools/coldsplit.py PROGRAM.c BINARY.dbg      -> the split, as text
  tools/coldsplit.py --tsv PROGRAM.c BINARY.dbg
"""
import re, subprocess, sys

def boundary(cpath):
    """The first line of the cold tower: mereoc emits `exit:` and then every
    error block, to the end of the function. Before it is the spine."""
    with open(cpath) as fh:
        for i, line in enumerate(fh, 1):
            if re.match(r"^(error_\w+|release_\w+):$", line.strip()):
                return i
    return None

def split(cpath, binpath):
    cut = boundary(cpath)
    if cut is None:
        return None
    out = subprocess.run(["objdump", "-dl", binpath], capture_output=True,
                         text=True).stdout
    here, spine, cold, unknown = None, 0, 0, 0
    ins_spine = ins_cold = 0
    for line in out.split("\n"):
        m = re.match(r"^.*\.c:(\d+)\s*$", line)
        if m:
            here = int(m.group(1)); continue
        m = re.match(r"^\s+[0-9a-f]+:\s+((?:[0-9a-f]{2} )+)", line)
        if not m:
            continue
        n = len(m.group(1).split())
        if here is None:
            unknown += n
        elif here < cut:
            spine += n; ins_spine += 1
        else:
            cold += n; ins_cold += 1
    return {"cut": cut, "spine": spine, "cold": cold, "unknown": unknown,
            "ins_spine": ins_spine, "ins_cold": ins_cold}

def by_region(cpath, binpath, top=12):
    """Bytes per source REGION, so the spine can be read as well as sized.

    A region is the run of generated C between two labels, which is how mereoc
    lays a program out -- one label per scope, per loop, per splice -- so the
    names are the program's own rather than an invented partition."""
    labels = []
    with open(cpath) as fh:
        for i, line in enumerate(fh, 1):
            m = re.match(r"^(\w+):$", line.rstrip())
            if m:
                labels.append((i, m.group(1)))
    out = subprocess.run(["objdump", "-dl", binpath], capture_output=True,
                         text=True).stdout
    here, bytes_at = None, {}
    for line in out.split("\n"):
        m = re.match(r"^.*\.c:(\d+)\s*$", line)
        if m:
            here = int(m.group(1)); continue
        m = re.match(r"^\s+[0-9a-f]+:\s+((?:[0-9a-f]{2} )+)", line)
        if m and here is not None:
            bytes_at[here] = bytes_at.get(here, 0) + len(m.group(1).split())
    region = {}
    for ln, n in bytes_at.items():
        name = "(before the first label)"
        for at, nm in labels:
            if at <= ln:
                name = nm
            else:
                break
        region[name] = region.get(name, 0) + n
    return sorted(region.items(), key=lambda kv: -kv[1])[:top]


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tsv = "--tsv" in sys.argv
    if len(args) != 2:
        sys.exit("usage: coldsplit.py PROGRAM.c BINARY.dbg [--tsv]")
    r = split(*args)
    if r is None:
        sys.exit("no error/release label -- nothing to split at")
    tot = r["spine"] + r["cold"] + r["unknown"]
    if tsv:
        print(f"spine\t{r['spine']}\t{r['ins_spine']}")
        print(f"cold\t{r['cold']}\t{r['ins_cold']}")
        print(f"unattributed\t{r['unknown']}\t0")
    else:
        print(f"  boundary: generated C line {r['cut']}")
        for k, b, i in (("spine (runs)", r["spine"], r["ins_spine"]),
                        ("cold tower", r["cold"], r["ins_cold"]),
                        ("unattributed", r["unknown"], 0)):
            print(f"  {k:14} {b:6} bytes  {i:5} instructions"
                  f"  {100.0*b/tot:5.1f}%")
        print(f"  {'total':14} {tot:6} bytes")
        print("\n  the spine, by region:")
        for nm, n in by_region(*args):
            print(f"    {nm:28} {n:6} bytes")
