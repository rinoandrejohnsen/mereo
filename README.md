# mereo 0.1

A prose-like, function-free systems language for Linux. A mereo program
transpiles to freestanding C and links to a static binary with no C library, no
runtime, and no allocator — raw system calls and nothing else.

```
include "linux.mereo"

program goes
  message is "hello, world\n"

  terminal is already linux.file (descriptor is 1)

  terminal.write (buffer is message, count is message.size)

end
```

That builds to a 784-byte executable.

## What is settled in 0.1

- **Lifetimes are derived, never registered.** A resource is released when its
  scope ends, in reverse order, on every path out — including a failed check and
  a Ctrl-C. There are no drop flags anywhere, and the release order is checked
  against real C++ binaries with real destructors (48 paired scenarios).
- **One jump, three words.** `repeat NAME` goes to a scope's top, `leave NAME`
  past its bottom, and both release exactly what that scope holds. A loop is a
  scope whose body ends by repeating; an `if` is `GUARD goes`, a scope with an
  entry condition; a branch road is a scope too.
- **A hot path and a cold path, verified.** `LABEL likely goes` keeps the common
  case inline and moves the rest past the exit — and the build disassembles the
  result and fails if the layout was lost.
- **Errors handle themselves.** `ensure` states what must be true; the cleanup,
  the exit status and the stderr record are all derived from it.
- **Reuse is splicing.** A template is copied into each use with its locals
  renamed. No call, no return, no stack frame.

## Layout

```
  mereoc.py        the transpiler: .mereo -> freestanding C
  mereocheck.py    verifies the hot/cold layout on the real assembly
  mereodis.py      binary -> C, for reading what actually shipped
  mereoraii.py     the Valgrind analog: fault injection at every syscall
  mereo.lds        the linker script (see its comment for where size goes)

  core.mereo       everything that needs no system call: bytes, text, JSON
  linux.mereo      everything that does: the syscall ABI and its resources
  examples/        small programs, including coreutils clones (wc, head, basename…)
  programs/tls     a TLS 1.3 client: X25519, AES-128-GCM, kTLS handover
  tests/           blackbox.sh, progs/, and scopes/ (the RAII parity suite)
  docs/            the guide; `python3 docs/build.py` renders it two ways
  wiki/            ...the second: pages for this repo's GitHub wiki (generated)
  notes/           design notes and history
  tools/           the highlighter, the verification helpers, publish_wiki.sh
  attic/           prototypes, experiments and the gem5 model -- see attic/README.md
```

## Building and testing

```sh
./build.sh                         # every program, layout-gated
./build.sh examples/branch.mereo   # just one
./test.sh                          # everything: parity, black box, build gate
```

`./test.sh` is the gate that matters. It runs four suites and a build gate:

| suite | what it proves |
| --- | --- |
| `tests/scopes/run.sh` | release order matches a C++ twin, scenario by scenario |
| `tests/blackbox.sh` | stdin/args → stdout/exit on the shipped binaries, plus fault injection |
| `tests/versus/run.sh` | what an abstraction costs, against hand-written C doing the same job |
| `tests/namespaces/run.sh` | that a namespace means what C++ means by one, on nine questions |
| `./build.sh` | every program compiles, and every crossroad's layout holds on the assembly |

## The guide

`docs/*.md` is the source, and it is written as one encyclopedia article about
the language — a lead with an infobox, then design, syntax and semantics, the
standard library, implementation, performance, limitations and a comparison with
other languages. One file per section, in reading order.

One command renders both outputs and refuses to write either if a check fails —
a retired phrasing, a broken link, or an example that no longer transpiles:

```sh
python3 docs/build.py     # -> docs/mereo.html  and  wiki/
```

`wiki/` is shaped for GitHub's wiki, which is a **separate repository** and so
is invisible to `./test.sh` and to `build.py`'s own checks. One command
rebuilds, syncs and publishes it, then reads it back to confirm what landed:

```sh
./tools/publish_wiki.sh             # or --dry-run to see what would change
```

Edit the guide in `docs/`, never in `wiki/` and never in GitHub's web editor —
both are output, and the next publish overwrites them.

## Requirements

GCC, Python 3, binutils, and `strace` for the RAII suites. x86-64 Linux.

`tests/versus` records instruction counts, which are a property of the compiler
as much as of mereo. The baseline names the GCC it was taken with; on a
different one the suite reports the comparison and does not call it a
regression. `./tests/versus/run.sh --bless` re-records it.

## What is not here, by design

No heap, no recursion, no functions, no dynamic linking. Programs that need
unbounded data (`sort`, `ls`, `du`) are out of scope rather than unimplemented.
The one thing that is *missing* rather than excluded is an intrinsic surface:
mereo gets everything an optimizer can find on its own — its branchless idiom
auto-vectorizes and matches C exactly — but hand-written SIMD has no spelling.

See `todo.md` for what is open.

## License

Boost Software License 1.0 — see `LICENSE`. Permissive, and it asks nothing of a
binary: the notice has to travel with source and derivative works, but not with
machine code generated from them, which suits a language whose whole output is
generated machine code.

## Provenance

The line below is literal, not a flourish, and it is here rather than buried
because it changes how the rest of this file should be read.

**The language is Rino Andre Johnsen's design** — its semantics, its
constraints, what to build and what to refuse. **The code was written by Claude
Opus 5**: the transpiler, both libraries, the programs, the test suites, the
tooling and the guide.

Which is the reason the verification above is not decoration. Nothing here asks
you to trust whoever wrote the code. Every claim the project makes is checked
against something outside it — syscall numbers against the kernel's headers,
release order against real C++ binaries under `strace`, hot/cold layout against
the shipped disassembly, generated code against hand-written freestanding C —
and `./test.sh` runs the lot.

---

*Designed by Rino Andre Johnsen. Written by Claude Opus 5.*
