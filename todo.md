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

## DONE 2026-08-22: `_scan` widened to 32 bytes

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

### How it was done, and what it cost

Thirty-two bytes a step through AVX2, as one inline-asm block inside the
existing `always_inline` helper. Intrinsics were not an option -- they need
`target("avx2")` on the function, which cannot then be inlined into a baseline
caller -- and one block keeps the broadcast and the loop together so the
compiler cannot reuse `ymm1` between iterations.

**The baseline question answered itself: CPUID at start-up, once.** Three checks
in the order the manual requires -- OSXSAVE, then XCR0 bits 1 and 2 for the YMM
state, then the AVX2 bit -- into a flag `_scan` branches on. Skipping the middle
check is the classic way to fault on a kernel that does not preserve the upper
halves. Nothing about the shipped flags changes and pre-Haswell still runs the
word-at-a-time path.

`_len >= 32` guards the SETUP rather than the loop: the broadcast and the
`vzeroupper` cost even when the body cannot run once, and a scan over a short
field is the common case. Without that guard a 16-byte scan measured slower than
what it replaced.

| the scan alone, 400,000 iterations | 8 bytes | 32 bytes |
| --- | ---: | ---: |
| len 16 | 0.4 ms | 0.3 ms |
| len 64 | 1.3 ms | 0.4 ms |
| len 256 | 6.0 ms | 1.0 ms |
| len 4096 | 60.3 ms | 15.6 ms |

Correctness is exhaustive rather than sampled: every length 0..200 against every
match position, plus the exam's 400 adversarial seeds and byte-identical output
on the full 84 MB.

**The size cost is real and was accepted deliberately.** `tests/versus`
caught it -- `span_scan` went from 140 instructions and 569 bytes to 172 and
657, against a C twin that did not move -- and the baseline was re-blessed
knowing that is what carrying two paths costs.

### The half that was not the compiler

Widening `_scan` on its own moved the exam 0.8%, not the 6 to 10% predicted.
The reason is worth keeping: **the exam hand-rolled its own SWAR** for the
newline scan, the one loop that touches every byte, so the library never saw it.
Routing that through `text.find` took the pair to **0.947 median, 0.943 min**
against the C twin, and 0.933 against mereo as it stood this morning --
17,958,755 executed instructions down to 15,296,270.

Which is a lesson about the library rather than about this program: hand-rolling
a scan was right advice when the library scanned eight bytes, and became wrong
advice the moment it scanned thirty-two. Anything else in the corpus doing the
same should be looked at.

### It did NOT beat C with the same scan, and the claim was corrected

0.947 is against the twin AS WRITTEN, which still scans eight bytes. mereo got a
wider scan and the twin did not, so that number measures the change and not the
languages. Given the same scan:

| | median |
| --- | ---: |
| C, glibc `memchr` (hosted) | **50.0 ms** |
| C, hand-written AVX2, freestanding | 51.4 ms |
| **mereo** | **51.7 ms** |
| C, eight-byte SWAR, as the exam writes it | 54.5 ms |

Parity with the AVX2 twin -- 0.991 median, 0.997 min -- which is the bar, and
**4.6% behind glibc's memchr**, which is the remaining headroom.

### Done: one stack slot per template, not one per expansion

mereo has no functions, so a template is spliced: nine calls to `format` are
nine copies and nine `char scratch[20]` at function scope. GCC will not overlap
those -- their live ranges span the whole function as far as it can tell -- so
nine expansions reserved nine slots. C++ inlines the same routine nine times and
shares one, which is the comparison that mattered:

| nine call sites, each needing a private 20-byte scratch | frame |
| --- | ---: |
| C++, nine `always_inline` expansions | 344 B |
| **mereo, before** | **520 B** -- 51% WORSE than C++ |
| **mereo, after** | **232 B** -- 33% better |

Values come from stdin in both, so nothing folds; nine distinct call sites in
the source, not a loop the compiler might unroll.

`scope_spliced_arrays` wraps each expansion's array in a `{ }` around the
statements that use it. GCC's slot colouring is already there and only needed
to be told the lifetimes -- a three-array test goes from a 216-byte frame to 88
on that alone. No liveness analysis in mereoc, no renaming.

**Corpus: -9.1% of stack (73,776 bytes) and -2.9% of `.text` (9,265),** 449
blocks over 98 programs. 91 of the 98 binaries are byte-identical -- only the
seven with spliced arrays move. The TLS stack is where it lands: `https` alone
is -8.5% frame and -5.7% `.text`.

### A kernel promise is now stated with the attribute, not a dead branch

`if (!(count <= capacity)) __builtin_unreachable();` became
`__attribute__((__assume__(count <= capacity)));` at all 192 promise sites.

**Byte-identical on 100 programs.** GCC lowers both spellings the same way, and
so does clang -- the generated C compiles under clang 22.1.8 with the attribute
in it. So this buys nothing today and is not an optimisation.

It is a correctness-by-construction change. The attribute **does not evaluate**
its expression; the `if` form does. Every clause today is a comparison between
scalars -- `count <= capacity`, `written <= count` -- with nothing to fault and
nothing to change, which is exactly why the two coincide. The moment a clause
reads memory the `if` form becomes a latent bug rather than a slower spelling,
and nothing in the language stops a contract from growing that way. Reserved
`__assume__` so a program that defines `assume` cannot collide.

### Four more ways of handing GCC a fact, and none of them paid

Worth collecting, because the shape repeats and each was measured:

| what was stated | result |
| --- | --- |
| a bound on an already-PROVED access | byte-identical (8 sites in the exam) |
| a guard replaced by an assumption | **+709 bytes**, no time saved |
| every loop bound's sign (`nonneg_loop_bounds`) | **3% SLOWER** -- 458,385 instructions added to save 27,153 compares |
| the attribute spelling instead of the `if` | byte-identical |

The one category that pays is unchanged: the kernel's promises, which GCC cannot
derive because the call is inline assembly with a `"memory"` clobber -- and a
clobber says *something changed*, not *at most this many bytes*.

The pattern behind all four: **GCC will SPEND a fact it is given.** The
loop-sign experiment is the clearest -- the fact was true, GCC used it, and used
it to peel and unroll. A true fact is not a free fact.

And the vectorisation question, which was the reason to look again: a second
loop exit does destroy vectorisation -- `paddq` 9 to 0 on a summation over 64 KB
-- but only when the exit is DATA-DEPENDENT and therefore carries meaning. A
redundant bound guard costs nothing, because GCC already deletes it: the two
binaries are identical to the instruction. There is no check that both blocks
vectorisation and could be dropped.

### Tried and REVERTED: dropping a `leave` whose condition can never hold

The idea is right in the abstract -- a check that provably never fires is not
worth paying for -- and `drop_proved_checks` already does exactly this for a
method's guard. Extending it to `leave X when COND` is a small change: a guard
goes when its condition is always TRUE, a `leave` goes when its condition is
always FALSE, and `i >= 20` is the negation of `i < 20`, so one interval test
decides both.

It was written, and it is **unsound**. On the exam it dropped exactly one check:

    if ((plen > 255)) goto parse_done;      -- `leave parse when plen > path_max`

A log line with a 301-byte path then comes out as a REQUEST rather than
malformed. The 84 MB corpus never showed it because the longest path in it is 23
bytes. Reverted.

**Why it fired, and it is NOT the idea's fault.** The probe reported
`left_hi=0` for `plen`. The reason is one line:

    copy = {}
    for i, st in enumerate(steps):
        if st.get("type") != "assign":      <- only assignments
            continue

The reaching-definition map is built from `assign` steps ALONE, so a call that
writes its out port never kills what the name held. `rel is 0` is still believed
after `find (... offset is rel)`, `pe is ps + rel` inherits it, `plen is pe - ps`
comes out as zero, and `plen > 255` is "impossible". Nothing to do with
circularity -- `skip_guard` was extended to the bounds derivation first, and
plain subtraction resolves correctly in isolation (`n is a - 20` at index 80 is
refused, naming the 80).

**The idea is sound; the prover is wrong.** Proving a bound WITHOUT the guard
and then dropping the guard is valid, and `skip_guard` already implements
exactly that. It cannot be trusted while the prover believes an out port is
still its declaration.

**A first fix was tried and is inert.** Recording a call's out port in `copy` as
an opaque definition fires only for primitives -- and `text.find` is a mereo
TEMPLATE, so `PRIMITIVES` has nothing to say about which of its ports is
written (`prim_keys=[]` at that step). Corpus unproved count: 39 before, 39
after. The direction lives in the method's own signature, and that is where the
real fix has to read it from.

**And the premise does not survive measurement anyway.** A guard that never
fires is not only a cost -- it is a RANGE FACT the C compiler uses. Deleting
`leave digits when i >= 20` from `format` costs **2,348 bytes and 561
instructions**, because without `i < 20` GCC cannot prove the store stays inside
a twenty-byte scratch and goes conservative on aliasing across the whole
expansion (stack spills 9 -> 16). The extension measured **+20 bytes** on the
exam, not less. The check earns its 68 bytes about thirty times over.

The original motivation -- recovering the 68 bytes `format` pays -- could never
have worked: that guard is load-bearing. Without it the analysis cannot bound
`i` at all, so `skip_guard` correctly refuses to drop it. A guard is droppable
only when something ELSE already bounds the variable, and then it was doing no
work in the first place.

### FIXED: a call now kills what its out port held

`copy`, the reaching-definition map, was built from `assign` steps alone, so a
call that WRITES its out port never killed the name. `rel is 0` was still
believed after `find (... offset is rel)`; every index built on it looked like
the constant zero; and the access looked proved. That is why indexing sixteen
bytes with a find offset over a 512-byte line passed in SILENCE, and why `plen`
came back with a ceiling of 0 in the exam and took a real check down with it.

Three parts, and the second two are the reason the first attempt was inert:

**A call records an OPAQUE definition of its out port.** Written, value unknown.
A contract promising more still arrives through `cbound`/`clow`, so a kernel
count keeps its bound while a find offset, which promised nothing, correctly has
none. Methods with a PROCEDURE body are not involved -- `expand_procedures` has
already spliced them, so their writes are ordinary assignments.

**The receiver may be a NAMESPACE, not an instance.** `text.find` is found under
`definitions["text"]`; `input.read` under the instance's definition. Both the
new code and the EXISTING `cbound` loop looked only for the instance, which is
why a promise on `scan` had never reached anything calling it through `text`.
That was a second, older bug sitting in the same shape.

**`scan` had no contract, so `until` produced an unknown length.** A scan stops
at the byte or at the end, so its offset is never past the length it was given
-- true of the implementation, and now stated. `until` narrows a span through
that port, and `views.mereo` went noisy without it. Helper declarations now take
`ensure` the way assembly declarations always have.

**Result:** unproved across the corpus 39 -> 42, and the three new ones are real
-- accesses whose bound traces to a value the analysis had been inventing.
`.text` +0.02% for the promise, exam byte-identical on the 84 MB log, all suites
green, blackbox 181 -> 182 with the find case now a gate.

### Still open: a STORE indexed from outside is not checked

Found while chasing the above. `tests/progs/load_outport_past_end.mereo` and
`store_outport_past_end.mereo` are the same program, one character apart:

    d is [small + n : 1]        -- READ:  refused, "reaches 65 bytes into 'small'"
    [small + n : 1] is 65       -- WRITE: accepted in SILENCE

`n` is a count the kernel returned, so `read`'s contract puts it at 0..64 and
every index above 15 is past the end of a sixteen-byte buffer. The read is
caught with the exact number. The write is not caught at all -- not refused, not
even reported unproved.

This is the mirror of the descending-index bug fixed earlier, where a LOAD was
under-analysed and the store was fine. Loads and stores travel different paths
and each has had a hole. The write side is the worse one to have: it is the
direction that corrupts.

`tests/progs/find_offset_past_end.mereo` is the same hole reached the other way
and is the simpler reproduction: index sixteen bytes with the offset a `find`
returns over a 512-byte line, and it is silent -- because `rel` is still
believed to be the zero it was declared with.

The load case is a blackbox gate now. The other two are deliberately NOT wired
in -- a red test that never goes green is a broken gate rather than a finding --
but the reproductions sit beside it, ready to be turned on by whoever fixes them.

**These are one bug with two faces.** An out port that never kills its name, and
a store that is not checked at all, both let an index from outside the program
look safe. That is the thing to fix, and dropping guards is worth revisiting
only afterwards -- at which point it should be as straightforward as it sounds.

### Landed: itoa is written in mereo, and `_decimal` is gone

One of the three C helpers is out of the compiler. `text.format` is now mereo --
scopes left early instead of `if`, digits staged in a 20-byte `scratch` and
copied back reversed, which is the shape the C helper had.

| | `.text` | unproved | output |
| --- | ---: | ---: | --- |
| `_decimal` C helper | 5,759 B | 14 | reference |
| `format` in mereo | 5,835 B | 14 | identical |

**+76 bytes, +1.3%, and not one new unproved access** -- the 14 in the exam and
39 across the corpus are the same ones as before, none of them from here.
Identical on 79 formatted values (negatives, zero, nineteen digits) and on the
84 MB log; jsontest, which formats heavily, is byte-identical too.

It took two other pieces of work to become possible, neither aimed at it:

* the **descending-index floor**, without which the copy-back loop reported two
  unproved accesses at every call site and forced an array-free algorithm that
  cost +36% instead of +1.3%
* **slot sharing**, without which nine call sites meant nine `scratch[20]`

The first attempt at this was +36% and 23 unproved, and the conclusion then was
that a spliced template could not match a C helper. That conclusion was wrong --
it compared two different algorithms -- and this is what the corrected version
looks like.

### What is still in the compiler, and the one reason for it

`find` and `equals` stay C. Both are general byte primitives whose bounds belong
to the CALLER, and the analysis cannot carry a caller's guard through a template
splice. Writing `equals` in mereo produces a hard error, not a warning:

    `[qp + equals_2_i : 1]` reaches 4294967295 bytes into 'arena',
    which is 1048576 bytes

-- because the exam passes `other is qp` where `qp` is `arena` plus a four-byte
unsigned field, so the analysis assumes the offset can be 2^32-1 and PROVES the
loop runs off the end. Bounding the offset where it is read does not help; the
induction variable is what cannot be bounded. `ensure other_length <= other.size`
does not resolve when the argument is a computed address into a larger buffer.

`format` moved because it is self-contained: its scratch is its own and the
bound is right there in the declaration. That is the whole difference, and it is
the test for any future candidate.

`_scan` additionally needs three things from `assembly` before it could move at
all: a multi-instruction template (`prim["template"]` is one string), a
read-write operand (`prim["out"]` is singular, and a quoted constraint would
emit `"=+r"`), and a home for the CPU probe. The `helper` keyword cannot go
until all three are out.

### The slot-sharing pass was WRONG, and X25519 is what said so

Shipped and pushed before this was found. The closure checked that nothing
jumps INTO a span -- entering past the declarations -- and never that something
inside jumps OUT and falls back in. A loop whose back-edge label sits above the
span does exactly that:

    format_33_digits:              <- label, ABOVE the block
        {
        char format_33_scratch[20];
        ...
        goto format_33_digits;     <- leaves the block
        }

Re-entering re-creates the array, so the digits staged on the previous pass are
gone. Not a crash: a **wrong answer**. `format` in mereo printed blanks where
numbers belonged, and X25519 returned
`21fd59d1...` against RFC 7748 s5.2's `c3da5537...` -- a corrupted shared
secret, silently.

**Every suite stayed green.** 58 re-entered blocks in the TLS client, 57 in
`https`, 23 in `x25519`, and nothing noticed, because nothing in the corpus
EXECUTED those programs. The exam was untouched only because it still calls the
C `_decimal` helper and so has no spliced array at all.

Three things came out of it:

* the closure now grows a span to contain any label its own jumps target,
  except the ladder, the tower and `exit`, which are never returned from
* a fail-safe re-check drops any span that still fails, rather than trusting
  the closure to be right -- same block counts on every program, so it costs
  nothing
* **`x25519` against RFC 7748 s5.2 is now a gate.** A whole crypto primitive
  against a number someone else published, and it is non-vacuous: run it
  against the compiler that shipped the bug and it fails.

The lesson is narrower than "test more". A transform that rearranges STORAGE
cannot be checked by a build gate or by output tests on programs that do not
run. The corpus had 37 programs and executed a handful; the ones with the most
to lose -- the TLS stack, the crypto -- were the ones nothing ran.

### A `leave` is a fact, and not reading it was REFUSING correct programs

Found while trying `equals` in mereo again. `ensure A <= B` states what holds;
`leave X when A > B` states what would have made it jump, so what holds after it
is the negation -- exactly as strong. The fact set only ever read `ensure`.

The cost was not a missed proof. It was a **false refusal**:

    buf is 200 bytes
    input.read (buffer is buf, capacity is 200, count is got)
    n is got
    leave program when n > 100
    d is [buf + n : 1]        <- "reaches 201 bytes into 'buf'" -- REFUSED

`read`'s promise of `count <= 200` was visible and the guard bounding `n` at 100
was not, so the analysis proved an overrun that cannot happen and rejected a
correct program. That is worse than an unproved warning: this is code that would
not compile, and the author's only recourse is to delete a guard that is doing
its job.

**And the first version of it was UNSOUND, which is the part worth keeping.** An
`ensure` holds for the rest of its scope; a `leave X when C` states `not C` only
until X ENDS. Past that `end`, control may have arrived THROUGH the leave, where
C was true, and the negation is exactly wrong. Letting one escape proved an
out-of-range access **silently** -- a program that had been correctly refused
was accepted. Each fact is now recorded against the scope that learned it and
dropped when that scope closes, and a `leave` naming an ancestor is dropped at
the innermost end instead: that loses a fact and can never invent one.

It was caught by looking at why `equals` still failed, not by the suite -- 42
unproved before and after, 100 files byte-identical, all six suites green with
the hole wide open. `leave_fact_escapes.mereo` is the planted violation and is a
gate now, and it is the third analysis change on this branch to ship a bug that
only a hand-written adversarial case would find.

Three directions are gated -- the bounded program must be SILENT, the same shape
against a fifty-byte buffer must be REFUSED, and the fact must not survive its
scope. Corpus unproved 42
before and after and 100 generated files byte-identical, which is why it went
unnoticed: no program here happens to bound an index with a `leave` and then use
it, presumably because anyone who tried had to work around it.

### `equals` in mereo: closer, and still blocked on the same thing

The hard error that stopped it last time is gone -- that was `plen` believed to
be zero, which the out-port fix corrected. It now transpiles and runs correctly
on the 84 MB log. Two problems remain:

**Written simply it is +5.6% instructions** (54,331,875 against the helper's
51,440,443). The C helper finishes with one OVERLAPPING word compare; the simple
mereo version falls into a byte loop, and paths are median 13 bytes, so the tail
IS the work.

**Written with the overlap it hits the splice boundary.** `[qp + i : 1]` where
`qp` is `arena` plus a four-byte offset field: the analysis says 4294967302
bytes into a 1 MB arena, correctly, because nothing bounds that field. Bounding
it at the call site does not help -- and neither `leave hit when qoff + plen >
arena_max` NOR `ensure qoff + plen <= arena_max` reaches the accesses inside the
spliced `equals`. A caller's guard still does not cross into a template.

**That explanation was wrong, and the question that killed it was "isn't the
template already spliced?"** It is. `equals` is spliced -- the error names
`equals_2_i`, a spliced local -- so the guard and the access sit in the same flat
stream, and dumping the fact set at the failing access shows `qoff <= arena_max`
live at every one of them. The caller's fact arrives. It was simply not being
USED.

`tighten` applies a fact `key + others <= rhs` by capping `key` at
`rhs - min(others)`, and it drops the fact when a sibling's LOWER bound is
unknown. That is correct, not a bug: if `plen` could be negative then
`arena_max - plen` is larger than `arena_max`, and capping at `arena_max` would
be a claim the fact does not support. The sibling here is `plen`, whose floor is
unknown because it is `pe - ps` and nothing says `pe >= ps`.

Bounding the offset by the CONSTANT rather than the variable removes the need
for the relation entirely -- `ensure qoff + path_max <= arena_max` is true,
because `plen <= path_max` was checked when the line was parsed, and it leaves
the whole of `plen` in front of `qoff` without the analysis having to relate the
two. With that, **`equals` in mereo compiles, proves, and produces byte-identical
output on the 84 MB log.**

### Why the last 1% is there: mereo has no `if`

Same algorithm, byte-identical output, and still 505,145 instructions apart. It
is not the C boundary and it is not codegen luck. Count the control structure of
the two bodies:

| | |
| --- | --- |
| C `_same` | 6 `if`, 2 `while`, 6 `return` -- **0 labels, 0 gotos** |
| mereo `equals` | **8 labels, 15 gotos**, 11 `if` |

`docs/control-flow.md` opens with it: *mereo has no `while`, no `if` and no
`switch`. It has scopes and two jumps.* So a conditional REGION costs a label, a
conditional jump in, and usually an unconditional jump out. C's
`if (_pl >= 4) { ... }` is one conditional branch; `quad goes / leave quad when
length < 4 / ... / end` is a label and two jumps.

At ~95,000 calls that is the whole difference, and the branch mix says so
exactly: `jg` +380,435, `jle` +297,838, `jmp` +135,925 against `jne` -407,988
and `jge` -188,092 -- plus ~95,000 extra alignment nops, one padded loop head
per call.

**And the shape of it is not what it looks like.** Adding scopes made it FASTER,
not slower: 54.3M with two, 52.7M with three, 51.9M with four. Each new scope
replaced a byte loop with a wider compare, and the loop it removed cost far more
than the jumps it added. The per-scope cost is real but small; it only becomes
visible once the algorithm is right.

So the 1% is the price of the control-flow model, paid per call, by any
primitive with several cases. It is a property of the language rather than a
defect in the port -- which makes it a thing to decide about rather than a thing
to fix. Nothing here is going to remove it short of giving mereo an `if`, and
that is a much larger conversation than one memcmp.

### And then it is a 1% loss, so it does not land

| | instructions | clock |
| --- | ---: | ---: |
| `_same` C helper | 51,440,443 | 46.2 ms |
| `equals` in mereo, byte tail | 54,331,875 (+5.6%) | -- |
| ...with the overlapping 8-byte tail | 52,653,026 (+2.4%) | 46.3 ms |
| ...and the 4-byte path for lengths 4-7 | **51,945,588 (+0.98%)** | 46.6 ms |

Each step closed part of the gap by making the mereo version match the C
algorithm more exactly -- the overlap first, then the four-byte path, which
matters because a quarter of the paths in the log are shorter than eight bytes.
The last 1% is not algorithmic and was not chased.

Clock is inside the noise either way (ratio 1.009, sd 1.5), so instructions
decide, and they say keep the helper. The port is preserved in the session
scratchpad. **What changed is that it is now a JUDGEMENT rather than a wall:**
`equals` can be written in mereo whenever the 1% is worth removing a C helper
for, and nothing about the analysis is stopping it.

### One resolver instead of three, and the third copy had the bug too

The analysis was resolving "which primitive does this step call, and which port
does it write" in THREE places, each written separately, and they had drifted.
Two looked the receiver up as an INSTANCE only, so a method reached through a
NAMESPACE -- `text.find`, `text.equals` -- resolved to nothing. That single
missing branch produced three bugs, found one at a time over two days:

* a promise on `scan` never reached anything calling it through `text`
* a write through an out port never killed the name, so `rel is 0` stayed 0
* **and a value off the wire was never marked as coming from OUTSIDE**

The third was still live after the other two were fixed, in the `tainted` scan.
It is now `call_prim`/`call_writes`, one implementation, used by all three.

**42 unproved before and after -- the same accesses -- but the ones classified
as input-derived go from 13 to 33.** Twenty accesses move out of "a bound is in
scope but could not be resolved to a number", which reads as a limit of the
compiler, and into "the index comes from input and nothing bounds it here --
this wants a run-time guard", which is a job for the programmer. Same facts,
and the half that matters for safety was being reported as the half that does
not. 100 binaries byte-identical.

### ...and then the concept was taken out of the analysis entirely

One resolver was the small version. The real fix is that the analysis should
never have known ports exist. It asks questions about STEPS -- what does this
write, what is known about the value, did it come from outside -- and "which
port of which primitive does this step happen to write" is a question for the
code that BUILT the step, asked once.

`annotate_calls` now runs immediately after `expand_procedures`, when everything
with a procedure body has been spliced flat and there is one stream of steps
under `_start`. It resolves each surviving call once and hangs the answer on the
step: `_writes`, `_bounds`, `_wired`, `_inports`. The three sites read fields.

**`classify_accesses` contains zero occurrences of `PRIMITIVES`, `"methods"`,
`get("out")`, `"bind"` or `call_prim` across 1,022 lines.** 100 generated C
files byte-identical, corpus unproved 42 before and after, all suites green --
a refactor that changes nothing, which is the only acceptable kind here.

That anything with a procedure body was already spliced is why `format` never
had a single one of these bugs while `find` had three: `format`'s writes are
ordinary assignments, and the analysis reads those without knowing a port is a
thing. Now every call looks like that to it.

### Searched for a THIRD fact that pays, and there is not one

`scan`'s promise was worth -0.37%, so the obvious move was to look for more.
The search is complete and it comes back empty, which is worth recording so the
ground does not get re-covered.

**`same` is the only other helper, and bounding it buys nothing.** Injecting
`__attribute__((__assume__(same >= 0 && same <= 1)))` after the call gives
**51,440,443 instructions -- identical to the digit**. Its result is a flag
compared against zero (`leave hit when same == 0`); the range is never needed.
That is the difference from `scan`, whose offset is used as an INDEX, and it is
probably the rule: a promise pays when the result reaches memory, not when it
reaches a branch.

**The remaining primitives are not candidates.** `population_count` is used in
one file, `trailing_zeros` and `random_word` in none. And `bsf` is undefined for
a zero input, so `result <= 63` would not even be true.

**The syscalls are already covered.** Every out port that is a LENGTH has its
upper bound stated -- `read`, `write`, `getrandom`. What is left returns a
status, a descriptor or a pid, none of which has a meaningful ceiling.
`sendmsg` and `recvmsg` do return lengths, but they take a msghdr, so there is
no port to bound them against.

**And a constant bound cannot be stated at all.** A clause whose right-hand side
names another PORT becomes a promise; anything else becomes a runtime check.
That is deliberate -- it is how `ensure count as signed >= 0` says `read` can
fail -- but it means "the result is at most N" has no spelling. Adding
`ensure result <= 1` to `same` emits

    if (__builtin_expect(!(same <= 1), 0)) goto error_7_equals_text;

a check and an error path, which is the opposite of the intent. Fixing that
needs a second keyword, and since the only candidate measured zero there is
nothing to spend it on.

### Every change on this branch, audited on clock first and instructions second

Clock is the metric. Where two builds are within noise of each other, the
instruction count to completion decides. `.text` decides nothing. Re-measured
commit by commit on the exam, against the 84 MB log:

| | instructions | vs previous |
| --- | ---: | ---: |
| branch start | 57,929,261 | -- |
| `_same` a word at a time + `_scan` early exit | 51,630,115 | **-10.9%** |
| descending-index floor | 51,630,115 | 0 |
| slot sharing | 51,630,115 | 0 |
| slot-sharing re-entry fix | 51,630,115 | 0 |
| `format` written in mereo | 51,630,260 | +145 |
| the assume attribute | 51,630,260 | 0 |
| out-port kill + `scan` promise | 51,440,652 | **-189,608** |
| slot spans that wrap a loop refused | 51,440,443 | -209 |

**Branch total: 52.0 -> 46.0 ms, ratio 0.884, and -11.2% of instructions.** The
two metrics agree, which is the case where neither needs arguing about.

Two corrections to corrections, both from comparing across too many commits:

**`format` in mereo is NEUTRAL, not a win and not a cost.** +145 instructions in
51.6 million. The -189,463 credited to it a day earlier belonged to the commit
after it. The `.text` figure it was first judged on (+76 bytes) was measuring
nothing that matters.

**And the -189,608 is the `scan` PROMISE, not the out-port kill.** Removing
`ensure offset <= length` from HEAD and changing nothing else puts the exam back
at 51,630,051. The out-port kill itself is -209, which is noise.

### `scan`'s promise is the SECOND fact that pays, and there was supposed to be none

`docs/performance.md` and the project record both say the kernel's half of the
syscall contract is the only fact worth stating to GCC, because it is the only
one absent from the translation unit. That is now wrong by one.

`ensure offset <= length` on `scan` is worth **-189,608 instructions, -0.37%**,
for six assume sites in the exam. Clock is unchanged (ratio 1.004 over 31 runs),
so by the rule above it is a win, and a small one.

The mechanism is the same as the kernel's, which is why it was missed: `_scan`
is `always_inline` C wrapped around an inline-asm block with a `"memory"`
clobber. GCC cannot see that the offset it returns is bounded by the length it
was given -- the SWAR tail's bound is not something value-range propagation
follows through the asm. It is a promise about a body GCC cannot read, exactly
like the kernel's, and it had simply never been written down.

**So the rule is not "only the kernel pays". It is "only a fact GCC cannot
derive pays" -- and inline assembly is a second place those live.** Worth a pass
over the other helpers: `same` returns 0 or 1 and never says so.

### Corrected: slot sharing was measured on the wrong axis, and cost instructions

`.text` and stack frame are not the metric. Clock time and instructions to
completion are. Re-measured on those, the scoping pass was **costing** work:

| x25519 (pure computation, RFC 7748 answer) | instructions | stack |
| --- | ---: | ---: |
| no scoping | 9,335,228 | 6,856 B |
| every span scoped | 9,387,557 (+0.56%) | 1,416 B |
| spans that WRAP a loop refused | **9,335,228** | 4,520 B... |
| ...and corpus-wide with that rule | -- | **-1.2%** (was -9.1%) |

**It is not a bug, and that is worth saying plainly.** The whole difference is
one instruction: `lea 0x4a8(%rsp),%rsi` running **63,744 times**. The unscoped
build keeps that inner loop's end pointer live in `%r9`; the scoped build
recomputes it every iteration. The brace cost GCC a register, so it
REMATERIALISED an address rather than keeping it. Nothing about the sharing is
wrong -- the register allocator simply made a different choice inside the block.

Not a spill trade either, which was the first guess: data references went UP
slightly too (2,266,159 -> 2,267,901). L1 misses fell 113 -> 28, and both are
0.0% of accesses, so that is noise at this size.

**The clock never moved** -- ratio 1.001 over 41 runs. So this cost only shows on
the instruction count, and only on x25519: the exam's delta is 209 instructions
in 51.4 million, 0.0004%.

Spans that wrap a loop are now refused. That is 24 blocks kept instead of 449,
and -1.2% of corpus stack instead of -9.1% -- the whole benefit on x25519 is
given up, because every array's span there wraps a loop. Bought at zero
instructions anywhere, which is the standard now.

**The lesson is about the measurement, not the pass.** Three things were argued
on `.text` in the days before this and two of them reverse when re-measured:
`format` in mereo executes **189,463 FEWER** instructions than the C helper it
replaced, not the "+76 bytes, a small cost" that was recorded; and the `format`
bound guard is free rather than worth 2,344 bytes -- deleting it changes 8
instructions in 51.4 million. The earlier "561 instructions" for that guard was
a STATIC count read out of the binary, not instructions executed.

### Pushed further, and there is nothing further to get

The reasonable next guess was that RAII was still holding slots back -- the
release ladder is LIFO, so the live sets are nested rather than arbitrary, and
a handle read from the tower ought to be shareable with a sibling expansion's
local. Two measurements say the ceiling is already reached, and neither says
what the guess expected.

**RAII refuses nothing.** Classifying every spliced array by why the pass would
turn it down -- read from the ladder or tower, span grown into the tail, brace
shape, overlap -- gives **660 of 660 MOVED, none refused**. The tower does read
556 spliced locals, but never an *array*: it reads counts and handles, which
are scalars. The safety condition that exists for RAII costs nothing in
practice, which is the good case, not a missed one.

**Scalars are already optimal, and blocks cannot improve them.** Scoping them
too was implemented and measured: **1,662 blocks in the TLS client against 98,
and a BYTE-IDENTICAL binary.** A scalar lives in a register, and when it spills
the register allocator picks the slot by live range -- which owes nothing to C
block scope. Only aggregates are laid out by declaration, so only aggregates
have anything to gain. The line in mereoc.py says so, with the numbers.

A false start worth recording, because it read as a real regression: the first
scalar attempt made the corpus **worse** (-0.9% of stack against -9.4%, and 7.2
KB more `.text`). That was not scalars being harmful -- it was the greedy
selection. Spans can both be kept only if disjoint or nested, and a scalar span
that merely OVERLAPS an array span was being taken first and locking the array
out. Sorting arrays ahead of scalars restored the exact arrays-only binary,
which is what proved the scalar blocks inert rather than damaging.

**Where the stack actually is now**, by declared bytes across the corpus:

| | bytes |
| --- | ---: |
| `in static` -- never on the stack | 1,400,832 |
| the program's OWN buffers | 601,111 |
| spliced arrays -- all moved | 186,584 |
| spliced scalars -- register-allocated | 87,976 |
| spliced arrays with `= {0}` -- excluded | 1,704 |

Nothing left in that table is both large and movable. The program's own buffers
are program-scope and live for its duration, which is what the programmer asked
for.

### What made it delicate, which is the RAII half of the question

A generated function is: locals at the top, body with expansions spliced, the
**release ladder**, then the **cold tower**. Both tail regions read the locals of
the expansion that failed -- measured, **556 spliced locals are read from tower
bodies**, and the ladder is named per instance (`release_aead_101_op`) so it
holds that instance's handle. In `https.c` a local declared on line 774 is read
on line 19602. Wrap that expansion in a block and neither region compiles.

So every move is refused unless it is provably safe:

* **the name appears nowhere outside the span** -- this is what keeps the ladder
  and the tower working, and it is why only arrays private to one expansion move
* **the span is CLOSED under labels and jumps.** The first attempt inserted 59
  blocks where the finished pass inserts 449, because a span that begins at the
  first line mentioning the array usually begins *inside* a loop whose header is
  above it -- so the loop's own `goto` jumps in from outside. Growing the span
  until every label in it is reached only from within is what found the other
  390.
* **brace depth nets to zero and never dips below it**, so a block cannot split
  an `if` from its body
* **spans overlap only by nesting**, never partially
* it gives up if the span reaches the ladder or the tower

**Arrays only, and only ones with no initialiser.** `long i = 20;` runs once at
entry today; inside a block that sits in a loop it would run every iteration --
a change in behaviour, not in layout. Uninitialised arrays carry no such meaning
and hold the bytes anyway: 334,040 against 1,704 in the `= {0}` forms.

Verified: all six suites green, the strace-checked release sequences included,
which is the evidence that the ladder still runs in order after the change.

### Fixed: a descending index proved nothing, and it was two missing mirrors

Found while trying to write `format` in mereo instead of keeping it as a C
helper. The minimal shape:

| loop shape | before | after |
| --- | --- | --- |
| ascending index, LOAD | proved | proved |
| descending index, STORE | proved | proved |
| **descending index, LOAD** | **not proved** | **proved** |

Neither half alone was the problem -- it was the combination, which is what made
it hard to see. Two causes, both mirrors that had never been written:

**`_INC` only matched `name + K`.** So `i is i - 1` fell into the `else` branch
marked *"opaque write: give up"*, and the whole loop binding was discarded. The
index then had no ceiling either, which is why `iv` answered `(None, None)`
rather than something merely loose. Now `step_of` reads a signed step and the
net change accumulates the same way in both directions.

**`loop_lo` is documented as "the floor of a counting-UP variable"** -- it infers
the value the loop entered with, and answers `None` for anything else. A
descending index therefore had no floor, and an access with `lo is None` is
reported however tight its ceiling. The mirror was already half-written: the
scan that reads `leave X when i >= K` as a CEILING now also reads
`leave X when i <= K` as a FLOOR under everything after it, carried forward
through the literal steps between the guard and the access.

**Why the store proved and the load did not**, which is the part worth keeping:
a store never reaches that code path. Only the load is put through `iv`, so only
the load could be defeated by `iv` failing. The asymmetry was never about loads.

**Verification.** Four adversarial shapes: a floor guard then a jump past the
end, a floor and ceiling with an offset that overruns, a floor guard naming a
different variable than the index, and an eight-byte load whose last byte falls
off. Two are reported unproved and **two are REFUSED** -- and being refused is
new: the analysis could not previously make the range concrete enough to say so.
97 corpus binaries byte-identical. All six suites green, blackbox 178 -> 180.

The new pair in `tests/blackbox.sh` is non-vacuous in both directions: before the
fix the planted violation was only *"not proved"* and the clean case was equally
noisy; after it, the violation is refused as *"reaches 34 bytes into 'buf'"* and
the clean case is silent.

**It changes nothing already written** -- the corpus has 39 unproved accesses
before and after, because no program here counts down through a load. That is
the point rather than a disappointment: the pattern was avoided because it did
not prove.

**What it unblocks.** `format` written in mereo with the same algorithm the C
helper used -- stage the digits, copy them back reversed -- goes from **23
unproved accesses and +36% of `.text`** to **0 unproved and +2.4%** (5896 bytes
against the helper's 5759). The array-free formulation only existed to dodge the
descending load. See the helper entry below for what still blocks `equals` and
`scan`.

### Reading the profile per instruction, which found what guessing did not

After the unroll came out flat, the exam was profiled **per instruction** --
`callgrind --dump-instr=yes`, joined to `objdump` addresses -- and the two
primitives that were actually paying for nothing came out immediately. Neither
was the scan loop the previous three entries on this page are about.

**`_same` compared a byte at a time.** The hash table's key comparison, 8.6% of
every instruction the exam executed, and the second-hottest loop in the program:
two five-cycle loads and about five uops per byte, while its sibling `_scan` was
doing thirty-two bytes a step. It now reads a word at a time with an
**overlapping** final word rather than a byte tail -- a 13-byte path is `[0,8)`
then `[5,13)`, two compares against thirteen iterations. Equality does not care
about byte order or alignment, so a whole word is simply the right instruction
for the question. **7.1% of all instructions, for 67 bytes.**

The width came from the input, not from taste: path lengths are median 13, **max
23**, so a 32-byte vector compare would have been dead code -- the identical trap
the four-vector scan fell into, avoided by measuring first this time.

**`_scan` re-derived answers it already had.** The vector loop finds the byte and
leaves it in `_i`; the word-at-a-time tail below then ran anyway and worked it
out a second time -- two ten-byte constants, a load, and the whole
has-a-zero-byte dance, about twelve instructions to learn what `tzcnt` had
established. It was visible in the profile as `movabs $0x2020202020202020`
executing once per line, which is what sent me looking. The vector loop examines
whole vectors only, so it has looked at exactly `[0, _len & ~31)`: a match lies
below that bound, exhaustion lands on it exactly, and two instructions settle
which. **A further 4.2% of instructions.**

| | median | min |
| --- | ---: | ---: |
| **mereo, both fixes** | **38.1 ms** | 37.5 ms |
| C, `glibc memchr` + `memcmp` (hosted) | 41.0 ms | 40.7 ms |
| C++, `string_view` + `partial_sort` (hosted) | 41.7 ms | 41.5 ms |
| C, `glibc memchr` (hosted) | 42.3 ms | 42.1 ms |
| mereo, before | 44.1 ms | 43.7 ms |
| C, hand-written AVX2 scan, freestanding | 44.6 ms | 44.2 ms |
| C, that plus a word-at-a-time compare | 45.2 ms | 44.8 ms |
| C, as the exam writes it, freestanding | 47.3 ms | 46.8 ms |

**13.9% faster, 10.9% fewer instructions, +292 bytes** on the exam; **+0.5% of
`.text`** across the whole corpus. Verified: `_same` over 45,451 cases (every
length to 300 x every mismatch position) and `_scan` over 2,439,104 (64
alignments x lengths to 600 x every match position), both also against buffers
laid flush against a `PROT_NONE` page so an over-read faults rather than passing.
Output byte-identical on the 84 MB log; all six suites green.

### The two work by opposite mechanisms, and the counters say so plainly

| | instructions | cycles | IPC |
| --- | ---: | ---: | ---: |
| before | 599M | 210M | 2.85 |
| + `_same` a word at a time | 555M | 199M | 2.79 |
| + `_scan` early exit | 533M | 176M | 3.03 |

`_same` removed **44M instructions but only 11M cycles**, and IPC fell: the byte
loop was well-predicted, independent, high-IPC filler. `_scan` removed **22M
instructions and 23M cycles**, and IPC rose -- more than a cycle recovered per
instruction removed, which is the signature of taking something off a **critical
path** rather than removing work. What came off was a five-cycle load and a
p1-only `tzcnt` sitting between finding the newline and using it.

**Instruction count and cycles are not the same currency**, and this is the
cleanest demonstration of it the project has: the change that removed twice as
many instructions saved half as many cycles.

**The same change does not help C.** Given the identical word-at-a-time compare
in the identical shape, the freestanding twin executes 4.8% fewer instructions
and gets *slower* -- 672M to 640M instructions, but 212M to 218M cycles, IPC
3.17 to 2.94. It began with more instruction-level parallelism to lose than it
had work to save. A primitive that is better in isolation is not automatically
better in a program.

### What the profile says is left

**The FNV-1a hash is now the top loop: 6.5M instructions, 12.6% of the exam.**
Six instructions a byte, and the chain is `xor` then `imul` -- 1 + 3 cycles,
serial in the accumulator, with `imul` on p1 only. Instruction selection here is
already optimal: `imul r32, r32, imm32` is 1 uop and the shift-add decomposition
of `0x1000193` is both longer and slower. This is an **algorithm** cost, not an
instruction cost, and it is out of reach anyway -- the C twin hashes identically
so the two agree slot for slot, and changing it changes the tie-break order of
the `top` output.

The whitespace and field skips are next at 5.8%, and they are already the right
instructions: the range test compiles to `sub $9; cmp $23; ja`, and the runs are
about one byte each, so there is nothing to vectorise. Decimal parsing uses
`lea (%rax,%rax,4)` plus an add for the times-ten, which is the standard optimum.

So the scalar side of the exam is now at its instruction-selection floor, and
what is left is either algorithmic or fixed by agreement with the twin.

### Measured and declined: unrolling the scan to four vectors

glibc's `memchr` is four 32-byte vectors per iteration with an aligned-head
prologue, so it issues one branch per 128 bytes where mereo issues one per 32
and never aligns. That was written, tested and measured. It does not ship, and
the reason is worth more than the code was.

The block is correct: one unaligned head vector covers `[i, i+32)`, then `i`
moves to `i + 32 - ((p + i) & 31)` so `vmovdqa` is legal, four compares OR into
one mask, and a hit re-examines the four masks in order. Verified exhaustively
at **64 alignments x lengths 0..400 x every match position, 0 bad** -- and a
misaligned `vmovdqa` faults, so the alignment arithmetic is proved, not argued.
It is **1.8x faster** than one vector a step on a scan of 8 KB or more.

**It made the exam 8% SLOWER.** Gated on `_len >= 512`, the way a length gate is
normally written:

| | median | min |
| --- | ---: | ---: |
| one vector a step | 43.0 ms | 42.4 ms |
| four, gated on `_len >= 512` | 47.4 ms | 46.8 ms |

**The gate tests the wrong quantity.** `_len` is the search BOUND; the cost is
the search WORK, which is the distance to the match -- and the two are unrelated
here. The exam scans for a newline with up to 64 KB of buffer left, and the
lines are **median 84 bytes, max 98**. So `_len` is 65536 at every call, the
gate opens every time, and the four-vector form then loads 128 bytes and
disambiguates four masks to find what one vector finds in three compares. At the
exam's own line length it is **21% slower**; the crossover is around 140 bytes.
No gate on `_len` can see this, because the distance is not knowable before the
scan runs.

**Escalating instead of gating removes the harm, and adds nothing.** Run one
vector a step until 256 bytes are cleared, and only then escalate -- an early
match never reaches the four-vector loop. The one-vector loop stops at exactly
`_lim & ~31`, so "did it match" is that comparison and not a load: three
instructions on the common path. That measures as **42.9 ms against the
baseline's 43.0** -- the distributions overlap, so it is nothing -- while
executing **2.9% MORE instructions** and costing **+1496 bytes of `.text`, +27%**,
because `_scan` inlines at five sites and every one of them grows.

Proved it is the restructure and not the unrolling: disabling the four-vector
loop while keeping the escalation gives **42.8 ms, identical**. The unrolled loop
contributes 9,097 instructions out of 59.6 million. It never runs on the exam.

**A control that lied, and how it was caught.** The first baseline was the new
`_scan` with the threshold sed'd to `0x4000000000000000` -- which leaves a dead
64-bit constant compare on every scan, ~3.5 instructions per line. It reported a
2% gain that did not exist. Building the true baseline from `git HEAD` erased it.
A control has to be the code you would actually ship, not the new code disabled.

**The conclusion is about the corpus, not the technique.** The unroll is a real
1.8x for scans that clear hundreds of bytes without a match. No program here has
one: every scan in the exam, and every `find` in the TLS stack, hits early
against a large bound. So the remaining 4.6% behind `memchr` is not this loop,
and the block is kept in the session scratchpad (`scan4g.h`) against the day a
program appears that scans far.

### What had to be decided first

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

## Scanning the language for more inconsistencies of the `N bytes` kind

Done 2026-08-22, after `N bytes` was closed. The shape to look for is what made
that one bad: **one spelling, more than one meaning, and something invisible
choosing between them.** Five turned up. None of them miscompiles -- that is the
first thing worth saying, because `N bytes` did, and these all either do the
right thing or refuse. They are consistency and diagnostic faults, not
correctness ones, and they are ranked here by how much they cost a reader.

### 1. DONE 2026-08-22: `already` borrows, `blank` zeroes

`already` was doing two jobs, and sharing the word made one of them silent:

```
t is already linux.file            -- descriptor omitted
t.write (buffer is msg, count is msg.size)
```

Accepted, because a field defaults to zero -- and zero is standard input. With
fd 0 opened read-write, which a shell does with `0<>`, it **exited 0 and wrote
the text into the wrong file**, no diagnostic at all. Caught only when fd 0
happened not to be writable, and then as a run-time `-9`.

Split. `already` borrows a thing that already exists, so it names every field;
`blank CLASS` is a fresh zeroed block of that shape and takes no values, since
zero is the whole of what it says. The refusal points from one to the other:

```
line 4: 't' is `already linux.file`, which borrows a thing that already exists,
so it must name every field -- missing descriptor. For a fresh zeroed one, write
`blank linux.file`.
```

**Lenses are excluded, and finding that out was the useful part.** `X is BACKING
as CLASS` gets `mode: "adopted"` internally, so the first strict rule refused
six corpus programs -- `ls`, `server`, `showcase`, `socket`, `uname` -- which
all read like `already CLASS` in the error and are nothing of the kind. A lens
borrows the BACKING's bytes and its fields ARE those bytes; there is nothing to
name. Once excluded, every one of the 90 built unchanged, which says the corpus
never wanted the loose form: the only two programs using it were two of this
week's own tests.

All 90 binaries byte-identical. Gated by `rejects adopt/already-bare`. Docs in
`resources.md` and `syntax-summary.md` -- the latter also had
`linux.file.already (descriptor is 1)`, which is not the syntax and never was,
and the stale "there is no named constant yet".

### 2-5 DONE 2026-08-22: all four were messages, and all four now explain

Every one fell through to a generic line, so a semantic limit on a keyword the
language plainly has arrived at the reader as a syntax error.

| was | now says |
| --- | --- |
| `ensure a <= b` in a definition -> "unrecognized definition line" | that an `ensure` there is an INVARIANT holding one shape, `FIELD <op> FIELD.size`, and that a check over values belongs in a method |
| `ensure` first in a method -> "`ensure` before the method's body" | that the first line declares a CONTRACT on a primitive body, that this body is a procedure, and that `span.at` writes `b is 0` before its check |
| `a is 8 bytes in static` -> "unrecognized definition line" | the field grammar in order, and that staticness belongs to the INSTANCE rather than one field |
| assigning to an `in stack` field -> "'h' is not a scalar slot" | that it is a run of bytes with no single value, and to write a store |

The last still names the address the field resolves to rather than the field,
because the splice has substituted one for the other by then; the sentence says
what happened, which is what the reader needed. Threading the original name
through the rename is more machinery than the message is worth.

Gated by four `rejects` cases, one per message, each matching on the clause that
carries the explanation rather than on the whole text -- so a reworded message
stays green and a message that stops explaining does not.

**Number 4 needed no code.** `NAME is NUMBER` does mean three things by
position, but its one real collision -- a scalar taking a constant's name -- is
already refused where it is written, with a message that names the pattern
outright: "two meanings, chosen by context". The gap was that nothing SAID so
where a reader would look, and `docs/memory.md` now carries the three in a
table. All 90 binaries byte-identical, as they should be for a pass over
diagnostics.

### The pattern across all five

Four of them are diagnostics rather than semantics: the language does the right
thing and describes it badly, usually by falling through to a generic
"unrecognized" line. The next pass over those belongs on the messages, not the
grammar.

The first is not in that group, and the correction to it is worth keeping as a
method note. The entry originally read as an ergonomic wart -- a default that
has to be repeated -- and was written from the shape of the rule rather than
from trying it. Asking what `already` MEANS turned it around: the state side is
right, the field side is wrong, and the wrong side writes to the wrong file and
exits 0. One of these is a real bug and the other four are wording, and the
first draft had them the other way up.

## Second scan: the messages were still speaking the old surface

Done 2026-08-22. The first scan looked for one spelling with two meanings; this
one looked at what the compiler SAYS, and found a different fault running
through it. The surface changed on 2026-08-14 -- parens for arguments, `.` for
members, `end` closing blocks -- and the diagnostics did not. **Eleven places
told the reader to write syntax the compiler rejects.**

The worst of them is the one anybody meets first:

```
mereoc: error: no `program is` -- this file declares things but never uses them
```

`program is` has its own refusal saying a program RUNS, so it opens with `goes`.
So the message for a missing program recommended a form the next message
forbids. I hit it myself earlier this week and read straight past it.

| said | should have said |
| --- | --- |
| ``no `program is` `` | ``no `program goes` `` |
| ``bad parameter list (expected `with a and b`)`` | a parameter list is `(a, b)` |
| ``declare the syscall as `... assembly "syscall" where ...` `` | ports bound on the lines below |
| ``Call it where you need it: `NAME where ...` `` | `NAME (...)` |
| ``construct with `X is CLASS where ...` `` | `X is CLASS (...)` |
| ``the call names the template in it: `TEMPLATE X where` `` | `X.TEMPLATE (...)` |
| the top-level list, offering ``program is`` and ``NAME (PORTS) is`` | both open with `goes` |

Plus four comments in `mereoc.py` naming `with A and B`, `program is` and
`helper CFUNC where ...`, which mislead a reader of the source the same way.

### Gated, because it rotted silently for eight days

`bb surface/no-dead-syntax` greps `mereoc.py` for the dead spellings and fails
if any comes back, excluding the one deliberate refusal that QUOTES `program is`
in order to reject it. Planting `with a and b` back into one message turns it
red.

### Three more, found on the way

**`leave` and `repeat` with no scope name** said `unknown primitive 'leave'`, as
though the word did not exist rather than as though it were missing its scope.
Both now name the shape and say why a jump carries the name it lands on.

**A call to something undeclared** said `unknown primitive 'triple'` -- the word
"primitive" for what the reader wrote as a template call. It now says what the
three callable things are and how each is spelled.

**`in register` is accepted on a buffer** and the error for an unknown storage
word listed only `stack` and `static`. All three are named now.

### One asymmetry left, recorded and not fixed

`when` composes with an assign, a store, a `leave`, a `repeat` and a declaration
-- but not with `ensure`, where it gives `trailing tokens in expression 'n > 0
when c'`. A conditional check is meaningful and the workaround is an enclosing
scope, so this is a small gap rather than a wrong answer, but the message should
say the word is not accepted there rather than blame the expression.

The other one left is its own entry below, because it turned out to be a real
restriction rather than a wording fault.


## A top-level template must have at least one port, and should not have to

Found in the second scan, 2026-08-22, and worth its own entry because the first
explanation for it was wrong.

A METHOD inside a definition may take no ports -- `bump goes` is fine, because
it has the instance's state to reach. A TEMPLATE at the left margin may not:

| written | |
| --- | --- |
| `bump goes` | not a template at all; falls to the top-level line list |
| `bump () goes` | refused: the port list is empty |
| `bump (v) goes` | accepted |

The regexes say it plainly: a method is `^(\w+)(?: \((.*)\))? goes$` with the
list optional, a template is `^(\w+) \((.*)\) goes$` with it required.

**The tempting justification is false.** A template with no state might look
like work nothing can reach, since its locals are private to the splice -- that
is what the refusal said until this was checked. But a template reaches the
world through calls, not only through ports:

```
shout (unused) goes                       -- `unused` is never read
  msg is "hi\n"
  screen is already linux.file (descriptor is 1)
  screen.write (buffer is msg, count is msg.size)
end
```

Accepted, and it prints. The port is pure ceremony: the template does real work
and the only reason it carries a parameter is that the grammar demands one. So
the restriction does not prevent anything -- it just makes people invent a fake
name, which is the shape a rule takes when it is arbitrary.

**Two ways out, and the first is nearly free:** let a top-level `NAME goes`
parse as a portless template, which is the method spelling already, so the two
stop differing for no reason. Or keep the requirement and say why -- but the why
would have to be better than the one that was there, since that one was wrong.

Worth doing with the `when`-on-`ensure` gap, which is the same size and the same
kind: something composes everywhere except one place, with no reason recorded.

## Scalars are the only kind whose name is not checked for reuse

**Answered 2026-08-22, and the answer was that it cannot be the same check.**
The uniqueness check is already uniform across kinds -- what differs is the
PARSER. A second `NAME is N bytes` makes a second slot and is caught; a second
`NAME is VALUE` makes an assignment STEP, so there is only ever one slot to
compare and nothing for uniqueness to see. The asymmetry is in what a repeated
line MEANS, not in what is checked.

So the hazard was closed from the other side, by refusing the case where the
sharing is invisible: a scope that reads a scalar a sibling opened and then
writes it itself. See the `NAME is VALUE` entry below.

What remains unwritten is the reason a buffer may not reuse a sibling's name
while a scalar may. Both rules are defensible -- a buffer is storage and two of
them under one name would be a genuine collision, while scalars are one flat set
by design -- but neither is stated anywhere a reader would look.

## `NAME is VALUE` is declaration AND assignment, with nothing saying which

Scanned thoroughly 2026-08-22, because this is the core spelling and the same
shape as every inconsistency found this week: one form, two meanings, something
invisible choosing. Here the chooser is whether the name already exists -- and
for a scalar that means anywhere in the program, since scalars are one flat set.

**There is no second spelling.** `new v is 5`, `let v is 5`, `v is new 5` and
`v is fresh 5` are all refused; the language offers no way to say "I mean a new
one" or "I mean the existing one".

### What is already caught

| | |
| --- | --- |
| reading a name nothing opens | refused -- `unknown name 'ghost'` |
| a name written but never read | refused -- which catches a misspelled assignment TARGET, since the misspelling is what nothing reads |
| nested loops counted by one scalar, inner RESETS it | refused -- `check_shadowed_counters` |

That is a better safety net than it first looks: the common typo is
`cuont is 5` where `count` was meant, and the new name is then written and never
read, so it is refused. It escapes only if the misspelling is ALSO read
somewhere, which means misspelling it twice consistently.

### What is not caught, with the numbers

**A scope meaning a fresh temp when the name exists.** Accepted, and it assigns
the outer one. `n is 1` then `n is 2` inside a scope leaves n as 2; the same
program in C++ leaves it 1.

**A scope reading what a sibling left.** Measured:

```
  one goes
    v is 7
    t is t + v
  end
  two goes
    t is t + v      -- v is 7 here
    v is 100
  end
```

mereo prints **14**. The C++ shape prints 7 and **warns**, `'v' is used
uninitialized`. mereo cannot warn the same way, because the read is not
uninitialised -- every scalar has a value -- it is simply the wrong one.

### The flat set stops at a template, which narrows all of the above

Verified 2026-08-22. A template's locals are NOT in the caller's flat set: each
splice gets its own, renamed per CALL SITE. The same template used twice has two
of everything -- `label_1_my_name` and `label_2_my_name` in the emitted C.

The isolation runs both ways. A template cannot read a caller's scalar it has no
port for (the read is a read of nothing, and the caller's scalar then reports as
written-but-never-read), and it cannot write one (that opens a local of its own,
which then reports as unused). The only thing it sees beyond its ports is a
top-level CONSTANT, which is a number rather than storage.

So the hazards above are bounded by the unit of reuse. Within one program body a
scalar opened in a scope is not private; within a template it is. That is worth
stating before any check is built, because it means the sibling-read shape can
only happen between two scopes of the SAME body -- which is a much smaller
surface than "anywhere in the program", and makes a check correspondingly more
affordable.

### DONE 2026-08-22: the sibling-temp read is refused

A scope that READS a scalar a sibling opened, and WRITES it later, is refused --
the write later is what says the scope meant a temp of its own, and the read
before it is what got someone else's:

```
line 10: 'two' reads 'v' before writing it, and 'v' was opened in 'one' -- so
this reads what 'one' left rather than a fresh value. Scalars are one flat set
per body, so `v is ...` in 'two' assigns that same name. Give this one its own
name.
```

Reading a scalar an earlier scope computed stays silent, because that is the
flat namespace working as intended -- a first attempt without the write-later
condition flagged 55 of those across the corpus, every one legitimate.

**Two things had to be got right, and the first was nearly a wasted build.** A
scalar's home scope comes from its declaration LINE against the scopes' line
ranges, because the IR has no "declared in scope X" -- every scalar is a flat
slot whether it was opened at the top or inside a loop. A detector that seeded
every scalar as program-level instead reported 0 on the corpus AND 0 on the
known-bad case, which is the shape of a check that would have shipped vacuous.

And spliced names have to be skipped: a template's line numbers are its own, so
a spliced scalar's declaration line falls inside whatever unrelated scope of the
caller happens to span it. That is `<template>_<n>_<local>` for a name and
`<template>_<n>` for a scope -- the second has no trailing underscore, and a
pattern requiring one left `x25519` refusing to build.

Measured quiet on all 90 programs and byte-identical binaries; gated by
`rejects scope/sibling-temp`.

### What is still not caught

Two shapes remain, both narrower than the one now refused.

**A fresh temp colliding with an ENCLOSING scope's name.** `n is 1` at the top
and `n is 2` inside a scope is an assignment, and always will be -- there is no
way to tell it from a deliberate update, which is the common and correct
reading. Nothing to do here beyond what `docs/control-flow.md` now says.

**A misspelled assignment target that is also read.** `cuont is 5` for `count`
is refused when nothing reads `cuont`, which is the usual case; it survives only
if the misspelling appears in a read as well, meaning it was written twice the
same wrong way.

## Scanning the language for more inconsistencies of the `N bytes` kind

Done 2026-08-22, after `N bytes` was closed. The shape to look for is what made
that one bad: **one spelling, more than one meaning, and something invisible
choosing between them.** Five turned up. None of them miscompiles -- that is the
first thing worth saying, because `N bytes` did, and these all either do the
right thing or refuse. They are consistency and diagnostic faults, not
correctness ones, and they are ranked here by how much they cost a reader.

### 1. DONE 2026-08-22: `already` borrows, `blank` zeroes

`already` was doing two jobs, and sharing the word made one of them silent:

```
t is already linux.file            -- descriptor omitted
t.write (buffer is msg, count is msg.size)
```

Accepted, because a field defaults to zero -- and zero is standard input. With
fd 0 opened read-write, which a shell does with `0<>`, it **exited 0 and wrote
the text into the wrong file**, no diagnostic at all. Caught only when fd 0
happened not to be writable, and then as a run-time `-9`.

Split. `already` borrows a thing that already exists, so it names every field;
`blank CLASS` is a fresh zeroed block of that shape and takes no values, since
zero is the whole of what it says. The refusal points from one to the other:

```
line 4: 't' is `already linux.file`, which borrows a thing that already exists,
so it must name every field -- missing descriptor. For a fresh zeroed one, write
`blank linux.file`.
```

**Lenses are excluded, and finding that out was the useful part.** `X is BACKING
as CLASS` gets `mode: "adopted"` internally, so the first strict rule refused
six corpus programs -- `ls`, `server`, `showcase`, `socket`, `uname` -- which
all read like `already CLASS` in the error and are nothing of the kind. A lens
borrows the BACKING's bytes and its fields ARE those bytes; there is nothing to
name. Once excluded, every one of the 90 built unchanged, which says the corpus
never wanted the loose form: the only two programs using it were two of this
week's own tests.

All 90 binaries byte-identical. Gated by `rejects adopt/already-bare`. Docs in
`resources.md` and `syntax-summary.md` -- the latter also had
`linux.file.already (descriptor is 1)`, which is not the syntax and never was,
and the stale "there is no named constant yet".

### 2-5 DONE 2026-08-22: all four were messages, and all four now explain

Every one fell through to a generic line, so a semantic limit on a keyword the
language plainly has arrived at the reader as a syntax error.

| was | now says |
| --- | --- |
| `ensure a <= b` in a definition -> "unrecognized definition line" | that an `ensure` there is an INVARIANT holding one shape, `FIELD <op> FIELD.size`, and that a check over values belongs in a method |
| `ensure` first in a method -> "`ensure` before the method's body" | that the first line declares a CONTRACT on a primitive body, that this body is a procedure, and that `span.at` writes `b is 0` before its check |
| `a is 8 bytes in static` -> "unrecognized definition line" | the field grammar in order, and that staticness belongs to the INSTANCE rather than one field |
| assigning to an `in stack` field -> "'h' is not a scalar slot" | that it is a run of bytes with no single value, and to write a store |

The last still names the address the field resolves to rather than the field,
because the splice has substituted one for the other by then; the sentence says
what happened, which is what the reader needed. Threading the original name
through the rename is more machinery than the message is worth.

Gated by four `rejects` cases, one per message, each matching on the clause that
carries the explanation rather than on the whole text -- so a reworded message
stays green and a message that stops explaining does not.

**Number 4 needed no code.** `NAME is NUMBER` does mean three things by
position, but its one real collision -- a scalar taking a constant's name -- is
already refused where it is written, with a message that names the pattern
outright: "two meanings, chosen by context". The gap was that nothing SAID so
where a reader would look, and `docs/memory.md` now carries the three in a
table. All 90 binaries byte-identical, as they should be for a pass over
diagnostics.

### The pattern across all five

Four of them are diagnostics rather than semantics: the language does the right
thing and describes it badly, usually by falling through to a generic
"unrecognized" line. The next pass over those belongs on the messages, not the
grammar.

The first is not in that group, and the correction to it is worth keeping as a
method note. The entry originally read as an ergonomic wart -- a default that
has to be repeated -- and was written from the shape of the rule rather than
from trying it. Asking what `already` MEANS turned it around: the state side is
right, the field side is wrong, and the wrong side writes to the wrong file and
exits 0. One of these is a real bug and the other four are wording, and the
first draft had them the other way up.

## Second scan: the messages were still speaking the old surface

Done 2026-08-22. The first scan looked for one spelling with two meanings; this
one looked at what the compiler SAYS, and found a different fault running
through it. The surface changed on 2026-08-14 -- parens for arguments, `.` for
members, `end` closing blocks -- and the diagnostics did not. **Eleven places
told the reader to write syntax the compiler rejects.**

The worst of them is the one anybody meets first:

```
mereoc: error: no `program is` -- this file declares things but never uses them
```

`program is` has its own refusal saying a program RUNS, so it opens with `goes`.
So the message for a missing program recommended a form the next message
forbids. I hit it myself earlier this week and read straight past it.

| said | should have said |
| --- | --- |
| ``no `program is` `` | ``no `program goes` `` |
| ``bad parameter list (expected `with a and b`)`` | a parameter list is `(a, b)` |
| ``declare the syscall as `... assembly "syscall" where ...` `` | ports bound on the lines below |
| ``Call it where you need it: `NAME where ...` `` | `NAME (...)` |
| ``construct with `X is CLASS where ...` `` | `X is CLASS (...)` |
| ``the call names the template in it: `TEMPLATE X where` `` | `X.TEMPLATE (...)` |
| the top-level list, offering ``program is`` and ``NAME (PORTS) is`` | both open with `goes` |

Plus four comments in `mereoc.py` naming `with A and B`, `program is` and
`helper CFUNC where ...`, which mislead a reader of the source the same way.

### Gated, because it rotted silently for eight days

`bb surface/no-dead-syntax` greps `mereoc.py` for the dead spellings and fails
if any comes back, excluding the one deliberate refusal that QUOTES `program is`
in order to reject it. Planting `with a and b` back into one message turns it
red.

### Three more, found on the way

**`leave` and `repeat` with no scope name** said `unknown primitive 'leave'`, as
though the word did not exist rather than as though it were missing its scope.
Both now name the shape and say why a jump carries the name it lands on.

**A call to something undeclared** said `unknown primitive 'triple'` -- the word
"primitive" for what the reader wrote as a template call. It now says what the
three callable things are and how each is spelled.

**`in register` is accepted on a buffer** and the error for an unknown storage
word listed only `stack` and `static`. All three are named now.

### One asymmetry left, recorded and not fixed

`when` composes with an assign, a store, a `leave`, a `repeat` and a declaration
-- but not with `ensure`, where it gives `trailing tokens in expression 'n > 0
when c'`. A conditional check is meaningful and the workaround is an enclosing
scope, so this is a small gap rather than a wrong answer, but the message should
say the word is not accepted there rather than blame the expression.

The other one left is its own entry below, because it turned out to be a real
restriction rather than a wording fault.


## A top-level template must have at least one port, and should not have to

Found in the second scan, 2026-08-22, and worth its own entry because the first
explanation for it was wrong.

A METHOD inside a definition may take no ports -- `bump goes` is fine, because
it has the instance's state to reach. A TEMPLATE at the left margin may not:

| written | |
| --- | --- |
| `bump goes` | not a template at all; falls to the top-level line list |
| `bump () goes` | refused: the port list is empty |
| `bump (v) goes` | accepted |

The regexes say it plainly: a method is `^(\w+)(?: \((.*)\))? goes$` with the
list optional, a template is `^(\w+) \((.*)\) goes$` with it required.

**The tempting justification is false.** A template with no state might look
like work nothing can reach, since its locals are private to the splice -- that
is what the refusal said until this was checked. But a template reaches the
world through calls, not only through ports:

```
shout (unused) goes                       -- `unused` is never read
  msg is "hi\n"
  screen is already linux.file (descriptor is 1)
  screen.write (buffer is msg, count is msg.size)
end
```

Accepted, and it prints. The port is pure ceremony: the template does real work
and the only reason it carries a parameter is that the grammar demands one. So
the restriction does not prevent anything -- it just makes people invent a fake
name, which is the shape a rule takes when it is arbitrary.

**Two ways out, and the first is nearly free:** let a top-level `NAME goes`
parse as a portless template, which is the method spelling already, so the two
stop differing for no reason. Or keep the requirement and say why -- but the why
would have to be better than the one that was there, since that one was wrong.

Worth doing with the `when`-on-`ensure` gap, which is the same size and the same
kind: something composes everywhere except one place, with no reason recorded.

## Scalars are the only kind whose name is not checked for reuse

Found 2026-08-22, comparing mereo's scopes against C and C++ (the result is in
`docs/control-flow.md`). Most of the differences are deliberate and stated: one
flat set of scalars, no shadowing, declaration order irrelevant. This one is not
stated anywhere and looks like an omission.

| two sibling scopes both open the name | |
| --- | --- |
| a scalar (`v is 1`) | **accepted** -- one variable, silently shared |
| a buffer (`tmp is 8 bytes`) | refused: "name 'tmp' is not unique" |
| an instance (`t is already linux.file`) | refused: "name 't' is not unique" |

So two of the three kinds get a uniqueness check and the third does not. And the
scalar case is the one where sharing is invisible: a buffer reused would at
least be the same bytes, while two scopes using `v` for unrelated purposes are
one `long v`, and a scope can read a name a sibling opened without opening it
itself. Measured: `one` sets `v is 10`, `two` adds `v` without declaring it, and
the program prints 20.

**Not obviously a bug.** The flat namespace is the design, and it is what lets a
scope reach its surroundings without ports -- refusing reuse outright would break
the accumulator pattern that nested loops rely on, which `check_shadowed_counters`
was written to permit while refusing the reset. But the ASYMMETRY wants a reason:
either scalars should be checked the way buffers are, or buffers should not be,
and whichever it is should be written down.

**Cheapest useful version:** report, do not refuse. A scope that opens a scalar
name a sibling scope already opened is almost always two people wanting a
temporary, and a note naming both lines would cost nothing and read like the
`check_shadowed_counters` message that already exists for the sharper case.

## `NAME is VALUE` is declaration AND assignment, with nothing saying which

Scanned thoroughly 2026-08-22, because this is the core spelling and the same
shape as every inconsistency found this week: one form, two meanings, something
invisible choosing. Here the chooser is whether the name already exists -- and
for a scalar that means anywhere in the program, since scalars are one flat set.

**There is no second spelling.** `new v is 5`, `let v is 5`, `v is new 5` and
`v is fresh 5` are all refused; the language offers no way to say "I mean a new
one" or "I mean the existing one".

### What is already caught

| | |
| --- | --- |
| reading a name nothing opens | refused -- `unknown name 'ghost'` |
| a name written but never read | refused -- which catches a misspelled assignment TARGET, since the misspelling is what nothing reads |
| nested loops counted by one scalar, inner RESETS it | refused -- `check_shadowed_counters` |

That is a better safety net than it first looks: the common typo is
`cuont is 5` where `count` was meant, and the new name is then written and never
read, so it is refused. It escapes only if the misspelling is ALSO read
somewhere, which means misspelling it twice consistently.

### What is not caught, with the numbers

**A scope meaning a fresh temp when the name exists.** Accepted, and it assigns
the outer one. `n is 1` then `n is 2` inside a scope leaves n as 2; the same
program in C++ leaves it 1.

**A scope reading what a sibling left.** Measured:

```
  one goes
    v is 7
    t is t + v
  end
  two goes
    t is t + v      -- v is 7 here
    v is 100
  end
```

mereo prints **14**. The C++ shape prints 7 and **warns**, `'v' is used
uninitialized`. mereo cannot warn the same way, because the read is not
uninitialised -- every scalar has a value -- it is simply the wrong one.

### The flat set stops at a template, which narrows all of the above

Verified 2026-08-22. A template's locals are NOT in the caller's flat set: each
splice gets its own, renamed per CALL SITE. The same template used twice has two
of everything -- `label_1_my_name` and `label_2_my_name` in the emitted C.

The isolation runs both ways. A template cannot read a caller's scalar it has no
port for (the read is a read of nothing, and the caller's scalar then reports as
written-but-never-read), and it cannot write one (that opens a local of its own,
which then reports as unused). The only thing it sees beyond its ports is a
top-level CONSTANT, which is a number rather than storage.

So the hazards above are bounded by the unit of reuse. Within one program body a
scalar opened in a scope is not private; within a template it is. That is worth
stating before any check is built, because it means the sibling-read shape can
only happen between two scopes of the SAME body -- which is a much smaller
surface than "anywhere in the program", and makes a check correspondingly more
affordable.

### DONE 2026-08-22: the sibling-temp read is refused

A scope that READS a scalar a sibling opened, and WRITES it later, is refused --
the write later is what says the scope meant a temp of its own, and the read
before it is what got someone else's:

```
line 10: 'two' reads 'v' before writing it, and 'v' was opened in 'one' -- so
this reads what 'one' left rather than a fresh value. Scalars are one flat set
per body, so `v is ...` in 'two' assigns that same name. Give this one its own
name.
```

Reading a scalar an earlier scope computed stays silent, because that is the
flat namespace working as intended -- a first attempt without the write-later
condition flagged 55 of those across the corpus, every one legitimate.

**Two things had to be got right, and the first was nearly a wasted build.** A
scalar's home scope comes from its declaration LINE against the scopes' line
ranges, because the IR has no "declared in scope X" -- every scalar is a flat
slot whether it was opened at the top or inside a loop. A detector that seeded
every scalar as program-level instead reported 0 on the corpus AND 0 on the
known-bad case, which is the shape of a check that would have shipped vacuous.

And spliced names have to be skipped: a template's line numbers are its own, so
a spliced scalar's declaration line falls inside whatever unrelated scope of the
caller happens to span it. That is `<template>_<n>_<local>` for a name and
`<template>_<n>` for a scope -- the second has no trailing underscore, and a
pattern requiring one left `x25519` refusing to build.

Measured quiet on all 90 programs and byte-identical binaries; gated by
`rejects scope/sibling-temp`.

### What is still not caught

A scope that READS a scalar it has not written, where the writes that reach it
come from a SIBLING scope rather than an enclosing one, is the suspicious shape.
Reading an enclosing scope's scalar is the whole point of the flat set and must
stay silent; reading a sibling's leftover almost never is.

`classify_accesses` already computes reaching definitions with kills, so the
machinery exists. **What has not been measured is whether such a check would be
quiet on the corpus**, and that is the thing to establish before building it --
a diagnostic that fires on `field.mereo` or the TLS stack every build is worse
than none, and this file already records `wants a run-time guard` going unread
for weeks for exactly that reason.

A first attempt at counting this by regex was abandoned: it cannot tell an
ordinary reassignment (`i is i + 1` inside a loop) from a fresh-temp collision,
and it counted 527 of the former. The count has to come from the planner's own
step list and scope stack, not from indentation.


## `new NAME is VALUE`, and the analysis re-measured

Three things, 2026-08-22.

### `new` says which half of `NAME is` you meant

The duality was that `NAME is VALUE` opens the name if nothing has and assigns
it if something has, with no way to state intent. `new NAME is VALUE` states it
and is refused when the name is taken:

```
line 6: `new v is ...` asks for a name of its own, and 'v' is already taken --
scalars are one flat set per body, so this would assign that one rather than
open a new one. Pick another name, or drop `new` if assigning 'v' was meant.
```

Neither `new` nor `blank` is RESERVED, and that was a correction rather than a
choice: reserving `blank` broke `field.mereo`, which has a method by that name.
Both read in exactly one position -- `new NAME is NUMBER`, `NAME is blank CLASS`
-- so contextual is enough, and the comment beside `RESERVED` now says so.

Gated by `rejects scope/new-taken` and `bb scope/new-free`.

### Why a buffer may not reuse a sibling's name -- it was one rule all along

The entry above asked for the reason and assumed there were two rules. There is
one: **a buffer, an instance and a scalar are each ONE declaration in one
function**, so two cannot share a name however far apart the scopes are. A
scalar is the exception that proves it -- `v is 5` written twice is one
declaration and an assignment, not two declarations, so uniqueness has nothing
to compare, which is exactly why it shares silently where a buffer cannot. Both
the message and `docs/control-flow.md` now say this.

### The analysis: unchanged at 98.7%, and one verdict split

Re-measured after the week's changes: **3016 of 3056 proved, 98.7%** -- the same
as before them, so nothing regressed.

One real improvement, and it was a reporting fault rather than a proving one.
`resolve_base` gives up when either half is unknown -- the buffer, or the OFFSET
into it -- and reported both as "the backing did not resolve", which sends the
reader looking for a backing that was never in doubt. In `jsontest`,
`at is [doc : 8] + off` resolves `doc`'s field to `raw` immediately; what does
not resolve is `off`. `backing_of` already answers the first question alone, so
the verdict now splits:

| | before | after |
| --- | ---: | ---: |
| opaque-base | 9 | **3** |
| offset-unresolved | -- | 6 |

Three accesses in the whole corpus genuinely have an unknown backing: two in
`head` (`[given : 8]`, a pointer out of the auxiliary vector) and one in `stat`
(`operand.data`, a span field). That is a much smaller and more honest number
than 9, and it points at the right half of each.

All 90 binaries byte-identical -- the analysis makes lists, not code.

## Signed scalars cost a compare at every length-bounded loop

Found 2026-08-22, running down why mereo executes 7% more compares than the C
twin. About 40% of that gap is this, measured from both ends.

mereo's scalars are signed 64-bit. The C twin's lengths and indices are `u32`.
A loop bounded by a length lowers to a test at the top:

```
  w is 0
  mix goes
    leave mix when w >= plen
```

For an UNSIGNED bound, `0 >= plen` is false whenever `plen != 0`, and the parse
has already refused `plen == 0`, so GCC folds the entry test away and falls into
the body. For a SIGNED bound it cannot -- `plen` might be negative and nothing
has said otherwise -- so the test survives and runs once more than the loop
does. mereo's per-line path runs nine such loops.

| | compares |
| --- | ---: |
| C as written | 2,921,593 |
| the same C with `long` instead of `u32` | 3,006,734 |
| mereo | 3,136,871 |

From the other end: stating `plen > 0` before one mereo loop removes 47,402
compares, and stating it at all twenty-five removes 48,495 -- the same handful,
since most bounds were never the blocker.

### BUILT 2026-08-22, MEASURED, AND REVERTED

It was built. `nonneg_loop_bounds` walked every `leave X when i >= BOUND`,
asked the interval domain for BOUND's lower bound through the same probe
`drop_proved_checks` uses, and the emitter stated the survivors before the
loop's label as `if ((long)BOUND < 0) __builtin_unreachable();`. Fifteen facts
on the exam, output byte-identical to the C twin on the full 84 MB.

**It works and it is slower.**

| | instructions | compares | wall clock |
| --- | ---: | ---: | ---: |
| as shipped | 17,958,755 | 3,136,871 | — |
| with the sign stated | 18,417,140 | **3,109,718** | **1.030 median, 1.019 min** |

The compares fall by 27,153, exactly as the experiment predicted. GCC then
takes the fact and peels and unrolls on the strength of it, adding 458,385
instructions to save those 27,153, and the program runs **3% slower**. Narrowing
it to the single loop that showed the whole compare win does not help either --
1.011 median, 0.997 min, which is noise and not a gain.

So the entry test was never the cost. It is one predictable, well-predicted
compare per loop, and on a machine that retires three instructions a cycle it is
nearly free; what is not free is what GCC does once it believes the loop always
runs.

Two things worth keeping from it. The mechanism is sound and small -- roughly
forty lines, and the probe that made it possible already existed. And it is a
second, sharper example of the rule recorded elsewhere in this file: **a fact
that changes what GCC does is not the same as a fact worth giving it.** The
earlier finding was that stating a proved bound changes nothing. This one
changes something, and the change is a loss.

### Why it had looked worth doing

**mereo already knows.** The bounds are lengths: they come from `.size`, from
`text.find`, from a `read` count with `ensure count >= 0` on it. The interval
analysis that proves accesses in range has the non-negativity of every one of
them, and throws it away at the point where GCC needs it.

Two shapes for a fix, neither designed yet:

* emit the fact -- `if ((long)BOUND < 0) __builtin_unreachable();` before a loop
  whose bound the analysis knows is non-negative. This is measured to work; it
  is also the one thing recorded elsewhere in this file as usually worthless,
  and it is worth understanding why this case differs. It is not a bound on an
  ACCESS, which GCC re-derives on its own -- it is a fact about a SIGN, which
  GCC cannot get from anywhere else.
* compare unsigned where the analysis proves both sides non-negative, which
  needs no new syntax and no assumption, but does change what the generated C
  says.

The first was built and reverted -- see above. **The second is untested**, and it
is not obviously the same experiment: comparing unsigned changes the
INSTRUCTION rather than adding an assumption, so GCC has no new licence to peel
or unroll and cannot spend the fact the way it spent the last one. That is the
one worth trying if this is picked up again.

### What it is NOT, recorded so it is not re-derived

The tempting explanation was that mereo has no functions, so a scope's early
exit needs a flag where `return` needs nothing. It is wrong. The flag is tested
once per line and can account for one of the nine. Rewriting the parse to count
each failure at its own site -- what C does, and expressible in mereo -- made
compares WORSE, 3,288,110, because a conditional scope costs the same test that
`leave ... when` did and adds the increment.

The other 60% of the gap is unattributed. It is spread across the parse rather
than sitting anywhere, and no single change has been found that moves it.

## The scalar width is what costs the IPC, and it is measured

Found 2026-08-22, running the front-end question to the bottom. mereo's IPC is
3.072 against the C twin's 3.490, at the same wall clock. The chain is now
complete and every link is measured.

**The front end fetches bytes, and the two programs fetch the same number:**

| | instructions | bytes fetched | bytes each |
| --- | ---: | ---: | ---: |
| C | 20,348,221 | 69,780,683 | 3.429 |
| mereo | 17,958,755 | 69,141,947 | **3.850** |

Same fetch work, 12% fewer instructions out of it. That is the front-end stall
(35.8% against 24.5%), and it is why the cycles do not fall when the instruction
count does.

**The instructions are bigger because the scalars are 64-bit.** Every 64-bit
operation carries a REX prefix, one byte: 68.7% of mereo's executed instructions
against C's 48.9%. Twenty points at a byte each is about half the 0.42-byte gap;
the rest is `movabs` for 64-bit constants, ten bytes where a 32-bit one takes
five, and mereo runs 679,237 of those against C's 403,002.

**Ruled out by measurement, not argument.** L1 instruction misses: zero, both --
5014 and 3798 bytes both sit in a 32 KB cache. Decode: 99.7% from the uop cache,
both. Fetch redirects: mereo executes FEWER taken branches, 89.7M against 91.6M.
Stack traffic: 2.4% against 2.6%, mereo lower, so it is not register pressure
from one huge function either. Each of those was the obvious answer and none of
them is.

### What could be done, and what it is worth

The scalar width is a language decision and not a bug -- see the signedness
entry, and `docs/design.md`. But it has a price that was not known before today,
and the price is the IPC.

**Nothing here is a small fix.** A narrower scalar would change what `X is 0`
means, which is the most-used line in the language. What is worth knowing is
that the exam's parity is not luck: mereo wins on instruction count and loses
the same amount on fetch, and the two happen to cancel on this workload. A
program with a different mix would not cancel, in either direction, and neither
outcome would mean anything had regressed.

Worth testing if it is ever picked up: whether narrowing only the LOOP COUNTERS
and LENGTHS -- the values the analysis already proves are small and
non-negative -- moves the REX share. That is a code-generation choice rather
than a language one, and it is the same family as the `in register` work.


## Narrower and unsigned scalars, written and measured: both are slower

Asked 2026-08-22, after the IPC gap was traced to scalar width. **mereo cannot
express it** -- `X is 0` is one machine word, signed, and there is no other
form -- so the experiment was done on the generated C, which measures exactly
what a language change would buy.

87 of the exam's scalars were narrowed, holding back the ones that carry an
address or a 64-bit total. Both variants build and produce output identical to
the C twin on the full 84 MB.

| | instructions | compares | REX | bytes/ins | vs mereo |
| --- | ---: | ---: | ---: | ---: | ---: |
| mereo, signed 64 | 17,958,755 | 3,136,871 | 68.7% | 3.850 | — |
| unsigned 64 | 18,917,697 | 3,040,975 | 69.8% | 3.853 | **1.034** |
| unsigned 32 | 19,779,417 | 3,020,059 | **59.5%** | **3.698** | **1.023** |
| the C twin | 20,348,221 | 2,921,593 | 48.9% | 3.429 | 1.000 |

Everything the analysis predicted happens, and the clock still goes the wrong
way. Unsigned removes 96,000 compares, exactly the signedness finding. Narrowing
to 32 bits drops the REX share nine points and the fetch cost to 3.698 bytes an
instruction, exactly the front-end finding. **And both are 2-3% SLOWER**, because
each buys its saving with a larger instruction count -- a 32-bit value mixed
with 64-bit addresses needs extending, and the extensions cost more than the
prefixes saved.

So the shipped design is the fastest of the three on this workload, and the IPC
"deficit" is not a deficit. It is the price of executing 12% fewer instructions,
and paying it is the better trade here.

**This closes the question rather than opening work.** The signedness entry
above and the scalar-width entry both end here: the fact can be handed to GCC
(measured, slower), and the types can be narrowed (measured, slower). What is
left is the possibility that a different workload -- one less dominated by
byte-at-a-time scanning over 64-bit addresses -- would come out the other way,
which is worth remembering when a future program does not reach parity.

### A real bug found on the way

`n is 0 as unsigned` is **accepted and silently ignored**: the emitted C is
`long n = 0`, exactly as without it. A reading that the language takes and drops
is worse than one it refuses, and this one looks like it does the thing this
entry is about. Either make it mean something or refuse it.


## uops.info on the exam's instruction mix: no better combination exists

Checked 2026-08-22 against `uops.info/instructions.xml`, architecture `ADL-P`,
which is the P-core this machine measures on. The question was whether a
different choice of instructions would beat the current one, given mereo is
front-end bound and its `movabs` constants are 6.9% of every byte fetched.

**The answer is no, and the table explains a failed experiment rather than
suggesting a new one.**

| | uops | TP | ports |
| --- | ---: | ---: | --- |
| `MOV (R64, I64)` -- movabs | 1 | 0.28 | **p0156B**, four wide ALU ports |
| `MOV (R64, M64)` -- a load | 1 | 0.33 | **p23A**, the two load ports |
| `MOVZX (R32, M8)` | 1 | 0.35 | p23A |
| `IMUL (R32, R32, I32)` | 1 | **1.00** | **p1 only** |
| `TZCNT` | 1 | **1.00** | **p1 only** |
| `ADD (R64, I8)` | **0** | 0.20 | eliminated |

The SWAR broadcast constants are `movabs`, ten bytes each, 679,237 executions,
4.75 MB of fetch. Routing them through memory to save three bytes apiece was
tried and lost -- 70.97 MB fetched against 69.14. The table says why: it moves
them off four idle ALU ports onto the two LOAD ports, which a program reading
every byte through `movzbl` is already leaning on. Measured port pressure agrees:
p2/3/10 is the busiest counter in both programs.

So `movabs` is the right instruction. It costs one uop on the widest ports in
the machine, and its only price is fetch bytes -- and every way of paying less
fetch costs something scarcer.

**The genuinely expensive instructions are `IMUL` and `TZCNT`**, both p1-only at
a throughput of 1.00, and both programs execute the same number of them --
271,904 IMULs each, since the FNV hash multiplies once per path byte. Neither
language has an advantage there, and a hash without a multiply would change the
output.

### What this closes

Together with the two entries above -- handing GCC the sign (slower) and
narrowing the scalars (slower) -- the instruction-level question is finished.
The mix mereo emits is the best of the ones available: fewer instructions than
C, each a little larger, on ports that are not the bottleneck. What is left is
structural, and it is the one thing not yet tried: **giving mereo real functions
instead of inlining every helper**, which is the other half of the size finding
and would move the fetch cost rather than shuffle it between ports.
