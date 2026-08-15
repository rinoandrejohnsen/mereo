mereo has exactly two libraries, split on one question: does this need a system
call? What does not is in `core.mereo`; what does is in `linux.mereo`. A program
that only computes needs the first and nothing else, and the first needs nothing
at all. Nothing in either is paid for unless used — an unused definition emits
no code.

## `core.mereo`

About 700 lines, in four parts.

**Raw instructions.** `population_count`, `memory_fence` and `random_word`: one
CPU instruction each, with their operand constraints written out.

**The byte layer**, gathered on a stateless `text` group. `find` and `last`
locate a byte; `search` locates a run; `compare` tests two regions; `measure` is
a bounded `strlen`; `copy` and `fill` are `memcpy` and `memset`; `upper` and
`lower` change ASCII case in place; `digit`, `space` and `alpha` are the three
`ctype` questions the corpus has asked; `format` and `number` convert decimal
both ways, and `hex`, `hexbytes` and `unhex` do the same for base 16.

Three of these — `find`, `compare` and `format` — are irreducible machine loops
kept as always-inline C helpers. `search` and `number` are composed from them in
mereo rather than in C, so the logic stays in the language.

**The two views**, `span` and `builder`, described under
[Memory and views](Memory). They exist because counting the corpus found 22
calls that scanned a region and 39 that appended into one, and because the
appending 39 checked nothing.

**A JSON reader** over bytes already in hand. Extraction is a flat scan: locate
the key, step over the colon, read the value. It handles top-level fields of an
object, does not descend into nested ones, and does not decode string escapes.

## `linux.mereo`

About 1,200 lines, wrapped in a `linux` namespace.

**The system-call ABI.** 43 declarations, each a raw `assembly "syscall"` with
the System V register assignment written out: number in `rax`, arguments in
`rdi`, `rsi`, `rdx`, `r10`, `r8`, `r9`, result in `rax`, with `rcx`, `r11` and
memory clobbered. There is no transpiler-injected wrapper. Every number is
checked against the kernel's `<asm/unistd_64.h>`.

**Resources**, built on those calls:

| Name | Owns | Notes |
| --- | --- | --- |
| `file` | a descriptor | read, write, status, redirect, watch |
| `directory` | a descriptor | opened `O_DIRECTORY`, read by `getdents64` |
| `mapping` | a region | `mmap` and `munmap` |
| `channel` | — | `pipe2`, whose two ends are adopted as ordinary files |
| `files` | nothing | the operations that *name* a file rather than hold one |
| `clock` | nothing | the time, and sleeping |
| `identity` | nothing | user and process identity, and the passwd lookup |
| `process` | nothing | signalling |

`files`, `clock` and `identity` hold nothing and are adopted with `already`.
They are resources rather than free templates because each of their operations
can fail, and a fallible primitive needs a release tower to fail into.

**Views** for the records those calls exchange: `sockaddr_in`, `file_status`
(`statx`) with `file_mode` over its mode bits, `timespec`, `poll_entry` and
`dirent`.

## What is absent, and why

The libraries are grown from measured demand rather than from surveying other
languages, and the omissions are recorded in the source with their reasons.
There is no `memmove`, because nothing has wanted one and a direction test is
not free. Ten of C's thirteen `ctype` questions are missing for the same reason.
`span` has no `find_first_of` and no ordering comparison, because no caller has
asked for a character set or for text to be ordered.
