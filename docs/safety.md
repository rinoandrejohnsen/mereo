# Safety, and what it costs

## Safety was never the goal

This page compares mereo's safety with other languages, so it should say at the
top what the project is actually trying to do — because it is not this.

Competing on safety was never a design goal. The single bar is **performance
parity with a hand-written, optimised, Linux-correct C program**, and no safety
feature is accepted that costs more than that. What follows from that rule is
not less safety but a redirection of it: compile-time work is free at run time,
so everything that can be settled before the program runs is worth taking, and
everything that has to be paid for while it runs is not.

That is why the page reads the way it does. The long list of faults mereo cannot
have is a by-product of constraints adopted for other reasons; the checks it
performs are the ones that cost nothing; and the gaps left open — overflow,
uninitialised reads, division by zero — are open because the run-time fix for
each would spend exactly what the constraints bought. Their COMPILE-TIME halves
are a different matter, and are unbuilt rather than declined.

The comparisons below are therefore a measurement, not a claim to be winning.

## Four ways to be safe

There are four ways a language can stop a program from corrupting memory, and
they are usually discussed as if they were competing answers to one question.
They are not. They are answers to different questions, bought at very different
prices.

| strategy | the question it answers | who |
| --- | --- | --- |
| **Prove it** | can a prover discharge every run-time error as impossible? | SPARK |
| **Type it** | can the type system make the mistake unrepresentable? | Rust |
| **Analyse it** | can a checker reject the bad programs in a language that permits them? | the C++ profiles proposal |
| **Remove it** | can the construct that creates the fault simply not exist? | mereo |

mereo is the fourth, and that is worth stating plainly because it is the one
most easily mistaken for the third. mereo does very little static analysis. What
it has instead is a shape in which whole families of fault have nowhere to live
— and, in the places where analysis is what is actually required, it is
currently the weakest of the four.

This page is that comparison, with the gaps measured rather than described.

## What is removed, and therefore never checked

Three decisions do nearly all of the work, and none of them is a safety feature.
Each was made for another reason and pays a safety dividend.

**There is no heap.** No allocator, no `free`, no pointer that outlives what it
points to. Use-after-free, double-free and allocator corruption are not caught
here; they are unrepresentable. This is also why mereo needs no borrow checker:
the borrow checker exists to police lifetimes among values that can outlive
their creator, and nothing here can.

**There are no functions.** Reuse is splicing, so there is no call, no frame, no
return. Every buffer in the program is declared once in the single frame that
`_start` opens, which means **every address in a mereo program is valid for the
program's entire life**. A dangling stack pointer has no mechanism. The price is
stack space — a template spliced ten times occupies ten slots — and it is a real
price, paid to make a whole family impossible.

**There are no threads.** Data races are absent the way they are absent from a
single-threaded C program: vacuously, and only until threads arrive.

To those, add the one thing mereo does derive rather than remove: the release
tower. Cleanup is read off the scope, so a resource cannot be released twice and
cannot be forgotten. That is checked against C++ destructors across 53 paired
scenarios in `tests/scopes`, and it is the one place mereo is straightforwardly
ahead of Rust — Rust permits conditional moves and so needs a hidden boolean to
record whether a value still needs dropping, and Rust treats leaks as safe.

## What is refused

Beyond removal, mereo refuses ten specific mistakes. These are checks, and
`tests/checking` writes each one three times — mereo, C++ with the requirement
as a `concept`, Zig — and compiles all three. The full table is in
[What the compiler decides](compile-time.md); the safety-relevant rows are:

| the mistake | mereo | C++ | Zig |
| --- | --- | --- | --- |
| a constant index past a known array | refused | accepted | refused |
| a view laid over a backing too small for it | refused | accepted | accepted |
| a two-step acquisition with no ownership boundary | refused | accepted (leaks) | accepted (leaks) |
| a fallible call whose failure is ignored | refused | warned | refused |
| a resource named after the scope that released it | refused | refused | refused |
| a write to a read-only buffer | refused | refused | refused |

The pattern is that mereo decides things that are decidable from the text and
declines to guess at anything else. A view's fit is two declared sizes compared;
a constant index is one number against another. None of it requires a prover.

## What is not checked

This is the half that matters for an honest comparison, and all three of these
were confirmed by compiling the program, not by reading the compiler.

**Run-time bounds are unchecked by default.** `[buffer + i : 1]` is exactly as
unchecked as C. There is a checked form, `.at`, and the corpus uses it **9
times against 485 unchecked accesses**. The default is the unsafe one, and the
default is what gets written.

**Uninitialised reads are accepted.** A layout is zero-filled — `data is rec`
emits `char data[8] = {0};` — but a raw buffer is not: `raw is 8 bytes` emits
`char raw[8];`. Reading it before writing it compiles without complaint.

**Signed overflow is undefined.** A scalar is a C `long`, the build does not
pass `-fwrapv`, and so `n is n + 1` at `LONG_MAX` is undefined behaviour that
the optimiser is entitled to assume cannot happen. Defined wrapping is not a
*check* — but it is free, which by the rule above is the only question that
decides whether it is admissible. Measured across the corpus and on a hot loop:

| | 89 binaries | 800M byte-loads | vector instructions |
| --- | ---: | ---: | ---: |
| baseline | 379168 bytes | 77.4 ms | 42 |
| `-fwrapv` | 377248 bytes | 75.4 ms | 42 |

Smaller, no slower, identically vectorised. The expectation was that it would
cost — `-fno-wrapv` is what lets an optimiser assume an induction variable never
wraps — and it does not.

Rust checks all three: bounds at run time, initialisation in the type system,
overflow with a panic in debug and defined wrapping in release. SPARK proves all
three absent before the program runs. mereo does neither, today.

## Stroustrup's argument, and what mereo is evidence for

The argument — that C++ can reach safety through profiles and static analysis
rather than by adopting a borrow checker — is usually met with the objection
that analysing C++ is hard *because* C++ permits unrestricted aliasing, pointer
arithmetic and unbounded lifetimes. mereo is a data point on that dispute, but
not the one it first appears to be.

Analysis here is easy. Whole-program, freestanding, no functions, no heap — the
preconditions really are as good as they can get, and the consequence is that
the compiler settles lifetimes, layout, release order and connections without
anything resembling a solver.

But that ease was **bought, not discovered**. It is the direct consequence of
restrictions far heavier than the ones Stroustrup is arguing against. Rust asks
you to give up aliasing with mutation. mereo asks you to give up the heap,
functions, recursion, threads, generics and data structures. If the choice is
framed as restriction versus analysis, mereo does not vindicate analysis — it
shows that the analysis was downstream of the restriction all along.

So the fair reading is the uncomfortable one. Measured as *theorem proved per
unit of expressiveness surrendered*, the borrow checker is a bargain and mereo
is not. What mereo buys with its much larger payment is a different good: a
language with no runtime, no ABI and no allocator, in which the safety is a side
effect rather than the goal.

## SPARK, and what mereo would have to become

SPARK is the language this project is actually reaching toward, and it is
comfortably ahead. GNATprove discharges verification conditions to prove
**absence of run-time errors** — no buffer overflow, no overflow, no division by
zero, no uninitialised read — which is precisely the list mereo does not cover.

The resemblance is close enough to be misleading. mereo has `ensure`, 118 of
them in the corpus, and they look like SPARK contracts:

```
  read (buffer is block, capacity is 4096, count is n)
  ensure n as signed <= capacity
```

They are not contracts in SPARK's sense. A SPARK precondition is a proof
obligation discharged before the program runs; a mereo `ensure` is a run-time
comparison that the optimiser may or may not notice it can fold. The difference
is between *knowing* and *checking and hoping the optimiser agrees*.

The gap between those is the open work. Every bounds check in the corpus is
already eliminated by GCC — only the deliberately out-of-range case keeps one —
so the mechanism is working; what is missing is the compiler being able to
*state* that it worked. Of the accesses in the corpus, roughly 98% are induction
variables whose bound chains back to a constant, and are provable in principle.
The remaining 2% are data-dependent, and every one of them is in the TLS parser.

The analysis lands exactly on the security-critical code. That is either
encouraging or ominous, and the next section decides which.

## How much of the expert's proof is recoverable?

The argument for trying is this. A C programmer writing optimal, Linux-correct
code omits the bounds check because they *hold a proof* — they know the index
cannot run past the buffer. That proof is real; it is simply never written down.
mereo sees more of the program than GCC does, so it should be able to
reconstruct it. Here is `span_scan.c` from `tests/versus`, doing exactly that:

```c
count = _sys3(SYS_read, input, (long)block, 64);   /* block is 64 bytes */
if (!(count >= 0)) goto err_read;
long n = _scan(block, count, 58);                  /* no check on count */
```

The expert relied on `count <= 64` — a promise of Linux, not of the C. That fact
now exists in mereo, written on the `read` primitive as
`ensure count as signed <= capacity`.

`tools/mereoprove.py` measures how far this reaches. It runs on the post-splice
IR and classifies every access. Over the corpus — 86 programs, 3359 accesses:

| | | |
| --- | ---: | --- |
| **proved** | **3277** | **97.6%** |
| bound-unresolved | 45 | 1.3% |
| opaque-base | 31 | 0.9% |
| data-dependent | 5 | 0.1% |
| out of range | 1 | 0.0% |

Read the last row first. The single access that does *not* fit is
`access_past_end.mereo`, the planted violation that mereo already refuses — the
analysis finds it independently and flags nothing else in 3359. Its soundness is
checked the way everything else here is: a loop bound wider than its backing, an
affine index that overflows, a syscall capacity larger than its buffer, and an
off-by-one in the branchless guard are each planted and each reported.

The first honest version of this reached 81%, and every point from there to
97.6% came from removing an approximation rather than from adding information:
tracking both ends of an interval instead of only the upper, so a subtraction
is usable; evaluating each definition where it sits rather than at the use;
killing what a dominating assignment overwrites; and case-splitting on mereo's
branchless idiom — `lt is i < 15` then `idx is idx * lt` — which a plain
interval domain gets wrong, because it loses the correlation between `i` and
`lt` and concludes the index can reach 16.

That last one is worth dwelling on, because it briefly reported 406 accesses out
of range. Every one was a false alarm. An analysis that cries wolf is worse than
one that says nothing, so the rule is that anything not *proved* is reported as
unproved — never as a bug — unless the index is a constant.

**The 2.4% that remains is almost entirely the TLS parser.** Some of it is still
the analysis: there is no fixpoint across a template's ports. But some of it is
not, and that is the more interesting half — the program does not state enough.
The transcript index needs `tlen >= 36` for its *lower* bound, which is true,
and which the programmer knows, and which is written nowhere:

```
  ensure tlen + inner_len <= tr.size     -- stated
  foff is tlen - 36                      -- needs tlen >= 36, which is NOT
  a is [tr + foff : 1]
```

Adding that one line proves all four of those accesses. Without it, none of
them. That is the boundary this page has been looking for: not what the
compiler cannot compute, but what the program never said.

## What that would buy, with performance in the background

Nothing, at run time. This is the result worth being clear about, because the
intuition runs the other way. Every bounds check in the corpus is *already*
eliminated — GCC proves them redundant and deletes the check and its error block
together, which [Performance](performance.md) measures against C that never had
one. Proving them a second time, earlier, removes no instruction that is still
there.

What it buys is the **list**. A compiler that classifies accesses can report the
ones nobody has proved, and that report is 82 accesses out of 3359,
concentrated almost entirely in the one program that parses hostile input. The
value is not a faster binary. It is a list short enough to read.

It also buys checks the compiler does not currently make. `read (buffer is
small, capacity is 4096)` where `small is 16 bytes` is accepted today, and
emits a syscall asking the kernel to write 4096 bytes into a 16-byte stack
buffer — while the *view* form of the same mistake, `small as big`, has always
been refused by the fit check. Both are two literals compared. No program in
the corpus does it, so refusing it would cost nothing.

## Why this is rare, and why it is cheap here

The obvious question about the previous section is why, if the information is
right there, other languages have not done it. They have — repeatedly, and
better.

| | |
| --- | --- |
| **Ada SPARK** | this, plus a prover to discharge it — absence of run-time errors since the 1980s |
| **Astrée** | an abstract interpreter used to prove absence of run-time errors in Airbus flight-control C |
| **Frama-C** | value analysis over C by abstract interpretation, with contracts in ACSL |
| **Dafny, Why3, F\*, ATS** | languages where carrying the proof is the entire point |
| **GCC and LLVM** | value-range propagation and scalar evolution, in every optimiser in use |

The last row is the pointed one. **GCC already runs a version of this analysis
on mereo's output.** That is why the bounds checks vanish, and why removing one
by hand produced a byte-identical binary. Nothing above was a discovery; it was
a re-derivation, less well done, of something the backend does as a matter of
course.

So the real question is narrower: why is this not a hard *gate* — a compiler
that refuses what it cannot prove — in general-purpose languages? Four reasons,
and mereo evades three of them by accident.

**Separate compilation.** The decisive one. Whole-program analysis cannot
coexist with compiling one translation unit at a time and linking against
libraries whose source is absent. Every mainstream systems language treats that
as non-negotiable. mereo gave it up for unrelated reasons.

**False positives.** Rice's theorem guarantees that any such gate rejects some
correct programs. The prototype here demonstrated it: one missing correlation
between two variables produced 406 false alarms out of 3359 accesses. With a
heap, aliasing, dynamic dispatch and function pointers in the language, that
rate grows rather than shrinks. Astrée's success rests on a deliberately
restricted target — no dynamic allocation, no recursion — which is mereo's
shape, arrived at independently.

**Annotation burden.** SPARK works, and the price is contracts written
everywhere. That price is paid where certification demands it, in avionics and
rail, and almost nowhere else.

**Economics.** Rust's answer is that proving is unnecessary: check at run time,
let the optimiser delete what it can prove, and memory safety arrives with no
false positives and no annotations. For general-purpose code that is the better
trade. Proving wins only where the check cannot be afforded or a certificate is
required.

mereo is therefore not unusual for having the idea. It is unusual in having
**already paid the bill for other reasons** — whole-program, no heap, no
recursion and no separate compilation were all chosen to make the release tower
and the freestanding binary work. The analysis is cheap here because the
expensive part was settled years earlier, for a different purpose.

One caution belongs with the number. It covers 3359 accesses in a corpus written
by the same hand as the tool, checked against deliberately planted violations —
not the standard of a tool validated against industrial code it has never seen.

## What is actually beyond GCC

If GCC already does this, the fair question is whether mereo adds anything it
cannot reach. The answer splits three ways, and only the first is a clean win.

**The bound hoist, which GCC provably cannot do.** `span.at` tests its bound
against a length held in the view's bytes, so after splicing the bound is a LOAD
on every iteration. mereo ships `-fno-strict-aliasing`, because byte views
type-pun by design — so from GCC's side any store might have changed that
length.
mereo knows the store went to the buffer rather than to the view, and that fact
is erased by the translation to C. Compiling the same program with the pass on
and off:

| | vector instructions |
| --- | ---: |
| bound hoisted | 41 |
| bound left in the loop | 4 |

Same compiler, same flags. The information has to be acted on before the handoff
or not at all.

**The syscall's shape, which GCC can never recover.** That a `read` writes
`capacity` bytes into `buffer` appears nowhere in the emitted C — it is inline
assembly with a `"memory"` clobber, and a clobber says *something changed*, not
*this buffer, that many bytes*. mereo declares the relationship. But tested
directly, with the result written out so nothing is dead code, **neither GCC nor
mereoprove reports it**: the analysis classifies accesses, and a capacity is not
an access. This one is potential rather than achievement, and it is the same gap
as `ensure capacity <= buffer.size`.

**Diagnostics GCC could reach but does not issue.** Two planted violations, each
with a live loop and a buffer initialised first, so that an uninitialised-value
finding could not stand in for a bounds one:

| planted mistake | GCC, all warnings + `-fanalyzer` | mereoprove |
| --- | --- | --- |
| a loop to 100 over a 64-byte backing | silent | out of range |
| a loop bounded by a count capped at 4096, into 16 bytes | silent | out of range |

mereo catches both and GCC catches neither — but nothing *structural* stops GCC
here. It has value-range propagation and object sizes; it simply does not
diagnose. That is a missed diagnostic, not an impossibility, and it would be
dishonest to bank it as a capability.

Which leaves the asymmetry that is not in any of those rows. For correct code
GCC
proves these checks away, and the binary is byte-identical to one written
without
them. For incorrect code it says nothing at all. An optimiser has only two
outcomes available — quietly succeed, or quietly fail — and no way to report *I
could not prove this one*. A compiler can refuse. That is a difference in
contract rather than in capability, and it is the honest argument for moving the
analysis into `mereoc`.

## The bug that settles it

While writing the contract bounds that this page describes, a
remotely-triggerable buffer overflow turned up in mereo's own TLS client.
`read_record` took a 16-bit length off the wire, added five, and wrote up to
65540 bytes into a caller-supplied buffer with no bound on it — and the
ServerHello path passes a 512-byte buffer, before authentication.

It was in a whole-program, freestanding, no-heap, no-functions language with
every precondition this page has been praising. It compiled cleanly. It passed
every gate. It was found by reading the code, not by any analysis, and it was
fixed by writing the bound down by hand.

That is the argument against believing this page's first half too readily.
Removing a family of fault removes that family. It does not make the rest
smaller, and the one mereo left in place — a run-time index into a buffer — is
the one that has been the leading source of remote compromise for thirty years.

## Where each language actually stands

| | C | C++ | Rust | SPARK | mereo |
| --- | --- | --- | --- | --- | --- |
| Use after free | — | RAII, partial | prevented | prevented | **absent** (no heap) |
| Double free | — | RAII, partial | prevented | prevented | **absent** (no heap) |
| Leak | — | RAII | permitted | prevented | **prevented** (derived) |
| Dangling stack pointer | — | — | prevented | prevented | **absent** (no frames) |
| Bounds, constant | — | — | prevented | proved | **refused** |
| Bounds, run-time | — | — | checked | **proved** | **unchecked** |
| Uninitialised read | — | partial | prevented | **proved** | **unchecked** |
| Integer overflow | UB | UB | checked/wrapping | **proved** | **UB** |
| Data race | — | — | prevented | partial | **absent** (no threads) |
| Type confusion via cast | — | — | prevented | prevented | **fit refused** |
| Unhandled failure | — | warned | `Result` | prevented | **refused** |

Read the mereo column as two blocks. Everything marked *absent* is free and
permanent — it cost expressiveness, not analysis. Everything marked *unchecked*
is work not yet done, and no amount of the first block substitutes for it.

## What none of this is

It is not a claim that mereo is safer than Rust or SPARK. On the faults each
language actually proves, both are ahead, and SPARK is ahead of everything here.

The claim is narrower and, I think, more interesting: a language can reach a
large part of memory safety by subtraction rather than by proof, and the
subtraction is cheap to implement and impossible to get wrong, because there is
no analysis to be wrong. What it cannot do is reach the rest. For the rest there
is no shortcut — the bound has to be written down, or proved, and mereo is at
the beginning of that work rather than the end.
