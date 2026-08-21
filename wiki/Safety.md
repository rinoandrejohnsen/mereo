## The barrier

> **The barrier is performance parity with a hand-written, optimised,
> Linux-correct C program. No safety feature is accepted that costs more than
> that.**

Competing on safety is not a design goal. The barrier redirects safety rather
than reducing it: compile-time work is free at run time, so everything
settleable before the program runs is worth taking, and everything paid for
while it runs is not.

| aimed for | not aimed for |
| --- | --- |
| whatever static analysis decides, since it is free | a proof of memory safety |
| refusing what is provably wrong at compile time | refusing what merely cannot be proved |
| deducing what an expert C programmer deduces | discharging every obligation, as SPARK does |
| a run-time check where an expert would keep one | a check an expert's C would not carry |
| knowing which accesses nobody has proved | a guarantee that the rest are correct |

**The standard is a person, not a theorem.** What a super-skilled C programmer
deduces from the program to be safe, and therefore leaves unchecked, mereo aims
to deduce too. That target is bounded and reachable, and it is the one the
barrier implies: an expert's binary carries no checks because the expert did the
deducing. Where the deduction fails the expert writes a check — so mereo may
write one too, at the same cost, and still be at parity.

Everything below is a measurement, not a claim to be winning.

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
mechanism. The price is stack space: a template spliced ten times occupies ten
slots.

**No threads.** Data races are absent as they are from a single-threaded C
program — vacuously, and only until threads arrive.

To those add the one thing derived rather than removed: cleanup is read off the
scope, so a resource cannot be released twice or forgotten. `tests/scopes`
checks that against C++ destructors across 53 paired scenarios.

## What is refused

`tests/checking` writes each mistake three times — mereo, C++ with the
requirement as a `concept`, Zig — and compiles all three.

| the mistake | mereo | C++ | Zig |
| --- | --- | --- | --- |
| a constant index past a known array | refused | accepted | refused |
| a view over a backing too small for it | refused | accepted | accepted |
| a two-step acquisition with no ownership boundary | refused | accepted (leaks) | accepted (leaks) |
| a fallible call whose failure is ignored | refused | warned | refused |
| a resource named after the scope that released it | refused | refused | refused |
| a write to a read-only buffer | refused | refused | refused |
| a syscall handed more room than the buffer has | refused | accepted | accepted |
| a nested loop resetting the enclosing loop's counter | refused | warned | warned |
| a span claiming more bytes than its backing has | refused | accepted | accepted |

The pattern: mereo decides what is decidable from the text and declines to guess
at the rest. A view's fit is two declared sizes compared: `backing 'small' is
16 bytes, too small to view 4096-byte 'wide' at offset 0`. None of it needs a
prover.

The loop-counter row is one mereo owes rather than wins. Every scalar is
visible everywhere — that is what lets a scope see its surroundings without
plumbing anything through ports — so reaching for a fresh counter inside a
nested loop silently takes the enclosing one's. C and C++ give each block its
own and say so at `-Wshadow`; mereo cannot, because the name really is the same
name, so it checks instead. Sharing a name between nested loops is allowed and
common — an accumulator the inner advances and both stop on. **Resetting** it is
what gets refused.

The syscall row is the one nothing downstream can catch. `read (buffer is small,
capacity is 4096)` with `small is 16 bytes` asks the kernel to write 4096 bytes
into a 16-byte frame; the kernel has never seen the buffer and cannot find where
it ends, and in the emitted C a syscall is inline assembly whose `"memory"`
clobber says *something changed*, not *this buffer, that many bytes* — so GCC is
silent at every warning level including `-fanalyzer`. Both numbers sit one line
apart in the source.

It is declared as an ordinary contract clause on the primitive, `ensure capacity
<= buffer.size`, and which side it constrains is **derived**: a clause on the
OUT port is a promise about the result and is checked at run time, while one on
an IN port is a requirement on the call and is decided when the program is read.
It covers `read`, `write`, `getrandom`, `getdents64` and `readlinkat`.

The row below it is the same keyword one level further out. A resource states an
invariant over its own fields, and it is checked where an instance is
**adopted**
rather than where the resource is declared, because that is where both numbers
exist:

```ada
span is
  data is 8 bytes
  length is 8 bytes
  ensure length <= data.size
```

A span claiming more bytes than its backing has is a lie every later
`[v.data + i]` inherits, and `find`, `last` and `search` all walk to `length` by
definition. Both checks are free: the corpus is byte-identical with every clause
added — 89 binaries, not one instruction.

## What is not checked

| | |
| --- | --- |
| run-time bounds | `[buffer + i : 1]` is as unchecked as C. `.at` checks, and costs 10% |
| integer overflow | wraps rather than being undefined; nothing detects it |
| division by zero | accepted, even for a literal zero divisor |
| uninitialised reads | a layout is zero-filled; `raw is 8 bytes` is not |

Each gap is open because its run-time fix spends what the barrier protects. The
**compile-time** half of each is admissible, and unbuilt rather than declined —
the last is decidable from two literals. Overflow is the one already taken as
far as it goes for free: the build passes `-fwrapv`, so `n is n + 1` at
`LONG_MAX` wraps instead of being undefined. That detects nothing, but it costs
nothing either — 377264 bytes against 379168 across 89 binaries, and on the
`tests/versus` cases it moves mereo *closer* to the C it is measured against,
matching it exactly on `layout_view` and closing six instructions of the gap on
`span_scan`.

## How far the analysis reaches

`tools/mereoprove.py` classifies every access in the post-splice IR. It is a
measurement, not part of the compiler.

| | | |
| --- | ---: | --- |
| **proved** | **3007** | **98.4%** |
| bound-unresolved | 25 | 0.8% |
| an unresolved base | 24 | 0.8% |

Over 95 programs and 3056 accesses. The one out-of-range access is
`access_past_end.mereo`, which mereoc already refuses. Six violations planted
outside the corpus — a loop wider than its backing, an affine index that
overflows, a syscall capacity larger than its buffer, an off-by-one in a
branchless guard, and two with live loops and initialised buffers — are each
reported.

Nothing is reported wrong unless it is **proven** wrong. A non-relational
interval domain loses the correlation between two variables and will call a safe
access out of range; anything merely unproved is reported as unproved.

The compiler sorts the remainder by cause, which is what makes the list a work
item rather than a number:

| cause | | |
| --- | ---: | --- |
| the backing did not resolve | 22 | the base is a scalar holding an address |
| guarded, but the guard could not be tied | 14 | a limit of the analysis, not a hole |
| a bound is in scope, but is not a number | 13 | the bound is a port, so symbolic |
| **comes from input, nothing bounds it** | **0** | |

**That last row is the one that matters, and it is empty.** It was not. It held
nine distinct sites — the same seven in the TLS stack, counted once per program
that includes it, plus two in the exam — and every one of them said *this wants
a run-time guard* on every build for weeks.

Reading them found `crypto.server_hello` walking off the end of a record. It
took `(rec, pub)` and no length, so the `ensure` that bounds the record to 512
bytes never entered it, while every offset inside was built from bytes the peer
sent. A server declaring a large extensions block walked the index tens of
kilobytes past the buffer and handed back 32 bytes from wherever it landed as
the peer's public key, before anything was authenticated. The flight loop had
two unsigned underflows besides. Seven sites are now guarded; the other two were
already safe, and what was wrong there was the message, which claimed nothing
bounded an index that had `leave narrow when j >= n` written above it.

The lesson is not about the analysis, which was right, and printed the line, and
was ignored. `todo.md` carries a proposal to make that one message fail the
build.

## What proving the rest would buy

Nothing at run time, and this is worth being blunt about. Every bounds check in
the corpus is already eliminated — GCC proves it redundant and removes the check
and its error block together, matching C that never had one, which
[Performance](Performance) measures. `.at` is used in five test programs and
nowhere else: the examples, the TLS stack and the exam all index raw, so there
are no checks left to remove.

What it buys is the **list**: 49 accesses out of 3056. Not a faster binary — a
list short enough to read, which is the only reason the nine above were ever
found.

The number to read is 49, not 98.4%. The percentage counts accesses after
splicing, so a template used ten times contributes ten; and the corpus and the
tool share an author.

## What is beyond GCC

One thing, and it is a category rather than a trick: **a fact that is true of
the program but is nowhere in the program's text.** GCC works from the
translation unit. Anything derivable from it, GCC derives — including every
bound this analysis proves, since those are built from buffer sizes, branch
conditions and syscall contracts, all of which reach the emitted C as literals,
branches and assumptions.

So the analysis makes no binary faster, and nothing here should be read as
claiming otherwise. Its product is the **list** — a refusal where a mistake is
provable, a line where it is not. The one fact worth stating is the kernel's
half of the syscall contract, which no compiler can derive because it is not
code; [Performance](Performance) measures what that is worth, along with the
separate matter of giving GCC a better SHAPE for something it already knows.

Everything else mereo reports and GCC does not is a missed diagnostic rather
than an impossibility. GCC has value-range propagation and object sizes; it
stays silent on a loop to 100 over a 64-byte backing even at `-Wall -Wextra
-Warray-bounds=2 -Wstringop-overflow=4 -fanalyzer`. The real asymmetry is that
an optimiser has two outcomes — quietly succeed or quietly fail — and no way to
report *I could not prove this one*. A compiler can refuse.

## Where each language stands

| | C | C++ | Rust | SPARK | mereo |
| --- | --- | --- | --- | --- | --- |
| Use after free | — | RAII, partial | prevented | prevented | **absent** (no heap) |
| Double free | — | RAII | prevented | prevented | **absent** (no heap) |
| Leak | — | RAII | permitted | prevented | **prevented** (derived) |
| Dangling stack pointer | — | — | prevented | prevented | **absent** (no frames) |
| Bounds, constant | — | — | prevented | proved | **refused** |
| Bounds, run-time | — | — | checked | **proved** | **unchecked** |
| Uninitialised read | — | partial | prevented | **proved** | **unchecked** |
| Integer overflow | UB | UB | checked/wrapping | **proved** | **UB** |
| Data race | — | — | prevented | partial | **absent** (no threads) |
| Type confusion via cast | — | — | prevented | prevented | **fit refused** |
| Unhandled failure | — | warned | `Result` | prevented | **refused** |

Read the mereo column as two blocks. *Absent* is free and permanent — it cost
expressiveness, not analysis. *Unchecked* is work not done, and no amount of the
first substitutes for it.

**SPARK** is ahead and is the nearest relative. GNATprove discharges every
run-time check as a proof obligation and reports each it cannot; nothing stays
unproved silently. mereo's `ensure` resembles a SPARK contract and is not one —
it is a run-time comparison the optimiser may fold, not an obligation discharged
before running. SPARK's ranges are also *declared*, which hands its prover the
fact; mereo infers everything from loop shape and syscall contracts.

**Stroustrup's argument**, that C++ can reach safety through profiles and static
analysis rather than a borrow checker, gets a data point here that is not the
one it looks like. Analysis is easy in mereo because the language was restricted
first — whole-program, no heap, no recursion, no separate compilation. The
analysis is downstream of the restriction, and mereo's restrictions are far
heavier than the ones the argument resists. Rust asks for aliasing with
mutation; mereo asks for the heap, functions, recursion, threads, generics and
data structures. Per theorem proved, the borrow checker is the better bargain.

This is also why a compile-time gate is rare rather than novel. SPARK, Astrée
and Frama-C all do it, and GCC and LLVM run a version of it on mereo's own
output. What blocks it elsewhere is separate compilation, the false-positive
rate in a language with aliasing and dynamic dispatch, the annotation burden,
and the economics: checking at run time costs nothing once the optimiser deletes
the provable ones. mereo evades the first three because it paid for them
already, for other reasons.

## What none of this is

It is not a claim to be safer than Rust or SPARK. On the faults each proves,
both are ahead, and SPARK is ahead of everything here.

The claim is narrower: a language can reach much of memory safety by
subtraction rather than proof, and subtraction is cheap and impossible to get
wrong because there is no analysis to be wrong. It cannot reach the rest. For
the rest the bound has to be written down or deduced — and the measure of the
deducing is a skilled C programmer, not a prover.
