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
beats the tool** -- now **44**, down from 74, and all 44 in the TLS parser. They
sort by cause, which is what the metric is for:

| cause | | |
| --- | ---: | --- |
| the program never states the fact | 20 | `tlen >= 36`, true and written nowhere |
| an invariant the compiler could enforce and does not | 7 | a span's `length` vs its backing |
| genuinely dependent on hostile input | 16 | an index off the wire -- the honest floor |
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

1. **Refuse what the analysis proves WRONG -- not what it cannot prove.** This
   is the step that costs nothing, and it was missed for a while because the
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

   **What is NOT done** is using the invariant as a FACT, which is what unblocks
   the 7. That waits on the analysis being in the compiler: assuming
   `length <= data.size` is only sound once every store to a length field is
   proved to preserve it, and `span.take` narrows through a conditional minimum
   that has to be checked rather than assumed.

   Note `size of X` does NOT exist; the member is `X.size`.

2. **The loop analysis**, in the `leave`-at-top shape first, then do-while with
   the initial value.
3. **What is left is no longer an open question.** It used to read "refuse it,
   or leave it unchecked by name". The bar above answers it: where a skilled C
   programmer cannot deduce the access safe, THE EXPERT WRITES A CHECK -- so
   mereo may write one too, at the same cost, and still be at parity. Refusal
   was never the right answer, because the expert does not refuse to write the
   program. What is still to decide is only the spelling: an automatic check, or
   a refusal that demands the programmer state the missing fact. `tlen >= 36` is
   the worked example -- true, known to whoever wrote it, written nowhere, and
   one line proves all four accesses.

### Plan: blessing accesses inside mereoc

Covers items 1, 2, 5, 6 and 8 above. The shape is one pass with three verdicts
per access, and a fourth thing it does not do.

| verdict | what happens |
| --- | --- |
| **proved safe** | blessed. Nothing emitted, nothing said |
| **proved wrong** | refused, naming the line and both numbers |
| **unproved** | one line naming the access and WHY it could not be proved |
| merely suspicious | nothing. A guess is worse than silence |

The fourth row is the discipline the prototype learned by breaking it: one
missing correlation between two variables reported 406 false alarms out of 3359.
Nothing is called wrong unless it is PROVEN wrong.

**Why blessing is worth anything.** The report and the refusal are the payoff.
There may be a third -- `.at` costs 10% today, and an access the compiler has
proved could compile to the unchecked form, giving the checked spelling at no
cost. That is NOT promised here: GCC already deletes the checks it can prove, so
the gain exists only where mereo proves what GCC cannot. Measure it before
claiming it.

#### One implementation, two front-ends

`tools/mereoprove.py` becomes a thin wrapper that calls the compiler's pass and
tallies, rather than a second copy of the analysis. Two copies would drift, and
this file already carries the rule about not doing the optimiser's job twice for
the same reason -- two answers to keep in agreement.

The pass sits in `plan()`, after `expand_procedures` and `check_call_fit`, where
the flat step list first exists and `hoist_guard_bounds` already runs.

#### The taxonomy, which is the whole of item 8

An unproved access is not one thing, and the message has to say which:

| | message |
| --- | --- |
| the index comes from an INPUT and nothing guards it | **needs a run-time guard** -- the actionable one |
| it comes from an input and a guard exists | informational: a guard is there, the compiler cannot connect it to this access |
| it comes from inside the program | **state the bound** -- `ensure tlen >= 36` and the like |

"Comes from an input" is a reachability walk over the reaching-definitions graph
already built: an index is input-derived if its computation reaches the OUT port
of a primitive. Those are known -- `prim["out"]` -- so no new machinery.

"A guard exists" reuses the `facts` map: a live `ensure` bounding the index at
that step. Note that guarded and proved are different -- a guard whose bound the
compiler cannot resolve leaves the access unproved but not unprotected, and
saying "needs a guard" there would be wrong.

Expected shape of the report on today's corpus: 16 in the first row, all in the
TLS parser, all indices parsed off the wire; 20 in the third; the rest small.

#### Order, and what depends on what

1. **`-fwrapv`** (item 5). **DONE.** The corpus is 1904 bytes smaller, and on
   `tests/versus` it moves mereo TOWARD the C it is measured against: the gap
   closes on `index_fast`, `span_scan` (21 to 15 instructions, 66 bytes) and
   `layout_view`, which now matches C exactly. `index_safe` widens by one. The
   baseline is re-blessed and all seven compile sites carry the flag, since a
   test that measures different flags from `build.sh` measures nothing.

   **Still owed when the analysis lands:** with wrapping defined, an index that
   overflows produces a wrapped value rather than undefined behaviour, so the
   analysis must report unproved when an interval leaves the range of a `long`
   instead of assuming it cannot happen.

2. **The span adoption check** (item 2, first half). **DONE** --
   `check_adoption_fit`, with the clause now allowed in a resource body.

3. **Port the analysis** (item 6). **DONE.** `classify_accesses` in mereoc.py,
   run from `plan()` after `check_call_fit`, leaving its verdicts in
   `ACCESS_VERDICTS`. `tools/mereoprove.py` is 87 lines now instead of 655: it
   compiles each file and tallies what the compiler decided.

   Verified the way the plan asked -- row by row against the old tool across
   every file both can analyse: **75 files, 0 differing verdicts**. The corpus
   is byte-identical and the pass costs 1.0s across 89 binaries (15.5s against
   14.5s), which is compile time and not a constraint.

   One thing the port changes that is worth knowing: the analysis now runs
   inside a full compile, so a program mereoc REFUSES never reaches it. The 26
   refusal tests and the 5 TLS library files (no `program is`, so not programs)
   drop out of the tally, which is why it reads 75 files and 3354 accesses
   rather than 86 and 3359. The verdicts on real programs did not move.

4. **Refuse what is proved wrong** (item 1). **DONE** -- `refuse_proven_wrong`,
   on `OUT` only. `tests/progs/loop_past_end.mereo` and
   `branchless_past_end.mereo` are the planted violations, both verified to
   fail with the check disabled; black-box is 159. The corpus is byte-identical
   and nothing correct is refused.

   One thing the implementation turned on: a WHOLLY LITERAL index already has
   its own check, later and with a better message ("Every part of this is known
   here -- the offset and the width are literals..."), so the new one stands
   aside for it. Without that it preempted the older check and the only
   suite failure was a message mismatch, not a wrong verdict.

5. **The report** (item 8). **DONE** -- `report_unproved`, one `note()` per
   unproved access on stderr, a clean program silent. Corpus-wide:

   | | |
   | ---: | --- |
   | **32** | comes from input, nothing bounds it -- **wants a run-time guard** |
   | 4 | comes from input, a guard is in scope but could not be tied to it |
   | 7 | internal, a bound exists but did not resolve |
   | 1 | the backing did not resolve |

   More land in the input rows than this plan guessed (it said 16), because an
   index is attacker-reachable when its LOOP BOUND came from outside even if the
   counter itself is local -- `copy`'s `i` stepping to a length off the wire is
   controlled by that length.

   Three things the taint needed that were not obvious. A resource METHOD
   reaches its primitive through `prim` + `bind`, so `stream.receive` had to be
   resolved to `linux.read` before its buffer could be seen. The in-ports have
   to exclude the out port, because `read`'s result is called `count` and
   folding it in made every read look like a `write`. And the buffer handed to
   a syscall is often a SCALAR HOLDING AN ADDRESS -- `read_record` receives into
   `at`, which is `sh_rec + got` -- so taint needs an offset-agnostic
   `backing_of`, where `resolve_base` correctly gives up because bounds need a
   number and taint does not.

6. **The span invariant as a FACT** (item 2, second half). This is what unblocks
   the 7. It cannot come earlier: assuming `length <= data.size` is only sound
   once every store to a length field is proved to preserve it, and proving that
   needs the analysis in place. `span.take` narrows through a conditional
   minimum, so it should go through; anything that does not, reports unproved.

#### Decided

**Print every message. No summary, no flag.** A clean program says nothing, and
a program with 44 unproved accesses should say so 44 times. The list is the
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
instructions against 41. The cause is that the bound is read THROUGH MEMORY --
`v.length` is a span field, so a store might change it, and `-fno-strict-aliasing`
(which mereo ships because byte views type-pun by design) makes that worse.
**Hoisting the length into a scalar once recovers all 41 while KEEPING the
check** -- same safety, same speed as unchecked. That is a codegen change rather
than an analysis, and worth doing whatever happens above.

Two things that did not work, so they are not retried: an `ensure count <=
v.length` before the loop, and a `__builtin_unreachable` assumption of the same
fact. Both leave it at 4: the equality has to survive every iteration, and
through memory it does not.

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

