#!/usr/bin/env python3
"""mereoprove -- how many accesses could the compiler prove in range?

A MEASUREMENT, not a compiler pass. It answers one question: when a C
programmer writes `p[i]` with no check, they are holding a proof in their head;
how much of that proof is recoverable from a mereo program's text?

It runs on the post-splice IR -- the flat step list `expand_procedures` hands to
`plan`, which is where such a pass would eventually live -- and classifies every
access `[base + index : width]`:

  proved            index bounded, and hi + width <= the backing's size
  OUT               index bounded, and it does NOT fit
  bound-unresolved  a bound exists but this prototype cannot chase it
  data-dependent    no bound in scope at all
  opaque-base       the backing itself did not resolve

WHAT IT KNOWS: constant indices; induction variables bounded at the top
(`loop_exit X >= B`) or the bottom (`loop_end cond X < B`), corrected for
increments that happen before the access; affine indices (`off is i * 8`);
interval arithmetic with BOTH ends, so subtraction is usable; reaching
definitions with kills, each definition evaluated where it sits rather than at
the use; `ensure` read as a premise, propagated through an assignment that
stores the guarded expression (`ensure tlen + n <= tr.size` then `tlen is tlen +
n`); syscall contract clauses, reached through the method's `prim` and `bind`;
and mereo's branchless idiom -- `lt is i < 15` then `idx is idx * lt` -- by
case-splitting on the comparison, which a plain interval domain cannot do
because it loses the correlation between `i` and `lt`.

WHAT IT DOES NOT KNOW: no fixpoint across a template's ports (the `opaque-base`
rows), and no relational domain, so two variables constrained by a shared fact
are still handled one at a time.

SOUNDNESS is checked the way everything else here is: by planting violations.
A loop bound wider than its backing, an affine index that overflows, a syscall
capacity larger than the buffer, and an off-by-one in the branchless guard are
each reported OUT. Across the corpus exactly ONE access is reported OUT, and it
is `access_past_end.mereo`, which mereoc already refuses.

Usage:  tools/mereoprove.py FILE...        one line per unproved access
        tools/mereoprove.py --tally FILE... corpus totals
"""

import sys, collections
sys.path.insert(0, "/home/rino/Projects/mereo")
import mereoc


class Skipped(Exception):
    pass


def classify(path):
    """Compile one file and hand back what the compiler decided about it."""
    mereoc.ACCESS_VERDICTS[:] = []
    try:
        mereoc.transpile(mereoc.load(path, set(), []), "x")
    except SystemExit:
        # mereoc refused it -- a refusal test, or a program needing arguments
        raise Skipped()
    return list(mereoc.ACCESS_VERDICTS)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tally_only = "--tally" in sys.argv
    if not args:
        sys.exit("usage: mereoprove.py [--tally] FILE...")
    tally, skipped = collections.Counter(), []
    for path in args:
        try:
            rows = classify(path)
        except Exception:
            skipped.append(path)
            continue
        tally.update(r[0] for r in rows)
        if not tally_only:
            for kind, base, expr in rows:
                if kind != "proved":
                    print(f"{path}: {kind:<17} [{expr}]   (backing {base})")
    total = sum(tally.values()) or 1
    print(f"\n{len(args) - len(skipped)} programs, {sum(tally.values())} accesses")
    for k, v in tally.most_common():
        print(f"  {k:<18} {v:5}   {100 * v / total:5.1f}%")
    if skipped:
        print(f"  ({len(skipped)} skipped -- refusal tests and programs "
              "needing arguments)")
