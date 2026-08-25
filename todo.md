# todo

Rewritten 2026-08-25. Everything closed was cut; the previous 3,524 lines are in
git (121 commits touch this file) if a detail is ever wanted. What survives is
what is still open, plus a one-line record of every measurement that came out
NEGATIVE -- those are not history, they are the reason not to try it again.

The live backlog for the ANALYSIS is not here. It is
`tests/validation/run.sh`, whose `KNOWN` table names every gap with its reason
and prints all of them on every run -- five at the moment, and all five are
one cause. A gap that starts behaving fails the suite, so the list cannot rot.

---

## Open, actionable

### Scalarise an instance's fields, the way GCC's SRA does

**76 of the corpus's 104 unproved accesses have a field load in them**, and all
five remaining validation gaps are this. It is the single biggest lever left.

Traced through GCC's own pass dumps on loglyze, 2026-08-25:

    ccp1     281 memory references to `page`
    esra       0     <- Scalar Replacement of Aggregates
    fre1      -2 error blocks
    evrp     -23 error blocks     37 -> 7 in total

SRA's log says exactly what it did:

    Created a replacement for page offset:   0, size: 64: pageD.4261    (data)
    Created a replacement for page offset:  64, size: 64: page$8D.4262  (count)
    Created a replacement for page offset: 128, size: 64: page$16D.4263 (limit)

It split the 24-byte aggregate into three SSA scalars, one per field, and after
that ordinary value-range propagation does the rest. mereo never takes that
step: `[page + 8 : 8]` is read as a load bounded by its WIDTH, and the moment
anything writes to an instance the analysis drops every adopted value it had
for it -- `mutated` is all-or-nothing and program-wide.

The conditions SRA requires (from `tree-sra.cc`) are ones mereo's instances
meet by construction: a complete fixed-size aggregate, no volatile or
bit-fields, constant offsets and sizes, consistent access widths at the same
offset, and no address escaping outside a call argument. mereo's layouts ARE
fixed offsets with declared widths -- the analysis simply does not use them
that way.

**But size the prize honestly.** Scalarising only helps where the resulting
scalars are statically known. GCC scalarised the TLS client too -- 81
replacements -- and still removed only 1 of its 187 checks, because those
counts come off the wire. loglyze's report appends a mostly constant sequence,
which is why 30 fell there. Expect this to close the builder and span gaps and
much of the corpus's 76, and to do nothing for `https`.

### Make "wants a run-time guard" fail the build

**The cost is zero again as of 2026-08-25**, which is the cheapest this will
ever be. That category counts an index that came from OUTSIDE the program with
nothing bounding it -- the one the design calls a mistake waiting to happen, as
against "a guard is in scope and could not be tied to this access", which is a
limit of the analysis and not a hole.

It was 9, then 0, then 12 on 2026-08-24 when a store became an access, and 0
again once a definition in a closed scope stopped killing the one before it.
Across `programs`, `examples` and `exam/mereo`: **zero**.

One program would fail the gate: `tests/progs/find_offset_past_end.mereo`,
which exists to produce exactly this warning and is a `reports` gate in
`tests/blackbox.sh`. So the gate needs the test suite to be able to ask for the
warning without the build refusing -- an env var the suite sets, or the gate
skipping `tests/progs`. Decide which before writing it.

The case for it is unchanged: one of the nine that prompted this was a remotely
triggerable walk off a 512-byte record, and a build that says "wants a run-time
guard" and passes anyway is a build whose warnings are furniture.

### Share the error-record formatter instead of splicing it

`_write_value` is spliced into every error block. Making it a real
`static __attribute__((noinline, cold))` function measured **-16% across the
corpus**:

| | spliced | shared |
| --- | ---: | ---: |
| `abc` | 1296 | 1120 |
| `jsontest` | 3696 | 3088 |
| `https` | 68696 | 55096 |

Cold-path only, so the clock should not notice -- which is exactly why it needs
measuring on the clock before it lands, not on the byte count.

### An array view: a span that counts elements

Open, unblocked, demonstrated end to end, not written into `core.mereo` yet.
`span` counts bytes; an array view counts ELEMENTS, which is a span plus a
stride. Leaning: ship the RECORD form, skip the scalar one.

### A top-level template must have at least one port, and should not have to

`bump goes` at the left margin is not a template at all -- it falls to the
top-level line list -- and `bump () goes` is refused for an empty port list. A
METHOD may take no ports because it has its instance's state to reach; a
template genuinely has nothing to reach, so the restriction is defensible. What
is not defensible is that neither spelling says so.

Worth doing with the `when`-on-`ensure` gap, which is the same size and the same
kind: something composes everywhere except one place, with no reason recorded.

### Strip section headers from the shipped binary?

Open, leaning NO, and measured: `objcopy --strip-section-headers` saves **287
bytes per binary, 22,157 over 77**, and on `abc` that is a further -22%. It
costs `objdump -d`, which then prints nothing. The tower's own tooling is worth
more than the bytes.

### The language server is gone, and nothing replaced it

Deliberate. `tools/mereolsp.py` served one idea -- bold at a name's declaration,
bold-italic at every later use -- which a stateless highlighter cannot do. The
new highlighter is stateless on purpose and reads better for it. Whether that
one idea is worth an LSP again is the open question.

---

## Open, and known to be hard

### Two counters whose SUM is bounded, used separately

**All five remaining validation gaps are this one thing**, and it is the only
class left. An interval carries a bound on a name; it cannot carry the
correlation between two, so reducing `a + b <= c` uses the other term's floor
and the relation is gone.

    builder   `data + count + i`, with `count + length <= limit`,
              `limit <= data.size` and `i < length`
    search    `at + j` where `at = data + i`, `i <= length - needle_length`
              and `j < needle_length`

mereo already does MORE of this than the tools it was measured against:
`tighten` keeps a fact as `key + others <= rhs`, which gets `line[held]` and
`arena[used]` in loglyze -- and Frama-C's Eva proves neither, with intervals or
with octagons. rustc keeps a run-time check for both. What none of them do is
carry the relation into a DERIVED index.

A relational domain would fix it and is a large piece of work. Nothing smaller
has been found.

### `check_call_fit`'s scalar-capacity hole

`syscall_extent_scalar`, recorded in `tests/cbmc.sh`'s `EXPECT_FAIL`. A
syscall's write is not an access in the IR -- inline assembly with a `"memory"`
clobber says *something changed* -- so the capacity is checked at the call site
instead, and a capacity held in a SCALAR escapes that check.

### Two shapes of name reuse that are not caught

A fresh temp colliding with an enclosing scope's name (`n is 2` inside a scope
is an assignment, and always will be -- nothing to do). And a misspelled
assignment target that is ALSO read, which survives only if the same
misspelling was written twice.

---

## Measured and CLOSED -- do not redo

Each was built or measured and came out negative. The number is the point;
without it the idea looks attractive again in six months.

| tried | result |
| --- | --- |
| `restrict` on every buffer | worth nothing, byte-identical |
| Telling LLVM more than GCC | the channel is not wider; the optimiser is better and that is not ours to claim |
| PGO | buys nothing -- the binaries are too small to have a cold half |
| Emitting C++ instead of C | changes nothing |
| Signed scalars narrowed | BUILT, MEASURED, REVERTED -- slower |
| Narrower and unsigned scalars | both slower |
| uops.info on the exam's mix | no better instruction combination exists |
| Slot sharing across templates | costs instructions; measured on the wrong axis the first time |
| Unrolling `_scan` to four vectors | 8% SLOWER -- the gate opens on the search bound, the cost is the distance to the match |
| Scoping spliced SCALARS (not arrays) | 1,662 blocks against 98, byte-identical binary |
| Storage as the DEFAULT rather than `in stack` | 81 to 1 against |
| A contradiction test for dead code | marked LIVE code dead, killed the exam's line assembly, reverted |
| Extent-as-access as a REFUSAL | false positive on the TLS client (`tlen` ~700 read as 32,746) |
| `--conversion-check` in the CBMC suite | 52 programs flagged, none real -- mereo converts on purpose |
| A backward slice to prune assumes | prunes nothing: from 32 checks it reaches every name |
| A byte-loop or word+tail `equals` | 6.8% and 3.1% slower; only the overlapping tail reaches parity |
| Overflow checks (`-fsanitize=signed-integer-overflow`) | **+23.8%** on loglyze, 120 traps GCC could not prove away. Release Rust wraps too. |
| `#pragma GCC unroll N` chosen by the verifier | cannot attach: the pragma needs `for`/`while`, mereo emits GOTO loops |
| `-funroll-loops` globally | -4.8% instructions on loglyze, clock CANNOT see it (two orderings disagree), `.text` 6926 -> 18421 |
| `#pragma GCC ivdep` / `restrict` to vectorise `copy` | the goto loop is ALREADY vectorised; `restrict` makes GCC call `memcpy`, which freestanding cannot link -- that is what `-fno-tree-loop-distribute-patterns` is for |
| `__builtin_assume_aligned` at uses | one instruction on an 8-byte load, nothing on a byte loop, and mereo's accesses are byte-wise |

### Two that came out POSITIVE, recorded because the mechanism is easy to lose

**A kernel promise is worth a great deal where a branch can use it, and a small
loss where none can.** With the promise 29,000,043 instructions; without it
103,000,036, and 3.8x on the clock. But loglyze carried six that no branch used
and paid 10,995 instructions for them. `prune_assumes` now emits one only where
an emitted branch mentions the value it bounds, in the matching direction.
Gated in `test.sh`'s build section.

**A check that is proved away costs nothing -- and so does one GCC can prove
itself.** `span.at` with a known length emits no check; with a length off the
wire it keeps one. But where GCC can see the bound, dropping the check changes
nothing: 19,968,797 instructions either way, the landing pad and its message
gone from both binaries. The saving is real only where the fact is absent from
the C.

What those two share: the analysis pays, and is UNDER-EXPLOITED.
`drop_proved_checks` fires on 4 of 120 candidates in 1 of 42 programs, because
`span.at` is the only checked accessor in `core.mereo`. A newly deployed check
costs about nothing -- ruling the short case out of `starts`/`ends` cost one
instruction and zero bytes. The action that points at is MORE checked
accessors, not fewer.

---

## `_scan` is the last C helper, and it stays

`HELPER_C` holds one entry. `_scan` is a 32-byte AVX2 compare and mereo has no
vector types, so writing it in mereo is a LANGUAGE question, not an analysis
one. `_same` left on 2026-08-25 at parity: byte-identical output on a 169 KB
and an 84 MB log, median clock ratio 1.003, +1.36% instructions.
