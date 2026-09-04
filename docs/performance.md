# Performance

The claim is narrow and testable: nothing costs more than a hand-written C
program that is **correct as a Linux program** — one that closes what it opens
on every path out including every failure, checks the calls that can fail, and
reports a failure rather than swallowing it. C that leaks a descriptor on an
error path is cheaper, and not worth comparing: mereo cannot write that
program. Cleanup is derived, so the leak is not available even as a mistake.

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
identical work landed on different bytes because the compiler chose one
register over another. Comparing the instruction *sequence* failed next, when
two instructions were merely scheduled in the other order. The multiset is what
cost means — an added check is a compare and a jump, a spill is a move, a
missed strength reduction is a multiply where a shift belonged — and register
allocation is none of those.

## What an error block costs

A failing `ensure` writes a record and routes into the release tower, so each
one is a small block of code in the binary's cold tail. Two error blocks
differing only in their record text share everything after it. The compiler
merges the identical tails; the layout gate is unaffected, working from DWARF
labels and the `exit` landmark rather than from the shape of the blocks.

What keeps the records distinct is the text itself, which names the stage:

```
  stat: 2: inspect linux.files: -21
```

So a program makes as many system calls as its C twin, including where it has
several similar failure sites.

## Checked access

A bounds check is not a fixed tax. Where the loop is bounded by the same length
the check tests, the compiler proves the check redundant and removes it — the
check and its whole error block are absent from the binary, matching C that
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
is why mereo offers no way to disable a check: the cheaper option is to say
what is known, not to stop looking.

Read the last two rows together, though, because they settle a design question.
33 ms against 30 ms is a **10% residual**, and hand-written C would not carry
that check at all. The bar is parity with that C, so a checked access can never
be the default. `[buffer + i]` stays unchecked and matches the 30 ms; `.at` is
opt-in and costs the 10%. The only way to make the default form safer without
spending that 10% is to decide it at compile time, which is what
[Safety](safety.md) measures.

## What is worth telling the compiler

The compiler already knows everything the program says. Stating a bound mereo
has proved — as an assumption, in front of a proved store in the generated
C — produces a **byte-identical binary**. That is not surprising once
said plainly: the proofs are built out of buffer sizes, branch conditions and
syscall contracts, and all three are already in the emitted C as literals, as
branches, and as assumptions. GCC re-derives the same ranges.

So the analysis makes no binary faster. Its product is the list of accesses it
could not prove, which [Safety](safety.md) covers. Only a fact **absent from
the program's text** is worth stating, and there is one:

| a log summariser, 84 MB of input | size | time |
| --- | ---: | ---: |
| the kernel's promise stated | 5920 B | 53.9 ms |
| the kernel's promise tested | 6576 B | 54.9 ms |

A `read` never returns more than the capacity it was given. That is the kernel
ABI's promise rather than a consequence of any code in the translation unit —
the call site is inline assembly with a `"memory"` clobber, and a clobber says
*something changed*, not *at most this many bytes*. Stating it lets a branch
fold away, at 117 sites across the corpus.

### Form, which is not knowledge

Three changes did move binaries, and none of them told the compiler a new fact.
Widening the byte scan to a word at a time took find-heavy code from 58 ms to
19 ms. Hoisting a checked loop's bound out of the loop body took it from 4
vector instructions to 41. Hoisting a copy loop's base address out of the loop
took 208 bytes off the corpus, at no change in time. Each states something GCC
already had, in a shape its optimiser acts on — and the first two are cases
where every small reproduction optimises unaided and the whole program does
not.

### Aliasing, measured

mereo gives up every aliasing mechanism a C compiler has. Memory is bytes,
`unsigned char` aliases everything by the language's own rule, and `-fno-
strict-aliasing` ships because byte views type-pun by design. Rust, by
contrast, marks every mutable reference `noalias` automatically.

It costs nothing here. GCC names its own aliasing failures, and the corpus has
exactly **seven** loops it declined to vectorise because it "would need a
runtime alias check" — all of them the byte copy inside a builder. Rewriting
all seven to copy through `restrict`-qualified pointers gives byte-identical
binaries:

| | span | stat | uname |
| --- | ---: | ---: | ---: |
| base hoisted | 2304 | 2512 | 1488 |
| base hoisted, and `restrict` on top | 2304 | 2512 | 1488 |

The limit on those loops was never disambiguation. It was that the destination
was recomputed from the builder's own bytes on every iteration — address
arithmetic, which is the row above. That result is about code shaped like this
one. Two things would change it: emitting real calls rather than splicing,
which is where `restrict` earns its keep, and typed numeric work, where the
languages that carry type information beat C for exactly this reason.

## Binary size

Hello world links to **784 bytes**, static, with no dynamic loader. A linker
script and size-motivated flags roughly halved file size. `objcopy --strip-
section-headers` would save a further 287 bytes per binary and is declined,
because the central claim is checked by disassembling what ships.

## The compiler is part of the result

Every figure above is a GCC figure, and that is not a neutral choice. The same
emitted C, compiled by Clang instead, changes by a third in either direction
depending on the program — so a comparison drawn from one program will not
carry to the next.

Two programs, each compiler swept over `-O2`/`-O3` with and without
`-funroll-loops`, each quoted at its own best:

| | GCC | Clang | |
| --- | --- | --- | --- |
| An HTTP head and JSON body reader | 983 cycles, 4,674 instructions | 1,647 / 6,187 | Clang **1.68x** slower |
| That parser plus a SQLite reader, serving a request | 536 cycles, 2,564 instructions | 491 / 2,962 | Clang **0.92x** — faster |

Clang emits **more** instructions for mereo in both cases — 32% more in the
first, 16% in the second. In the first that decides it; in the second Clang
still wins, because of what the slot accounting shows:

| | issue slots | retiring | fetch-latency stalls |
| --- | --- | --- | --- |
| mereo, GCC | 3,168 | 71% | 186 |
| mereo, Clang | 2,920 | **96%** | **~0** |
| the hand-written C twin, Clang | 3,166 | 82% | 135 |

**GCC's builds of mereo stall on instruction fetch and Clang's do not.** That
is the whole of the difference. mereo has no functions — every template is
spliced, so a program is one `_start` — and GCC lays that single large function
out in a way the front end keeps having to catch up with. Where that stall is
larger than Clang's extra instructions, Clang wins; where it is not, GCC does.

A third program says the same thing more strongly, and then says something the
first two did not. The SQLite demo server — HTTP parse, b-tree walk, JSON
build, one response — measured over 1000 requests, user space only, twelve
interleaved rounds:

| | instructions | cycles | stdev of cycles |
| --- | --- | --- | --- |
| gcc -O2, before the work below | 1,936 | 1,595 | |
| clang -O3, before | 1,649 | 1,323 | |
| gcc -O2, after | **1,375** | 1,259 | 8.4 (0.67%) |
| clang -O3, after | **1,348** | 1,210 | 16.5 (1.37%) |

**Instruction counts have zero variance** — 1,375 and 1,348 in all twelve runs,
identically. Cycles carry about 1%, and Clang's spread is twice GCC's, which
fits: its binary is 89% larger in `.text` and its hot path is threaded through
cold code, so it is more sensitive to what else the machine is doing. A
difference has to clear roughly 30–50 cycles here before it means anything.

Here Clang emitted **fewer** instructions than GCC, not more — the opposite of
both rows above, and the reason to distrust any generalisation drawn from one
program. The cause was neither a better `memcpy` nor idiom recognition. Both
binaries contain **zero call instructions**, no undefined symbols and no
dynamic dependencies; they compile the same library. Clang's optimised IR does
hold four `llvm.memcpy` and four `llvm.memset` intrinsics, but every one is a
fixed-size C aggregate initialiser — the sigaction blocks, `char bound[16] =
{0}` — expanded inline, and GCC does the same. What Clang actually did was
**unroll**: 101 distinct loops in GCC's build against 46 in Clang's, bought
with 89% more `.text`.

No GCC flag reproduces it. Twelve configurations were swept — `-funroll-loops`,
`-funroll-all-loops`, raised `max-unroll-times` and `max-unrolled-insns`,
`-fpeel-loops`, aggressive complete-peeling, `-falign-loops=32`, `-fipa-pta`,
`-march=native`, and dropping `-fno-tree-loop-distribute-patterns` so GCC may
rewrite copy loops as `memcpy`. The best moved six instructions out of 1,936;
the unrolling flags grew static size to 2,192 and left dynamic work unchanged.
GCC's unroller declines loops whose trip count is a runtime value, and raising
its thresholds does not change that judgement.

So the arithmetic moved into the library, where it helps both compilers. Six
changes across two rounds, in order of what they were worth:

- **`varint` takes a single byte without entering its loop.** In a SQLite
  record header that is nearly every varint. Worth 273 instructions a request
  to GCC and 48 to Clang — Clang was already unrolling it, which is most of why
  this one change closed most of the gap.
- **`builder.add` names its destination first.** Written `target is data +
  count`, the port is substituted as an EXPRESSION into `copy`'s loop, so every
  byte reloaded `data` and `count` from the block; an unsigned-char store may
  alias them, so the compiler is not permitted to hoist it. `into is data +
  count` took the inner loop from eight instructions and two loads per byte to
  five and none.
- **`text.copy` moves a word at a time, with a 4/2/1 tail.** Every copy has a
  tail and most of the copies this library makes ARE tail: a six-byte literal
  never enters the word loop.
- **`text.format` answers anything under a hundred with no loop** — neither the
  staging loop nor the reversing one. An id, a count, a small Content-Length.
- **`text.equals` answers lengths under eight with two overlapping loads**
  rather than one per byte, so a six-byte route check costs two compares.
- **`writev`** removes the copy of the response body into the head buffer.

Together: GCC 1,936 → 1,375 instructions and 1,595 → 1,259 cycles, **−29% and
−21%**. GCC's gap to Clang fell from 17% to 2% on instructions and from 21% to
4% on cycles. Most of what the better unroller was buying now sits in the
source, where neither compiler has to find it.

### Layout is real, verifiable, and has never predicted anything

GCC partitions cold blocks into `.text.unlikely`; Clang has no equivalent on by
default, so `__builtin_expect` steers its *prediction* but not its *placement*
and the cold chain is left inline for the hot path to jump over. Counting the
branch after each syscall check:

| | GCC | Clang |
| --- | --- | --- |
| `abc` (straight line) | 3 fall-through, 0 inverted | 1 / 2 |
| `catview` (one loop, syscalls inside) | 4 / 0 | 2 / 2 |
| the SQLite server | 6 / 1 | 5 / 2 |

GCC wins on all three regardless of shape. It has never once decided a
measurement. `-mllvm -enable-ext-tsp-block-placement` repairs Clang's layout —
3-of-3 on `abc`, matching GCC exactly — and on the server it raised taken
branches from 118 to 141 and cost 2% in cycles. Nothing in the C changes it: on
Clang 22, six source forms were tried, including plain `long`s with no fields,
no casts and no negations, and every one keeps the cold block inline. Moving
the cold region above the hot path in the emitted C does fix `abc` outright,
and does nothing for the server.

`catview` is the counter-example that keeps the whole section honest. Copying
64 MB through a 4 KB buffer, Clang runs 229,485 instructions against GCC's
295,023 — 22% fewer — and takes 5% MORE cycles, consistently. Taken branches
are equal (16,390 against 16,386), so unrolling has nothing to work with in a
loop whose body is two syscalls. Fixing the polarity changed nothing.
Instruction-cache misses are ~0.1 per iteration, ITLB misses ~100 in total, and
the uop cache delivers nothing at all — every uop comes from legacy decode.
**Why GCC wins there is not known.** Code density is the surviving hypothesis;
Clang's loop body spans 863 bytes to GCC's 441.

Three things follow. `build.sh` uses GCC, and that is the right default — but a
mereo program that turns out to be fetch-bound may do better under Clang, and
the way to find out is the topdown slot accounting above rather than a guess.

Where the two compilers differ by more than a little, the difference is usually
a loop the library should not have been running, and closing it in `core.mereo`
is worth more than picking a compiler: it is measured once and paid by both.

And treat any figure here as a claim about one compiler on one program.
Instruction counts are deterministic and safe to quote. Cycles are not, and the
trap is worse than run-to-run noise: on this hardware the *measurement
configuration* moves them. A three-event `perf` run showed one build 4% ahead
of another; with two events and a two-binary rotation the same pair were 0.5%
apart with overlapping spreads, and the 4% was retracted. Quote cycles only as
a minimum or a mean with its spread, from the same binary measured the same
way.

## What has not been measured

There are no benchmarks against other languages, no throughput figures for the
libraries beyond the byte layer, and no measurements on hardware other than one
x86-64 machine. The corpus is small — a TLS client is the largest program — so
these figures describe small freestanding programs and should not be read as a
general claim.