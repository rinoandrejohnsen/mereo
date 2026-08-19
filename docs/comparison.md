# Comparison with other languages

## C

C is the closest relative, and the differences cluster in three places: there is
no standard library, there are no functions, and the type belongs to the access
rather than to the variable.

| | C | mereo |
| --- | --- | --- |
| Printing | `printf("Hello\n")` | `terminal.write (buffer is "Hello\n", count is 6)` |
| Reuse | a function, called | a template, spliced |
| Returning | `return x` | an out-port the caller names |
| Types | on the variable — `int x` | on the access — `[p + 4 : 2] as big` |
| Cleanup | written at each exit, or `goto` | derived from the scope |
| Errors | a return value and `errno`, checked by the caller | `ensure`, checked at the step |
| Comments | `//` and `/* */` | `--` only |
| Allocation | `malloc` | none |

The absence of a format string means no format-string bugs and no buffering to
flush. The absence of functions means no calling convention and no ABI, at the
cost of recursion and indirection. mereo's `ensure` at the primitive means a
call site never tests a result: a system call that failed has already ended the
program, with a record naming the step.

Generated mereo is C, so the two can be compared directly. On paired programs
doing the same work with the same checks, mereo's output matches hand-written
freestanding C to within a few instructions, and is byte-identical on the
simplest cases — see [Performance](performance.md).

## C++

mereo takes RAII from C++ and rejects almost everything else about how C++
implements it. A resource is released at the end of its scope, in reverse order,
on every path out. There the resemblance stops: C++ needs an unwinder and
exception tables, and mereo needs neither, because acquisition is restricted to
one step so progress is statically known.

| | C++ | mereo |
| --- | --- | --- |
| Cleanup mechanism | destructors plus an unwinder | a ladder of labels |
| Partial construction | tracked by the ABI | the label jumped to encodes it |
| Conditional ownership | drop flags where needed | not expressible |
| Errors | exceptions, or `expected` | `ensure` and the release tower |
| Scope guard | `gsl::finally` | the tower itself |
| Owning pointer annotation | `gsl::owner<T*>` | a resource, enforced |
| Preconditions | `Expects` / `Ensures` | `ensure`, which is both |
| Checked indexing | `.at()` versus `[]` | `span.at` versus `[v.data + i]` |

The C++ Core Guidelines Support Library is a useful mirror: most of it is
annotations retrofitted because the language cannot enforce the rule, and mereo
enforces the same rules structurally. Its view family maps directly —
`std::string_view` and `std::span` become mereo's `span` — while the roughly
three dozen range adaptors do not map at all, since they compose lazily through
iterators and take callables, and mereo has neither.

## Rust

Both derive cleanup from scope, and both refuse a garbage collector. Rust
permits conditional moves and therefore needs drop flags — a hidden boolean
recording whether a value still needs dropping — which mereo avoids by
forbidding the move. Rust's borrow checker has no counterpart here; mereo's
guarantee is narrower, resting on ownership never leaving the scope that made
it. Rust's `Result` and `?` have no counterpart either: a mereo program cannot
observe a failure without handling it, because a failed `ensure` has already
begun the cleanup.

## Lua and Ada

The influence is on surface rather than semantics. Comments are Lua's `--`.
Blocks close with `end` in the manner of both. The reserved words are ordinary
English chosen to be read aloud — `is`, `goes`, `already`, `ensure`
— which is closer to Ada's spirit than to C's.

The semantics are opposite to Lua's in nearly every respect: Lua is dynamically
typed, garbage-collected and interpreted, with tables as its one data structure;
mereo has no types on values, no allocator, no runtime and no data structures at
all.

## Where mereo does not compete

Anything wanting a heap, a thread pool, a package ecosystem, a second target
platform, or a parser generator. None of those exist, and the design decisions
that give the language its guarantees are the same ones that rule them out.
