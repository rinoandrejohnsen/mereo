mereo has exactly two libraries, split on one question: does this need a system
call? What does not is in `core.mereo`; what does is in `linux.mereo`. A program
that only computes needs the first and nothing else, and the first needs nothing
at all. Nothing in either is paid for unless used — an unused definition emits
no code.

## `core.mereo`

About 900 lines, in four parts.

**Raw instructions.** `population_count`, `memory_fence` and `random_word`: one
CPU instruction each, with their operand constraints written out.

**The byte layer**, gathered on a stateless `text` group. `find` and `last`
locate a byte; `search` locates a run; `equals` tests two regions; `measure` is
a bounded `strlen`; `copy` and `fill` are `memcpy` and `memset`; `upper` and
`lower` change ASCII case in place; `digit`, `space` and `alpha` are the three
`ctype` questions the corpus has asked; `format` and `number` convert decimal
both ways, and `hex`, `hexbytes` and `unhex` do the same for base 16.

Three of these — `find`, `equals` and `format` — are irreducible machine loops
kept as C helper macros. `search` and `number` are composed from them in
mereo rather than in C, so the logic stays in the language.

**The three views**, `span`, `builder` and `array`, described under
[Memory and views](Memory). The first two exist because counting the corpus
found 22 calls that scanned a region and 39 that appended into one, and because
the appending 39 checked nothing. `array` is the third axis: `span` counts
bytes, `array` counts RECORDS, which is a span plus a stride. Its `at` and
`add` hand back the ADDRESS of a record rather than the record, because a
method cannot hand back a view — the caller lays the layout over it with
`[where : record.size] as record`. Both are bounds-checked the way `span.at`
is.

**A JSON reader** over bytes already in hand. Extraction is a flat scan: locate
the key, step over the colon, read the value. It handles top-level fields of an
object, does not descend into nested ones, and does not decode string escapes.

## `linux.mereo`

About 1,400 lines, wrapped in a `linux` namespace.

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
| `socket` | a descriptor | `connect`, or `bind`/`listen`/`accept`; `read`, `fill`, `write`, `write_vectors`, `option` |
| `mapping` | a region | `mmap` and `munmap` |
| `channel` | — | `pipe2`, whose two ends are adopted as ordinary files |
| `files` | nothing | the operations that *name* a file rather than hold one |
| `clock` | nothing | the time, and sleeping |
| `identity` | nothing | user and process identity, and the passwd lookup |
| `process` | nothing | signalling |

`socket` is one resource for both halves: what makes it a server is that
`bind`/`listen`/`accept` get called, and a method never called emits no code.
`accept` hands back a descriptor rather than a resource, because a method
cannot make one — the caller writes `client is adopted linux.socket
(descriptor is peer)`, and the scope that adopted it closes it. It is also the
one name in either library that is both a primitive and a resource: as a step
`linux.socket (…)` is the system call, and as a construction
`x is linux.socket (…)` is the resource. The compiler keeps the two in separate
tables.

`write_vectors` is `writev`: several separate runs of bytes sent as one, each
described by a `linux.iovec` (a `base` and a `length`). It is what a response
whose length has to precede its body wants — the head and the body are built in
different buffers and neither is copied into the other. On the SQLite demo that
is worth 92 instructions a request, all of them a byte-at-a-time copy.

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
