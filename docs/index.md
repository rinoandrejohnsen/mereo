# mereo

| | |
| --- | --- |
| **Paradigm** | Imperative, structured, function-free |
| **Designed by** | Rino Andre Johnsen |
| **Made by** | Claude Opus 5 (Anthropic) |
| **Current version** | 0.1 |
| **Typing discipline** | Values untyped; memory accesses typed |
| **Memory management** | Static and stack only; scope-derived release |
| **Platform** | Linux on x86-64 |
| **Implementation language** | Python (`mereoc`, transpiling to C) |
| **Influenced by** | C, C++, Lua, Ada |
| **License** | Boost Software License 1.0 |
| **Filename extension** | `.mereo` |

**mereo** is a systems programming language for Linux that compiles to
**freestanding** binaries — programs that make system calls directly and link
against no C library, no runtime, no allocator and no garbage collector. Its
implementation, `mereoc`, is a transpiler that emits C, which is then compiled
by an ordinary C compiler. A complete "hello world" builds to a 784-byte static
executable.

The language is distinguished by three decisions. It has **no functions**: reuse
is by *splicing* a template into each use site, so there is no call, no return
and no stack frame, and consequently no recursion or indirect dispatch.
Lifetimes are **derived rather than registered**: a resource is released when
its scope ends, on every path out including a failed check or an interrupt, and
because acquisition is statically known the cleanup requires no drop flags and
no unwinder. Failure is **not a value**: a program states what must be true with
`ensure`, and the cleanup, the exit status and the diagnostic written to
standard error are all derived from it, so a non-zero exit status has exactly
one meaning.

mereo is at version 0.1, designed by Rino Andre Johnsen and written by Claude
Opus. Its two
libraries — one for
computation, one for system calls — total roughly 1,900 lines, and the reference
implementation is checked against external oracles rather than against itself:
system call numbers against the kernel's own headers, resource release order
against equivalent C++ binaries under `strace`, and the generated machine code
against hand-written freestanding C.

## In this guide

**[Design](design.md)** — the one commitment everything follows from, where the
name comes from, and what was deliberately left out.

The language itself, in reading order:

- **[Syntax and semantics](syntax.md)** — a complete program, and the shape of
  the surface.
- **[Control flow](control-flow.md)** — scopes, and the two jumps everything
  else is made of.
- **[Memory and views](memory.md)** — backings, typed accesses, layouts, spans.
- **[Templates](templates.md)** — reuse by splicing, and what that forbids.
- **[Resources and lifetimes](resources.md)** — the release tower.
- **[Error handling](errors.md)** — `ensure`, and where a failure goes.
- **[Being a good Linux citizen](citizen.md)** — how those three are one path.

**[Standard library](library.md)** — the two files, and why the split is where
it is.

How it is built and what it costs:

- **[Implementation](implementation.md)** — the transpiler, the tools, and the
  oracles every claim is checked against.
- **[What the compiler decides](compile-time.md)** — what freestanding,
  whole-program and no-functions settle before the program runs, and how that
  compares with Zig's `comptime` and C++'s `concept`.
- **[Safety](safety.md)** — what is removed, what is refused, what is still
  unchecked, and how that compares with Rust, SPARK and the C++ profiles.
- **[Performance](performance.md)** — measured against hand-written C.
- **[Limitations](limitations.md)** — what is deliberate, and what is unfinished.

Reference:

- **[Comparison with other languages](comparison.md)** — C, C++, Rust, Lua.
- **[Examples](examples.md)** — complete programs, all of them compiled by the
  documentation build.
- **[Syntax summary](syntax-summary.md)** — every form on one page.
