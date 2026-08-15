# mereo — architecture

mereo is a Mereology-Oriented Programming language. It transpiles prose-like
source to freestanding C — raw Linux syscalls, one flat `_start`, no libc, no
`call`/`ret` for any mereo construct (the language is function-free; reuse is
by inlining).

This document records the architectural principles that shape the language.
It grows one principle at a time.

---

## Thesis — a mereo program is the layout of optimized assembly, automated

mereo adds nothing to the machine. Everything it emits, an expert could write by
hand; the output is byte-for-byte what careful freestanding assembly would be —
the canonical programs are frozen against hand-written references, and at `-O0`
there is not one `call`. Assembly is maximal; mereo compiles *to* it. So *"what
can mereo do that assembly can't?"* has an honest answer: **nothing.** mereo
produces a *subset* of what assembly can express — the optimal-layout subset —
with the raw `assembly` primitive as the escape hatch when you need the rest.

What mereo adds is on a different axis entirely: it **generates the layout of a
highly-optimized assembly program, and keeps it correct as the program changes.**

An expert hand-writing a run-once syscall machine already converges on one shape:
a single flat routine, no calls; the common path straight down the middle; error
handling and cleanup pushed past the tail as cold blocks; every fault jumping to
exactly the cleanup sequence for the resources live at that point, in reverse
order of acquisition. That shape is what *optimal* is — and it is punishing to
maintain by hand: add one resource or one branch and every cleanup and error edge
must be re-threaded correctly, or the program leaks, double-frees, or exits wrong.

mereo's higher-order concepts are **not abstractions over that shape — they are
the shape, named, so the compiler can emit it:**

- a resource and its methods → an inlined operation and its check (a syscall +
  `ensure`);
- a branch (`likely goes` / `when … goes`) → the hot-path dispatch: the common
  road inline, the rest cold past the tail, all rejoining at one point;
- ownership (`adopted` / `already`) and the release tower → the acquire/release
  discipline, derived in reverse for exactly what is live;
- `ensure` → the success test and its jump to the cold error block.

Each concept automates *one part* of the optimal layout; you compose them and the
whole layout falls out — generated, not hand-kept. There is no runtime machinery
because there is no abstraction to run: the name *is* the code it stands for,
emitted in place. This is zero-cost abstraction at its limit — not "you don't pay
for what you don't use," but "the construct *is* the hand-written code, byte for
byte."

So the value is orthogonal to capability. **mereo cannot do anything assembly
can't — it can only stop you from getting the optimal layout wrong**, and
re-derive that layout on every edit, so the optimization never rots and the
cleanup is never mismatched. Assembly lets you write the optimal shape once and
hope it survives the next change; mereo makes the optimal shape the only thing
that can come out.

The first two principles below are not independent choices — they are what this
thesis *requires*. The hot-path-with-cold-branches (one level deep, never
nesting) and the single flat routine (no functions) are simply what optimized
assembly for this machine already is. Between the code they shape and the OS
around it sits mereo's **core** — the backing/view model, RAII, and automatic
error handling, which are not three features but one derived tower, the live set
every path routes through. A third principle then carries the same
*derive-everything-but-the-happy-path* ethos past the code and onto the process's
contract with the OS around it — good citizenship, generated rather than typed.

---

## Principle 1 — a natural top-down language: one level deep, never nesting

A mereo program reads top to bottom, like prose. Its control flow is a column of
steps; where a branch or a loop needs a body, that body is indented **one level**
and closed by the dedent — and one level is as deep as the language ever goes.
**The flow never nests:** no block is opened inside another. You are only ever
*on the spine* or *one body in* — never a stack of contexts deep.

And a branch's *cold* roads — the cases you rarely take — are still pushed **out
of line**, below `exit`, in the cold region past the tail. Only the hot default
and the loop body sit inline, one indent under their opener. A rarely-taken
divergence is a footnote past the tail; a road you're actually on is one shallow
step in.

### One level, and never two

mereo indents for three things, and the rule is about *depth*, not indentation:

- **A step's arguments.** The bindings under a step (`buffer is @buffer`) — one
  wrapped logical line, not a nested flow.
- **A definition's body.** A layout, a resource, a method, a primitive
  declaration — indented because it defines *vocabulary*, not the program's flow.
- **A branch or loop body.** The steps a `goes` / `again` opener governs,
  indented one level and closed by the dedent.

The first two were never flow at all. The third is the **one** level of
flow-indentation mereo permits. What it forbids is the *second* level — a branch
inside a branch, a loop inside a loop, a body opened inside a body. That second
indent is the nesting that grows a tree, and it is exactly the context-stack —
*"I'm in the else, inside the loop, inside the try"* — that a shallow read is
meant to spare you. One level in, you still read straight down; two levels in,
you are climbing.

So if a branch needs to branch again, it does **not** indent a second time — it
does what the spine does: a `goes` to a road out of line, past `exit`. The tree
is replaced by a spine with shallow one-deep bodies hanging off it, and
footnotes below the tail.

### The shape of it

Other languages build control flow as a tree of nested blocks:

```
read data
if empty:                 # inline block
    say "nothing"
else:                     # inline block
    write data
    if many:              # block nested in a block
        ...
cleanup
```

To read `write data` you must first know you are inside the `else` of the `if`.
The program is a tree; reading it is a walk, and indentation is the map you
hold in your head.

mereo keeps the flow a flat column and *points* at out-of-line blocks. The hot
default sits inline, on the spine, where it runs; only the cold cases are pushed
below the tail:

```
program is
  input.read
    buffer is @buffer
    capacity is capacity
    count is count

  report likely goes      -- the default — inline, hot, on the spine
    terminal.write
      buffer is "many bytes\n"
      count is 11
      written is written
  end

  exit

  report when count == 0 goes    -- only the cold roads are out of line
    terminal.write
      buffer is "nothing\n"
      count is 8
      written is written
  end
  report when count == 1 goes
    terminal.write
      buffer is "one byte\n"
      count is 9
      written is written
  end
end
```

The main story — `read → report (the default, inline) → exit` — reads straight
down, one indent, no nesting. The common case sits *on* the spine, where it
executes; only the two cold `when` roads are footnotes below the tail. The
source layout is the object layout.

### How each construct obeys the principle

- **The happy path** is a flat sequence of steps, one indent, top to bottom.
- **`ensure`** replaces the try/catch block. The success condition is a
  one-line postcondition on a step; the failure handling — the error record and
  the release tower — is *derived* and emitted cold, after the happy path.
  There is no inline handler to write.
- **`or continue (...)` / `or (...)`** — recovery and alternatives attach to a
  step as a one-line marker; their bodies are cold blocks after the flow.
- **`LABEL likely goes` / `LABEL when GUARD goes`** — the purest case, and the
  tightest fit to the thesis. The `likely` road *is* the default, written inline
  on the spine where it runs; the crossroad peels off only the *cold* `when`
  roads, which live below `exit`, each a detour that runs and returns to the
  merge (`LABEL`). Source layout equals object layout: hot default inline, cold
  roads out of line.
- **The release tower** — cleanup is derived from what is live and emitted cold
  after the flow. You never write a cleanup block inline.

### Why

1. **You read the main story top-to-bottom.** Divergences are footnotes, not
   detours inside the sentence. One indent level, always.
2. **The source mirrors the object code.** Freestanding C lays a program out as
   a straight-line hot path with branches and handlers past the tail. mereo's
   source *is* that layout — there is no gap between what you write and what
   runs.
3. **A flow that never nests is what makes cleanup derivable.** With no block
   inside a block, *what is live is a function of position*. That is the exact
   invariant that lets mereo derive the release tower and the error edges. Nested
   branches would make liveness depend on the path taken, and the whole
   derivation would collapse.

### The loop — inline, one level, on the happy path

A loop is *hot*: its body is the code that runs most. The thesis settles where
it goes — an optimizing assembler never exiles a loop body to the cold region;
it lays it out inline, on the hot path:

```asm
        <entry guard>          ; skip the body if it runs zero times
.loop:
        <body>                 ; inline, hot
        <per-iteration cleanup>
        <test>; jnz .loop      ; back-edge — predicted taken, the hot direction
.after: <continuation>         ; exit falls through, straight ahead
```

So one tempting idea is simply wrong: folding the loop body into an out-of-line
block below `exit` would put the *hottest* code where the *coldest* goes. The
loop body belongs on the happy path.

The friction was never the loop's *location* — it was the *indentation*, and the
one-level rule settles it directly: a loop body is a body like any other,
indented one level under its opener and closed by the dedent. No flattening
needed.

The surface is `serve goes … again` (see *Control flow*, below):

```
program is
  ...

  serve goes               -- the spine continues into the loop (inline top)
    server.accept
      connection is peer
    client.handle
      ...
    again                  -- the back-edge — the body's last step
  end

  exit                     -- the dedent is what closes the loop
end
```

- **`serve goes`** is just the spine carrying on into the loop; the body indents
  one level under it.
- **`again`** is the back-edge, written as the body's **last indented step** (not
  a closing bracket — the loop, like a branch, is closed by the *dedent*). Bare
  for a loop that never stops (a server, left by a fault or an early exit),
  **`again when COND`** for a bounded one (loops while the condition holds, falls
  through to `exit` when it doesn't).
- **Per-iteration cleanup rides the back-edge.** `again` releases what the body
  acquired, in reverse order, *before* looping — so every iteration is
  liveness-neutral and the fall-through exit is already clean. (A connection
  accepted in the body is closed each time round.) An early exit that leaves the
  loop releases the same set on its edge, derived identically.

An earlier sketch instead *flattened* the loop body into a `loop … repeat`
bracket, to dodge a body-delimiter question the one-level rule dissolves; it is
superseded. The one thing a loop adds to the top-to-bottom read is a single
visible backward edge — `again` — never a hidden cycle. It is the assembly
back-branch, surfaced.

*(Implemented: `server.mereo` uses `serve goes … again`, and GCC lowers it to
the rotated loop by hand — the `accept` guard fused into the back-edge, the body
inline, the cleanup on the edge.)*

---

## Principle 2 — function-free: no call, no return

mereo has no functions. No mereo construct compiles to a `call`/`ret`; the whole
program is one flat `_start`. A resource, a method, a named block — none of them is
a callable. They are *vocabulary and layout*, resolved at compile time and
inlined at every use.

- **Reuse is inlining, not calling.** A block used in two places is emitted
  twice — duplication, not a shared callee. Sharing one body across call sites
  needs a `call`/`ret`, i.e. a function, which mereo does not have.
- **No recursion.** Inlining a construct into itself would never terminate, so
  nothing may refer to itself.
- **Compile-time cost scales with the flattened program**, not with the number
  of definitions — the price of trading calls for inlining.

### Why forbid functions — it is what makes Principle 1 possible

The two principles hold each other up.

- The out-of-line blocks that Principle 1 depends on — a cold `when` road, a
  cold error handler, a release-tower floor — are reached by `goto`, and a `goto`
  only reaches labels in the *same* function. One flat `_start` means every
  block is a jump away from every other. Introduce a function boundary and those
  cross-block jumps become illegal; you would be forced back to inline nested
  blocks, or to calling out — the very things Principle 1 forbids.
- A cold `when` road returns by a *static* `goto` back to the merge, not a
  `ret`. There is no return address and no stack frame, because there is no
  call. That is only coherent in a function-free frame.

So: **no functions** is what lets the flow stay flat with everything else out of
line, and a flat single frame is what makes **no functions** cost nothing at
runtime — every execution model mereo uses is already intra-frame `goto`
dispatch, so removing functions removes none of them.

---

## Control flow — one jump, four words

Every branch and loop in mereo is the same machine primitive — **the flow goes
to a labeled point** — and the surface spells it with four small words, each
pulling exactly one direction. Learn the four and you can read any control flow:
follow `goes` straight down, glance at `likely` / `when` for the roads, and
`again` is the only thing that ever sends you back up.

- **`goes`** — where the flow goes on. Forward; and inline on the spine for the
  default road and the loop top.
- **`likely`** — the road the flow usually takes: the hot default, committed to
  the spine. It is `[[likely]]` made prose — you *state* which road is hot,
  because the compiler cannot guess. (And, as measured, it will otherwise guess
  from the *shape* of the condition — `if (x == 0)` makes GCC commit the *else*
  arm — and pick the wrong road for your program.)
- **`when …`** — a road taken only under a condition: a cold turn-off in a
  branch, or a loop's exit test.
- **`again`** — round the loop; the one move that goes *backward*, given its own
  word so it is never mistaken for a forward jump.

### A branch

The label (`bytes`) is the crossroad; each `bytes … goes` is a road off it. The
`likely` road is the fall-through — inline, on the spine. The `when` roads are
cold, past `exit`, each rejoining where the fork was.

```
  bytes likely goes           -- the road the flow usually takes — inline, on the spine
    terminal.write
      buffer is "many bytes\n"
      count is 11
      written is written
  end

  exit

  bytes when count == 0 goes  -- a road taken only when count is 0 — cold, after exit
    terminal.write
      buffer is "nothing\n"
      count is 8
      written is written
  end
  bytes when count == 1 goes
    terminal.write
      buffer is "one byte\n"
      count is 9
      written is written
  end
```

### A loop

The loop top is the spine simply continuing — the same `goes` — and `again` is
the back-edge:

```
  serve goes                  -- the spine flows on into the loop (inline top)
    server.accept
      connection is peer
    client.handle
      ...
    again                     -- round the loop — the body's last step
  end
```

`again` is the body's last indented step; the dedent below it closes the loop,
exactly as a branch's body is closed (no bracket keyword — the indentation is the
mark). Bare `again` never stops (a server, left by a fault or an early exit).
`again when running` circles while the condition holds and falls through to
`exit` when it doesn't.

### One primitive, two directions

`goes` and `again` are the *same* operation — a `goto` to a label in the one
flat `_start` (Principle 2 is what makes that legal). Only *where the label
sits* differs:

- **forward**, to a road below → a branch: dispatch to it, and let the `likely`
  road fall through inline;
- **backward**, to the loop top → a loop: emit a back-edge, the predicted-taken
  hot direction.

The backward move gets its own word (`again`) not because the machine needs it,
but so a reader never has to notice a label was defined *above* to realise
they're in a loop. One primitive underneath; two legible words on top.

And it lands exactly on the layout the rest of this document builds: the
`likely` road inline on the spine (the Thesis — the hot path *is* the object
layout), the `when` roads cold past the tail beside the error blocks
(Principle 1 — divergences out of line), the whole thing one flat frame of
`goto`s (Principle 2). Nothing is left over to explain — the four words *are*
the layout, named.

*(**Implemented.** The frame/loop body is **indented one level, closed by the
dedent** — the single level of flow-indentation Principle 1 allows, never a
second. The transpiler ships the full `goes` / `likely` / `when` / `again`
surface: `branch.mereo` is the crossroad (`LABEL likely goes` inline default +
`LABEL when GUARD goes` cold roads), `server.mereo` is the loop (`serve goes …
again`). The older `visit` / `loop is` spellings are gone.)*

---

## The core — the backing/view model, RAII, and error handling are one tower

Three of mereo's features read like separate conveniences and are in fact **one
mechanism seen from three sides.** They are established together because each is
what makes the others zero-cost:

- the **backing/view model** — what a resource *is*;
- **RAII** — when its cleanup runs;
- **automatic error handling** — where a fault goes.

All three are operations on a single compile-time structure: the **live set** —
the sequence of resources acquired at a given point in the program.

### Backing and view — storage is not interface

A **backing** is raw bytes. A **view** is a typed lens laid over them. Nothing
owns meaning but the view; nothing owns storage but the backing. This is the old
data-versus-resource split, unified — both are views, differing only in whether
they carry behavior:

- a **data view** — a layout's fields over the bytes (`lflag from work`);
  a pure lens, no lifecycle;
- a **behavioral view** — a resource's methods *and lifecycle* over the bytes (a
  `descriptor`'s open / read / close); the fd lives in the backing.

Who owns the backing and what lifecycle runs are **two independent axes**, and
mereo's existing construction words already name every combination — no new
vocabulary. (A pure data view has no lifecycle, so for it only the backing column
matters; a behavioral view uses both.)

| | backing | on construct | on exit |
|---|---|---|---|
| **new** (`is …` / `is … where`) | its own, allocated | the acquire fills it | the release runs |
| **`B as adopted …`** | yours | — (state already there) | the release runs (close / restore) |
| **`B as …`** | yours | — | nothing — a pure lens |

And a view can **extend** another: `tty extends descriptor` is a stacked view
over a *combined* backing — the terminal's raw-mode state layered on the fd. Each
layer keeps its own single-op lifecycle; the stack composes them.

### The backing forms — a small, closed set

If a view is open-ended — new interpretations arrive forever — a **backing** is
the opposite: just *bits, somewhere, of some size,* deliberately minimal, and its
set of forms is meant to **close.** All the richness lives in the views; the
storage under them is a short list. Bits live in a register or in memory, and
mereo names each shape:

| form | where | |
|---|---|---|
| **scalar** — `x is 0` | a register | a 64-bit word (its default reading is a signed integer) |
| **buffer** — `buf is N bytes` | the stack | `aligned M` for SIMD / DMA / cache-line separation |
| **byte-literal** — `bytes "…"` | the stack, initialized | or **`constant bytes` → `.rodata`**: read-only, no runtime copy |
| **in-instance field** | the resource's block | a resource's own oversized field (`backup is 36 bytes`) |
| **layout block** — `v is vector` | the stack | contiguous byte fields; `aligned M` too |
| **mapping** | `mmap` | the dynamic / large-allocation primitive — mereo's heap |

And the *addressing* over them is complete: a backing's name **is** its address;
`[base + expr : N]` reaches any computed slice; `over B + N` offsets a lens; and
an address loaded from memory can be dereferenced again. Named, computed, offset,
indirected — the whole set.

Two recent completions closed the last edges. **`constant`** puts read-only data
in `.rodata` — no stack copy, and a write to it is a *compile* error (the
read-only page would otherwise fault at runtime); it is also the only form that
links for a large table, since a big stack initializer lowers to a `memcpy` the
freestanding binary does not have. And **`aligned M`** now applies to a layout
block as well as a plain buffer.

That the backing set closes while the view set stays open is not an accident — it
is the model working. Storage is simple by nature; meaning is where the language
earns its keep. A short, finished list of backings under an unbounded vocabulary
of views is exactly the shape the split predicts.

### The same model at the register — the machine's own

The backing/view split is not a high-level convenience bolted over a typed core;
it is **the machine's own model, named.** It goes all the way down to a single
register, and there the correspondence is exact.

In assembly, storage is typeless. A register is 64 bits; a memory cell is bytes.
Whether those bits are a signed integer, an unsigned integer, or a double is
decided *not by the storage* but by the instruction you feed them to — `sar` vs
`shr`, `add` vs `addsd`, `cmp;jl` vs `cmp;jb`. The bits carry no type; the
instruction supplies the interpretation, at the point of use.

That is exactly what a **view** is. A backing is typeless bits; `as signed` /
`as unsigned` / `as big` / `as float` is *which interpretation to apply here* —
which is *which instruction to emit.* It is not metadata on the storage; it is
the instruction selection, at the use site. Compiled and disassembled, each view
is the instruction a hand-assembly programmer would have picked:

| mereo | x86-64 | |
|---|---|---|
| `a >> 4` (bare) | `sar` | arithmetic (signed) shift |
| `(a as unsigned) >> 4` | `shr` | logical (unsigned) shift |
| `[b:1] as signed` | `movsx` | sign-extend load |
| `[b:1] as unsigned` | `movzx` | zero-extend load |
| `[b:4] as big` | `bswap` | byte-swap |
| `a as float` | `movq r,xmm` | bit-preserving move (a reinterpret) |
| `a to float` | `cvtsi2sd` | integer → double convert |
| `f to whole` | `cvttsd2si` | double → integer convert |

The last three rows are the sharpest evidence, because they show the **`as` / `to`
law** is the hardware's own line. A view (`as`) never changes the bits — `as
float` is a `movq`, the 64 bits moved verbatim into an XMM register. A conversion
(`to`) is a real computation that produces new bits — `to float` is a `cvtsi2sd`.
`as`/`to` **is** `movq`/`cvtsi2sd`. The rule *a view relabels bits you already
have; a conversion computes new ones* is not a mereo invention — it is the
distinction the instruction set already draws.

Note what this is **not**: a type system. A type system would forbid using an
integer as a double. mereo forbids nothing of the kind — it keeps assembly's full
reinterpretation freedom (any backing, any view) and only *names* the
interpretation, adding two honesty rails: `as` may not change bits (that needs
`to`), and byte order is a memory property (`as big` is rejected on a register,
which has none until it is stored). It is assembly's typeless model with the
interpretations given names, not abstracted away.

So the backing/view model is the **data-side of the Thesis.** Just as a resource, a
branch, or the tower *is* the optimal assembly layout named, a backing *is* a
register or memory cell and a view *is* the instruction's interpretation — the
name is the code, on the data as on the control flow. Two honest seams remain: a
bare read carries a **default view** (a signed 64-bit integer), the one
convenience the machine lacks — in assembly every op is explicit; and the path is
`view → C type → the compiler's instruction`, a faithful lowering rather than
direct emission, which is why the layout-critical output is *checked* against the
real assembly (`mereocheck`), not trusted.

### The access itself — volatile and atomics

The reinterpret views say *how the bits are read.* Two further concerns are about
*how the access behaves,* and they matter only when the memory is shared with
another agent — the kernel writing an `io_uring` ring, another process on an
`mmap`'d page, a device register. There the compiler's usual freedom (cache a
value in a register, coalesce two reads, reorder) is *wrong,* because the bytes
can change underneath it. Both, once again, are the machine's own mechanisms,
named.

**`volatile` forces the access.** `[ring + 4 : 4] as volatile` is an
access-qualifier view — spelled with `as`, and it composes with the reinterprets
(`as volatile big`) — telling the compiler the access is real: do not elide,
coalesce, cache, or reorder it. The proof is direct: two reads of one address
compile to *two* loads under `volatile` and *one* without (the compiler coalesces
the plain pair away). Without it, a poll loop reading a ring's tail pointer would
read once, hoist it out of the loop, and spin forever.

**Atomics make the access indivisible and ordered.** These *compute,* so they are
operations, not views, and take a statement form — `[addr:N] atomic OP` — each
lowering to exactly the instruction hand-assembly would pick:

| mereo | x86-64 | |
|---|---|---|
| `[c:8] atomic add 1` | `lock xadd` | fetch-and-add — a counter |
| `[l:4] atomic compare 0 set 1` | `lock cmpxchg` | compare-and-swap — the lock-free primitive |
| `[f:8] atomic store 1` | `xchg` | a published write (seq_cst) |
| `[f:8] atomic load` | `mov` | already atomic on x86 |
| `fence` | `lock or` | a standalone barrier |

And **memory ordering** is an optional word — `atomic relaxed add 1`, `acquire
fence` — defaulting to the strong, safe `seq_cst`. On x86-64 most orderings are
*free* (the architecture is already strongly ordered): `relaxed` merely drops the
compiler barrier, a `seq_cst` store takes an `xchg`. mereo invents no ordering
model — it names the one the hardware and the C memory model already have, and
lowers to the exact `lock` prefix or fence.

Together with the `mapping` backing this is the whole shared-memory story: `mmap`
gives you the region, `as volatile` makes the access real, atomics make it
indivisible and ordered. None of it is new machinery — a volatile qualifier, a
`lock` prefix, a fence are the machine's; mereo only gives them names.

### RAII — cleanup is derived, never written

Constructing a view (`new`, or `adopted`) appends it to the live set. At the end
of its scope — a block, a method body, the program — the live set unwinds **in
reverse order of acquisition**: the release tower. You write the acquire and the
release *once*, on the view; the tower places the release at every exit, for
exactly what is live there. A stacked view unwinds layer by layer — `restore`
then `close` — each a single op, the reverse of the order they went up. C++
destruction order, derived from the acquisition sequence rather than threaded by
hand.

### Automatic error handling — a fault is an early door into the same tower

An operation states its success condition with `ensure`. A violation raises
nothing — it is a **jump into the tower at the floor matching what is live right
there.** A fault half-way through a stacked construction releases exactly the
layers already up and no more; a fault deep in the program releases the whole
live set. Same cascade, a different door. There is no exception object, no
unwinder, no stack of handlers — the fault edge is one conditional `goto` into
the shared cleanup, chosen at compile time. The diagnostic (a stderr record) and
the graceful cases (`-EINTR`, a broken pipe leaving cleanly) are derived at that
same edge.

### The harmony — one live set, three doors

The three do not merely coexist; each is the reason the others are free:

- **normal exit** enters the tower at the top — RAII;
- **a fault** enters at its floor — error handling;
- **the view model supplies the entries** — one per acquired view, and the floors
  between them (a per-layer stack for a stacked view).

The keystone is that every view's lifecycle is **single-op**: one acquire, one
release. That makes the live set **exact at every program point** — there is
never a half-built thing to guess about — and *that exactness* is precisely what
lets both cleanup and error-routing be **derived**, with no drop flags, no
runtime type, no unwinder, because nothing is left to decide at runtime. Remove
single-op and partial construction needs a runtime flag; remove the shared tower
and errors need their own unwinding machinery; remove RAII and every fault edge is
hand-threaded. Kept together they collapse into one flat cascade of gotos — the
shape an expert writes once and dreads maintaining. Which is the Thesis exactly:
**you declare a view's lifecycle once, and correct cleanup and correct
error-routing fall out of every path, byte-for-byte optimal, with nothing to
run.**

---

## Principle 3 — a good Linux citizen, derived

Principles 1 and 2 shape the code the author writes. This one shapes everything
*around* it. The program you write is the **happy path**; everything the
operating system asks of a well-behaved process next to that path — reacting to
a signal, cleaning up on the way out, coping with a short read or a broken pipe,
exiting with the right status, handing over `argv` — mereo **derives or
provides**, the same way it derives the release tower. A mereo program should be
a *poster child* for a good Linux application, and its author should have written
almost none of that.

This is the Thesis pushed to the process boundary. An expert hand-writing a
run-once syscall machine doesn't just converge on the optimal *layout*; they also
thread in the same citizenship every time — ignore `SIGPIPE`, loop the partial
`write`, restore the terminal, unlink the half-made output, leave through
`exit_group`. It is correct-but-tedious plumbing that rots on the next edit — so
it is exactly what mereo should generate, leaving the author on the happy path.

### One contract per party

A process lives inside a handful of contracts, one with each party it touches. A
good citizen honors every one:

- **the kernel** — start cleanly, never return from `_start`, terminate the
  whole process (`exit_group`), don't leak descriptors across an `exec`;
- **the signal system** — a catchable signal is a *request*, not a murder:
  honor shutdown (`SIGINT`/`SIGTERM`), and survive `SIGPIPE`;
- **its pipe peers** — a `write` may be short, a `read` may be short or EOF, a
  reader may vanish; none of these is a crash;
- **the shell that launched it** — take arguments, keep stdout for output and
  stderr for diagnostics, exit with a status a script can read;
- **the filesystem** — don't leave a half-written file behind; create with a
  sane mode;
- **the terminal** — whatever you changed (raw mode), put it back before you go.

mereo's job is to honor them **by construction**, so the author writes the happy
path and gets the rest for free.

### The throughline — the tower's move, widened

None of this is new machinery. It is the *one* thing the tower already does —
**read what the OS just told you, and route it to the deliberate response** —
generalized past "a fault" to every event the boundary produces. The tower takes
a failed syscall and routes it to exactly the cleanup for what is live;
citizenship is the same routing, one step wider:

- a **short write** → go back and write the rest (retry), not fault;
- **EOF** (`read` returns `0`) → the loop's clean exit, not fault;
- a **broken pipe** (`-EPIPE`) → graceful shutdown — your reader finished early
  — the same road as `-EINTR`;
- a **transient `accept` error** → back around the loop, not the server's grave;
- a **fatal error** → the tower, exit non-zero;
- an **interrupt** → the tower, exit graceful *(already built)*.

So a mereo syscall is not "do it and check `>= 0`" — it is *do it, and dispatch
on the result*, and the dispatch (retry / continue / graceful / fault) is mostly
**derived from what the call is**: a `read` in a copy loop knows EOF ends it; a
`write` to a stream knows a short count means "again."

### Everything defaulted, nothing hand-coded

Every item above has a **sensible automatic default**, so a happy-path program is
a good citizen with no extra words. The few genuine *policies* are defaulted too,
and overridable with a single marker — never hand-written control flow, the same
economy as `ensure` (you state the success condition, not the failure machinery)
and `likely` (you state the hot road, not the layout):

- **graceful vs fatal** — default: `-EINTR` and a broken pipe are graceful,
  everything else faults; mark a call if your program treats one differently;
- **interrupt exit code** — default `0` (a clean, intended shutdown); state `130`
  for the "interrupted" convention;
- **a listener** gets `SO_REUSEADDR` and shrugs off transient `accept` errors;
- **a half-written output** is unlinked on failure; ask for temp-then-`rename`
  when you need atomic replacement — cleanup as *more than close*.

The author writes the happy path; the defaults make it a good citizen; a marker
changes a default only when the program is genuinely unusual.

*(**Status.** Honored today: `SIGINT`/`SIGTERM` → the derived tower → graceful
`0`, with the teardown made uninterruptible inside the signal stub itself;
diagnostics on stderr; a non-executable stack; blocking, never spinning; a
static binary with no runtime deps. The rest of the contract — `SIGPIPE`,
partial-I/O routing, `exit_group`, `argv`, the server hygiene (`SO_REUSEADDR`,
accept resilience), and atomic output cleanup — is the derivation this principle
commits to, built the same way: read the result, route it, keep the author on
the happy path. The sharpest next gap is `SIGPIPE`: its default action kills the
process outright, past the tower — the one boundary event that today still slips
the net.)*
