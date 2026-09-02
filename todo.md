# todo

Rewritten 2026-08-25. Everything closed was cut; the previous 3,524 lines are in
git (121 commits touch this file) if a detail is ever wanted. What survives is
what is still open, plus a one-line record of every measurement that came out
NEGATIVE -- those are not history, they are the reason not to try it again.

The access analysis was removed on 2026-08-25; see below for the numbers that
decided it. `tests/validation` went with it.

---

## Open, actionable

### `embedded` embeds ONE file; Go's `embed.FS` embeds a TREE

`NAME is "path" embedded` shipped, and it is the equivalent of Go's
`//go:embed file` with a `[]byte` -- one file, one backing, `NAME.size` for the
length. What it is NOT yet is the equivalent of `embed.FS`, and that is the
form people reach for: a whole directory embedded under one name, looked up BY
PATH at run time, with the directory listable.

What that needs, in this language's terms:

  * **a pattern at compile time**, so one declaration takes many files --
    `assets is "www/*" embedded`, or a directory name meaning everything under
    it. The compiler already resolves the path against the declaring file, so
    only the globbing is new.
  * **a table the compiler emits beside the blob**: the files concatenated into
    one `constant` backing, plus a record per file of (path offset, path
    length, data offset, data length). `array` already expresses exactly that
    table, and the record is a layout view -- no new machinery.
  * **a lookup**, which is `text.equals` over the path column. Since the
    compiler owns the table it can emit it SORTED by path, making the lookup a
    binary search rather than a scan, and the caller supplies nothing.
  * **a listing**, if it is wanted at all: `array` already counts records, so
    walking them in order is the directory walk. Worth deciding whether that is
    needed or whether lookup alone covers the demand -- Go ships both because
    `fs.FS` demands it, which is not a reason here.

Decisions to weigh before starting, none of them settled:

  * a MISS has to be sayable. Every other reader in this project answers with a
    `result` out-port, so `-1 not found` fits, and nothing needs to fault.
  * paths are the SOURCE paths, forward slashes, as Go's are -- but `..`
    escaping the declaring file's directory should be refused at compile time
    rather than embedded, which is the analogue of Go refusing to embed outside
    its module.
  * the single-file form must keep working unchanged. `NAME.size` on a tree
    would have to mean the total, or be refused; refusing it is probably
    honest.

Not needed for the SQLite reader, which embeds one database file and is served
by what shipped. This is for the case that motivated `embed.FS`: a program
carrying a directory of assets.

### Share the error-record formatter instead of splicing it

`_write_value` is spliced into every error block. Making it a real
`static __attribute__((noinline, cold))` function measured **-16% across the
corpus** (`abc` 1296 -> 1120, `https` 68696 -> 55096). Cold-path only, so the
clock should not notice -- which is exactly why it needs measuring on the clock
before it lands, not on the byte count.

### An array view: a span that counts elements -- SHIPPED

`array` is in `core.mereo`: data, count, limit, stride, with `at` and `add`,
both bounds-checked the way `span.at` is. The record form only, as the leaning
said.

**What was actually missing was smaller than this entry assumed.** The
capability was already there and had been all along -- an inline backing takes
a RUNTIME address, so `[slots + i * 32 : 32] as record` compiles and runs
today; only a NAMED backing needs a constant offset. What was missing was the
stride written once instead of twice as a bare number, a count, and a check.

Two one-line compiler gaps closed on the way, both the same disagreement:
`const_offset` had always answered `record.size` inside a lens offset by
reading `psize` off the definition, while `size_of_c` could not, so the same
words were a number in one place and "not a buffer, view, or literal" in the
other. A `VIEW_SIZES` table fills where the layouts are elaborated, and the
inline backing's WIDTH now takes `X.size` too -- which is what lets the stride
appear once. Purely additive, and measured as such: **89 binaries
byte-identical** across the compiler change, and 89 again after `array` was
added to `core.mereo`, since an unused definition emits no code.

The seam that remains is that `at` and `add` hand back an ADDRESS and the
caller lays the record over it, naming the layout at both ends. A method cannot
hand back a view, so that is the language's shape and not a gap in this.

### The HTTP parser against a C reference: 1.8x, then 0.91x

Measured 2026-09-02 against the well-known C request parser with its SSE4.2
path OFF (`__SSE4_2__` undefined on baseline x86-64; verified as zero SSE4.2
string instructions in the binary). Both built freestanding with build.sh's own
flags, no libc on either side, same 287-byte 6-header request, and both
harnesses exit with the SAME checksum, so they agree on the parse before
anything is timed. Startup cancels: every figure is
(metric at N=200,000 - metric at N=1) / 199,999.

|  | cycles | instructions | IPC | branch misses |
| --- | --- | --- | --- | --- |
| the C reference, scalar | 503 | 2500 | 4.97 | 0.685 |
| `programs/http/parse.mereo` | 836 | 3581 | 4.28 | 0.029 |
| ...with the token check ablated | 752 | 2581 | 3.43 | 0.380 |

**A table on the TOKEN check bought almost nothing; a table on EVERY scan
halved the cycles.** The first attempt put a 256-byte lookup behind `token`,
which covers method names and field names -- about 78 bytes of a 287-byte
request. It removed 747 instructions and about 3% of cycles, and it made branch
prediction WORSE. That looked like proof that a comparison chain is free on a
wide core, and the conclusion was wrong: the table was on the cold loop.

The hot loop is the field VALUE scan, and `perf annotate` on the emitted code
showed it asking four class questions with four branches per byte:

    movzbl (%rcx,%r10,1),%eax    ; the byte
    cmp $0xd  / je               ; CR?
    cmp $0x7f / je               ; DEL?
    cmp $0x1f / jg               ; control?
    cmp $0x9  / jne              ; HTAB?
    add $1 / cmp / jne           ; step and bound

Nine instructions and five branches per byte, over the ~124 value bytes and 46
target bytes that the token table never touched. One table with THREE class
bits -- token, value-legal, target-legal -- answers all of it in one load, and
because CR scores zero in every class the loop stops on it without testing for
it: whether the value ended or the byte was illegal is settled once after the
loop instead of twice per byte inside it.

Pinned to one core, seven interleaved rounds, median (min) cycles per parse:

| | cycles | instructions | IPC | branch misses |
| --- | --- | --- | --- | --- |
| the C reference, scalar | 467 (460) | 2500 | 3.33 | 0.726 |
| comparison chains | 851 (823) | 3581 | 3.32 | 0.035 |
| table on `token` only | 831 (817) | 2834 | 3.15 | 0.450 |
| class table on every scan | 426 (418) | 2086 | 4.48 | 0.009 |

So the parser went from **1.82x the C reference to 0.91x**, and all 5,813
differential cases still agree. Two honest qualifications. The last row changes
the ALGORITHM, not the language: the same three-bit table would speed the C
side up too, so this does not show mereo beating C -- it shows that the 1.8x
was mine, in the parser's design, and not the code generator's. And the cycle
spread across rounds reached 63% on the noisiest binary, which is why the table
carries medians and minima and why the instruction counts, which do not vary at
all, tell the same story on their own.

**Then the same fix was given to C, which is the only way to know what the
LANGUAGE costs.** A C twin of the mereo parser -- same rules, same three-bit
table, same index-based loops, same -1/-2/consumed contract -- put through the
same differential harness and agreeing on all 5,813 cases, so it is provably
equivalent and not merely intended to be. Pinned to one core, 15 interleaved
rounds, minimum cycles per parse (p25 within 2% of it, so these are clean):

| | cycles | instructions | IPC |
| --- | --- | --- | --- |
| the C reference, scalar, as shipped | 455 | 2500 | 5.49 |
| mereo, comparison chains | 794 | 3581 | 4.51 |
| C twin, class table | 441 | 2322 | 5.27 |
| mereo, class table | 418 | 2086 | 4.99 |

**The same algorithmic change is worth 47% in mereo and 3% in C.** That
asymmetry is the finding, and it is about what mereo EMITS, not about the
algorithm: the chains were written in the branchless comparison-as-value idiom
(`bad is (c < 32) & (c != 9)`), which materialises a 0/1 with setcc and then
tests it, where C's `if (c < 32 && c != 9)` just branches. Comparison-as-value
is not free when the result is only ever used to branch -- it buys the
prediction (0.035 branch misses against 0.726) by paying instructions for a
value nothing keeps. Worth knowing anywhere a guard is written that way.

With the algorithm held constant the two languages land at **mereo 0.90x the
instructions and 0.95x the cycles** of the hand-written C twin, which is the
parity the project claims, measured on something neither trivial nor rigged.

One hypothesis was raised and REFUTED on the way, recorded so it is not raised
again: that mereo's advantage came from out-ports being values where C's
out-parameters are pointer stores. A third twin keeping everything in locals
and writing the out-parameters once at the end came out WORSE, 2,574
instructions against 2,322, because the write-back duplicates at every return.
GCC was already handling the out-parameters fine. The 10% is not explained.

**The IPC reading was a symptom, not the cause.** An earlier ablation showed
the parser needing 752 cycles against 503 at near-equal instruction counts and
concluded the emitted loop was inherently serial. It was not: five branches per
byte were what held IPC at 3.3, and removing them took IPC to 4.48. Measure the
loop before blaming the code generator.

**What mereo wins:** 0.029 branch misses per parse against 0.685, twenty-three
times fewer, which is the comparison-as-value style predicting where the
reference branches.

One thing found on the way, and it is why the table was not simply tried:
`constant bytes` is refused inside a GROUP and at a library's top level, and
accepted only in a program body. So a lookup table cannot live beside the
template that would use it -- it would have to be declared by the caller and
passed in as a port. Worth fixing if a table is ever wanted in a library.

### GCC's mereo builds stall on FETCH; Clang's do not -- and that decides which wins

Same three binaries, same workload, same sweep, Clang 22.1.8. Cycles per
iteration; all 15 binaries checksum-agree first.

| | default | loops=1 | =16 | =32 | =64 | instructions |
| --- | --- | --- | --- | --- | --- | --- |
| the C reference | 781 | 763 | 794 | 766 | 742 | 4458 |
| the C twin | 1006 | 981 | 1011 | 994 | 994 | 5043 |
| **mereo** | **739** | 796 | 752 | **664** | **662** | **3531** |

**Under Clang, mereo is the fastest of the three at every alignment point**, and
its DEFAULT (739) is already better than anything GCC gave it without the flag
(886-903). Best against best it is 662 against the reference's 742, and against
its own GCC best of 714. It is also far less layout-sensitive here: a 20% spread
against 35% under GCC, with the default sitting near the optimum instead of at
the bad end.

So on THAT program the fetch-latency problem is largely a GCC layout problem,
not a property of what mereo emits.

**It does not hold on a bigger one.** The end-to-end handler below -- the same
HTTP parser plus the JSON reader, one program -- goes the other way, and by
more:

| mereo, instructions | GCC | Clang | |
| --- | --- | --- | --- |
| HTTP head only | 3583 | 3531 | Clang 0.99x |
| HTTP + JSON handler | 4794 | 6215 | Clang **1.30x** |

Instruction counts, which do not move with layout, so this is code generation
and not noise. On the same handler Clang HELPS the C side (6601 -> 5908), so it
is not that Clang is worse in general -- it is worse on mereo's ONE BIG
FUNCTION as that function grows, which is what splicing everything into
`_start` produces. Two points is a trend and not a law, but the direction is
clear enough that "use Clang for mereo" would have been the wrong lesson to
draw from the smaller program alone.

Two cautions before anyone acts on this. The C TWIN does badly under Clang
(1006 against 743 under GCC), so Clang is compiling that particular C poorly
and the reference is the honest baseline to beat -- which mereo still does.
And switching compilers is not a flag: build.sh, the freestanding link,
`externally_visible` (which Clang ignores with a warning), and everything
mereocheck asserts about the emitted assembly are all GCC-shaped today. This is
a measurement, not a migration.

Note this does NOT contradict the closed entry "Telling LLVM more than GCC",
which was about the analysis channel being no wider. This is about code
generation for the C that is already emitted.

### The alignment effect is FETCH LATENCY, and the flag does not generalise

Two results that settle the entry below, and they point opposite ways.

**The mechanism, from the topdown counters** -- measured, after three guesses
(spilling, fetch-line straddling, iteration estimates) had failed:

| mereo, request+response | cycles | fetch-latency | retiring |
| --- | --- | --- | --- |
| `-O2` default (loops=16) | 903 | 610 | 3300 |
| `-falign-loops=32` | 718 | 386 | 3308 |

The whole 185-cycle difference is **front-end fetch latency, -223 (-37%)**.
Retiring does not move (+8, 0%), back-end bound and bad speculation are zero.
So the code is not executing differently -- it is being FETCHED differently,
which is what the alignment knob was always going to be about, and it is why
the instruction count never moved through any of this.

**But the flag is not a general win.** Across the corpus programs long enough
to measure at all (the rest run under 200,000 cycles and say nothing):

    upper    4,633,338 -> 4,608,431   -0.5%
    wcl      1,255,169 -> 1,251,949   -0.3%
    x25519   2,670,012 -> 2,657,357   -0.5%

Half a percent, three times. So `-falign-loops=32` does NOT belong in build.sh
on this evidence: it is worth 20% to the HTTP parser and nothing to anything
else, which says the parser is unusual -- fourteen small hot loops packed into
one function -- rather than that mereo's code generally wants 32.

**On the drift question this was raised to answer.** There is no evidence here
of mereo drifting from C. On the swept comparison mereo executes the FEWEST
instructions of the three (3,583 against the C twin's 4,100 and the reference's
4,318) and its best layout is within 5% of the reference's best. What is real
is that mereo's parser is more layout-SENSITIVE: 35% spread across layouts
against the C twin's 8%, and it is fetch-bound where they are not. That is the
thing worth watching, and it is invisible to any instruction-count gate.

### mereo's loops want `-falign-loops=32`, and GCC's default does not give it

A proper sweep, after the single-point measurement below was caught being an
artifact: 15 layout points per contender (`-falign-loops` x `-falign-functions`),
min-of-3 per point, pinned, all 45 binaries agreeing on a checksum first.
Request + response in one program, cycles per iteration:

| | min | median | max | spread | instructions |
| --- | --- | --- | --- | --- | --- |
| the C reference, as shipped | 676 | 712 | 792 | 17% | 4318 |
| the C twin, same algorithm | 707 | 756 | 762 | 8% | 4100 |
| mereo | 714 | 899 | 967 | 35% | 3583 |

**mereo's number is not noise -- it tracks one knob.** Against `-falign-loops`
of 1 / 8 / 16 / 32 / 64 it runs 961 / 946 / 890 / **714** / 900, and
`-falign-functions` does nothing at all, which is what a program with one
function should do. The optimum is sharp and it is at 32.

**GCC's own -O2 default puts mereo at the bad end** (~890, its loops=16
behaviour) and the C twin near its best. So at default flags mereo gives up
about 20% on this workload, and asking for the alignment explicitly costs
**+0.3% of .text across 95 programs** -- 313,095 bytes to 314,135.

At each side's own best layout it is 714 for mereo against 676 for the
reference: mereo about 5% behind on cycles while executing 17% fewer
instructions. The "dead heat" claimed before the sweep was mereo's single best
point against C's typical one, which is exactly the error the sweep exists to
prevent.

**The mechanism is NOT identified, and three candidates were tested and
failed:** register spilling (the combined binary has five stack moves against
two, and the same frame size); 32-byte fetch-line straddling (both builds have
nine of fourteen tight loops straddling, and the loops that matter are already
32-aligned in both); and GCC's own iteration estimates, where
`-fdump-tree-profile_estimate` did not show a difference that could be read off
cleanly. So "mereo's goto loops miss a GCC heuristic" is a reasonable reading
of the numbers and is NOT established by them.

**Before adopting the flag** it needs measuring on more than this one program.
Two conclusions have already been drawn this week from a single binary and both
were wrong.

### Loop ALIGNMENT moves these binaries 34%, which is bigger than anything measured here

The entry that used to sit here claimed that splicing a request parser and a
response parser into one program cost 19% of cycles, because mereo has no
functions and both bodies land in one `_start`. **That was wrong**, and the
mistake is worth more than the claim was.

The same source, one compiler flag apart:

| | cycles | instructions | IPC |
| --- | --- | --- | --- |
| `-falign-loops=1` | 954 | 3572 | 3.74 |
| `-O2` default | 888 | 3584 | 4.03 |
| `-falign-loops=64` | 898 | 3586 | 3.99 |
| `-O3` | 727 | 3632 | 5.00 |
| `-falign-loops=32` | 714 | 3583 | 5.02 |

**714 to 954 cycles on layout alone, with the instruction count flat.** The
"sum of the two parsers measured apart" that the whole argument rested on --
757 cycles -- sits in the middle of that range, so the 19% was the distance
between two arbitrary points in it. Two hypotheses had been tested and ruled
out (spilling, and the parsers alternating) and both were correctly ruled out;
the conclusion still did not follow, because the alternative that was never
tested was the one that was true.

With alignment held at 32 for all three, the combined request+response workload
is a dead heat:

| | best cycles | instructions |
| --- | --- | --- |
| the C reference, as shipped | 713 | 4318 |
| the C twin, same algorithm | 743 | 4099 |
| mereo | 713 | 3583 |

**What to take from this, for any future measurement here.** A single `-O2`
build's cycle count is not evidence at this program size: the layout noise is
larger than every effect the last several rounds were chasing. Instruction
counts do not move -- they were stable to ~0.3% across all five builds above --
and were the only trustworthy signal the whole time. Cycle comparisons that
came out inside +-20% should be read as "no difference measured", including
mereo-against-the-C-twin at 0.95x on requests alone. What survives is what is
big or what is stable: the class-table rewrite (a 42% instruction drop, and
1.9x on the clock, far outside this band) and mereo's instruction count, which
is 17% under the C reference on the combined workload.

### The Clang question, answered: it is the fetch stall

The bisection below found no single pass and stopped there. The slot accounting
finishes it. On the HTTP+SQLite handler, with both compilers swept:

| | issue slots | retiring | fetch-latency |
| --- | --- | --- | --- |
| mereo, GCC | 3168 | 71% | 186 |
| mereo, Clang | 2920 | **96%** | **~0** |
| the C twin, Clang | 3166 | 82% | 135 |

Clang emits MORE instructions for mereo in every program measured -- 32% more
on the HTTP+JSON handler, 16% more here -- and still wins here, because GCC's
build loses 186 slots to instruction fetch and Clang's loses none. Which
compiler is faster is therefore not a property of either: it is whether that
stall is bigger than Clang's extra instructions for that particular program.

Measured both ways, each side swept over -O2/-O3 x unroll, at its own best:

    HTTP + JSON handler      gcc  983 / 4674     clang 1647 / 6187   clang 1.68x
    HTTP + SQLite handler    gcc  536 / 2564     clang  491 / 2962   clang 0.92x

**The 1.32x instruction figure recorded below survives a full sweep** -- it was
first measured as clang -O2 against gcc's best, which was the same one-sided
tuning error caught elsewhere in this file, so it was re-run properly: clang's
own best on that program is 6187 against gcc's 4674, still 1.32x.

This also explains `-falign-loops=32` being worth 20% to one program and 0.5%
to the corpus: it attacks the fetch stall, and only a program that HAS one can
be paid for it. And it is the first evidence that mereo's fetch problem is a
GCC LAYOUT problem rather than an unavoidable cost of splicing everything into
one function -- Clang compiles the same single function without the stall.

### Bisecting Clang's passes: no single pass is responsible

Ran `opt -passes='default<O2>' -print-after-all` over the handler's -O0 IR and
counted the instructions in `@_start` after every one of the 118 dumps that
contain it. NET effect of each pass, summed over its runs:

    grows:   LoopSimplify +388   LCSSA +385   LoopUnroll +190   LoopFullUnroll +156
    shrinks: SimplifyCFG -1562   SROA -1063   InstCombine -404   EarlyCSE -118

`LoopSimplify` and `LCSSA` are canonicalisation -- preheaders and phis that
later passes consume -- so the only real codegen growth is the two unrollers,
+346 between them. **Tested and refuted**: `-fno-unroll-loops` makes it WORSE
(6,440 instructions against 6,339), and `-unroll-threshold=0` /
`-unroll-full-max-count=0` shave about 70 instructions while moving cycles not
at all.

**What the bisection did establish.** Clang's FINAL IR for `@_start` is 888
instructions and its machine output is 885 -- the backend is close to a 1:1
lowering -- while GCC reaches **697 machine instructions** for the same C. So
the divergence is in the middle end, and it is DIFFUSE: Clang's optimiser
simply does not simplify this function as far as GCC's does, and no single pass
accounts for it. The three biggest reducers are SimplifyCFG, SROA and
InstCombine, and none of them is failing outright -- they are collectively
arriving somewhere worse.

Five hypotheses have now been raised and killed on this question: register
spilling, the two parsers alternating, 32-byte fetch-line straddling,
branchless if-conversion (three separate knob families), and loop unrolling.
The practical answer has not changed and is not blocked on the explanation:
**build mereo with GCC**, where this program runs at 992 cycles with
`-funroll-loops` -- the fastest of everything measured, C included.

### Branchless is NOT Clang's problem, and -march=native does not rescue it

Two follow-ups, both negative, both worth not repeating.

**There is no way to switch Clang's branchless generation off that changes
anything here.** Every knob the LLVM option list offers was tried on the
handler -- `-disable-early-ifcvt`, the four `-disable-ifcvt-*` (diamond, simple,
triangle, forked-diamond), `-phi-node-folding-threshold=0`,
`-two-entry-phi-node-folding-threshold=0`, `-x86-cmov-converter=true`, and all
of them together. The instruction count stayed at **6339**, or rose to 6424
where it moved at all. So the `cmove`/`sete` excess in the opcode histogram was
a SYMPTOM and not the cause, and the hypothesis is now refuted three separate
ways. What remains established is only the localisation: each half of the
handler compiles as well under Clang as under GCC, and only the combined
function does not.

**`-march=native` (AVX2 + BMI2 + SSE4.2 here) is worth about 2% to mereo under
GCC and nothing under Clang:**

| | cycles | instructions | IPC |
| --- | --- | --- | --- |
| mereo, gcc baseline | 1089 | 4794 | 4.40 |
| mereo, gcc `-march=native` | 1069 | 4794 | 4.48 |
| **mereo, gcc `-funroll-loops`** | **992** | 4674 | 4.71 |
| mereo, gcc native + unroll | 1074 | 4675 | 4.35 |
| mereo, clang baseline | 1682 | 6339 | 3.77 |
| mereo, clang `-march=native` | 1691 | 6295 | 3.72 |

Note the third and fourth rows: **native and unroll do not compose** -- together
they are worse (1074) than unroll alone (992). Whatever unroll wins here,
`-march=native` undoes.

**On the C side `-march=native` is a DIFFERENT CONFIGURATION**, not a faster
build of the same one: it defines `__SSE4_2__`, which switches picohttpparser's
vector path back on (11-13 vector string instructions in the binary against the
8 that are glibc's). It is worth a lot -- 5,892 instructions to 4,835 and 1,124
cycles to 1,076 under Clang -- and it is no longer the no-SIMD comparison.

Even so: with its SIMD path enabled and its best compiler, the C handler is
**1076** against mereo's **992**.

### Clang's 30% is FUNCTION SIZE, and `-funroll-loops` buys mereo 8% here

**Why Clang emits more, localized.** Each half of the handler, compiled alone,
comes out the same under both compilers -- it is only the combination that
degrades:

| instructions | GCC | Clang | |
| --- | --- | --- | --- |
| the JSON walk alone | 2567 | 2528 | Clang 0.98x |
| the HTTP head alone | 3583 | 3531 | Clang 0.99x |
| both, one program | 4794 | 6339 | Clang **1.32x** |

So it is not a construct mereo emits that Clang dislikes -- it handles both
halves fine. It is that everything mereo emits lands in ONE function, and
Clang's optimiser degrades on that function as it grows where GCC's does not.
Instruction counts, so layout plays no part. The pass responsible is NOT
identified: if-conversion was the obvious suspect and was refuted, since
`-mllvm -phi-node-folding-threshold=0` and `-mllvm -x86-cmov-converter=true`
both left the count at exactly 6339.

**On chasing the C's IPC.** It is worth being clear that IPC is a rate, not a
goal. The C reaches 5.2 while executing 5,892 instructions; mereo sits at 4.4
while executing 4,794. The C's higher rate is partly a CONSEQUENCE of having
more independent work to overlap, and mereo's advantage is doing less work at
all. Raising mereo's IPC by giving it more instructions would be moving
backwards; cycles are the number.

**What did help: `-funroll-loops`**, on this program:

| | min cycles | instructions | IPC | .text |
| --- | --- | --- | --- | --- |
| C, gcc | 1441 | 6704 | 4.65 | |
| C, clang | 1126 | 5892 | 5.23 | |
| mereo, gcc `-O2 -falign-loops=32` | 1082 | 4794 | 4.43 | 2930 |
| **mereo, + `-funroll-loops`** | **994** | 4674 | 4.70 | 4913 |

994 against the best C build's 1126 -- **1.13x** -- and the fastest of the four.

**This does not reopen the closed corpus entry.** `-funroll-loops` GLOBALLY is
recorded below as measured and rejected: -4.8% instructions, invisible on the
clock, `.text` 6926 -> 18421. Both are true. It is worth 8% on a parser with
many short hot loops and nothing on the corpus, and it costs 68% of `.text`
here (2930 -> 4913), so it belongs on a program that has earned it and not in
build.sh.

### End to end against picohttpparser + tiny-json: mereo 0.83x

The realistic comparison, not a microbenchmark. One 403-byte POST -- 195 bytes
of head, six headers, a 208-byte JSON body -- and a handler that does what a
handler does: parse the head, find `Content-Length` WITHOUT caring about its
case, take the body pointer, walk the JSON, read `id` and `name`. Both sides
compute the same checksum and are checked on it before anything is timed.

Alignment swept (`-falign-loops` 1/16/32/64), min-of-3 per point, pinned:

| | min | median | max | instructions |
| --- | --- | --- | --- | --- |
| C: picohttpparser + tiny-json | 1330 | 1363 | 1459 | 6704 |
| **mereo: parse.mereo + json.mereo** | **1101** | **1123** | **1173** | **4794** |

**0.83x the cycles and 0.72x the instructions.** The spread is 10% on the C
side and 7% on mereo's, so this one is outside the layout band that ruined the
earlier rounds, and the instruction counts say the same thing independently.

Four things that keep it honest:

  * **No SIMD in either parser.** Verified per object file: `picohttpparser.o`
    and `tiny-json.o` contain zero SSE4.2 string instructions. The eight in the
    linked C binary are glibc's own `strspn`/`strcspn`, which nothing on the
    handler's path calls.
  * **The C side links libc** because tiny-json needs `strtoll` and ctype. That
    is how it is actually used, and the per-iteration subtraction removes
    startup, so the linkage difference does not enter the number.
  * **tiny-json copies the body every request** -- 208 bytes -- because its
    design writes into the document. That is inherent to it, not a handicap
    added here, and it is part of what the 1330 pays for.
  * **tiny-json builds a queryable tree and mereo does not.** A handler wanting
    many scattered fields later would favour the tree; this one takes two as
    they go past, which is the common shape.

**Under Clang it goes the other way**, which is why the compiler is now part of
the result rather than a footnote:

| compiler | implementation | cycles | instructions | IPC |
| --- | --- | --- | --- | --- |
| GCC | C: picohttpparser + tiny-json | 1316 | 6601 | 5.02 |
| GCC | **mereo** | **1091** | **4794** | 4.39 |
| Clang | C: picohttpparser + tiny-json | 1059 | 5908 | 5.58 |
| Clang | mereo | 1679 | 6215 | 3.70 |

    GCC     mereo / C   cycles 0.83x   instructions 0.73x
    Clang   mereo / C   cycles 1.59x   instructions 1.05x

So the honest headline is **compiler-dependent**: mereo wins by 17% under GCC
and loses by 59% under Clang, because Clang emits 30% more instructions for
mereo's big spliced function while emitting 10% FEWER for the C. IPC tracks it
-- mereo falls to 3.70 under Clang where the C rises to 5.58.

One asymmetry to keep in mind before reading too much into the Clang column:
the two flag sets cannot be identical, because
`-fno-tree-loop-distribute-patterns` and `-fwhole-program` are GCC-only, and
the Clang builds carry `-fno-builtin` in their place to keep the freestanding
link working. Both sides still compute the same checksum, so the WORK is the
same; the flags around it are not exactly.

### The JSON reader is built, and it beats tiny-json

`programs/http/json.mereo`, a `document` group with one `step` that hands back
events. Single pass, zero copy, validating, and no recursion: nesting lives in
an explicit one-byte-per-level stack the CALLER supplies, so `depth_limit` is
also the maximum nesting and a deep document is refused rather than smashing
anything. Escapes are validated but not decoded -- a string's span is the raw
bytes, because decoding needs somewhere to put the result and that is the
caller's buffer to choose.

Measured on the same 208-byte body as the study below, same discipline:

| | cycles | instructions |
| --- | --- | --- |
| tiny-json, full parse + 2 lookups | 1013 | 4421 |
| **`document.step`, full validating walk** | **625** | **2567** |
| `core.mereo`'s `json`, scan only (accepts garbage) | 55 | 311 |

**1.6x tiny-json on cycles and 1.7x fewer instructions**, and comfortably
outside the ±20% layout band that made a fool of the earlier rounds -- the
instruction counts corroborate independently. Not the same task, and the
difference favours neither cleanly: tiny-json builds a node tree and can be
asked for any field afterwards, and pays a `memcpy` per parse because its
design mutates the document. `document.step` builds nothing, so a caller that
wants three fields takes them as they go past.

Gated with everything else: the harness now runs **15,364 cases** across
requests, responses, chunked and JSON, the JSON half contributing well-formed
documents, every prefix of each, eight mutation classes, and 3,500 random and
mutated inputs, all against an oracle written from the same rules.

`request.parse` and `response.parse` now also hand back `body`, the address of
the first byte after the head, so the handoff to a body parser is one port and
no arithmetic.

### A JSON parser for request bodies: what the three candidates teach

tiny-json, RSJp-cpp and nlohmann measured on one task -- read top-level "name"
and "id" out of a 208-byte body -- pinned, min-of-9, all four agreeing on a
checksum first:

| | cycles | instructions | heap |
| --- | --- | --- | --- |
| tiny-json (C, caller-supplied node pool) | 1009 | 4421 | none |
| nlohmann (C++, DOM) | 7193 | 23279 | yes |
| RSJp-cpp (C++, lazy) | 9123 | 30228 | yes |
| `core.mereo`'s `json` | 54 | 311 | none |

**Do not read that last row as a win.** `json.text` accepts ALL FIVE malformed
documents it was fed -- a truncated object, a missing comma, a missing value,
nonsense nesting, and `not json at all "name": "x"` -- where tiny-json rejects
four of the five. It is 18x faster than tiny-json because it does not parse: it
scans for a key and reads what follows. On well-formed input it answers; on
anything else it answers confidently and wrongly. That is fine for a trusted
document and disqualifying for a request body off the network.

Among the three real parsers **tiny-json wins by 7x**, and it is the only one
that touches no heap.

**Fit, which is a different question from speed:**

  * *tiny-json's memory model fits* -- a caller-supplied array of nodes is
    exactly what the `array` view now expresses. But it RECURSES (`objValue`
    calls itself, and mereo refuses general recursion) and it MUTATES the input,
    writing NULs into the document, so it is not zero-copy and re-parsing a
    buffer costs a copy first. Both are structural, not details.
  * *RSJp-cpp's philosophy fits* -- parse lazily, only what is asked for, which
    is what `core.mereo`'s `json` already does. Its implementation is the
    slowest of the three because it copies into `std::string` at every step.
  * *nlohmann does not fit at all* -- heap, templates, exceptions. Useful only
    as a reference for what an ergonomic API looks like.

**So port none of them.** The shape the language wants is tiny-json's caller-
supplied storage with RSJp-cpp's laziness and neither one's recursion: a
single-pass tokenizer that hands back SPANS into the caller's buffer, carries
its nesting in an explicit depth stack the caller supplies, and writes an index
into an `array` of records when the caller wants one. It composes with the HTTP
parser for free, since both then hand back spans into the same read buffer.

The number to beat is tiny-json's **1009 cycles for a full validating parse**,
and mereo should beat it, because it need not copy the document or build a tree
unless asked. What must not happen is comparing a future parser against the 54
above and thinking anything regressed.

### A lens may not be laid over a template-local scalar

Found writing `programs/http/parse.mereo`, and it is why that parser writes its
header records with raw `[slots + count * field.size : 8]` stores instead of
through the `array` view built for exactly that job.

```
put (slots, mark) goes
  where is 0
  where is slots + 32
  one is [where : field.size] as field     -- unknown name 'where'
```

The same line at PROGRAM level compiles and runs. The cause is ordering:
`resolve_lenses` runs inside `plan()` over the global slot list, before
anything is spliced, and a template's locals are renamed per splice, so the
name it is asked to resolve does not exist yet. Confirmed to be the SPLICE and
not templates as such -- a resource METHOD gives the identical refusal, and a
method body is spliced the same way.

The effect is that `array` serves the READER and raw stores serve the WRITER,
which is a seam in a view whose whole purpose was to remove one. Two shapes
worth weighing before starting:

  * resolve lenses again AFTER splicing, when the renamed locals exist. The
    splice is where every other name is already resolved, so this is where it
    belongs; the risk is that lens diagnostics would then point at a spliced
    line rather than the written one, which is the thing mereoc is careful
    about everywhere else.
  * let a lens name a PORT or a local by deferring only its address, keeping
    the fit check where it is. Narrower, and it covers the case that came up.

Not urgent: the raw form is correct, gated, and one line per field. It is the
ugliness that is the cost, and it lands in library code rather than in a
caller's.

### Strip section headers from the shipped binary?

Open, leaning NO, and measured: `objcopy --strip-section-headers` saves 287
bytes per binary, 22,157 over 77. It costs `objdump -d`, which then prints
nothing.

### Ctrl-Z leaves the terminal as the program set it

The one citizenship gap left open after 2026-08-26. SIGTSTP keeps its default,
so the process stops as it should -- but a program driving a terminal in raw
mode is stopped with those settings applied, and the shell that gets the
terminal back has no echo and no line buffering until it is continued
(measured: `keys` on a real pty, `canonical` false while stopped).

The fix is a LANGUAGE question, not a runtime one. A resource would have to be
able to say what "suspended" means for it -- `suspend`/`resume` as derived
methods beside `release`, mereoc calling them at the one place it can know they
are needed, routed the way an interrupt already is: signal -> EINTR -> a block
that hands things back, stops, takes them again, and redoes the step. It was
built far enough to see the shape and then stopped, so the two things worth
recording are: `release`'s elaboration (`defn["cleanup"]`) is the model for the
hooks, and the live set at each fallible step is already computed as `floor`.

Its LIMIT is what to weigh before starting again: a signal routed through EINTR
only lands where a syscall is in flight, so Ctrl-Z would take effect at the
program's next system call. For a program blocked reading a terminal that is
always; for one that is computing, Ctrl-Z would appear to do nothing, which is
a worse failure than the one being fixed. Confining the SIGTSTP handler to
programs that actually declare `suspend` keeps every other program's Ctrl-Z
exactly as it is today, and is what makes the trade defensible.

### The language server is back, and it does not highlight

`mereolsp.py`, gated by `tools/check_lsp.py` in `test.sh`. Diagnostics (mereoc
in a subprocess -- its `CONSTANTS` and `FIELD_SIZES` survive `transpile`, so a
second run in one interpreter would see the first run's declarations), plus
document symbols, definition across `include`s, hover, port completion and
references. 3,403 symbols over 230 files in 39 ms; 1,463 of 1,470 dotted names
resolve, and six of the seven that do not are in files refused on purpose.

**It says which port is the OUT port**, and it does not work that out for
itself. A direction is never declared: for a template mereoc derives it from
the body (read it, input; assign it, output) and leaves the answer in
`port_needs`; for a primitive it is written (`written out rax`) and a method
that binds one inherits it through `bind`. `plan()` derives both and throws the
working set away, so the compile worker WRAPS `derive_port_needs` and keeps
what it produced -- 133 callables, 110 out-ports, 19 with none. It shows up in
hover (in/out), in completion (`count` reads "out-port of input.read", and
`sortText` holds the declared order against a client that would sort
alphabetically), in the outline (`text.find (data, length, byte) -> offset`),
and in signature help, where the active parameter is found BY NAME because
mereo wires arguments by name and highlighting the third one after the second
comma would be confidently wrong. `check_lsp` spot-checks five known
signatures, so a rename of `derive_port_needs` cannot silence it quietly --
verified by removing the hook and watching the gate fail.

**The one idea it used to serve is not expressible in Kate**, and that is
measured rather than assumed. `semantic_tokens_legend.cpp` maps a server's
token types onto SEVEN attributes -- DataType, Keyword, Variable, Preprocessor,
Function, Constant, Comment -- each taking its colour AND its bold/italic from
the theme's own style, and `lspsemantichighlighting.cpp` discards the modifier
byte outright (`// auto mod = data[i + 4];`). Measured against Breeze Light,
three of the scheme's twelve looks are reachable: `structure` via `namespace`,
`call` via `function`, `member` via `parameter`. Bold-at-declaration and
bold-italic-at-use are not among them at any theme setting, because no two of
the seven give the same hue in both weights. So `tools/mereo.xml` keeps the
colours, `check_lsp` FAILS if the server ever declares `semanticTokensProvider`
or `documentHighlightProvider`, and the open question is now whether to serve
tokens anyway for an editor that honours a custom legend -- which costs nothing
in Kate, since Kate skips every type it does not know.

Still open: rename, formatting, call hierarchy, and a port used as a RECEIVER
(`screen.write` where `screen` is a port) -- one occurrence outside the refused
files, and resolving it means reading the call site.

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
| A third parameter on `_sigaction` for `oldact` | costs 2 instructions in programs that never query -- GCC allocates registers differently. Two wrappers (`_sigaction`, `_sigquery`) instead, and `index_fast` is byte-identical again |

### Five that came out POSITIVE, recorded because the mechanism is easy to lose

**A kernel promise is worth a great deal where a branch can use it, and a small
loss where none can.** With the promise 29,000,043 instructions; without it
103,000,036, and 3.8x on the clock. But one program carried six that no branch used
and paid 10,995 instructions for them. `prune_assumes` now emits one only where
an emitted branch mentions the value it bounds, in the matching direction.
Gated in `test.sh`'s build section.

**Being a good Linux citizen costs nothing the clock can see.** The startup a
resource-owning program now does -- one `poll` for the standard descriptors and
one disposition read per shutdown signal -- is 42 more user instructions and 4
more syscalls. On the clock: 308.1 us against 299.7 us over 3000 runs of
`catview`, which is to say the difference is under the noise (sigma ~140 us,
process setup dominates). The C twins in `tests/versus` were rewritten to do
the same work, because the suite's premise is a twin that is LINUX-CORRECT, and
`open_close` and `two_resources` came back at exact instruction parity: 255/255
and 316/316. (They are 253/255 and 314/316 since the helpers became macros --
see the entry below.)

**A macro is not an always_inline function, and the difference is the branch
predictor.** Every helper mereoc injects became a `#define` -- statement
expression where it yields a value, `do { } while (0)` where it does not -- so
the emitted C now holds exactly one function, `_start`. Measured over the 91
binaries, on REAL instructions with alignment padding excluded (counting padding
made `whoami` look 24 instructions worse when it was 3): 74 fewer, 11 unchanged,
6 more, net -134. `span` over 60 KB: 468,795 instructions to completion against
475,296, repeatable to the instruction. On the clock: 170.5 us +- 51.2
against 170.9 us +- 50.2 over ~18,500 runs each -- nothing the clock can see,
process setup dominating as usual.

The cause is one heuristic, and GCC names it in `-fdump-tree-profile_estimate`:
`early return (on trees)` fires on the branch guarding an early `return`,
predicts it unlikely, and the Dempster-Shafer combination takes that edge from
41% to 26.36%. A macro has no `return` to key on -- an early exit becomes
`break` out of the `do { } while (0)` -- so the heuristic never fires and the
block layout differs. Proved by holding everything else fixed: the same body,
still a FUNCTION but restructured with `break`, produces byte-identical code to
the macro. So the difference is the `return`, not the inlining. It is also
backwards where it fired: `_stdfd`'s early return is the case that happens every
time all three descriptors are open.

The one thing that bit on the way: a macro parameter is substituted into an asm
operand NAME, `[descriptor] "D" (...)`, which is a binding occurrence and not an
expression. 81 of 89 programs failed to compile until the parameters were
underscored. A function had no such problem.

Two side effects worth knowing. `tests/versus` was re-blessed: `open_close` is
now mereo 253 against the C twin's 255 and `two_resources` 314 against 316 --
mereo is BELOW its hand-written twin. The twin's helpers were converted to
macros too, so the comparison holds the C idiom constant, and the measurement
says the conversion changed nothing on that side: all nine twins came out at the
SAME real instruction count, five of them byte-identical. The twin never paid
the early-return cost, because `GUARD_STDFD()` was already a macro written as a
nested `if` rather than a guard-and-return -- so the old 255/255 parity was two
different costs cancelling, and the 2 mereo is ahead by now is register
allocation (`push-1 sub+1 xor-2`), not work either program does. And `_scan` was
the one helper with a `return` inside a loop, which needed a `_hit` flag to
express; 41,406 differential cases against the old body agree exactly.

**The exit path's two eyesores: one was real, one was already free.** Both are
in the tower's tail, which every run reaches.

`if (_dying) _reraise(_dying);` is NECESSARY wherever a fault can carry EINTR --
it is what turns a caught signal back into the wait status the parent would have
seen -- and it is now `__builtin_expect(_dying, 0)`. Without the hint GCC put
`_reraise`'s twenty instructions on the FALL-THROUGH and made the success path a
taken branch over them; with it the exit is one linear run into `exit_group`.
Instructions TO COMPLETION do not move (128 against 128 on `copy` and `catview`,
326 on `ls`, 117 on `showcase`) -- the test and its branch are there either way.
The cost is +12 instructions of out-of-lining across 7 of 91 binaries, all of it
in the cold copy.

`goto release_keep;` -- the happy path jumping past floors for resources an
inner scope already released -- costs NOTHING and needs no work. Measured by
walking the DWARF line table for instructions attributed to that exact line, in
all 46 programs that emit one: ZERO, every time. GCC folds it into the
conditional above it (inverting the branch), or drops it once block reordering
has put the target next, or deletes the skipped floor as unreachable. The
straightened form -- floors past the exit, each ending in a jump back -- would
move a jump onto the cold path to remove one the hot path never had.

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
