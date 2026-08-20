# todo

## Share the error-record formatter, or keep splicing it?

**Status:** open, waiting on a decision. Everything below is measured.

### How this came up

`abc.mereo` — open a file, read it, write it, exit — built to 1664 bytes. Taking
it apart:

```
  ELF header + 2 program headers    176
  .text                            1060
  .rodata (one path + 3 messages)   128
  padding                            12
  section headers + names           288
```

Splitting `.text` by DWARF label (`readelf --debug-dump=info`, each
`DW_TAG_label`'s `DW_AT_low_pc`, differenced against the next):

| region | bytes |
| --- | ---: |
| `mereo_sigstub` | 32 |
| `_start` — the entire program | 223 |
| `release_input` + `exit` | 20 |
| `error_1_input` | 256 |
| `error_2_read_input` | 266 |
| `error_3_write_output` | 263 |

**74% of the code was the three error blocks.** A program with no arithmetic in
it carried 24 `idiv` instructions, because `_write_value` was `always_inline`
and written as five unrolled divisions, spliced once per `ensure` site.

### What was already fixed

Two things, both done:

1. `_write_value` is now a digit **loop** rather than five unrolled divisions.
   `abc` .text 1060 → 704, zero `idiv` left; corpus −20% (512408 → 409144 B),
   `https` alone −22 KB.
2. It was also **wrong**. Five digit slots silently truncated any value ≥ 100000
   (`1234567` printed as `34567`), so an `ensure` on a large value reported a
   number that was not the one it saw. The loop negates into an unsigned
   accumulator and is exact over the whole signed range, `LONG_MIN` included.

### What is still open

`_write_value` is still spliced into every error block. Making it a real
`static __attribute__((noinline, cold))` function is worth a **further −16%
across the corpus** (re-measured after the stage markers came out, which took
the corpus from 409144 to 375152 on its own):

| | spliced (now) | shared function |
| --- | ---: | ---: |
| `abc` | 1296 | 1120 |
| `basename` | 1328 | 1200 |
| `jsontest` | 3696 | 3088 |
| `https` | 68696 | 55096 |
| **corpus** | **375152** | **313264** |

There is no speed argument against it: every call site is inside an error block
that runs at most once, immediately before exit.

**The cost is the reason this is not just done.** It would put the first `call`
instruction into a mereo binary — there are currently **zero** across all 73 —
and *"Reuse is splicing, not calling. … One flat program, no call, no return, no
stack frame"* is one of the five commitments on the front page of `docs/`.

Arguments each way, honestly:

- **For sharing.** The commitment is about how the *language* reuses work:
  a template is spliced, and that stays true. `_write_value` is emitter
  plumbing, not something anyone writes. The binary already carries
  `mereo_sigstub` as a separate symbol — the kernel enters it — so "one flat
  function" is already not literally true of the image.
- **Against.** "No call" is checkable today, and a property you can check is
  worth more than one you have to qualify. Losing it costs a sentence of
  explanation forever after, on every reading of that page.

If it goes ahead, `docs/index.md` needs its wording made precise in the same
change — the commitment should say what it means (splicing, not calling, for
*reuse*) rather than being quietly falsified.

### How to redo the measurement

```sh
sed 's/static inline __attribute__((always_inline)) void _write_value/\
static __attribute__((noinline,cold)) void _write_value/' build/PROG.c > /tmp/x.c
gcc -O2 $CFLAGS $LDFLAGS -s -o /tmp/x /tmp/x.c     # flags per build.sh
```

and to re-split a binary's `.text` by region, build it with `-g` through
`mereo.lds` and difference the `DW_TAG_label` low_pcs.

---

## Strip section headers from the shipped binary?

**Status:** open, and leaning no. Measured.

`objcopy --strip-section-headers` on the shipped build saves **287 bytes per
binary — 22157 B over 77**. On the small programs that is a real fraction:
`abc` 1296 → 1008, a further −22%. The stripped binaries run:

```
$ objcopy --strip-section-headers build/abc /tmp/abc && /tmp/abc
Lorem ipsum ...
```

**What it costs, demonstrated on that same file:** `objdump -d` prints the
format line and no instructions, and `size -A` prints a header and no rows. The
binary becomes something you cannot take apart.

That is the whole argument against. This project's claim is that what you write
is what the machine does, and the way anyone checks that claim is by
disassembling the thing that ships. `mereodis` reads the `.dbg` build so it
would still work, but "you can read the shipped binary" is worth more than 287
bytes — the same reasoning that keeps `.dbg` on the same layout as the release.

Reasons it might still be worth doing: a program being SHIPPED rather than
studied, where the `.dbg` artifact travels alongside it. If so it belongs as an
opt-in in `build.sh` (`STRIP_SECTIONS=1`), not as the default.

---

## Two road-grammar gaps

**Status:** open, both small, both confirmed still present today.

A road body has its own statement parser (`mereoc.py`, the `likely goes` and
`when ... goes` blocks). It knows method calls, free-standing template calls,
`NAME is EXPR`, `NAME is adopted CLASS (...)`, `NAME goes`, `scope`, `leave` and
`repeat`. It does not know two things the spine knows.

**1. A direct construction.** `NAME is CLASS (...)` in a road is not refused —
it is misparsed as an assignment, so the diagnostic talks about scalars:

```
  pick likely goes
    source is linux.file (path is "lorem_ipsum.txt", flags is 0, mode is 0)
    ^  mereoc: error: 'source' is not a scalar slot (declare it with
       `NAME is NUMBER` before assigning)
  end
```

That misdirection is most of why this is worth fixing: the diagnostic names a
rule the line was never trying to use. It belongs above the assignment rule,
mirroring `NAME is adopted CLASS (...)`, which is already there.

**2. `ensure`.** A road body has no rule for it at all, so it gets the
grammar-summary refusal:

```
    ensure n >= 0
    ^  mereoc: error: a `likely goes` body is method calls, `NAME is EXPR`
       assignments, `NAME is adopted CLASS (...)` resources, or
       `NAME goes`/`scope` blocks
    end
```

**The planner handles both already** — this is parsing, not lowering. Roads have
gone through the spine's own `plan_one` since templates were allowed in them, so
a construct or guard step arriving from a road is planned like any other. Proof
for each, by routing it through a template (a splice puts the step into the road
after parsing, so it never meets the road grammar):

- construction — `tests/progs/branch_res.mereo`, whose `peek` opens a file in
  both roads; it is in the black-box suite and under `mereoraii`.
- `ensure` — a template whose body is `ensure value >= 0`, spliced into a road,
  transpiles and emits the guard and its error block in the right places.

So the fix is two rules in each of the two road parsers, and the workaround
meanwhile is the same for both: put it in a template and splice it.

## `N bytes` means two different things, silently

**Status:** open. A real miscompile, worked around in
`tests/progs/method_syscall` by picking a wider field.

In a program body, `slot is 8 bytes` is storage — `char slot[8]`. As a resource
STATE field, the same eight words are a register word, because a state field is
a run of bytes only when it is wider than a register:

```
watcher is
  slot is 8 bytes            -- a register word, holding 0
  arm goes
    [slot + 0 : 4] is 1      -- ...so this stores through a null pointer
  end
end
```

That is not a wrong rule — `descriptor is 4 bytes as signed` is the library's
idiom everywhere, and a register field must be a register. The problem is that
the two meanings share a spelling, and the collision is silent: it compiles, and
it segfaults. `tests/progs/method_syscall.mereo` sidesteps it with `16 bytes`
and says why in a comment, which is a workaround and not a fix.

**The obvious shape of a fix is syntax that already exists.** `in register` and
`in stack` are how a program body already says which side of this line it wants;
letting a state field take the same words would make the intent explicit where
it is currently inferred from a width. `slot is 8 bytes in stack` is storage,
`slot is 8 bytes in register` is a word, and a bare `N bytes` keeps today's
meaning so nothing in the corpus moves. Worth deciding before it bites someone.

The cheap half, if the design half waits: refuse `[FIELD + ...]` when FIELD is a
register-width state field, naming the width rule. That turns a segfault into a
message without settling the surface question.

## An array view -- a span that counts elements?

**Status:** open, now UNBLOCKED, and demonstrated end to end. Leaning: ship the
RECORD form, skip the scalar one. Not written into core.mereo yet.

`span` counts bytes. An array view counts ELEMENTS, which is a span plus a
stride:

```
array is
  data is 8 bytes           -- where the elements are
  count is 8 bytes          -- how many there are
  stride is 8 bytes         -- how far apart

  at (index, address) goes
    a is 0
    ensure index < count    -- the check a raw `data + i * stride` never has
    a is data + index * stride
    address is a
  end
end
```

This was refused twice before, and both refusals are gone: `at` hands back an
ADDRESS, and interpreting an address needs `[p : 8] as LAYOUT`, which the
runtime-address view made possible. A run of poll entries -- what `ppoll` takes, and what `linux_calls` could
only ever build ONE of -- reads:

```
  watched is already array (data is slots, count is 2, stride is 8)

  setup goes
    leave setup when i >= 2
    watched.at (index is i, address is p)
    entry is [p : 8] as linux.poll_entry
    entry.descriptor is fd
    entry.events is 1                  -- POLLIN
    entry.revents is 0
    i is i + 1
    repeat setup
  end
```

**Measured**, on two pipes with one written and both polled: it reports the
index that woke (1, and 0 when the other is written instead). Out of range fails
into the tower (`at: 4`, exit 1). The whole cost is one branch:

```c
    if (__builtin_expect(!((i < (*(unsigned long *)((watched + 8))))), 0)) goto error_1_at;
    at_1_a = ((*(unsigned long *)(watched)) + (i * (*(unsigned long *)((watched + 16)))));
```

**A correction worth recording, because it was stated the other way first:** the
stride CAN be a runtime field. The earlier reasoning -- that `[data + i * stride
: stride]` needs a literal width -- applies to an array of SCALARS, where `at`
returns a value. For records `at` returns an address, no load happens, and the
width only appears at the caller's `[p : 8]` where it is already a literal.
`stride` really does live at `watched + 16`, and changing it to 16 relayouts the
array with no other edit.

**Why it is not written yet.** The scalar form (`words`, `quads`, `halves`) is
the half that would need hand-monomorphising, one definition per width, since
there are no generics. And its only real customer is `programs/tls/field.mereo`
-- 20 of the corpus's 23 stride sites, the bignum limbs -- whose loops are
`repeat step when bi < 16`, already bounded by construction and the hottest code
in the tree. A bounds check per limb access re-checks what the loop bound
guarantees. So the scalar form should be measured against the TLS handshake
before it is believed, and the record form does not need it at all.

**Two rough edges found while demonstrating it**, both worth their own entries
if they bite again:

- A lens name is program-unique, not scope-scoped. Two loops each declaring
  `one is [p : 8] as linux.poll_entry` collide with `name 'one' is not unique`,
  though neither is in scope where the other is used.
- A method call cannot carry `when`. `page.number (value is i) when got == 1` is
  refused; the shape is a guarded scope (`got == 1 goes`). Conditional STORES
  take `when`, calls do not.

## A constant access into a known buffer is not bounds-checked

**Status:** open, small, and decidable. Measured.

Everything is present at compile time: `block is 8 bytes` puts the size in the
compiler's own table, and `[block + 100 : 1]` has a literal offset and a literal
width — the rule that a width must be 1, 2, 4 or 8 guarantees the second. The
access is still accepted, and GCC does not warn at the shipped flags either:

```
  block is 8 bytes
  n is [block + 100 : 1]        -- compiles; reads past the frame
```

A view IS checked against its backing (`backing 'block' is 4 bytes, too small to
view 16`), so the machinery and the message shape both exist; raw accesses just
never went through it.

**Measured across the corpus:** 314 accesses have a literal offset, a literal
width, and a backing whose size is known. None of them overruns, so the check
would be a guard rather than a fix — which is what a planted violation is for.

**What it does not reach**, and why that is not a failing: an index computed at
run time (`[block + i : 1]`, where `i` came from a `read`) is not decidable by
any amount of whole-program analysis, because the value comes from the kernel.
The answer there is already in [Performance](docs/performance.md): bound the
loop by the same length the check tests and the compiler proves the check
redundant, so the safety costs nothing.

## The language server is gone, and nothing replaced it

**Status:** open, deliberately.

`tools/mereolsp.py` served ONE idea -- semantic tokens that marked an
identifier bold at its declaration and bold-italic at every later use, because
Kate's XML highlighting is stateless and cannot remember what was declared. It
was deleted with the old highlighter rather than ported.

Whether that idea is worth an LSP again is an open question. The new
highlighter is a stateless token scanner and deliberately so -- it colours what
the GRAMMAR gives a role and leaves every other identifier plain, which is
Lua's restraint and reads better than colouring everything. "Bold at the
anchor" is a different claim: it needs to know what a name IS, which means
resolution, which means either an LSP or teaching the highlighter to parse.

If it comes back, note that `mereoc.py` now imports cleanly as a module
(`tools/mereohl.py` does exactly that for its word lists), so a language server
could use the real parser instead of approximating it -- which is what made the
old one drift.

