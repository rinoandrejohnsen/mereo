Before calling anything a release, one program written twice: once in
hand-optimised freestanding C, once in mereo. Same input, same output, byte for
byte. Then measured.

The barrier this project sets itself is **parity with a hand-written, optimised,
Linux-correct C program**. This is the test of it.

## The program

`loglyze` reads NCSA Common Log Format on stdin and writes a summary on stdout:
total requests, total bytes, malformed lines, a count per status band, and the
ten most frequent paths. `exam/SPEC.md` states it exactly, down to how ties
break and what counts as malformed.

```
127.0.0.1 - frank [10/Oct/2000:13:55:36 -0700] "GET /apache_pb.gif HTTP/1.0" 200 2326
```

It was chosen because it is not a toy. A 64 KiB read buffer that lines straddle;
a 1 MiB arena; an open-addressed table of 8192 slots holding at most 4096 paths;
and a parser walking bytes that arrive from outside. Every index is derived from
input, which is the case that matters. Nothing is allocated in either version.

## The C

214 lines, freestanding — no libc, raw syscalls, the same flags the mereo corpus
builds with. Optimised by hand in three steps, each measured on 80.5 MB:

| | median | |
| --- | ---: | --- |
| byte-at-a-time scan, every line copied to a line buffer | 91.9 ms | |
| ...parse in place when the line does not straddle a read | 85.5 ms | the input stops being touched twice |
| ...word-at-a-time scanning for newline, quote and space | 54.7 ms | the only loops that see every byte |

The word-at-a-time step is the classic one: XOR a 64-bit word against a
broadcast byte, and the byte that matched becomes zero, which the
has-a-zero-byte test finds without a branch per byte.

### Verifying it

SPARK, Frama-C and CBMC were not available on this machine, so the C was held to
what was:

| | |
| --- | --- |
| `gcc -fanalyzer`, with `-Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Warray-bounds=2 -Wstringop-overflow=4 -Wshadow -Wcast-qual` | 0 warnings |
| clang static analyzer | 0 warnings |
| ASAN + UBSAN over 300 adversarial inputs | 0 reports |
| valgrind | clean |
| 800 adversarial inputs against an independent Python oracle | 0 mismatches |

The last row is the one that carries the weight. The oracle is written the
obvious slow way in `exam/tools/reference.py`; the fuzzer in
`exam/tools/fuzz.py` produces the shapes a log never has and a hostile peer
might — no quotes, one quote, a 300-byte path, a 9000-byte line, a status with a
letter in it, and 200 bytes of arbitrage.

## The mereo

357 lines, and structured differently on purpose. The first draft used templates
and hit an 18-port call, because mereo has no globals and a template sees only
what it is given. The second draft threw that away: **a template is for reuse,
and there is none here** — each phase runs once, in order — so the structuring
device is the named scope, which sees what encloses it.

The table is five parallel runs of bytes rather than one run of records, because
mereo has no array of layouts. An index is scaled by hand:

```ada
  walk goes
    four is hidx * 4
    two is hidx * 2
    cnt is [t_count + four : 4]
    leave walk when cnt == 0
    ...
```

That costs a multiply per probe and buys stating each run's size exactly.

It got the same two optimisations as the C, and one the C did not need.

## The C++

Added afterwards, to ask a different question: the two programs above are both
hand-rolled to the byte, so what happens if a language is allowed to bring its
library? `exam/cpp/loglyze.cpp` is the same program written to play to C++'s
strengths — **hosted**, so it can link one, and reaching for the standard
library wherever the library is plausibly better than a loop:

| | |
| --- | --- |
| `memchr` | glibc dispatches to an AVX2 implementation: 32 bytes a step against the SWAR twin's 8 |
| `from_chars` / `to_chars` | the fastest integer parse and format in the standard, and the first validates |
| `string_view` | the whole parse is subranges of one buffer, at no run-time cost |
| `partial_sort` | ten winners out of 8192 in one pass, against the C twin's ten linear passes |

It does not allocate. `unordered_map` would be the idiomatic choice for the path
table and is the wrong one here, because the spec fixes the storage — so the
table is open-addressed by hand, exactly as in the C. That is itself a finding
about where the library stops helping.

It agrees with both other programs byte for byte, on the million-line log and on
all 800 adversarial seeds. **And it is 10% faster than either.**

### Where the 10% actually comes from

Not from C++. Taking the C twin and changing **one function** — `find_byte`
becomes a call to `memchr`, and nothing else is touched:

| against mereo, 21 runs | median | min |
| --- | ---: | ---: |
| the C twin as written, word-at-a-time | 0.998 | 1.001 |
| the same C, `memchr` and nothing else | 0.903 | 0.912 |
| the C++ | 0.905 | 0.904 |

The C with `memchr` and the C++ are the same speed. Every abstraction in the C++
— the views, the charconv, the partial sort, the constexpr table — is worth
nothing measurable, which is the same result the rest of this project keeps
getting. What is worth 10% is that glibc scans 32 bytes at a time and both other
programs scan 8.

The scan is reachable without a libc, too. A hand-written AVX2 loop compiled
freestanding into the C twin gets **0.940** — 6% of the 10%, with glibc's tuned
version keeping the rest. So this is not a hosted-versus-freestanding gap and
not a language gap. It is a scan-width gap, and mereo generates its own scan.

## The numbers

80.5 MB, one million lines, interleaved A/B over 21 runs each so drift hits
both:

| | min | median | sd |
| --- | ---: | ---: | ---: |
| C, hand-optimised | 53.6 ms | **54.7 ms** | 0.86 |
| mereo | 54.3 ms | **54.8 ms** | 0.96 |

**Ratio 1.000.** The medians are the same. A clock has variance in it, though,
so the same claim is made again below with none: counted exactly, **mereo
executes 10.9% fewer instructions than the C twin** on this input, and the same
inlining that makes its binary 30% larger is why. This started at 1.012, and what
closed it was not the program but the compiler: `read` cannot return more than
the capacity it was given — that is the kernel's design, not a hope — so mereo
states it to GCC rather than testing it. The branch could never have been
taken. On identical output: the two programs agree byte
for byte on the million-line log and on all 800 adversarial inputs.

| | C | mereo |
| --- | ---: | ---: |
| source | 214 lines | 357 lines |
| binary, same linker script | 4656 B | 5920 B |
| `.text` | 3798 B | 5014 B |
| instructions in `.text` | 988 | 1250 |

mereo is 27% more instructions at the same speed. **The reason given here for
years was wrong**, and is corrected: it said the extra sat in cold paths — the
error blocks, the release tower — and never ran. `tests/size` attributes every
byte, by building with `-g` and reading each instruction's generated-C line:

| | |
| --- | ---: |
| mereo `.text` | 5014 B |
| ...the spine, which runs | **4958 B** |
| ...the cold tower | 56 B |
| ...unattributed | 0 B |

The tower is **1.1%**. GCC deletes most of it — six of the program's
thirty-one error messages survive into the binary, the rest being unreachable
once the checks around them are proved — so there is very little cold code left
to blame. The extra 1160 bytes are in the spine, against the C twin's whole
3798, and the honest statement is that **mereo's running code is about 30%
larger than the C twin's at the same speed**, which the timing above already
implies: more bytes, the same work, no slower.

The old claim went unchecked long enough that the figures in this table drifted
by 150 instructions without anyone noticing, which is why the attribution is now
a suite rather than a sentence.

### The instructions actually executed

Wall-clock says parity and the binary says 30% larger, which reads like a
contradiction until the third measurement. `valgrind --tool=callgrind` counts
every instruction a run executes, exactly and deterministically -- three runs of
the same binary on the same input give the same number to the digit -- and it
works on these freestanding no-libc binaries unchanged.

| 84 MB, one million lines | instructions executed |
| --- | ---: |
| C, hand-optimised | 798,334,157 |
| mereo | **711,505,137** |

**mereo executes 10.9% fewer instructions than the C twin.** The ratio is stable
as the input grows -- 0.854 at 200 KB, 0.883 at 2 MB, 0.889 at 8 MB, 0.891 at
84 MB -- converging as start-up washes out.

So the three numbers fit together rather than fighting:

| | |
| --- | --- |
| mereo's binary is **30% larger** | every library helper is `always_inline`, so one used nine times is nine copies |
| mereo executes **11% fewer instructions** | ...and inlining is also why: no call, no frame, no argument shuffling, and GCC specialises each copy against what it knows there |
| the wall clock is **the same** | fewer instructions at a lower IPC -- more code in flight against the same caches |

That is the trade stated plainly. mereo spends bytes to save instructions, and
the two cancel on this workload. It is not a coincidence that the size and the
instruction count move in opposite directions: **they have the same cause.**

### Why the lower IPC, since it sounds like a fault

Pinned to one core so the counters are whole:

| | cycles | instructions | IPC |
| --- | ---: | ---: | ---: |
| C | 228,728,737 | 798,334,309 | **3.490** |
| mereo | 231,640,663 | 711,505,256 | **3.072** |

The first thing to say is that a lower IPC here is arithmetic rather than a
fault: the same cycles divided by 11% fewer instructions is a smaller number by
construction. mereo is not stalling more in any way that costs time — the wall
clock is the same.

The second is *why* the cycles did not fall along with the instructions, and the
counters answer it. mereo is **front-end bound**: the pipeline is waiting for
instructions to be fetched, not for work to finish.

| | retiring | front-end | back-end | bad speculation |
| --- | ---: | ---: | ---: | ---: |
| C | 48.6% | 24.5% | 4.7% | 22.2% |
| mereo | 40.9% | **35.8%** | 3.5% | 19.8% |

mereo is better on the other three and loses on that one. Its front end fails to
deliver 507 million uops against C's 344 million. The obvious causes are not it:
**L1 instruction misses are zero for both** — 5014 bytes and 3798 both sit in a
32 KB cache — and both run 99.7% out of the uop cache, so it is not decode
bandwidth either.

What it is:

| | branches | of instructions |
| --- | ---: | ---: |
| C | 152,300,541 | 19.1% |
| mereo | 157,470,696 | **22.1%** |

**mereo runs 87 million fewer instructions and 5 million more branches** — and
the second number is the smaller story of the two. Branches are up **3.4%**;
instructions are down **10.9%**. Had mereo executed C's instruction count with
its own branches, density would read 19.7% against C's 19.1%, which is nothing.
**The denominator moved, not the numerator.**

So mereo does not branch meaningfully more. It does less straight-line work
between the same branches — inlining removes the call, the frame and the
argument shuffling, and leaves control flow exactly where it was. The front end
fetches one contiguous run per cycle, so it redirects just as often as C's and
has less to show for each one.

The two profiles agree on this. Sampling branches by region gives the same shape
for both: about half in the byte scan, a tenth in the hash. The loops are the
same loops — mereo's scan and C's `find_byte` are the same SWAR word-at-a-time
test, branch for branch.

### What the executed instructions actually are

Counted exactly, by kind, on the same input — `callgrind --dump-instr=yes`, each
address mapped to its opcode:

| | mereo | C | |
| --- | ---: | ---: | ---: |
| arithmetic | 2,355,402 | 3,251,528 | **−28%** |
| data movement | 5,258,248 | 6,950,955 | **−24%** |
| bitwise / shift | 3,104,274 | 3,174,391 | −2% |
| compare | 3,136,871 | 2,921,593 | +7% |
| control | 4,056,199 | 3,964,658 | +2% |
| total | 17,958,755 | 20,348,221 | −12% |

So mereo is not doing worse arithmetic to get its smaller count — it does
**28% less of it**, and 24% less shuffling of values between registers and the
stack. The one column where it does more is comparing, and that has a cause
worth naming, because it is the same cause as the other two.

**C's `do_line` is a function, so `return` ends the line.** It uses that eight
times: eight ways for a line to be malformed, each one `malformed++; return;`,
and nothing after them runs. mereo has no functions, so `leave parse` leaves the
*scope* and the code after it still runs — which means it has to be told whether
the parse succeeded:

```ada
  ready is 0                      -- and then, further down
  leave slow when ready != 0
  leave finish when ready == 0
  leave digits_loop when bad == 0
```

`ready`, `over` and `bad` are the flags that stand in for a return, and testing
them is where the extra comparing goes. Five such tests per line against C's
zero, on a program whose whole per-line path is about sixteen tests, is the
7%.

The shape of the saving names its cause. Straight-line work — arithmetic and
data movement — falls by a quarter, while control flow and comparison stay
flat. That is the signature of removing calls: the address arithmetic, the frame
adjustment and the argument shuffling go, and every branch and test the program
actually asked for stays exactly where it was.

**All of it is one decision.** mereo has no functions, and that single fact
produces every number on this page: the binary is 30% larger because each helper
is copied per use; the instruction count is 11% lower because no call, frame or
argument shuffling remains; and the comparing is 7% higher because a scope's
early exit needs a flag where a function's `return` needs nothing. The trade is
not three trades. It is one, seen from three sides.

So the shape of the trade is sharper than "bigger but the same speed". mereo
does the same work in fewer, branchier instructions, and pays back in fetch what
it saved in execution.

A note on tooling, since it cost an hour. `perf stat -e instructions:u` is the
obvious instrument and is wrong here: this is a hybrid CPU, the process migrates
between P-cores and E-cores, and each PMU counts only while the process is on
its own core type. Reading `cpu_core` alone said mereo executed 8% MORE, which
is the opposite of the truth. Callgrind has no such split, needs no privileges,
and is exact.

### Where the 1160 bytes are

**mereo has no functions.** Everything lowers into one flat `_start`, and every
library helper is `always_inline`, so a helper used nine times is nine copies.
GCC keeps three real functions in the C twin and one in mereo:

| | C | mereo |
| --- | --- | --- |
| functions in the binary | `_start`, `do_line`, `emit_u64` | `_start` |
| the number formatter | `emit_u64`, **one copy**, called 5 times — 192 B | `_decimal`, **inlined at all 9 call sites** — 846 B |

That one helper is 654 of the 1160. `_write_value` and `_write` add most of the
rest the same way. The trade is deliberate and it is the same trade that buys
the speed: no calls means no call overhead, no frames, and no spills at a
boundary, which is why the timing above is at parity while the size is not.

Two things this is *not*. It is not the error paths, which are 1.1%. And it is
not signedness: mereo's `_decimal` takes a signed value and handles a minus
sign where C's `emit_u64` does not, but compiled side by side that is 288 bytes
against 240 — 48 per copy, not 654. The multiplier is the copies.

## What the exam found

Parity is the headline, but the findings are the point of running it.

**A library that was below the bar.** mereo's `find` — its `memchr`, reached by
every `search`, `measure` and `until` in the language — was a byte-at-a-time
loop. Hand-optimised C would never leave it that way. Widening it made
find-heavy code **2.9× faster** (55 ms to 19 ms on a scanning benchmark) for
2848 bytes across the whole corpus. The exam is what surfaced it; no program in
the corpus scanned hard enough to notice.

**mereo needed the same hand-optimising the C did.** The idiomatic first version
ran at 99 ms against a C of the same shape at 91.9 ms — 1.06×, near parity for
equivalent code. It did not reach 55 ms by being higher-level. It reached it by
being told the same three things the C was told, in the same order. That is the
honest shape of the result: **the language does not close the gap for you; it
declines to open one.**

**The access analysis has visible limits in real code.** Compiling the mereo
version reports 14 accesses it cannot prove in range — the 8-byte load in the
word-at-a-time scan, the parser's indices into a line whose address is computed,
and the table probes. All are safe. None is provable by the analysis as it
stands, and the report says which is which:

```
line 120: `[rbuf + j : 8]` not proved in range -- a bound is in scope but
          could not be resolved to a number
line   5: `[rbuf + i + copy_1_i : 1]` not proved in range -- the index comes
          from input and nothing bounds it here -- this wants a run-time guard
```

That is the analysis behaving as designed — reporting rather than guessing — and
it is also a list of work.

**Three things about writing mereo that only writing 357 lines of it shows.**
There are no top-level constants and no top-level buffers, so a size used in two
places is a literal in two places. A `likely` road could not hold a template call (roads are gone now).
And `compare` answers **1 for equal**, which reads backwards next to C's
`memcmp`
and cost the first hour of debugging — the table never found an entry and every
path came out counted once.

## What it does not show

One program is one program. It is a byte pipeline over a fixed table, which is
the shape mereo is built for; nothing here says anything about the shapes it is
not built for, and [Limitations](Limitations) lists those.

The verification is also not proof. It is two analysers, two sanitizers,
valgrind, and 800 adversarial inputs against an independent implementation —
which is enough to say the two programs agree and neither reaches out of bounds
on anything tried, and not enough to say more than that.

Everything here is in `exam/`: both programs, the oracle, the fuzzer, the
generator and the benchmark harness.
