| | |
| --- | --- |
| **Paradigm** | Imperative, structured, function-free |
| **Designed by** | Rino Andre Johnsen |
| **Made by** | Claude Opus 5 (Anthropic) |
| **Current version** | 0.2 |
| **Typing discipline** | Values untyped; memory accesses typed |
| **Memory management** | Static and stack only; scope-derived release |
| **Platform** | Linux on x86-64 |
| **Implementation language** | Python (`mereoc`, transpiling to C) |
| **Influenced by** | C, C++, Lua, Ada |
| **License** | Boost Software License 1.0 |
| **Filename extension** | `.mereo` |

A systems language for Linux that compiles to **freestanding** binaries: direct
syscalls, no C library, no runtime, no allocator, no collector. `mereoc` emits
C, which an ordinary C compiler then builds. Hello world is a 784-byte static
executable.

Three decisions distinguish it.

**No functions.** Reuse splices a template into each use site. No call, no
return, no stack frame — and so no recursion and no indirect dispatch.

**Lifetimes are derived, not registered.** A resource is released when its
scope ends, on every path out including a failed check or an interrupt.
Acquisition is statically known, so cleanup needs no drop flags and no
unwinder.

**Failure is not a value.** A program states what must hold with `ensure`.
Cleanup, exit status and the diagnostic on stderr all follow from it, so a
non-zero exit has one meaning.

The two libraries — computation, and syscalls — total about 1,900 lines. Every
claim is checked against an external oracle rather than against the compiler:
syscall numbers against the kernel's headers, release order against equivalent
C++ under `strace`, generated code against hand-written freestanding C.

## In this guide

**[Design](Design)** — the one commitment everything follows from, and what
was left out.

The language, in reading order:

- **[Syntax and semantics](Syntax)** — a complete program, and the surface.
- **[Control flow](Control-flow)** — scopes, and the two jumps.
- **[Memory and views](Memory)** — backings, typed accesses, layouts, spans.
- **[Templates](Templates)** — splicing, and what it forbids.
- **[Resources and lifetimes](Resources)** — the release tower.
- **[Error handling](Errors)** — `ensure`, and where a failure goes.
- **[Being a good Linux citizen](Citizen)** — how those three are one path.

**[Standard library](Library)** — two files, and why the split is there.

Built and measured:

- **[Implementation](Implementation)** — the transpiler, the tools, the
  oracles.
- **[What the compiler decides](Compile-time)** — what freestanding,
  whole-program and no-functions settle before the program runs, against Zig's
  `comptime` and C++'s `concept`.
- **[Performance](Performance)** — measured against hand-written C.
- **[Safety](Safety)** — what is removed, what is refused, and the analysis
  that was built, measured and taken out again.
- **[Limitations](Limitations)** — deliberate, and unfinished.

Reference:

- **[Comparison with other languages](Comparison)** — C, C++, Rust, Lua.
- **[Examples](Examples)** — complete programs, all compiled by the docs build.
- **[Syntax summary](Syntax-summary)** — every form on one page.
