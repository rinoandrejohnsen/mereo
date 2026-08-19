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
`static __attribute__((noinline, cold))` function is worth a **further −23%
across the corpus**:

| | spliced (now) | shared function |
| --- | ---: | ---: |
| `abc` | 1296 | 1120 |
| `basename` | 2016 | 1520 |
| `jsontest` | 3792 | 3056 |
| `https` | 72856 | 56568 |
| **corpus** | **409144** | **312024** |

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
`NAME is EXPR`, `NAME is adopted CLASS where`, `NAME goes`, `scope`, `leave` and
`repeat`. It does not know two things the spine knows.

**1. A direct construction.** `NAME is CLASS where` in a road is not refused —
it is silently misparsed. The line matches the assignment rule (`NAME is EXPR`,
with `file where` read as the expression), so the failure lands on the
*following* line and names the wrong problem:

```
  pick likely goes
    source is linux.file (path is "lorem_ipsum.txt"      <- mereoc: error: line 8: unexpected)
                                          line in a `likely goes` body:
                                          'path is "lorem_ipsum.txt"'
  end
```

That misdirection is most of why this is worth fixing: the diagnostic points at
a binding and says nothing about the construction that actually failed. The rule
belongs above the assignment rule, mirroring `NAME is adopted CLASS where`,
which is already there and already collects its bindings at +4.

**2. `ensure`.** A road body has no rule for it at all, so it gets the
grammar-summary refusal:

```
    ensure n >= 0
    ^  mereoc: error: line 7: a `likely goes` body is method calls, `NAME is
       EXPR` assignments, `NAME is adopted CLASS where` resources, or
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

## What the linux.mereo half hit: seven places the language stopped short

**Status:** all seven are DONE. All were found by writing real code against
the new library rather than by reading the compiler, and each is stated with
the program that wanted it.

None of these blocked the work — every one had a workaround, and the workaround
was in the shipped code. They are kept because they were found together and
because five of the seven are the same shape: **a view is a lens at a
compile-time offset into a named backing, and nothing else.**

### 1. A view at a runtime address — **DONE**

**Closed.** `[ADDRESS : WIDTH] as LAYOUT` is accepted; the address is any
expression and the compiler checks `WIDTH >= psize`, refusing with
`view 'entry' needs 19 byte(s), but `[at : 8]` promises 8`. `linux.dirent` now
names the record's head and `examples/ls.mereo` reads it through
`entry is [at : 19] as linux.dirent`. Output identical across 271 directory
entries and `.text` byte-identical at 1155 bytes, so the names cost nothing.
The original entry follows.


`getdents64` returns a run of variable-length records, so the cursor is a
runtime value and the next record's offset is only known once the current one
is read. A layout view cannot name it:

```
  entry is at as dirent
  ^  mereoc: error: view 'entry' needs 19 byte(s) at offset 0 of 'at', which is
     8 bytes in a register -- a register word has nothing after it
  end
```

The refusal is principled — the compiler checks that a lens fits its backing,
and it cannot check this one. But the language already has a spelling for "N
bytes at this address", and it states the fit itself:

```
  entry is [at : 19] as dirent
```

`[ADDRESS : WIDTH]` is how every other memory access in mereo is written, the
programmer supplies the width, and the compiler checks `WIDTH >= psize` exactly
as it checks a backing's size today. This is the one of the seven worth doing.

**Workaround, and what ships:** `[at + 16 : 2]` and friends, with the offset
table in a comment on `getdents64`. See `examples/ls.mereo`.

### 2. A view over another view's field — **DONE**

**Closed.** A lens may take another view's field as its backing --
`bits is info.mode as linux.file_mode` -- and the offset comes from the layout
that declares the field, so it is not written twice. The field's own width is
what the fit is checked against. `examples/stat.mereo` uses it and its generated
C is byte-identical to the `meta + 28` it replaces; the corpus is unchanged.

The entry below proposed a different spelling -- a field carrying a view,
`mode is 2 bytes as file_mode` -- which would need nested member access
(`info.mode.setuid`) that the expression grammar does not have. This closes the
same gap without it. The original entry follows.

`file_mode` is the flag view over `statx`'s `mode`, which is at offset 28 of the
block `file_status` already describes. Laying one over the other means writing
that 28 down again — the exact number the layout view exists to remove:

```
  info is meta as linux.file_status
  bits is meta + 28 as linux.file_mode      -- ...28 is `mode of info`'s offset
```

What would close it is a layout field carrying a reading, the way a byte access
does: `mode is 2 bytes as file_mode`, alongside the `as big` / `as signed` that
a field can already carry.

### 3. The argument vector cannot be walked — **DONE**

**Closed.** The index in `view_access_c` is an ordinary expression now, not
`\d+`, so `arguments.pointer + i` and `environment.pointer + i` both work.
`examples/getenv.mereo` is the program this was blocking: it walks envp,
splits each `NAME=VALUE`, and agrees with `printenv`. A name that is a prefix
of a real one does not match it, which is what comparing both lengths buys.
The original entry follows.


`pointer of arguments + N` takes a **literal** N (`(?: \+ (\d+))?` in
`view_access_c`), so there is no loop over argv:

```
  name is arguments.pointer + i
  ^  mereoc: error: 'arguments.pointer' is not a flag or layout field
```

Every example in the corpus takes exactly one argument, which is why this never
came up before. `examples/stat.mereo` wanted several and takes one.

### 4. A layout field cannot be a run of text — **DONE**

**Closed.** A field wider than a register is a run of bytes rather than a
number, so it answers with its ADDRESS; a store to one is refused, there being
no load or store of that width. `linux.utsname` names uname's six strings, and
`examples/uname.mereo` reads two of them through spans and agrees with the
system's own `uname`. 81 binaries unchanged.

One name had to move: POSIX calls the third field `release`, which is a reserved
word here, so it is `revision`. The original entry follows.

`uname` answers with six 65-byte NUL-terminated strings in one block. A layout
view's fields are 1/2/4/8 bytes because they name a *number* at an offset, so
the six offsets are written in a comment instead. Same family as 1 and 2: the
field would have to be an address rather than a value.

### 5. A procedure method's body cannot open with a memory store — **DONE**

The procedure-body detector (`mereoc.py`, `^\w+ is .+$|^\w+ goes$|^scope$`)
recognises an assignment, a loop or a block — not a store:

```
  await with entry and events and timeout and ready is
    [entry + 0 : 4] is descriptor
    ^  mereoc: error: `ensure` before the method's body
```

The error names something the line has nothing to do with, which is the part
worth fixing even if the rule stays. A leading scalar (`watching is descriptor`)
is enough to get in.

**Closed.** The detector recognises a store (`[...] is ...`) and a field write
(`inst.field is ...`) as body statements. The misleading message is gone with
the rule that produced it.

### 6. A procedure method cannot call a primitive — **DONE**

A procedure body is spliced into the caller, so a primitive in it arrives in the
program body bare, and the bare-primitive rule refuses it:

```
    ppoll system where
    ^  mereoc: error: bare 'ppoll' -- fallible primitives must live in a
       resource so they carry an `ensure`
```

It IS in a resource, which is why the message misleads. The consequence is that
a method may either do several steps OR make one syscall, never both — so
`watch` cannot fill the `poll_entry` it then polls, and the caller fills it.

**Closed.** A spliced step is marked as coming from a method, and the bare rule
skips a marked one. The emitter then had to do what the ordinary call path does
and did not: skip constant arguments (it broke on `number is 271 in rax`; `exit`
only worked because its constant is declared last), bind the out-port, build the
guard from the primitive's own contract — and register a **stage**, so the guard
has an error label to jump to and the failure routes into the release tower.

`tests/progs/method_syscall.mereo` is a `watcher` that fills its own poll entry
and then polls it, covering 5 and 6 together. Both fixes are load-bearing on it:
the pre-fix compiler stops at 5, and with 5 alone backported it stops at 6.
`ppoll` was not in mereoraii's injectable list, so the new failure path had no
standing audit; it is now, and faulting it closes the descriptor. The corpus is
88 for 88 byte-identical.

### 7. A resource method cannot read its own state bytes — **DONE**

**Closed for procedure methods.** An in-instance buffer was emitted as
`char INST_field[N]` but never registered as a backing, so a method's
`[block + i : 1]` substituted the C cell and then failed to re-parse as mereo.
It is registered now, and the splice substitutes the emitter's name rather than
the cell. `tests/progs/own_state_bytes.mereo` is a resource that fills its own
block and reads bytes back out of it; the corpus is 80 for 80 unchanged.

**And closed for SINGLE-CALL methods.** `acquire` and `release` resolve their
arguments by name, so an access fell through to "unknown name"; `release` had a
second rule of its own admitting only state slots and literals. Both now accept
a read of the resource's own bytes, resolved the way a splice does -- substitute
the in-instance buffer's emitter name, which is registered as a backing, and use
the ordinary expression path. Three release emitters were building their
arguments with the same copied expression; they now share one resolver.

Two guards came with it, each checked to fire: a name inside the brackets that
is not this resource's state or the method's parameter, and an access over a
register-width field, which has no address to read from. That second message is
the `N bytes` ambiguity below, caught in this one position rather than left to
segfault.

`tests/progs/release_own_bytes.mereo` is `duct`, the resource that could not be
written: it owns a whole pipe and closes both ends out of its own buffer. A byte
is pushed through it, and mereoraii sees two descriptors acquired and both closed
on the happy path and on a fault at each of the four syscalls after them.

`channel` still ships, for a better reason than the one first given. The comment
said a `pipe` resource would have to hand its descriptors out and could not; the
real reason is that a resource owns ONE thing, and closing the write end to
signal end-of-input while still reading is the ordinary way to use a pipe --
which an owner of both cannot express.

Two things found while doing it, worth their own entries if they bite again:

- **mereoraii miscounted pipes.** `pipe2` returns its two descriptors through
  the ARGUMENT array and returns 0, and the audit read the return value -- so
  both ends went untracked and a stray `close(0)` counted as releasing "it". A
  program leaking a whole pipe pair passed. Fixed; it now reads the array.
- **An unsigned state field made a syscall's `ensure` vacuous** -- fixed. A
  contract may now carry a reading, `ensure count as signed >= 0`, and all 35
  syscalls that promise a non-negative result declare it. The signedness is a
  fact about the call, so stating it there means no binding can defeat it; the
  same spelling works in a method's own `ensure`. All 81 binaries came out
  identical, the cast being free on the signed fields the library already used.

The original entry follows.

```
  reader (descriptor) is
    descriptor is [pair + 0 : 4] as signed
    ^  mereoc: error: unknown name '[pair + 0 : 4]' (not a parameter or state slot)
  end
```

This is why there is no `pipe` resource owning both descriptors: it could
acquire the pair and close both, but it could not hand either one out. What
ships instead is `channel`, a stateless namespace whose one method makes the
pair, with each end adopted as an ordinary `file` — two owners, which is what
two descriptors are. That is arguably the better design, but it was chosen
because the first one would not compile.

## `N bytes` means two different things, silently

**Status:** open, found while writing the test for 5 and 6. A real miscompile,
worked around in the test by picking a wider field.

In a program body, `slot is 8 bytes` is storage — `char slot[8]`. As a resource
STATE field, the same eight words are a register word, because a state field is
a run of bytes only when it is wider than a register:

```
watcher is
  slot is 8 bytes            -- a register word, holding 0
  arm is
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

## The stage marker costs a tail merge

**Status:** open, measured, found by `tests/versus` on its first run over
`layout_view`. Waived there, with the reason printed on every run.

Every error block ends with a marker naming its stage:

```c
    _status = 1;
    __asm__("# stage 2" : "+r"(_status));
```

mereocheck reads those out of the shipped assembly, which is what makes the
hot/cold layout claim checkable rather than hopeful. But they are DISTINCT per
stage, so two error blocks that are otherwise byte-identical -- same EPIPE test,
same `_write_value`, same status -- cannot be tail-merged by GCC. A program with
two similar failure sites pays for two copies of the record path.

**Measured** on `tests/versus/cases/layout_view`, whose two write failures are
identical apart from the stage number: 8 syscall sites with the markers, **7
without**, which is exactly the C twin's count. Stripping the markers from the
generated C and rebuilding is the whole experiment.

**What to look at, if it is worth it.** The marker is only READ for programs
mereocheck inspects -- ones with crossroads. `layout_view` has none, so its
markers are emitted, block a merge, and are never read by anything. Emitting
them only where a layout claim exists would cost nothing and recover the merge
everywhere else. The risk is that "where a layout claim exists" is not
obviously a property of one program, since a template with roads is spliced into
whatever uses it.

Not urgent: it is a handful of bytes on programs with several similar failure
sites, and the verifiability it buys is the point of the whole gate.

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

  at (index, address) is
    a is 0
    ensure index < count    -- the check a raw `data + i * stride` never has
    a is data + index * stride
    address is a
  end
end
```

This was refused twice before, and both refusals are gone: `at` hands back an
ADDRESS, and interpreting an address needs `[p : 8] as LAYOUT`, which is gap 1
above. A run of poll entries -- what `ppoll` takes, and what `linux_calls` could
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

## The library's comments were never checked — **DONE**

**Closed**, and listed because the hole was open for months and nothing noticed.

`docs/build.py` refuses to ship a retired spelling in the documentation. The
library's comments are documentation too — `linux.mereo` carries a worked
example above nearly every resource, and those are what a reader copies — but no
gate read them, so the syntax change left them written in a surface that no
longer parses. Following the `ppoll` comment gave you `descriptor of watched is
here`; following `channel`'s gave you `make channel where`; `argcat`'s said
`program with arguments is`. Run the gate against the commit before this one and
it reports **42 lines across seven files**, 29 of them in `linux.mereo` — with
the library itself as the source of the mistake.

Two were worse than stale syntax — they stated a limitation that had since been
lifted. `examples/stat.mereo` said the argument vector "cannot be walked with a
counter yet", which gap 3 above closed; `linux.mereo` documented `size of X`,
which is now `X.size`.

`tools/check_comments.py` is the gate, run by `./test.sh`. The difficulty is
that `of`, `from`, `where`, `use` and `system` are all ordinary English and
these files are mostly prose, so it only examines what is code-shaped — an
indented snippet (`--` then three or more spaces, the convention every worked
example already follows) or anything in backticks — and a determiner after `of`
means the line is a sentence rather than a projection. Seven rules, each with a
planted violation checked to fire. The corpus is 102 for 102 byte-identical,
comments being comments.

## `is` declares, `goes` runs — **DONE**

**Status:** implemented. `contains` is retired, namespaces are `is` blocks, and
two namespaces declaring the same name are two things.

Every block now answers one question in its keyword: **does its body run?**

```
NAME is ... end                 a definition -- namespaces, views, groups,
                                resources, primitives
NAME goes ... end               executable -- the program, templates, methods,
NAME (ports) goes ... end       loops, roads, scopes
program goes ... end
```

`attic/migrations/to_goes.py` did the rewrite: 410 lines across 165 files, plus
the fenced snippets in `docs/`. One pass with an indent stack is enough because
the answer depends only on a line's PARENT block.

**A namespace has no keyword of its own.** It is an `is` block whose children
DECLARE, which after the migration is a one-level question — a namespace holds
definitions and primitives, a definition holds fields and `goes` methods. That
is the old ambiguity going away rather than moving: `acquire is` and `file is`
used to be the same line meaning different things depending on what enclosed
them, which is exactly how a definition inside a definition came to be read as a
method.

**Separation, which was the point.** Declarations are keyed by their canonical
path, so `alpha.rec` and `beta.rec` are two keys rather than one collision. No
tree was needed: every lookup already went through `deref`, which now answers
with the same path the declaration registered. `tests/progs/namespace_separate`
is the test, with the two `rec`s deliberately different shapes so a collision
could not pass unnoticed; the previous compiler refuses it with
`definition 'rec' redefined`.

A receiver resolves to a declared INSTANCE first, as a local does in C++.
Without that, `file is linux.file (...)` followed by `file.read (...)` is
ambiguous — and two programs in the corpus were relying on the old flattening to
resolve `linux.file.read (...)` to their instance, which separation exposed as
the accident it was.

**What it cost the output.** 81 of 83 binaries are byte-identical to the
pre-migration build. The two that differ do so for one stated reason: an error
record now names the namespace (`inspect linux.files`, not `inspect files`),
which is a longer string in `.rodata`. Primitives are the one declaration whose
name reaches the C, as `_assembly_linux_close`; the `exit` LABEL keeps its bare
name, because it marks the program's end rather than a syscall's symbol, and
`mereocheck` measures hot/cold layout against it.

**Two things deliberately not done**, per the decision: no `using`, and no
aliases. Qualification stays mandatory.

### Verified against C++

`tests/namespaces/` is `cases.mereo` and `cases.cpp`: the same nine questions
asked of each language, in two programs that must print the same nine numbers.
`./test.sh` runs the pair as Suite 4. They agree on `7 18 68 5 1 1 100 1 1000`.

The nine: a top-level name reachable although a namespace declares that name
too; a namespace member of the same name being a DIFFERENT type; nesting; a
sibling namespace; outward lookup from an inner namespace to the outer one's
member, unqualified; shadowing, where the inner declaration wins; reopening;
qualified access at every depth; unqualified access from within.

Each answer is chosen so a wrong resolution gives a different number -- the four
`rec`s differ in width and byte order, the templates add 1, 100 and 1000 -- so
agreement by luck is not available. Checked by planting two wrong resolutions
and watching the comparison catch both.

**Two divergences it found**, neither visible from the mereo side alone:

- a **top-level name was permanently shadowed** by any namespace member of the
  same name. `OF_NAMESPACE` was keyed by bare name and the top level was
  recorded nowhere, so `rec` at the left margin became unreachable the moment
  any namespace declared a `rec`. Lookup is innermost-first now and walks
  outward to the top level, which is a scope like any other -- and that is what
  makes shadowing work rather than merely not crash.
- **reopening required a definition** in the reopened block, so
  `namespace alpha { void late(); }` had no equivalent. Reopening is by NAME
  now, as in C++.

Not compared, because mereo does not have them and says so: `using`, namespace
aliases, anonymous namespaces (one flat program, no linkage to hide), and
argument-dependent lookup (no overloading to resolve).

### Still open, found on the way

- A member calling a **sibling** — **DONE**. Two things stood in the way. The
  procedure-body detector knew stores, assignments, loops and blocks but not a
  CALL, and a simple method's body *is* a call (`linux.close (...)`), so shape
  alone cannot separate them — what separates them is what is being called: a
  primitive makes a simple method, anything else makes a procedure. Past that
  the call reached the planner still bare, because a body is re-parsed as its
  own program and nothing there knows the method has neighbours; it is rewritten
  as a call on the same receiver now and the ordinary fixpoint splices it.
  Precedence matters and the shipped library is the test of it: `linux.file`'s
  `read` has `read (...)` for a body meaning the SYSCALL, so a primitive wins
  over a sibling of the same name — otherwise that method would splice into
  itself. `tests/progs/sibling_call` covers a stateless group and a resource;
  164 files byte-identical.
- A **free-standing template inside a namespace** — **DONE**. `lib.bump (...)`
  reads as a method call on `lib`, so it met the receiver rule first and was
  refused for `lib` not being an instance, while the rule that resolves a lone
  template sat below it and never ran; it is tried first now, and answers only
  when the name really resolves to a template. What decides a namespace is that
  it holds a DEFINITION: templates alone cannot make one, because a group is
  exactly a block of templates and reading `text is` as a namespace would
  scatter `find`, `compare` and fifteen more across the top level to collide
  with `span`'s. A FIELD makes it neither, which is what keeps a view or a
  resource from being read as one. `tests/progs/namespace_template` covers it.

  Found while doing it: the `goes` migration left the `free_templates` pre-pass
  matching `NAME (ports) is`, so a template declared BELOW the program stopped
  being found — silently, because nothing in the corpus declared one there. That
  is exactly the case the pre-pass exists for, so `tests/progs/tmpl_alone` now
  declares its template below the program; reverting the pattern breaks it.
- A **procedure body cannot open with a call**, which is the same family as the
  body-detector gaps closed earlier: the detector knows stores, assignments,
  loops and blocks, but not a call. It surfaces as ``ensure` before the method's
  body`, naming the wrong thing.
- **Nesting** — **DONE**. It needed no machinery beyond running the fold again:
  after a pass an inner namespace sits at the left margin, and because folding
  BLANKS lines rather than removing them, its header is still the line number
  the outer pass recorded a parent against — so each pass composes one more
  segment and `alpha.beta.rec` falls out of the same rule applied twice. A
  nested namespace reaches its enclosing one's members by bare name, which is a
  prefix test on the path rather than a chain walk.

  Found while doing it: the path-keying commit registered a free template's
  ALREADY-QUALIFIED name as its member name, so `alpha.tally` went in where
  `tally` belonged. Only the fully-written form worked, and `namespace_template`
  passed anyway because a later fallback matched on the definitions key. Fixed;
  `tests/progs/namespace_nested` is what caught it.
- `leave NAME` where NAME denotes something real — **DONE**. It answered *not a
  scope this sits inside* and then explained ancestors at length: all true, and
  none of it about the mistake. Four kinds of name get their own sentence now —
  a namespace has no body at all, a definition declares, an instance is a
  resource whose lifetime ends with the scope around it, a primitive is a call —
  and the reading is the one the language settled on: `is` declares, `goes`
  runs, so an `is` has nothing to leave. A name denoting nothing, and a real
  scope that is merely closed, still get the general message, which is the right
  one when there is no better answer. `tests/progs/leave_definition` covers it.

## `contains` and `is`: what actually separates them — **one gap DONE**

**Status:** the question was whether a namespace and a stateless group differ in
the end. They do, and the difference is not cosmetic; one hole found while
checking is closed.

Established against the compiler rather than by reading it:

| | `NAME contains` | `NAME is` (stateless group) |
| --- | --- | --- |
| what it is | a scope over NAMES, folded out of the line stream before parsing; emits nothing | a definition — a resource with the state left out |
| holds | resources, views, other groups, raw `assembly` primitives | methods and fields |
| a method directly in it | refused: *'lib' is a namespace, not an instance* | that is all it holds |
| a raw primitive in it | yes — all 41 syscalls live in `linux contains` | refused: *unrecognized definition line* |
| instantiable | no — `already linux` is *unknown definition 'linux'* | yes — `already linux.clock` compiles |
| nests in itself | refused explicitly | no |

So they are **complementary, not redundant**: neither can do the other's job.
`linux.channel.make (...)` needs both — `linux` to scope the name, `channel` to
be something a method can hang on. And a group is one field away from being a
resource, which a namespace can never become.

Where they really are indistinguishable is the CALL SITE: `linux.ppoll (...)` is
namespace→primitive and `linux.clock.elapsed (...)` is namespace→group→method,
and nothing in the syntax says which. Both cap at `A.b.c`. That is a fair
criticism of the surface, and it is a different question from whether the two
constructs do the same thing.

**The hole, now closed.** A definition written inside a definition reads exactly
like a no-parameter method, so the parser took it as one:

```
grp is
  rec is                    -- meant as a view
    tag is 1 bytes
  end
end
```

`grp.rec` became a callable method whose body declared a local. Nothing called
it, and a procedure method is otherwise checked only when it is INLINED — so
nothing ever looked at it again, and the complaint arrived at the use
(`` `as` needs a view ``), naming neither the nesting nor the group.

What makes it checkable without guessing: a method taking no parameters reaches
the world in exactly two ways — it calls something, or it writes its resource's
state. A body of nothing but declarations of its own locals does neither, so it
cannot have an effect however it was meant. Refused at the declaration now, with
a message that names the rule and where the definition belongs.

The corpus found the one case that reads like a declaration but is not:
`tests/scopes/04_method_local` writes `tmp is adopted mark_a (...)` in a method
precisely so the release runs when the method returns. An instance is an effect,
so instances are excluded. 162 files byte-identical after that.

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

## `linux:` was a spelling; `namespace` is the thing

**Status:** done for `linux.mereo`, and the reason the rest is not is listed
here rather than assumed.

`NAME contains ... end` is a scope over names and nothing else -- it is
folded out of the line stream before anything looks at indentation, and a thing
keeps the single bare name it was declared with. That is what lets the whole
change be verified: all 117 generated `.c` files are byte-identical.

The consequence is that two namespaces exporting the SAME bare name collide,
and so does a namespace member with a top-level name — `definition 'rec'
redefined`, naming neither namespace. Today `linux` is the only one, so it
cannot happen in practice. This is not a message problem: a namespace that
partitions nothing is not yet a namespace, and the fix is the canonical-path
keying designed under "Merging `contains` into `is`" above.

`core.mereo` declares no namespace, on purpose: its byte layer is reached
constantly and `core.text.find (...)` earns nothing over `text.find (...)`.
That is a judgement, not a rule -- if core grows something collision-prone it
can gain one, and a file may hold several.
