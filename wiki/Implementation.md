The reference implementation is `mereoc`, a Python program of roughly 6,000
lines that transpiles `.mereo` source to freestanding C. That C is then compiled
by GCC and linked with a custom script into a static binary. There is no second
implementation and no specification apart from the source and this article.

## The pipeline

```
  program.mereo  ->  mereoc.py  ->  program.c  ->  gcc  ->  static binary
```

The emitted C is deliberately plain: every mereo template becomes inlined code,
every system call becomes an `__asm__ volatile ("syscall")` with its operand
constraints spelled out, and the entry point is `_start` rather than `main`.
Nothing in the output calls a library function, because there is no library to
call.

The build flags state what the program is rather than tuning it.
`-fno-tree-loop-distribute-patterns` prevents GCC recognising a byte-copy loop
and rewriting it into a `memcpy` call that would then fail to link.
`-fwhole-program` is true by construction, since a program is one translation
unit. `-fno-asynchronous-unwind-tables` reflects that cleanup is ordinary jumps
that nothing ever unwinds. Each was measured: with them added, every binary in
the corpus came out byte-identical, so they buy correctness and honesty rather
than speed.

## Tools

| Tool | Purpose |
| --- | --- |
| `mereoc.py` | the transpiler |
| `mereocheck.py` | verifies hot/cold layout on the real assembly |
| `mereodis.py` | binary back to C, for reading what actually shipped |
| `mereoraii.py` | `strace` plus fault injection, asserting cleanup on real binaries |
| `tools/mereohl.py` | syntax highlighting, shared with the editor definition |

## Verification

The project's practice is to check claims against something outside itself. Six
gates run on every test pass:

| Claim | Checked against |
| --- | --- |
| system call numbers | the kernel's `<asm/unistd_64.h>` — 41 of them |
| resource release order | equivalent C++ binaries under `strace` — 53 scenarios |
| hot/cold layout | the disassembly of the shipped binary |
| program behaviour | 147 black-box cases on the built binaries |
| generated machine code | hand-written freestanding C — 9 paired cases |
| syntax highlighting | the editor's own highlighting library |

The release-order comparison uses C++ because that is the behaviour being
claimed, not a reimplementation of it. The highlighting gate exists because a
highlighter fails quietly: an unknown construct is still printed, merely
unstyled, so nothing about a stale definition is visible without a check.

A rule applies to the gates themselves: every gate ships with a deliberately
planted violation, run to prove the gate fails on it. A gate that matches
nothing accepts everything, and the difference is invisible from a passing
run.

## Byte-identical verification

The standing method for a change that should not alter behaviour is to transpile
the whole corpus before and after and compare the generated C byte for byte. It
is used for compiler changes, library additions and syntax migrations alike, and
it is what establishes that adding to a library costs programs that do not use
it exactly nothing.
