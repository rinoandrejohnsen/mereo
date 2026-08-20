# Safety, and what it costs

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
the optimiser is entitled to assume cannot happen. This is the cheapest of the
three to improve — `-fwrapv` makes it defined wrapping — but defined wrapping is
still not a *check*.

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
| **proved** | **2722** | **81.0%** |
| bound-unresolved | 592 | 17.6% |
| opaque-base | 31 | 0.9% |
| data-dependent | 13 | 0.4% |
| out of range | 1 | 0.0% |

Read the last row first. The single access that does *not* fit is
`access_past_end.mereo`, the planted violation that mereo already refuses — the
analysis finds it independently and flags nothing else. That is the project's
standing non-vacuity rule holding.

Read the fourth row next. Only **13 accesses in the whole corpus** are genuinely
data-dependent, with no bound in scope at any level. The bound almost always
exists.

The 17.6% in the middle is the honest part: a bound exists and the prototype
cannot chase it. Nearly all of it is x25519's carry loops and the TLS parser,
and the two gaps are specific. It tracks upper bounds only, so any subtraction
is refused. And — the one that matters — **it does not read `ensure` as a
premise.** At the exact site of the overflow described below, the transcript
index is unproved despite the fact being stated one line above it:

```
  ensure tlen + inner_len <= tr.size     -- the fact
  foff is tlen - 36                      -- refused: a subtraction
  a is [tr + foff : 1]                   -- so: unproved
```

The language already has the mechanism. The compiler does not yet read what the
programmer wrote as something it may assume.

## What that would buy, with performance in the background

Nothing, at run time. This is the result worth being clear about, because the
intuition runs the other way. Every bounds check in the corpus is *already*
eliminated — GCC proves them redundant and deletes the check and its error block
together, which [Performance](performance.md) measures against C that never had
one. Proving them a second time, earlier, removes no instruction that is still
there.

What it buys is the **list**. A compiler that classifies accesses can report the
ones nobody has proved, and that report is currently a fifth of the corpus,
concentrated almost entirely in the one program that parses hostile input. The
value is not a faster binary. It is knowing where to look.

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
