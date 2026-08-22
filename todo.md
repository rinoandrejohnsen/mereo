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

## `N bytes`: fixed with `in stack`

**Status:** closed. The surface question and the diagnostic are both done.
`slot is 8 bytes in stack` is storage; a bare `N bytes` keeps its meaning, so nothing in the corpus
moved -- all 90 binaries byte-identical. `in register` states the default and is
refused on a width a register cannot hold.

The problem was that `N bytes` on a resource field meant two things and the
width chose between them silently. A field of 1, 2, 4 or 8 bytes is a NUMBER, so
`[field + k : w]` reads it as an ADDRESS; only a wider one is a run of bytes.
Both meanings are needed and neither is wrong:

```
span is
  data is 8 bytes             -- holds where the bytes are; `[data + i]` FOLLOWS it
holder is
  pair is 8 bytes in stack    -- IS eight bytes; `[pair + 0 : 4]` offsets into them
```

Without the words, the second stores through the zero the field holds. It
compiled and it segfaulted, and `tests/progs/method_syscall.mereo` sidestepped it
with `16 bytes` and a comment explaining why -- which is now `8 bytes in stack`,
an honest poll entry.

Gated by `bb field/in-stack`, which prints `7 9 16` with the words and exits 139
without them, and by `rejects field/bad-register`.

### The measurement that did NOT work, and why it is worth recording

The attractive idea was to stop choosing: emit every field as storage and let
GCC's scalar replacement of aggregates put it back in a register wherever it is
only read and written whole. That part is true and measured -- 84 fields
rewritten by hand, 22 of 24 binaries byte-identical, +80 bytes across the corpus,
and the boundary behaves, with a field whose address reaches a syscall keeping
its stack slot and one used as a value keeping none.

It is still the wrong fix, because the ambiguity is not about WHERE the field
lives. `span.at` writes `[data + offset]` and `watcher.arm` writes
`[slot + 0 : 4]`; both are bare 8-byte fields inside a method, and one must load
while the other must address. Storage-for-everything would silently turn every
span in the corpus into a read of its own header. Representation was never the
question; meaning was.

### Should storage be the DEFAULT instead? Measured: no, 81 to 1

Asked because `N bytes` reads like bytes, and in a program body that is exactly
what it is -- so a field defaulting to a NUMBER looks like the tail wagging the
dog. Counted across both libraries and the whole corpus:

| field declarations inside a definition | |
| --- | ---: |
| bare, register width -- the ambiguous ones | 81 |
| wider than a register, storage by width | 81 |
| carrying a reading (`as signed`), so plainly a number | 38 |
| explicit `in stack` / `in register` | 2 |

Of the 81 bare ones, **exactly two are ever used as an access base**:
`span.data` and `builder.data`, and both genuinely hold an address, so reading
them as a number IS what they want. The other 79 -- every stat, poll and termios
field in `linux.mereo`, `builder.count`, `builder.limit`, every `record.tag` in
the test corpus -- are plain numbers that nothing dereferences. Exactly one
field in the corpus wanted storage at register width, and it is the poll entry
that started this.

So flipping the default would mean writing `in register` on 81 declarations and
silently breaking any that were missed -- the same failure mode, pointed the
other way. The default stays.

### The inconsistency that IS real, and is not the default

`buffer is 4096 bytes` in a program body is storage; `length is 8 bytes` in a
definition is a number. Same words, different meaning, decided by where they are
written. `in stack` does not remove that -- it only settles the narrower
question of what a WIDTH means inside a definition, which is where the silent
miscompile was.

The context split is defensible on its own terms: a program body declares
storage, that being what a program body is for, while a definition's field list
describes a record layout, where fields are values at offsets. The width rule
was the weak part -- eight bytes a number and nine bytes storage is an
implementation artifact wearing a surface -- and that is the half now sayable.
Worth revisiting only if someone trips on the first half in real code; nothing
in the corpus has.

### Done 2026-08-22: a resource is nothing special in terms of storage

A definition with `N bytes` fields was one contiguous block only if it did NOT
own a lifecycle. The same three fields gave `char f[14]` on a layout and three
separate locals on a resource, decided by whether an `acquire` happened to be
present -- so the same declarations meant a record in one case and independent
registers in the other. The stated reason was that a descriptor must stay in a
register across syscalls; that is no longer true of the block, and measurably
was not.

Now the fields ARE the storage in both. `method_syscall`'s watcher is
`char source[12]`, four for the descriptor and eight for the poll entry, instead
of an `int` and a `char[8]` side by side.

| | |
| --- | --- |
| binaries byte-identical | **88 of 90** |
| the two that moved | `jsontest` +64 B, `keys` +48 B |
| corpus | 388344 -> 388456 bytes, **+112, or +0.03%** |
| the exam | 5920 bytes unchanged, identical output, ratio 1.010 |

The mixed-width case is what made it free, and it is worth recording separately
because it is the one that looked risky: three fields at offsets 0, 4 and 12,
read and written at 4, 8 and 2 bytes, inside one `char[14]`, keeps **0 stack
references** under both gcc and clang and comes out one instruction shorter than
three separate locals. Scalar replacement handles a shared block at mixed widths
as well as it handles separate scalars.

Five sites moved together: the buffer-entry decision, the declaration, the
splice's `_data` test, `state_cell`, and the three body-substitution paths, which
now share `own_bytes_text`. Flag views needed including in `_data` -- they carry
`bitfields` rather than a `playout` and were briefly left behind.

Only scalar state (`NAME is 0`, no width) keeps a long per field: it has no
bytes and so no offset, and a definition cannot mix widths with defaults anyway.

### Done 2026-08-22: the silent case is refused

A register-width field that a method DEREFERENCES has to be able to hold an
address, and one that nothing ever gives an address holds zero. That is now a
message instead of a segfault:

```
line 9: 'w' reads `[slot + ...]`, which follows 'slot' as an ADDRESS -- but
nothing ever gives 'slot' one, so it holds zero. Write `slot is 8 bytes in
stack` if those bytes ARE the storage, or give it an address to follow.
```

The rule counts a value from anywhere a field can get one: a method body, a
primitive method's bound argument, or the adoption at the use site. That last
one is what a first pass by regex could not see -- `page is already builder
(data is room, ...)` gives `data` an address, and the adopted name arrives in
`pending` rather than `init`, so the check reads all five of `init`, `pending`,
`constinit`, `runinit` and `aliases`. Without that it refused every builder in
the corpus, which is the false positive the earlier note predicted.

`span.data` passes on the first count instead: `skip` writes `data is data + n`.

All 90 binaries are byte-identical -- it is a diagnostic and generates nothing.
Gated by `rejects field/unset-deref`, and the same program with `in stack` added
builds and exits 0.

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

## Deciding accesses before committing to C

**Status:** open, measured, and the order of work is now clear. Nothing
implemented; the prototypes below are throwaway scripts and hand edits.

The ambition: mereo forces whole-program, no functions, no heap, and splices
everything, so after expansion it holds more about a program than GCC ever
sees. It should be able to decide most accesses itself, and emit a run-time
check only where it genuinely cannot.

That is the right ambition and the substrate supports it. What the measuring
changed is the ORDER: the analysis is not the first missing piece.

### The substrate is good

`expand_procedures` already produces the flat IR, and `plan` lowers it to C, so
the two-stage structure this needs EXISTS -- an analysis sits between them. No
interpreter and no second language: an interpreter is the wrong tool anyway,
since `count` comes from the kernel and there is nothing concrete to evaluate.
What is wanted is abstract interpretation, and for the common shape not even
that.

`tests/versus/cases/index_safe`, post-splice:

```
loop_start   step
loop_exit    step, cond 'i >= v.length'      <- the bound
loop_start   at_1                            <- the spliced `span.at`
assign       at_1_b = 0
guard        cond 'i < length'               <- the check
assign       at_1_b = [data + i]             <- the access
loop_end     at_1
assign       total = total + b
assign       i = i + 1
loop_end     step
```

Everything is in one list, and here the guard and the loop's exit condition are
the SAME predicate on the same names -- a syntactic match, not a lattice. Field
names resolve globally through `INSTANCE_FIELDS`, so `length` and `v.length`
denote one thing.

### But there is almost nothing to elide

Across the whole corpus there are **109 guards, of which 7 are `IDX < BOUND`,
of which 1 is implied by its enclosing loop.** Eliding proven checks would save
almost nothing, because the corpus already reaches for the UNCHECKED form
(`[v.data + i]`) nearly everywhere.

So the goal is the inverse of what it looks like: not removing checks that
exist, but making the CHECKED form cost nothing, so that reaching for the raw
access stops being worth it.

### Two loop shapes, and only one is easy

| | where the bound is tested | what a proof needs |
| --- | --- | --- |
| `leave L when i >= N` | at the top -- a while | the loop condition alone |
| `repeat L when i < N` | at the bottom -- a do-while | ...and the initial value, since the body runs before the first test |

The second is the corpus's dominant idiom. `examples/wcl` reads a byte and only
then tests, so the first iteration is guarded by `i is 0` and by the ENCLOSING
loop's `leave fill when count == 0`.

### The piece without which none of it works

**35 syscall contracts declare a lower bound. Zero declare an upper one.**

```
  read is assembly "syscall"
    count out rax
    capacity in rdx
    ensure count as signed >= 0       -- and nothing about capacity
  end
```

The kernel guarantees `read` returns at most `capacity`, and programs pass
`buffer.size` for it. Without that clause the chain cannot close however good
the analysis is, because nothing relates the loop's bound to the backing's size.

With it, `examples/wcl` closes completely, and every link is already present:

1. `capacity is 4096`, `buffer is capacity bytes` -> the backing is 4096
2. `read` returns `count <= capacity` -> **the missing clause**
3. `repeat scan when i < count` -> `i < count` on every iteration after the first
4. `i is 0` -> and on the first
5. therefore `i + 1 <= 4096`, so `[buffer + i : 1]` is in range

### Could EVERY access be decided, including the unchecked form?

Not every one -- that cannot be a theorem for any language that reads input,
since proving arbitrary accesses safe reduces to halting. But the corpus splits
far more sharply than that suggests:

| | | |
| --- | ---: | --- |
| induction variables | 2604 | **98%** -- built from constants and loop steps |
| data-dependent | 38 | 2% -- an offset advanced by a length read out of the input |

(Measured by tracing each index back through the assignments that define it and
asking whether the chain reaches a memory load. Only 5 indices in the whole
corpus are ever wired to a call, so the scan's blind spot -- it follows `assign`
steps, not out-ports -- changes nothing.)

The 98% is a DECIDABLE CLASS, not a currently-provable set: deciding them still
needs the three things above, in that order.

The 38 are all in the TLS protocol parser -- `[shmsg + server_hello_c]`,
`[tr + foff]` -- offsets advanced by lengths read from the packet. A sound proof
needs "the parser validated this length against the buffer first", which is a
fact about the program's logic rather than its shape. The language cannot infer
it. The programmer can state it, with `ensure`, and then it is provable again.

**And the residue does not need to be proved, because the check is free.** The
hoist measurement below is what makes that true: where a check survives,
hoisting its bound recovers the full vectorisation. So the end state is not "no
checks" but:

- every access CHECKED by default, `.at` rather than `[v.data + i]`;
- 98% of those checks proven away when the program is read;
- the rest carrying a check that costs nothing, sitting exactly where a check
  earns its place -- an index whose value arrived from outside.

Which makes the unchecked form unnecessary rather than merely discouraged, and
that is the prize worth aiming at.

### The rule that decides what belongs here

Stated 2026-08-20, and it triages every item below. Competing on safety was
never a design goal. The bar is **parity with hand-written, optimised,
Linux-correct C**, and nothing is accepted that costs more. Safety is therefore
whatever free compile-time analysis yields, and a gap is not automatically work.

| | where it is paid | verdict |
| --- | --- | --- |
| refuse what is proven wrong | compile time | **take it** — 0 programs break |
| `ensure capacity <= buffer.size` | compile time | **take it** — 0 corpus sites |
| a literal-zero divisor | compile time | **take it** — decidable, unbuilt |
| read-before-write of a raw buffer | compile time | **take it** — flow analysis, unbuilt |
| `-fwrapv` | nothing, measured | **DONE** — see below |
| a run-time guard on an unbounded index | every iteration | only where the binary is measured unchanged |
| zeroing raw buffers | a store per buffer | no |
| a run-time divisor guard | every division | no |

`-fwrapv` was expected to cost, since assuming an induction variable cannot wrap
is exactly what a loop optimiser wants. Measured: **377248 bytes against 379168
across 89 binaries, 75.4 ms against 77.4 ms on 800M byte-loads, and 42 vector
instructions either way.** Smaller, no slower, identically vectorised. It does
not detect an overflow, but it removes the undefined behaviour for free, and
free is the whole test.

The tension worth keeping in view is in `docs/performance.md`: a checked access
with the invariant stated is 33 ms against 30 ms unchecked. That 10% is why a
check can never be the DEFAULT form. `[buffer + i]` stays unchecked and matches
the C; `.at` is opt-in. Compile-time analysis is the only route to a safer
default, which is what the rest of this entry is about.

### Order of work

**Done:** the bound hoist (`hoist_guard_bounds`), which makes a checked access
in a loop cost what an unchecked one costs; the TLS bounds, which were a
remotely-triggerable overflow rather than an analysis question; the contract
upper bounds; and `tools/mereoprove.py`, which measures how far the analysis
reaches without being part of the compiler.

**The metric is not the percentage.** By the rule above the target is a person,
so the score that means anything is **the count of places a skilled C programmer
beats the tool** -- now **34**, down from 74. They sort by cause, which is what
the metric is for:

| cause | | |
| --- | ---: | --- |
| comes from input, nothing bounds it | 28 | **wants a run-time guard** -- the honest floor |
| comes from input, guarded, not tied to the access | 4 | a limit of the analysis |
| a bound that did not resolve | 1 | |
| an unresolved base | 1 | |

Only the last two rows are tool work, and the third is not work at all: an index
parsed from a ServerHello cannot be bounded by any analysis, and it is where an
expert keeps a run-time check -- so mereo may too, at parity.

Closed on the way, each a case where a reader is not even conscious of deducing:
a load's WIDTH bounds its value, and the width may be implicit (`b is [data + i]`
is a byte); a resource's own state array is not a slot but splices to
`<instance>_<field>`; `buffer is capacity bytes` names its size, which the
emitter already resolves through the scalar's init; a scalar slot's init is a
value even though no `assign` step carries it; a scalar can HOLD AN ADDRESS
(`shmsg is sh_rec + 5`), so the base is reached by chasing it; loops that count
DOWN take their ceiling from the value they entered with; and a counting-up loop
that starts at 1 has floor 1, not 0 -- assuming 0 is sound but too loose to
prove `poff is ii * 8 - 8` non-negative.

Two of those places were closed by writing this down, which is the argument for
the metric. A load's WIDTH bounds its value -- `b is [data + i]` makes `b` a
byte, and `[digits + (b >> 4)]` is then obviously in range, which a reader sees
without effort and the tool did not. And a resource's own state array is not a
slot; it lives on the definition and splices to `<instance>_<field>`, so
`[doc_block + 0 : 1]` -- a CONSTANT index of zero -- was unresolved. Both are
now handled, and `text_bytes` and `own_state_bytes` are at 100%.

On the last: it is **six** primitives, not the 35 said here earlier. 35 declare a
LOWER bound, but only six promise a result bounded by an argument -- `read`,
`write`, `getrandom`, `getdents64`, `readlinkat`, `ppoll`. The rest answer with a
descriptor, a position or zero, and have no argument to be bounded by.

1. **Refuse what the analysis proves WRONG -- not what it cannot prove.**
   **DONE** (`refuse_proven_wrong`). This
   is the step that cost nothing, and it was missed for a while because the
   decision below looked like the only one available. There are three postures,
   and only the third narrows the language:

   | | accesses that stop compiling, in today's corpus |
   | --- | ---: |
   | report only | 0 |
   | **refuse what is proven wrong** | **0 new** |
   | refuse what cannot be proven | 81 |

   The proven-wrong count is 1, and it is `access_past_end.mereo`, which mereoc
   already refuses for other reasons. So nothing that compiles today would stop.
   What it BUYS is two planted mistakes that GCC does not report at `-Wall
   -Wextra -Warray-bounds=2 -Wstringop-overflow=4 -fanalyzer`: a loop to 100
   over a 64-byte backing, and a loop bounded by a count capped at 4096 into 16
   bytes. Both tested with live loops and initialised buffers, so that an
   uninitialised-value finding could not stand in for a bounds one.

   The discipline this depends on is the one the prototype learned the hard way:
   **nothing is reported wrong unless it is proven wrong.** A single missing
   correlation between two variables once produced 406 false alarms out of 3359.
   An analysis that cries wolf is worse than one that says nothing, so anything
   merely unproven is reported as unproven, never as a mistake.

   **The does-it-fit family.** Three places ask the same question -- does this
   thing fit in that backing -- from two sizes both known when the program is
   read. mereo now answers two:

   | | today |
   | --- | --- |
   | `small as wide`, a view over a backing too small | **refused** from the start |
   | `read (buffer is small, capacity is 4096)` | **refused** -- `ensure capacity <= buffer.size` |
   | `already span (data is line, length is 999)` over a 5-byte `line` | **refused** -- `ensure length <= data.size` on the resource |

   **All three are done.** The syscall half is five primitives carrying the
   clause; the span half is a RESOURCE stating an invariant over its own
   fields, checked where an instance is adopted rather than where the resource
   is declared, because that is where both numbers exist:

       span is
         data is 8 bytes
         length is 8 bytes
         ensure length <= data.size

   `span` and `builder` both declare one (`limit <= data.size` for the latter).
   The corpus is byte-identical with all of it added -- 89 binaries, not one
   instruction -- and `tests/progs/syscall_fit.mereo` and `span_fit.mereo` are
   the planted violations.

   `ensure` takes `PORT.size` on its right now, and the direction is DERIVED
   rather than declared: a clause on the OUT port is a promise about the result,
   checked at run time; one on an IN port is a requirement on the call, decided
   when the program is read.

   Using the invariant as a FACT is done too, inductively: assume
   `length <= data.size` before each store to the field, show it still holds
   after, drop what fails and repeat. A LOAD of the field carries the fact, so
   the induction has a base. `skip` is handled by checking the PAIRING that
   makes it safe -- a store of `ptr + X` beside a store of `len - X` leaves
   `offset + length` unchanged -- and `take` by splitting on the `when` that
   selects each branch.

   Note `size of X` does NOT exist; the member is `X.size`.

2. **The loop analysis**, in the `leave`-at-top shape first, then do-while with
   the initial value. **DONE** -- all three shapes are in `classify_accesses`,
   including the counting-down loop that takes its ceiling from the value it
   entered with.
3. **DECIDED and done.** An access the analysis cannot prove keeps whatever the
   programmer wrote -- spelled `.at` it keeps its check, spelled `[base + i]` it
   stays raw. Where an `.at` IS proved, the check is dropped: it can never fail,
   and a branch that never goes anywhere is dead code with a label on it, not a
   safety net. A raw access is never touched either way.

   `drop_proved_checks` does it. Soundness turns on one thing: the proof must
   not LEAN on the guard being removed, or the argument is circular --
   `ensure i < length` makes `[data + i]` provable by itself. Each candidate is
   re-checked with its own fact suppressed and survives only if still proved
   without it. A span of 11 indexed by a count the kernel caps at 8 loses its
   check; a span of 3 indexed by a count capped at 64 keeps it, and still
   reports `at3: 2: at: 10` at run time.

   MEASURED, and the number is honest: 2 checks dropped corpus-wide, binaries
   BYTE-IDENTICAL. GCC was already deleting the same ones. The mechanism earns
   its keep only where GCC cannot see what mereo can -- the
   `-fno-strict-aliasing` cases the hoist exists for -- and not here.

#### Decided

**Print every message. No summary, no flag.** A clean program says nothing, and
a program with 34 unproved accesses should say so 34 times. The list is the
pressure.

**Compile time is not a constraint.** The barrier governs the run time of the
program, not the run time of the compiler, and the two are not traded against
each other here.

#### Standing rule

**Soundness posture.** A false refusal is worse than a missed one, and the
corpus cannot prove the absence of false refusals -- it can only show that today
exactly one access is called wrong and it is the planted one. Every new
inference rule ships with a planted violation and a re-run of the corpus, and
any rule that cannot be given one does not go in.

### Measured on the way, and worth keeping

Where GCC can prove the bound, emitting the check costs NOTHING -- removing it
from the generated C by hand gives a byte-identical binary, and the `error_2_at`
label is absent from the `.dbg` build. (That label is the isolable evidence;
comparing `index_safe` against `index_fast` by instruction count says nothing,
they are different programs.)

Where GCC cannot, the cost is the VECTORISATION rather than the size: 4 vector
instructions against 41. The bound is read THROUGH MEMORY -- `v.length` is a
span field -- and a memory read in an exit test does not vectorise. Hoisting the
length into a scalar once recovers all 41 while KEEPING the check.

Two things that did not work, so they are not retried: an `ensure count <=
v.length` before the loop, and a `__builtin_unreachable` assumption of the same
fact. Both leave it at 4: the equality has to survive every iteration, and
through memory it does not.

## The bound hoist earns 37 vector instructions in one program and nothing else

`hoist_guard_bounds` in `mereoc.py`, `tests/progs/span_hoist.mereo`. Keep it for
now. Three things are true of it at once and they pull different ways.

**It works.** 4 vector instructions against 41 on the shape it targets, and the
check survives -- the point of it.

**It changes one binary in the tree.** 89 shipped and 78 test binaries are
byte-identical with the hoist off; `span_hoist` is the only difference, and it
is the program written to exercise it. No real program has the shape, because
the shape is a loop bounded by something OTHER than the length the check tests,
which is a slightly odd thing to write.

**Nothing gates the 41.** `bb views/hoisted-bound` pins the program's OUTPUT,
which is identical with the hoist off. So the optimisation is untested in the
only sense that matters, and it silently died once already: while
`drop_proved_checks` retired a check on the wrong fact, `span_hoist` had no
check left to hoist and the pass was inert -- with the black-box case still
green. If the hoist is kept, the gate should be the vector-instruction count,
not the output.

**And it is not knowledge.** Every small reproduction of the shape -- punned
byte array, local buffer filled by a syscall, early exit into a block with side
effects -- vectorises with no help from mereo at all. Something between those
and the whole program stops GCC, and it is not aliasing (`-fstrict-aliasing`
changes neither column). So this is a form the optimiser happens to act on, not
a fact mereo has and GCC lacks. See `docs/safety.md`, which used to claim
otherwise.

The decision is whether a pass that pays off in one synthetic program is worth
its own maintenance. Deleting it is defensible. Keeping it needs the real gate.

### On the corpus figures

2642 run-time-indexed accesses sounds large and is misleading: 89% of it is the
TLS stack, counted once for each of the four programs that include it
(`example_client`, `hello`, `https`, `rest` at 590 each, `x25519` at 252). The
distinct non-crypto programs have handfuls. Any claim about "how much of the
corpus is provable" should be made per distinct program, not per access.

The same caution applies to the 97.6% above, and doubly: it counts accesses
after splicing, so a template used ten times contributes ten, and the corpus and
the tool were written by the same hand. It is a useful number for deciding where
to look next. It is not a validation result.

## From the exam: four things one real program showed

`docs/exam.md` and `exam/`. Writing 357 lines of mereo against 214 lines of
hand-optimised C turned up work that the corpus never would have.

**Fixed on the spot:** `_scan` -- the language's memchr, reached by every `find`,
`search`, `measure` and `until` -- was a byte-at-a-time loop. Widened to
word-at-a-time: **2.9x on find-heavy code**, 55 ms to 19 ms, for 2848 bytes
across the corpus. No program in the corpus scanned hard enough to notice.

**Also fixed:** a nested loop that RESETS the enclosing loop's counter is
refused now (`check_shadowed_counters`). mereo's flat namespace is what makes
this possible in the first place, and C's block scoping is what makes it a
`-Wshadow` warning there instead. Narrow on purpose: sharing a name between
nested loops is a real pattern -- `examples/head.mereo` counts newlines across
blocks that way -- so only a reset is refused. Both false positives it first
produced (`head`, and the exam program itself) came from treating a plain
`leave NAME when` scope as a loop; it looks only at loops that repeat.

**Also fixed:**

* **A layout field resolves as a base now.** `t is store as tables` then
  `[t.count + idx * 4 : 4]` proves, where before the idiomatic grouping was
  LESS provable than the parallel buffers it replaces -- taking the good advice
  cost you the proof. A lens has no `pending` map, because its fields are laid
  OVER a backing rather than bound to one; the field's own declared width is
  the room in front of it. An index past that end is still caught precisely:
  `reaches 65536 bytes into 't.count', which is 32768 bytes`.
* **`t.field.size` parses.** `size_of_c` is reached from expression rendering
  and has neither slots nor definitions in scope, so `plan` fills a
  `FIELD_SIZES` registry once both are known. A template holding a layout port
  can ask how big a field is.
* **`compare` is `equals`.** It answers 1 for EQUAL, and the old name reads
  backwards beside C's `memcmp` -- a doc line was the other option and would
  not have helped, since the group header already said so and I still got it
  wrong. Named for what it reports now, with the sense stated on the method
  itself rather than only in the header.

**Nothing open.** `NAME is NUMBER` at the left margin works now -- a name for a
number with no storage behind it, accepted wherever a literal is because
`_int_value` reads it, rather than in a list of places someone remembered to
update. The exam program names its seven sizes once instead of spelling `8191`
four times.

Two things it needed beyond the parse. `norm_int_c` strips `_` as a digit
separator, so a constant has to be caught before it or `table_slots` becomes the
undeclared identifier `tableslots` -- which is exactly how it first failed. And
a slot may not share a name with a constant: the constant reads as its number in
every arithmetic and the slot would be left alone everywhere else, two meanings
chosen by context.

The companion entry, "no top-level buffers", WAS WRONG: a top-level layout
groups them, the storage is one backing in `program`, and the instance passes to
a template as one port. The exam's 18-port draft was bad design on my part, not
a missing feature.

### The exam program: fourteen unproved, now one

Thirteen of the fourteen closed themselves when the analysis learned to SEE
nested accesses, resolve a pointer-field load as a base, and follow a layout
field. They were never fourteen separate problems; they were three blind spots.

What is left is one, and it is the honest kind:

```
[arena + [t_off + best * 4 : 4] + copy_41_i : 1]
```

The offset is read out of the table, and a 4-byte load is bounded by its WIDTH
-- 0..4294967295 -- whatever it actually holds. The real value is below
`arena_used`, which is at most 1 MiB, and nothing in the program says so. An
`ensure` would close it.

That same load is what briefly made the compiler REFUSE this program: a
width-derived bound was treated as knowledge, and the message even said "every
step of that is known", which was false. A width is a bound, not a proof, so it
can no longer support a refusal -- it reports unproved instead. Nine planted
violations still fire.

The gap that let a broken exam program sit in a green tree is closed too:
`exam/mereo` was not in `build.sh`'s SUBDIRS, so nothing compiled it. A gate
that skips a directory does not protect it.

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


## Where more analysis could still pay, and where it provably cannot

Searched the literature 2026-08-21 and measured each candidate against the
corpus rather than against the paper. The filter is the barrier: a technique
earns its place only if it produces a fact GCC does not already have, or a
diagnostic we do not already print.

### First, the thing that closes off most of the field

A proved bound is worth nothing to GCC. Injecting `if (!(used + copy_2_i <
4194304)) __builtin_unreachable();` in front of a PROVED store in the exam's
generated C gives a **byte-identical binary**. That is not a surprise once
stated plainly: the analysis derives its 144 proved accesses from buffer-size
literals, branch conditions, and kernel promises -- and all three are already in
the emitted C, as literals, as branches, and as assumptions. GCC re-derives the
same ranges.

So the only facts worth handing GCC are ones **absent from the program's text**.
Today that is the kernel's half of the syscall contract, stated at 117 sites
across the corpus, and there is no second example. Anything the program says,
GCC hears.

The second thing that closes off the rest: `.at` appears in five test programs
and **nowhere else**. Every real program -- the examples, the TLS stack, the
exam -- indexes raw. So "prove more, drop more checks" has no prize to collect
in real code, because real code carries no checks. Proving harder buys the
LIST, and only the list. Which is fine, as long as nobody claims otherwise.

### The list, then: 66 unproved accesses, by why

| why | count | what would fix it |
| --- | ---: | --- |
| index from input, nothing bounds it | 30 | nothing -- these WANT a guard |
| the backing did not resolve | 22 | resolve the BASE (below) |
| a bound is in scope, not a number | 10 | Pentagons (below) |
| a guard is in scope, not tied to this | 4 | Pentagons |

The 30 are diagnosed correctly and should stay. The other 36 are blind spots.

### Resolve the base -- mostly a missing constant lookup, now fixed

**Corrected 2026-08-22.** The claim here was that 22 accesses needed reaching
definitions applied to the base, and that `exam/mereo/loglyze.mereo` was the
whole story because `ln` holds either `rbuf + i` or `line`. Wrong on the
diagnosis. Fifteen of them were `_acc_const` not consulting `CONSTANTS`: `rbuf
is read_buf bytes` with `read_buf is 65536` at the left margin, and the emitter
resolved that while the analysis did not, so every access into the biggest
buffer in the program reported that its backing did not resolve. A blind spot
introduced by the top-level-constants work itself, three commits earlier.

Fixed, and the corpus goes from 3007 proved to **3016 of 3056, 98.7%**, with
opaque-base falling from 24 to 9. All 90 binaries are byte-identical across the
change, which is the expected shape: the analysis makes lists, not code.

The nine that remain are genuinely dynamic bases -- `[given : 8]`, a pointer
loaded from memory; `number_2_at`, a template local holding an address;
`operand.data`, a span's own field. Those do want the reaching-definition work
described above, and it is now a nine-case job rather than a twenty-two-case
one.

And `ln` was not a base problem at all. With the constant resolved it moves to
**bound-unresolved**, which is the honest verdict: the access is `[rbuf + i +
st_s]` with `i` up to 65535 and `st_s` up to 8191, and 73726 is past the end of
a 65536-byte buffer. The program is safe because `llen` is `j - i` and `j <= n`,
so `i + llen <= n` -- a RELATION between two variables, which a non-relational
interval domain cannot hold, and which is exactly what the next section is
about. The base was never the problem.

### Pentagons -- 14 cases, a known algorithm

Logozzo and Fahndrich, `x in [a, b] AND x < y`. Intervals plus strict symbolic
inequalities between variables: more precise than intervals, far cheaper than
octagons, O(n^2) and near-linear in practice, and built for precisely this
purpose -- validating array accesses in a low-level IL. It was designed as the
fast tier of an adaptive analysis, proving the easy majority so an expensive
domain is only needed on a fraction.

Our domain is non-relational, which is exactly the gap it names: `[t_len + best
* 2 : 2]` reports "a bound is in scope but could not be resolved to a number"
because `best < tableslots` is known as a RELATION and our intervals cannot
hold a relation. Ten of the fourteen are that sentence.

### Considered and not taken

**Octagons / polyhedra.** More precise than Pentagons and much costlier;
polyhedra have known scalability trouble. Nothing in the 66 needs `±x ±y <= c`.

**Refinement types (Flux for Rust, liquid types).** The other architecture:
declare refinements on types, discharge them with an SMT solver, pay nothing at
run time -- which fits the barrier exactly. It cuts against the grain here
though: mereo's contracts are DERIVED from what the code does, not declared, and
Flux's power comes from the declarations. Worth knowing about; not a fit.

**Astree / Frama-C EVA.** The reference points for sound whole-program analysis
of real C -- hundreds of thousands of lines in hours. They are what "complete"
costs, and a useful yardstick for not overclaiming what a transpiler's own pass
achieves.

**Anything aliasing-shaped.** The lowering does launder pointers through `long`,
so GCC loses object identity -- but the exam is already at parity with its
hand-written C twin (min ratio 0.997, and 6 vector instructions against C's 10
with no time difference, because the hot path is the SWAR scan). There is no
deficit to recover. Restoring aliasing information could only make mereo BEAT
hand-written C, which is not the bar.

## The 9 sites the analysis has been pointing at, unread

Found 2026-08-21, while answering "have we exhausted what we know". No -- we had
not read the output. The count is 9 DISTINCT sites, not the 30 the raw total
says: seven are the TLS stack counted once per program that includes it, exactly
the caution recorded further up this file.

**`crypto.server_hello` walks off the end of the record.** `programs/tls/
crypto.mereo`. The template takes `(rec, pub)` and NO length, so the
`ensure total <= capacity` that bounds `sh_rec` to 512 bytes -- the fix for the
earlier overflow -- never enters it. Inside:

    sidlen is [rec + 38 : 1]        -- 1 wire byte, 0..255
    c is 39 + sidlen ; c is c + 3   -- c now 42..297
    endx is [rec + c : 2] as big    -- 2 wire bytes, 0..65535
    endx is endx + c                -- absolute, up to ~65832
    walk goes
      et is [rec + c : 2] as big
      el is [rec + v : 2] as big    -- 2 more wire bytes
      c is c + 4 ; c is c + el
      repeat walk when c < endx
    end
    text.copy (source is rec + ks_off, target is pub, length is 32)

A server sends a well-formed 512-byte record whose ServerHello declares a large
extensions length. The walk reads up to ~65 KB past `sh_rec`, then copies 32
bytes from an attacker-chosen offset into `spub`. Pre-authentication, remotely
triggerable, and read from the source -- NOT executed against a hostile server,
so treat the exact reach as unconfirmed and the shape as confirmed.

The fix is the same shape as `read_record`'s: give the template the length it is
missing, and bound `endx` and `ks_off` by it.

    server_hello (rec, reclen, pub) goes
      ...
      ensure endx <= reclen
      ensure ks_off + 32 <= reclen

The other two are `exam/mereo/loglyze.mereo` and want the same treatment.

### What this says about the analysis

It works, and it was ignored. Every one of the nine says "the index comes from
input and nothing bounds it here -- this wants a run-time guard", which is
precise, correct, and was printed on every build. The failure was downstream of
the compiler.

It also settles what the analysis is FOR. It changes no binary (see the survey
above), so its entire value is these nine lines -- and the barrier positively
WANTS the guards they ask for: where the expert cannot deduce it, the expert
writes a check, so mereo may too and still be at parity. At these nine sites we
are not at the bar, we are BELOW it: an expert's C would carry a bound here and
ours does not.

### Done 2026-08-21: seven guarded, two were already safe

`crypto.server_hello` now takes `(rec, reclen, pub)` and bounds every offset it
builds against the record: `39 <= reclen` before the session id length,
`c + 2 <= reclen` and `v + 2 <= reclen` for the two reads of each extension
header, `endx <= reclen` for the block, and `ks_off + 32 <= reclen` for the key
itself. Both callers pass `shlen`, which they already had.

The flight loop in `https.mereo` and `client.mereo` had two UNSIGNED underflows,
not one. `inner_len is reclen - 22` is 18446744073709551615 for a record of 21,
and `ensure tlen + inner_len <= tr.size` then passes because the sum wraps --
so the copy after it would have taken that as a length. `foff is tlen - 36`
underflows the same way. Both bounded now.

The two in `loglyze` were SAFE and stay unguarded: `j < n <= 65536 = rbuf.size`
in the narrow scan, and `i + take <= n` for the copy, by `take <= chunk = j - i`.
An expert's C carries no check at either, so adding one would break the bar.
What was wrong there was the MESSAGE: `is_guarded` consulted only `ensure`
facts, so it said "nothing bounds it here" about an index with `leave narrow
when j >= n` written directly above. It now reads loop exits too, and both say
"a guard is in scope, but it could not be tied to this access" -- which is the
truth, and points at the interval gap rather than at the programmer.

Verified: the handshake completes against openssl s_server with all five new
guards live (it then fails at the kTLS setsockopt, which is the pre-existing
module-autoload problem and identical on a pre-change build).
`programs/tls/probe_server_hello.mereo` drives the guards from both sides off
one byte of stdin, and is gated by `bb tls/server-hello-{ok,bad}`. With only
`ensure endx <= reclen` commented out, the hostile case exits 0 and prints a key
byte it read past the end of the record -- so the gate is not vacuous.

Reaching those cases also meant letting `tests/blackbox.sh` build from
`programs/tls/`, and its freshness check did not list crypto.mereo -- a
`server_hello` with its bounds removed passed both new cases from a cached
binary. Fixed the same way core.mereo was: anything a listed program includes
belongs in the list.

## SUGGESTION: make "wants a run-time guard" fail the build

Not done -- this is a policy change and should be a deliberate one.

The case for it is the section above. The compiler printed those nine lines on
every build for weeks, and one of them was a remotely triggerable walk off a
512-byte record. A build that says "wants a run-time guard" and passes anyway is
a build whose warnings are furniture.

**The cost is currently zero.** All nine are closed, so the corpus emits no
`wants a run-time guard` at all -- the gate could be turned on today without
failing anything, which is the cheapest moment it will ever have. That is also
the argument AGAINST waiting: the next one that appears is a new one, and it
appears in a build that is otherwise green.

What makes it defensible as an error rather than a warning is that the message
is precise about its own limits. It fires only when the index is input-derived
AND nothing in scope bounds it -- not merely when the access is unproved. The
weaker verdicts stay as notes:

| message | today | proposed |
| --- | --- | --- |
| index from input, nothing bounds it | note | **error** |
| index from input, a guard could not be tied | note | note |
| the backing did not resolve | note | note |
| a bound is in scope, not a number | note | note |

Two things to settle before turning it on:

* an escape hatch. There is none today, and a false positive would be
  unfixable -- the programmer would have to add a check they know is
  unnecessary, which is exactly the run-time cost the bar forbids. `is_guarded`
  reading loop exits (done above) removes the false positives we know of, but
  "we know of" is doing work in that sentence.
* whether it belongs in `mereoc` or in `mereocheck`. The gates live in the
  latter; making the transpiler itself refuse is a stronger claim, and the
  checking suite is where a refusal is normally proven to fire.

## `restrict` is worth nothing here, measured

Asked 2026-08-21, because Rust emits `noalias` on every `&mut` and mereo emits
nothing of the kind. The concern is fair on its face: mereo's model is bytes,
`unsigned char` aliases everything by C's own rule, and `-fno-strict-aliasing`
ships. Between them that is every aliasing mechanism a C compiler has, given up.

It costs nothing, and the measurement is clean.

GCC names its own aliasing failures. Across the corpus it reports exactly
**seven** loops it declined to vectorise because it "would need a runtime alias
check" -- three in `span`, three in `stat`, one in `uname`, all of them the
`text.copy` inside `builder.add`. Every other vectoriser miss is a syscall's
`"memory"` clobber, an unvectorisable statement, or an unaddressable base.

Rewriting those seven to copy through `__restrict`-qualified pointers gives a
**byte-identical binary** in all three programs.

| | span | stat | uname |
| --- | ---: | ---: | ---: |
| base hoisted | 2304 | 2512 | 1488 |
| base hoisted + `__restrict` | 2304 | 2512 | 1488 |

The control is the interesting row. Reaching those loops meant lifting the base
address out of the loop body, and THAT is what moved the binaries -- 80 bytes on
`span`, 128 on `loglyze`, 208 across the corpus, on 2 programs of 20. Adding
`restrict` on top of it changed nothing at all.

So the limit on those loops was never aliasing. It was that the destination is
recomputed from `[page]` and `[page + 8]` on every iteration -- address
arithmetic, not disambiguation. Fix the form and the aliasing question stops
being asked.

### Worth doing, small

Lift a copy loop's two base addresses out of the loop. -208 bytes on the corpus
and **no time difference** on the exam (median ratio 1.000, min 0.998, output
identical, still at parity with the C twin). A size change with no speed change
is worth having and worth not overselling, and it is the same category as the
bound hoist: FORM, not knowledge. See [the survey above] -- that is now three
measured wins in a row that are all form, against one fact (the kernel promise)
and nothing else.

**Do not conclude that aliasing never matters.** It does not matter to code
SHAPED like this. Two things would change that: emitting real function calls
instead of splicing every template, which is exactly where `restrict` earns its
keep; and typed numeric work, where Fortran and Rust beat C for this reason.
Neither is where mereo is today.

## Could we tell LLVM more than GCC?

Measured 2026-08-21 against clang 22.1.8 and gcc 16.2.1. **No** -- the same three
facts behave the same way under both. But asking turned up something else.

### The channel is not wider

| fact | gcc | clang |
| --- | --- | --- |
| a bound the analysis PROVED, stated | byte-identical | byte-identical |
| `restrict` on the seven copy loops | byte-identical | byte-identical |
| the kernel's promise, stated not tested | 2.2% | 0.9% |

The proved-bound result is the one that matters: `__builtin_assume(used +
copy_2_i < 4194304)` in front of a proved store gives clang the same
byte-identical binary that `__builtin_unreachable` gives gcc. So the finding
recorded above -- that a fact already in the program's text buys nothing --
is about optimisers in general, not about GCC.

The kernel promise still pays under both, and pays LESS under clang, because
clang's baseline is quicker and the branch matters less.

### The optimiser is better, and it is not ours to claim

| | vs its own C twin | vs the same source under gcc |
| --- | ---: | ---: |
| mereo + gcc | 1.007 | -- |
| mereo + clang | 1.006 | 0.945 |
| the C twin + clang | -- | **0.935** |

Clang is about 6% quicker on the exam, and it is quicker on the HAND-WRITTEN C by
the same margin. So it is clang beating gcc, not mereo gaining: the bar does not
move, both sides of it do. The speedup is also not the vectoriser -- it survives
`-fno-vectorize -fno-slp-vectorize` intact (0.948), so it is instruction
selection and scheduling.

**One concrete consequence: LLVM does not need the bound hoist.** 37 vector
instructions with the hoist and 37 without, where gcc needs it to get 41 rather
than 4. `hoist_guard_bounds` is a GCC workaround, which is worth knowing given
the entry above already argues it earns its keep in exactly one program.

### What it would cost

Size, which is a stated claim of this project rather than an incidental.

| `exam/mereo/loglyze` | bytes | vs gcc |
| --- | ---: | ---: |
| gcc -O2 -fwhole-program | 5920 | -- |
| clang -O2 -Os | 9792 | +65%, and the speed advantage is gone |
| clang -O2, no vectorise, -flto | 12256 | +107%, 0.939 |
| clang -O2 | 15040 | +154%, 0.946 |

On the small examples the gap is only +15% in total, so it scales with the
program. All 90 corpus programs build under clang unmodified; the only
complaint is `externally_visible`, which clang ignores with a warning.

### The decision, not taken

Roughly **6% of run time for double the binary** on the largest program. Both
numbers are real and they point opposite ways, so this is a judgement rather
than a finding. Three things worth weighing:

* the 6% is not a parity gain. mereo is at parity under either compiler, and
  switching moves both sides equally.
* supporting BOTH is the expensive option, not the safe one: `tests/versus`
  compares instruction histograms, and two backends means two sets of expected
  output, or a gate that only ever runs against one.
* if clang were ever the default, `hoist_guard_bounds` should go with it -- it
  buys nothing there, and a pass that exists for the other compiler is exactly
  the kind of thing that rots.

### The other levers, pulled

Asked afterwards whether LLVM had levers C source cannot reach. Two more were
tested and neither moved anything.

**Buffer alignment.** mereo declares `char rbuf[65536]` and has never set an
alignment, so every buffer is 1-byte aligned as far as either compiler knows,
and the SWAR scan's 8-byte loads are all presumed unaligned. This is not even a
matter of telling: mereo writes the declaration and could align it. Doing so at
16, 32 and 64 gives the same 5920 bytes and, over 41 runs, a ratio of 1.000 and
a min ratio of 1.000. x86-64 unaligned loads have been free since Nehalem.

**Loop form.** LLVM's own remarks over the corpus are led by "could not
determine number of loop iterations" (349) and "Cannot vectorize uncountable
loop" (341), which reads like an indictment of emitting loops as `goto` with a
conditional `leave`. It is not. The same body written as a counted `for` and as
mereo's goto form vectorises identically under gcc (38 against 38) and not at
all under clang (0 against 0). The uncountable loops are uncountable because
they exit on a data condition -- `leave narrow when [rbuf + j : 1] == 10` --
which no loop syntax in any language makes countable.

**So the tally across both compilers.** Facts that pay: the kernel's contract,
and nothing else. Facts that pay nothing: every bound the analysis proves,
`restrict`, alignment. Form that pays: the widened scan, the bound hoist (gcc
only), the copy-base hoist. The pattern has held through every measurement --
what buys anything is either a fact from outside the translation unit, or a
shape that suits a particular optimiser's weakness.

## PGO buys nothing, and the reason is the binary size

Asked 2026-08-21. Profile data is the most promising lever on paper: branch
frequencies are genuinely absent from the program's text, which is the one
category that has ever paid here. It buys nothing, and unlike the other empty
levers this one has a clean mechanical explanation.

Instrumented PGO does not link at all -- `libgcov` wants `mmap` and `calloc`,
and these binaries are freestanding. Sampling PGO does work: `perf record -b`
plus `llvm-profgen` plus `clang -fprofile-sample-use`, no instrumentation and
no libc.

| `exam/mereo/loglyze`, against clang -O2 | median | min |
| --- | ---: | ---: |
| sample PGO, 224 KB of perf data | 1.066 | 1.044 |
| sample PGO, 11 MB of perf data | 1.016 | 0.977 |
| all 31 `__builtin_expect` hints STRIPPED | 1.000 | 1.008 |
| hints stripped, then PGO | 1.015 | 1.029 |

A thin profile makes it 4-6% slower; a 50x denser one gets back to noise. Never
better.

### Why, in three numbers

**`.text` is 5014 bytes.** L1i on this Alder Lake P-core is 32 KB, so the entire
program sits in instruction cache six times over. Code layout and hot/cold
splitting are PGO's principal lever and there is nothing here for them to do.

**The branch miss rate is 1.6%** -- 3.84 M misses in 235 M branches. The
hardware predictor is already at 98.4% on this workload, so knowing a branch's
direction at compile time adds nothing it does not already learn in the first
few iterations.

**There are no calls.** Every template is spliced, so PGO's third lever,
inlining decisions, has no decision to make.

### The uncomfortable row

Stripping all 31 `__builtin_expect` hints changes nothing measurable: 1.000
median, 1.008 min. The `likely` machinery and the not-taken default are not
paying for themselves on this program, for the same reason PGO is not -- the
predictor gets there without help. They are not therefore pointless: they place
the error blocks out of line, which is a layout and readability property of the
generated C rather than a speed one.

`docs/control-flow.md` was checked and needs no change -- it describes `likely`
as a prediction and never claims a speed benefit, which is exactly right and is
now measured rather than assumed. What would be wrong is to start claiming one.

## Emitting C++ instead of C would change nothing

Asked 2026-08-22, as the last of the "could we tell the compiler more" line.
The answer is unusually clean: the generated C **already compiles as C++,
unmodified**, and produces the same binary.

| | |
| --- | --- |
| clang vs clang++ on `exam/mereo/loglyze` | **byte-identical**, 15040 both |
| gcc vs g++ | 5920 both; ratio 0.983 median, 1.000 min |
| g++ with and without `-fno-exceptions -fno-rtti` | 5920 both, no extra sections |

Not one C++ feature is used, so nothing distinguishes the two compilations. The
opt-outs are not even needed -- with exceptions and RTTI left on, the binary is
the same size and gains no `.eh_frame`, `.gcc_except_table` or static-init
machinery, because there is nothing in the output that could throw, no virtual
call and no object with a constructor.

### The one lever C genuinely lacks, and why it is still empty

A C++ reference carries `nonnull` and `dereferenceable(N)` to the optimiser, and
C has no way to state either. Measured on a struct-and-loop shaped like a view
walk:

| | `View *` | `View &` | `View &__restrict` |
| --- | ---: | ---: | ---: |
| g++ | 38 | 38 | 38 |
| clang++ | 0 | 0 | 0 |

Identical. And it would be moot regardless: a reference is a PARAMETER, and
mereo splices every template into one function, so the output has no parameters
for it to qualify.

### The pattern, one last time

Every optimiser-facing advantage C++ has over C -- references implying
dereferenceability, templates, `constexpr`, type-based aliasing -- needs
structure that mereo deliberately does not emit. Functions, types,
abstractions. One function of byte arrays, gotos and raw stores uses none of it,
which is exactly why the two languages produce the same binary from it.

Worth keeping for a different reason than speed: that the output is valid C++
unchanged means `tests/scopes` can go on comparing against C++ twins, and any
future interop is free. That is a property to preserve, not a lever to pull.

## Widen `_scan` from 8 bytes to 32 -- worth 6 to 10% on the exam

Found 2026-08-22 by writing the exam a third time, in C++. See `docs/exam.md`.

The C++ is 10% faster than both the C twin and mereo. None of that is C++.
Taking the C twin and changing ONE function -- `find_byte` becomes `memchr` --
gets the same 10%, and lands within noise of the C++:

| against mereo, 21 runs | median | min |
| --- | ---: | ---: |
| the C twin as written, word-at-a-time | 0.998 | 1.001 |
| the same C, `memchr` and nothing else | 0.903 | 0.912 |
| the C++ | 0.905 | 0.904 |
| the C twin with a hand-written AVX2 scan, freestanding | 0.940 | 0.939 |

So the gap is scan width, not language and not libc. mereo's `_scan` is the SWAR
implementation -- eight bytes a step, XOR against a broadcast byte and the
has-a-zero-byte test. glibc's `memchr` does 32, tuned. The last row is the one
that matters: a naive AVX2 loop, compiled freestanding with no library at all,
recovers 6 of the 10 points. mereo generates its own scan, so it can have this.

### What has to be decided first

**Baseline.** mereo targets x86-64 with no `-march`, and AVX2 is not in the
baseline. Three ways out, in increasing order of what they cost:

* a build flag, and the corpus stops running on pre-Haswell hardware;
* CPUID at startup and a function pointer, which is what glibc does with IFUNC
  -- but mereo splices everything into one function and has no calls, so a
  pointer here would be the first indirect call in any mereo binary;
* CPUID once into a flag and branch on it in `_scan`, which keeps the code
  direct at the cost of one well-predicted branch per call.

**Size.** The whole reason the shipped flags are `-O2` and not `-O3` is that
vectorising everything made it slower and bigger. This is the opposite case --
one specific loop, vectorised deliberately -- but the AVX2 twin above is 13784
bytes against the C's 4592, and where that lands for mereo needs measuring
rather than assuming.

**Whether it is the language's business.** `_scan` is a compiler-generated
primitive, so this is a mereoc change and not a mereo one, which is the right
side of the line. But it is the first target-specific code generation in the
project, and that is a door rather than a step.
