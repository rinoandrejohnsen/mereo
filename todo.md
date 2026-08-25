# todo

Rewritten 2026-08-25. Everything closed was cut; the previous 3,524 lines are in
git (121 commits touch this file) if a detail is ever wanted. What survives is
what is still open, plus a one-line record of every measurement that came out
NEGATIVE -- those are not history, they are the reason not to try it again.

The access analysis was removed on 2026-08-25; see below for the numbers that
decided it. `tests/validation` went with it.

---

## Open, actionable

### Share the error-record formatter instead of splicing it

`_write_value` is spliced into every error block. Making it a real
`static __attribute__((noinline, cold))` function measured **-16% across the
corpus** (`abc` 1296 -> 1120, `https` 68696 -> 55096). Cold-path only, so the
clock should not notice -- which is exactly why it needs measuring on the clock
before it lands, not on the byte count.

### An array view: a span that counts elements

Open, unblocked, demonstrated end to end, not written into `core.mereo` yet.
`span` counts bytes; an array view counts ELEMENTS, which is a span plus a
stride. Leaning: ship the RECORD form, skip the scalar one.

### Strip section headers from the shipped binary?

Open, leaning NO, and measured: `objcopy --strip-section-headers` saves 287
bytes per binary, 22,157 over 77. It costs `objdump -d`, which then prints
nothing.

### The language server is gone, and nothing replaced it

Deliberate. It served one idea -- bold at a name's declaration, bold-italic at
every later use -- which a stateless highlighter cannot do. Whether that is
worth an LSP again is the open question.

---

## The access analysis was removed on 2026-08-25

It reached 98.4% of 3056 accesses and made no difference to the generated code,
which was the claim it was built on. GCC's SRA scalarises an instance's fields
into SSA and EVRP ranges them from there -- 30 of one program's 37 error blocks go
that way -- and the 4 checks mereo removed corpus-wide, GCC removed anyway:
same `.text`, same instruction count, landing pads gone from both binaries.

The full lever search came back empty too: the unroll pragma cannot attach to a
goto loop, `restrict` makes GCC emit a `memcpy` freestanding cannot link, the
copy loop is already vectorised, `assume_aligned` is one instruction on an
eight-byte load, and overflow checks cost 23.8%.

**What stays is the one thing that pays**: a syscall's out-port contract, said
to GCC as an assumption, emitted only where a branch can use it. Worth
29,000,043 instructions against 103,000,036 where one does, and pruned to zero
to zero where none does. Gated in `test.sh`'s build section.

What it was good for while it lasted was finding bugs, and those are fixed and
gated on behaviour: `json.text` answering an offset outside its document,
`text.search` matching a needle assembled from outside its region,
`starts`/`ends` reading before checking, three buffers sized for the expected
value rather than `format`'s worst case.

Reopening it means reopening the same question, so the number to beat is
recorded: **4 checks, in 1 of 42 programs, all of which GCC removed anyway.**

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
| uops.info on the measured instruction mix | no better combination exists |
| Slot sharing across templates | costs instructions; measured on the wrong axis the first time |
| Unrolling `_scan` to four vectors | 8% SLOWER -- the gate opens on the search bound, the cost is the distance to the match |
| Scoping spliced SCALARS (not arrays) | 1,662 blocks against 98, byte-identical binary |
| Storage as the DEFAULT rather than `in stack` | 81 to 1 against |
| A contradiction test for dead code | marked LIVE code dead, killed a working line assembler, reverted |
| Extent-as-access as a REFUSAL | false positive on the TLS client (`tlen` ~700 read as 32,746) |
| A backward slice to prune assumes | prunes nothing: from 32 checks it reaches every name |
| A byte-loop or word+tail `equals` | 6.8% and 3.1% slower; only the overlapping tail reaches parity |
| Overflow checks (`-fsanitize=signed-integer-overflow`) | **+23.8%** measured, 120 traps GCC could not prove away. Release Rust wraps too. |
| `#pragma GCC unroll N` chosen by the verifier | cannot attach: the pragma needs `for`/`while`, mereo emits GOTO loops |
| `-funroll-loops` globally | -4.8% instructions, clock CANNOT see it (two orderings disagree), `.text` 6926 -> 18421 |
| `#pragma GCC ivdep` / `restrict` to vectorise `copy` | the goto loop is ALREADY vectorised; `restrict` makes GCC call `memcpy`, which freestanding cannot link -- that is what `-fno-tree-loop-distribute-patterns` is for |
| `__builtin_assume_aligned` at uses | one instruction on an 8-byte load, nothing on a byte loop, and mereo's accesses are byte-wise |

### Two that came out POSITIVE, recorded because the mechanism is easy to lose

**A kernel promise is worth a great deal where a branch can use it, and a small
loss where none can.** With the promise 29,000,043 instructions; without it
103,000,036, and 3.8x on the clock. But one program carried six that no branch used
and paid 10,995 instructions for them. `prune_assumes` now emits one only where
an emitted branch mentions the value it bounds, in the matching direction.
Gated in `test.sh`'s build section.

**A check GCC can prove away costs nothing.** `span.at` carries
`ensure offset < length`, and mereoc emits it in both cases now -- with a known
length and with one off the wire. Where GCC can see the bound it deletes the
branch, the landing pad and the message string together: 19,968,797
instructions either way. Where it cannot, the check stays and is doing its job.

mereo used to delete some of them itself, and that is what `drop_proved_checks`
was. It fired on 4 of 120 candidates in 1 of 42 programs, GCC removed the same
four, and it went with the analysis on 2026-08-25.

---

## `_scan` is the last C helper, and it stays

`HELPER_C` holds one entry. `_scan` is a 32-byte AVX2 compare and mereo has no
vector types, so writing it in mereo is a LANGUAGE question, not an analysis
one. `_same` left on 2026-08-25 at parity: byte-identical output on a 169 KB
and an 84 MB log, median clock ratio 1.003, +1.36% instructions.
