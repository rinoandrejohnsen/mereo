## The barrier

> **The barrier is performance parity with a hand-written, optimised,
> Linux-correct C program. No safety feature is accepted that costs more than
> that.**

Competing on safety is not a design goal. The barrier redirects safety rather
than reducing it: compile-time work is free at run time, so everything
settleable before the program runs is worth taking, and everything paid for
while it runs is not.

That was the reasoning. This page now records what it produced, including the
part that did not work, because the branch that tested it is closed and the
answer is worth more than the intention.

---

## The claim that was tested, and failed

**The hypothesis.** mereo is whole-program, heapless, function-free and
separately compiled from nothing. A verifier built into the transpiler should
therefore know more about the program's data and procedures than a C compiler
can, and should be able to hand that knowledge to GCC.

It was built. An interval analysis over the post-splice step list classified
every `[base + index : width]` in the program, refused what it proved wrong,
and reported the rest by cause. It reached **98.4% of 3056 accesses across 95
programs**. It was not wrong, and it is gone as of 2026-08-25.

### It changed no binary

`drop_proved_checks` deleted a run-time check when it could show the check
could never fire. Across 42 corpus programs it fired on **4 checks, in 1
program**. Leaving all four in gave the same `.text`, the same instruction
count, and a binary with the landing pads and their message strings gone either
way — GCC had removed them too.

That is the whole contribution to code generation, and it is zero.

### GCC already does it, and does it better

Traced through GCC's own pass dumps on the exam program rather than reasoned
about. Error blocks surviving:

006t.original   37 016t.cfg        32     unreachable code 044t.fre1       30
full redundancy elimination 045t.evrp        7     <- early value range
propagation

And the step that enables it, counting memory references to a `builder`:

038t.ccp1      281 041t.esra        0     <- Scalar Replacement of Aggregates

SRA's own log:

Created a replacement for page offset:   0, size: 64: pageD.4261    (data)
Created a replacement for page offset:  64, size: 64: page$8D.4262  (count)
Created a replacement for page offset: 128, size: 64: page$16D.4263 (limit)

GCC splits the aggregate into three SSA scalars, one per field, and then
ordinary range propagation tracks them. **30 of 37 error blocks go that way.**
mereo read the same fields as loads bounded by their *width*, and dropped every
value it knew about an instance the moment anything wrote to one.

The conditions `tree-sra.cc` requires — a complete fixed-size aggregate, no
volatile or bit-fields, constant in-bounds offsets, consistent access widths,
no address escaping outside a call argument — mereo's layouts meet by
construction. The analysis simply did not use them that way, and closing that
gap means reimplementing SRA.

### Every other lever was tried and is closed

| lever | result |
| --- | --- |
| `__attribute__((__assume__))` | **works** — the one that pays; see below |
| `if (!P) __builtin_unreachable()` | works, identical |
| `__builtin_expect` | a hint, not a fact — the branch survives |
| `restrict` | worth nothing, and it makes GCC emit a `memcpy` freestanding cannot link |
| `#pragma GCC unroll N` | cannot attach: it needs `for`/`while`, mereo emits GOTO loops |
| `-funroll-loops` globally | −4.8% instructions, the clock **cannot see it**, `.text` 6926 → 18421 |
| `#pragma GCC ivdep` | the copy loop is **already vectorised** without it |
| `__builtin_assume_aligned` | one instruction on an 8-byte load, nothing on a byte loop |
| overflow checks | **+23.8%**, and 120 traps GCC could not prove away |
| `access(mode, ptr, size)` | feeds `-Warray-bounds`, not range propagation |
| PGO, LTO, C++ output | measured worthless, or N/A in one translation unit |

Two structural reasons close the selective levers for good: pragmas need
**structured loops** and mereo emits gotos; per-function attributes need
**more than one function** and everything splices into `_start`. Neither is an
oversight — both are what buys −32% instructions against the C twin.

### Cross-checked against two other tools

Frama-C's Eva and rustc were run over the same programs. On the exam's 13 hard
accesses: **8 neither Eva nor mereo could prove**, 4 Eva proved and mereo did
not, and 2 appeared to be mereo's alone. That last claim was **withdrawn**: it
rested on a bug, and once `reaching` stopped answering with a value's declared
initialiser for a name grown in an enclosing loop, mereo reported those two as
well. No case survived where mereo proved something GCC could not.

### The failure mode was silence

Four soundness holes were found in the analysis in its final days, all of them
one question asked wrong — *which definitions can arrive here*:

- a definition inside a scope that **closed** killed the one before it, so
  `k is 40` then `k is 4` under a `leave` proved an access at 40 into 16 bytes;
- a definition always **overwritten before the back edge** was offered as a
  candidate, and the join threw away a mask;
- a value grown in an **outer** loop was read as its declared value, proving an
  offset that reaches 400 into 64 bytes;
- a `leave` folded with dataflow rather than constants marked **149 live steps
  unreachable**, so their accesses were never classified at all.

Each was found by CBMC or by running a binary, never by the test suite, because
what they broke they broke by staying quiet. A checker whose bugs are silent
costs more than one that is merely absent.

---

## What is kept, and it is one thing

**A syscall's half of its own contract**, stated to GCC as an assumption. This
is the single category that pays, and the reason is exact: a syscall is inline
assembly with a `"memory"` clobber, which says *something changed*, not *at
most this many bytes*. The fact is true of the program and nowhere in the
program's text, so no compiler can derive it.

Measured on a hot loop over a span whose length is a read count:

| | instructions |
| --- | ---: |
| with the promise | **29,000,043** |
| without it | **103,000,036** |

3.55×, and 3.8× on the clock. It is emitted only where an emitted branch
mentions the value it bounds, in the matching direction — six that no branch
used cost the exam **+10,995 instructions** before that pruning existed. The
pair `assume_needed` / `assume_idle` gates both halves in `test.sh`.

---

## What is removed, and therefore never checked

Three decisions do most of the work. None is a safety feature; each pays a
safety dividend.

**No heap.** No allocator, no `free`, no pointer outliving what it points to.
Use-after-free, double-free and allocator corruption are unrepresentable rather
than caught. This is also why no borrow checker is needed: it exists to police
lifetimes among values that outlive their creator, and nothing here can.

**No functions.** Reuse is splicing, so there is no call, no frame, no return.
Every buffer is declared in the single frame `_start` opens, so **every address
is valid for the program's whole life** and a dangling stack pointer has no
mechanism. The price is stack space.

**No threads.** No data races.

Subtraction is cheap and impossible to get wrong, because there is no analysis
to be wrong. It is also the only part of this page that never needed defending.

---

## What is still refused

None of these needed the analysis, and all of them survive it.

`tests/checking` writes ten mistakes three times over — mereo, C++ with the
requirement as a `concept`, Zig — and compiles all three. mereo refuses every
one *at the mistake*:

| the mistake | mereo | C++ | Zig |
| --- | --- | --- | --- |
| a constant index past a known array | refused | accepted | refused |
| a view over a backing too small for it (`view_fit`) | refused | accepted | accepted |
| a two-step acquisition with no ownership boundary | refused | accepted (leaks) | accepted (leaks) |
| a template that calls itself (`recursion`) | refused | accepted | accepted |
| a fallible call whose failure is ignored | refused | warned | refused |
| a local nothing reads (`unused_local`) | refused | warned | refused |
| a resource named after the scope that released it | refused | refused | refused |
| a write to a read-only buffer | refused | refused | refused |
| an out port wired to something that cannot take one | refused | refused | refused |
| a method reached through the wrong receiver | refused | refused | refused (line 5) |

And these mereo refuses with no counterpart in that suite, each decided from
numbers in the text:

| | |
| --- | --- |
| a syscall handed more room than the buffer has | `input.read (buffer is small, capacity is 4096)` with `small is 16 bytes` |
| a span claiming more bytes than its backing has | `ensure length <= data.size`, checked where the instance is adopted |
| a nested loop resetting the enclosing loop's counter | every scalar is visible everywhere, so the name really is the same name |
| a loop that cannot leave through any exit it has | no exit tests anything the body writes |

The pattern: mereo decides what is decidable **from two numbers in the text**
and declines to guess at the rest. A view's fit is two declared sizes compared.
A syscall's capacity against its buffer's size is two literals one line apart.
None of it needs a prover, and none of it was touched when the prover left.

The syscall row is the one nothing downstream can catch, for the same reason
the assume is worth keeping: in the emitted C the call is inline assembly, and
GCC is silent at every warning level including `-fanalyzer`.

---

## What is not checked

| | |
| --- | --- |
| run-time bounds | `[buffer + i : 1]` is as unchecked as C. `.at` checks, and costs 10% |
| integer overflow | wraps rather than being undefined; nothing detects it |
| division by zero | accepted, even for a literal zero divisor |
| uninitialised reads | a layout is zero-filled; `raw is 8 bytes` is not |
| termination | only the case where no exit tests anything the body writes |

These were once described as "unbuilt rather than declined". They are declined
now. The first was built, and the rest of this page is why it was removed.

Overflow is the one taken as far as it goes for free: the build passes
`-fwrapv`, so `n is n + 1` at `LONG_MAX` wraps instead of being undefined. That
detects nothing and costs nothing — and checking it instead costs **23.8%**,
which is the barrier saying no. Release Rust makes the same choice.

---

## Why safety will not be pursued again beyond what GCC gives

Not because it is hard, and not because it failed to work. Because it was
**measured, twice, against the thing it was meant to beat, and found redundant**.

Three findings settle it, and each is a number rather than a judgement:

1. **The analysis removed 4 checks in 1 of 42 programs, and GCC removed all
four anyway.** Same `.text`, same instruction count. 2. **GCC removes 30 of 37
error blocks on its own**, through a pass mereo would have to reimplement to
match. 3. **Every remaining lever is closed** — by measurement, or by mereo's
own shape (goto loops, one function) which exists for reasons worth more than
the levers.

If this is reopened, the number to beat is **4 checks, in 1 of 42 programs, all
of which GCC removed anyway.** Anything short of that is a diagnostic, not an
optimisation — and a diagnostic has a cheaper home.

**That home is CBMC.** `tests/cbmc.sh` is bit-precise, answers with a
counterexample rather than a verdict, and is run by hand when `core.mereo` or
the emitter changes. It found the guard that overflowed a signed long and the
`count + length <= limit` that wrapped unsigned, both of which the analysis had
accepted in silence. It is not on the routine run because its answers do not
change between edits.

What the analysis was genuinely good for was **finding bugs while it was being
written**, and those are fixed and gated on behaviour, not on the analysis:
`json.text` answering an offset outside its own document, `text.search`
matching a needle assembled from bytes outside its region, `starts` and `ends`
reading a needle before checking the view was long enough, and three buffers
sized for the value someone expected rather than what `format` can write. Each
has a black-box test that holds without a verifier.

---

## Where each language stands

| | C | C++ | Rust | SPARK | mereo |
| --- | --- | --- | --- | --- | --- |
| Use after free | — | RAII, partial | prevented | prevented | **absent** (no heap) |
| Double free | — | RAII | prevented | prevented | **absent** (no heap) |
| Leak | — | RAII | permitted | prevented | **prevented** (derived) |
| Dangling stack pointer | — | — | prevented | prevented | **absent** (no frames) |
| Bounds, constant | — | — | prevented | proved | **refused** |
| Bounds, run-time | — | — | checked | proved | **unchecked** |
| Uninitialised read | — | partial | prevented | proved | **unchecked** |
| Integer overflow | UB | UB | checked/wrapping | proved | **wraps** |
| Data race | — | — | prevented | partial | **absent** (no threads) |
| Type confusion via cast | — | — | prevented | prevented | **fit refused** |
| Unhandled failure | — | warned | `Result` | prevented | **refused** |

Read the mereo column as two blocks. *Absent* and *refused* are free and
permanent — they cost expressiveness, not analysis. *Unchecked* is a decision
now rather than a gap, and this page is the reasoning behind it.

**SPARK** is ahead and is the nearest relative. GNATprove discharges every
run-time check as a proof obligation and reports each it cannot; nothing stays
unproved silently. mereo's `ensure` resembles a SPARK contract and is not one —
it is a run-time comparison the optimiser may fold, not an obligation
discharged before running. SPARK's ranges are also *declared*, which hands its
prover the fact.

**Rust** checks bounds at run time and lets LLVM remove the provable ones,
silently. Measured here on the exam's own shapes, three of six checks survive
optimisation — including both relational cases. Release Rust wraps on overflow,
exactly as mereo does.

**Stroustrup's argument**, that C++ can reach safety through profiles and
static analysis rather than a borrow checker, gets a data point here that is
not the one it looks like. Analysis was easy in mereo because the language was
restricted first — and it still lost to the optimiser it was meant to inform.
Per theorem proved, the borrow checker remains the better bargain.

---

## What none of this is

It is not a claim to be safer than Rust or SPARK. On the faults each proves,
both are ahead, and SPARK is ahead of everything here.

The claim is narrower, and one half of it did not survive contact:

**A language can reach much of memory safety by subtraction rather than
proof.** That holds. No heap, no frames, no threads — four rows of the table,
free and permanent.

**And a verifier inside the transpiler can reach the rest.** That does not
hold. It was built, it reached 98.4%, and it changed nothing a modern optimiser
was not already doing. The one fact worth telling GCC is the one that is not in
the program's text, and that is a contract clause, not an analysis.
