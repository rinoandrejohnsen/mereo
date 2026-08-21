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

## The numbers

80.5 MB, one million lines, interleaved A/B over 21 runs each so drift hits
both:

| | min | median | sd |
| --- | ---: | ---: | ---: |
| C, hand-optimised | 53.7 ms | **54.7 ms** | 0.62 |
| mereo | 54.5 ms | **55.4 ms** | 0.82 |

**Ratio 1.012.** mereo is one and a bit percent behind, which is inside the
spread of the two measurements. On identical output: the two programs agree byte
for byte on the million-line log and on all 800 adversarial inputs.

| | C | mereo |
| --- | ---: | ---: |
| source | 214 lines | 357 lines |
| binary, same linker script | 4592 B | 6512 B |
| instructions in `.text` | 988 | 1402 |

mereo is 40% more instructions at the same speed, because the extra sits in cold
paths — the report, the error blocks, the release tower — and never runs in the
loop that reads 80 MB.

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
places is a literal in two places. A `likely` road cannot hold a template call.
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
