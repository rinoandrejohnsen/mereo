# What the compiler decides

A mereo program is compiled freestanding, as one translation unit, with no
functions in it. Those three facts together decide an unusual amount before the
program runs — and, just as usefully, they mark exactly where deciding stops.

This page is about that boundary: what is settled when the program is read, what
is handed to the C compiler, and what is genuinely a run-time question. It ends
with two comparisons, because the obvious neighbours — Zig's `comptime` and
C++'s `concept` — are each half an answer to something asked here.

## Why so much is decidable

**Freestanding.** There is no libc and no allocator, so every byte a program
uses is declared in it. A buffer's size is in the source; nothing arrives from a
heap whose shape the compiler cannot see.

**Whole-program.** One translation unit, no separate compilation, no dynamic
linking. There is no call across a boundary the compiler cannot look through,
so "what does this program do" has an answer rather than a set of possibilities.

**No functions.** Reuse is splicing: a template is copied into each use with its
locals renamed, and recursion is refused. So the call graph is finite and
acyclic, and any property that propagates along it reaches a fixpoint.

The last is the one that does the most work, and it is the one most easily
mistaken for a limitation.

## What is settled when the program is read

| | what is decided |
| --- | --- |
| Release points | which resources are live at every step, and therefore which cleanup each exit runs |
| Partial construction | the label a failure jumps to *is* the record of how far acquisition got |
| Layout | every field's offset, every view's fit against its backing |
| Access width | 1, 2, 4 or 8 — a run-time width would be a run-time load size, which the machine has no instruction for |
| Constant bounds | `[block + 100 : 1]` against `block is 8 bytes` is refused |
| Port requirements | what a template's body needs of each port, derived from the body |
| Lifetimes of names | a resource's name ends with the scope that released it |
| Sizes | `X.size` is the number the array is declared with |

None of this runs any code. It is all reading — which is why none of it needs a
compile-time evaluator.

The first two are the substantial ones. A program holding several descriptors
contains no boolean recording which it still holds; the release order is a
ladder of labels, checked against equivalent C++ binaries with real destructors
across 53 paired scenarios.

## What is handed to the C compiler

Constant arithmetic is not folded here:

```
  n is 2 + 3 * 4
```

emits `n = (2 + (3 * 4));`, and GCC folds it. That is deliberate. The compiler's
job is to know the *shape* of memory and lifetimes; an optimiser already folds
arithmetic, eliminates redundant checks and merges identical blocks, and doing
any of it twice would mean two answers to keep in agreement.

The same division decides bounds checking. Where a loop is bounded by the same
length its check tests, GCC proves the check redundant and deletes it — the
check and its whole error block are absent from the binary. [Performance](performance.md)
measures that against C.

## Where deciding stops

An index that came from a system call is not decidable, and no amount of
whole-program analysis reaches it:

```
  source.read (buffer is block, capacity is 4096, count is count)
```

`count` is whatever the kernel returned. A check on an access derived from it is
a real run-time check, and mereo's answer is not to prove it away but to make it
free: bound the loop by the same value the check tests, and the optimiser
removes it. Where the bound genuinely differs, one `ensure` before the loop does
the same for every iteration after it.

So the compile-time claim here is deliberately narrow. It covers the decidable
half completely and says nothing about the other.

## Compared with Zig's `comptime`

`comptime` is compile-time **evaluation**: running code while compiling, with
types as values, which is how Zig expresses generics. mereo has nothing like it
and would gain little, because the two languages spend their compile time on
different problems.

It is worth separating, because `comptime` is often credited with Zig's bounds
safety and does not provide it. Zig inserts a **run-time** bounds check in Debug
and ReleaseSafe, LLVM elides the ones it can prove, and ReleaseFast removes them
outright. That is the same mechanism described above — an optimiser deleting
what it can prove — reached by a different route.

| | Zig | mereo |
| --- | --- | --- |
| Compile-time evaluation | yes, general | none |
| Generics | `comptime` type parameters | none; one definition per width, by hand |
| Bounds checks | run-time, elided by LLVM, off in ReleaseFast | run-time, elided by GCC; the constant case refused outright |
| Resource cleanup | `defer` / `errdefer`, written per site | derived from scope; nothing written |
| Compile-time execution of user code | yes | no |

The row that matters is the last but one. Zig's `defer` is a statement the
programmer places; forgetting one is a leak the compiler does not see. mereo
derives the release point instead, which is a compile-time result Zig does not
attempt — and pays for it with restrictions Zig does not accept, listed in
[Limitations](limitations.md).

## Compared with C++'s `concept`

A `concept` constrains a template parameter, and does two things: it selects
between overloads, and it moves the diagnostic from inside the instantiation to
the call. The second is what mereo needed.

mereo's ports are **already structurally typed** — what a body does with a port
is the whole requirement, so a template splices over any instance carrying the
method it calls, with no shared base and nothing declared. That is what a
`concept` buys over an interface. What was missing was the check.

It is derived rather than declared, and this is the real difference. A C++
template body is type-generic, so the compiler cannot summarise what it needs of
`T` — the requirement has to be written down. A mereo body is not generic that
way; it says exactly what it does with each port:

| the body writes | the port needs |
| --- | --- |
| `thing.read (...)` | an instance — it is a receiver |
| `[area + offset : 1]` | an address: a buffer, a literal, or a scalar holding one |
| `n + 1`, `n > 0` | a value |
| `value is ...` | a scalar slot to land in |

So the requirement is read off the body and checked where the connection is
made. A template that only passes a port on inherits the requirement of the one
it passes it to, which is why the derivation runs to a fixpoint — and why it
terminates.

The other half of `concept` has nothing to attach to: there is no overloading,
so there is no candidate set to select from.

**Ada** is the useful contrast to both. An Ada generic states its formal
parameters and the operations it needs, and an instantiation must supply them:
declared, checked, and documented at the declaration. mereo gets the checking
without the declaration, and gives up what a declaration is good at — a reader
seeing the requirement without reading the body, and a requirement the body does
not happen to exercise yet.

## The comparison is a suite, not a claim

`tests/checking` writes one mistake three times — once in mereo, once in C++
with the requirement written as a `concept`, once in Zig — and compiles each.
Two things are recorded, because *refused* alone is not the interesting half:

| case | mereo | C++ (concepts) | Zig |
| --- | --- | --- | --- |
| a constant index past a known array | refused, at the mistake | accepted | refused, at the mistake |
| a port used as a receiver, given a number | refused, at the mistake | refused, at the mistake | refused, **inside the template** |
| an out-port given a literal | refused, at the mistake | refused, at the mistake | refused, at the mistake |
| a resource named after its scope | refused, at the mistake | refused, at the mistake | refused, at the mistake |

Read it for where each language is *not* alone. C++ and mereo agree on three of
four, and the row C++ loses is the one where an unchecked subscript is the
documented behaviour. Zig decides the constant index and mereo does too. The
row that separates them is the second, and only in *where* the error lands:
`anytype` is unconstrained, so the mistake surfaces inside the instantiation
with a reference trace back to the call — which is what C++ did before concepts,
and what mereo did before a port's requirement was derived.

The last row is the one where mereo is doing real work for a reason the others
do not have: C++ and Zig scope a name to its block, so the mistake is a name
error. mereo does not — a scalar or a buffer outlives its block — so it is
caught by liveness instead, from the set of resources still held.

Disabling any of the three checks moves mereo's column, which is how the suite
is kept honest.

## What none of this is

It is not a proof of memory safety. A run-time index is unchecked unless the
program checks it; `[v.data + i]` is exactly as unchecked as C, and is meant to
be. What the compiler decides is the part that can be decided from the text: the
lifetimes, the layout, the widths, the constant accesses and the connections.

The value is not that the list is long. It is that each item is checked rather
than promised, and that the checks are run against the shipped artifact —
[Implementation](implementation.md) describes the gates and the rule that every
one of them ships with a deliberately planted violation.
