mereo's performance claim is narrow and testable: it should cost nothing against
a hand-written C program that is **correct as a Linux program** — one that
closes what it opens on every path out including every failure, checks the calls
that can fail, and reports a failure rather than swallowing it. C that leaks a
descriptor on an error path is cheaper than mereo and is not a comparison worth
making, since mereo cannot write that program: its cleanup is derived, so the
leak is not available to it even as a mistake.

The figures below are measured by `tests/versus`, which builds each mereo
program beside such a twin and compares the instruction histogram and `.text`
size. Correctness is not taken on trust: both binaries are audited by
`mereoraii`, which traces the system calls, injects a failure at each fallible
one in turn, and requires the cleanup to close what was open and report it. A
twin that skips one close on one error path is rejected before its code is
compared at all.

## Against hand-written C

| Case | mereo | C | difference |
| --- | --- | --- | --- |
| one checked system call | 65 insns, 262 B | 65 insns, 262 B | identical, byte for byte |
| a counted loop | 62 insns, 241 B | 62 insns, 241 B | identical work |
| unchecked indexing | 144 insns, 585 B | 143 insns, 577 B | +1 |
| a span scan | 114 insns, 433 B | 113 insns, 430 B | +1 |
| one owned descriptor | 172 insns, 701 B | 170 insns, 689 B | +2 |
| two owned descriptors | 220 insns, 887 B | 218 insns, 875 B | +2 |
| checked indexing | 169 insns, 680 B | 164 insns, 668 B | +5 |

The release tower costs **two instructions, flat** — the same for two owned
descriptors as for one, so it does not scale with what a program holds. The
difference is frame setup, not work.

The comparison is on the instruction *multiset* rather than on bytes, and that
choice was forced twice. Byte-identity failed first: two programs doing
identical work landed on different bytes because the compiler chose one register
over another. Comparing the instruction *sequence* failed next, when two
instructions were merely scheduled in the other order. The multiset is what cost
means — an added check is a compare and a jump, a spill is a move, a missed
strength reduction is a multiply where a shift belonged — and register
allocation is none of those.

## An excess that turned out to be avoidable

Error blocks used to end with a marker naming the stage, distinct per stage, so
that two otherwise identical blocks could not be merged by the compiler. On a
program with two similar failure sites that cost an extra copy of the record
path — 8 system-call sites against the C twin's 7.

It was believed to be what made the layout claim checkable. It was not: the
layout checker works from DWARF labels and the `exit` landmark, and neither
moves when two tails fuse. Removing the markers cost nothing that could be
found — the crossroad layouts still verify, the disassembler prints the same
reconstruction, and all 83 binaries give byte-identical fault records under
fault injection, because the stage number is in the record's *text*, which is
what keeps the blocks distinct where it matters.

It was worth 4% of the corpus, and the case above now matches its twin's
system-call count outright.

## Checked access

A bounds check is not a fixed tax. Where the loop is bounded by the same length
the check tests, the compiler proves the check redundant and removes it —
the check and its whole error block are absent from the binary, matching C that
never had one.

Where the bound differs, the check survives, and its real cost is not the
compare but that a per-iteration bounds check stops the loop vectorising.
Measured over 200 million byte-loads:

| | time | vector instructions |
| --- | --- | --- |
| checked, invariant not stated | 51 ms | 1 — scalar |
| checked, `ensure` before the loop | 33 ms | 54 — vectorised |
| unchecked | 30 ms | 54 — vectorised |

Stating the invariant once recovers the vectorisation and keeps the check. This
is why mereo offers no way to disable a check: the cheaper option is to say what
is known, not to stop looking.

## Binary size

Hello world links to **784 bytes**, static, with no dynamic loader. A linker
script and a set of size-motivated flags roughly halved file size against the
default layout; `objcopy --strip-section-headers` would save a further 287 bytes
per binary but is declined, because the project's central claim is checked by
disassembling what ships.

## What has not been measured

There are no benchmarks against other languages, no throughput figures for the
libraries beyond the byte layer, and no measurements on hardware other than one
x86-64 machine. The corpus is small — a TLS client is the largest program — so
these figures describe small freestanding programs and should not be read as a
general claim.
