# Memory and views

mereo has no heap. Memory is declared where it is used, in the stack or in
static storage, and a buffer's name is its address. What carries a type is not
the variable but the access.

## Backings

A **backing** is a run of bytes with a name:

```
  block is 4096 bytes
  message is "hello, world\n"
```

`in stack` is the default; `in static` places the bytes in the program's data
rather than its frame. A buffer sized by a run-time scalar is a run of memory by
definition and cannot live in a register.

## Typed accesses

An access states its width, and optionally its signedness and byte order:

```
  c is [block + i : 1]                  -- one byte
  n is [header + 4 : 2] as big          -- two, big-endian
  v is [record + 8 : 8] as signed       -- eight, signed
```

The width must be a literal 1, 2, 4 or 8: a run-time width would be a run-time
load size, which the machine does not have. This is the whole of the type
system, and it sits at the boundary between a register and memory.

## Layout views

Writing readings out at every use is repetitive, so a **layout view** names them
once and a record describes itself:

```
sockaddr_in is
  family is 2 bytes
  port is 2 bytes as big          -- network order, stated here rather than
  address is 4 bytes as big       -- remembered at every use
  pad is 8 bytes
end
```

### Laying one over a backing

`as` lays the view over bytes that already exist. It converts nothing, copies
nothing and allocates nothing — the instance *is* those bytes, and reading a
field is the load the view describes:

```
  block is 16 bytes

  host is block as sockaddr_in
  host.family is 2                -- AF_INET
  host.port is 8080               -- stored most-significant first, because
                                  -- the layout said so
```

`host.port is 8080` writes two bytes at offset 2 of `block`, byte-swapped. The
program never states the offset or the swap again; both came from the
declaration.

The same view may be laid at an offset, or over an address only known while the
program runs — a run of variable-length records, for instance, where the
programmer supplies the width the compiler checks against the layout's size:

```
  bits is meta + 28 as linux.file_mode     -- at a compile-time offset

  entry is [at : 19] as linux.dirent       -- at a runtime address
```

### Three ways to get one

A layout instance can also own its bytes rather than borrow them:

```
  over is block as header            -- a lens: block's bytes, nothing allocated
  fresh is header                    -- owns a zero-filled block of its shape
  given is already header (tag is 9, length is 4660)   -- ...and filled at once
```

All three describe identical memory and are written with the same field
accesses afterwards. Byte order holds across all of them: a value handed in at
construction is swapped exactly as one stored later would be.

## Layouts with templates

A layout may carry templates as well as fields. It stays *data* — a packed
block, not a resource — because a template is inlined work rather than a
lifecycle, and a view's whole point is the bytes it describes. What it gains is
a name for the operations that belong to the record:

```
include "linux.mereo"

record is
  tag is 1 bytes
  span is 2 bytes as big

  fill (a, b) is
    tag is a                   -- its own fields, by bare name
    span is b                  -- ...and byte order still holds
  end
end

program is
  buf is 8 bytes

  h is buf as record
  h.fill (a is 5, b is 4660)   -- 0x1234, stored most-significant first

  ensure h.tag == 5
  ensure [buf + 1 : 1] == 18   -- 0x12 first: the template kept network order
end
```

Inside the template, a field is reached by its bare name — `tag is a` writes the
instance's `tag`, not a local. Nothing is passed in to say which instance: the
template is spliced at the use site, so `h.fill (...)` becomes stores into
`buf`.

This is how `span` and `builder` in [the standard library](library.md) are
built. They are layouts of two or three fields carrying the operations that go
with them, which is why `rest.find (...)` costs no more than the loads it
performs.

A **flag view** names the individual bits of a word, which is what a mode or a
set of options is:

```
local_mode is
  echo is bit 3
  canonical is bits 1 to 2
end
```

A view normally sits over a named backing at a compile-time offset, so its fit
can be checked. Where the address is only known while running — a run of
variable-length records, for instance — the backing is stated inline instead,
and the programmer supplies the width the compiler checks:

```
  entry is [at : 19] as linux.dirent
```

## Spans and builders

Two views in `core.mereo` name an address and a length together rather than
passing them as separate arguments. A **span** is a region being read, a
**builder** a buffer being filled; neither owns anything, so neither is
released.

```
  rest is already span (data is block, length is count)
  rest.find (byte is 10, offset is n)
  rest.skip (count is n + 1)

  page is already builder (data is room, count is 0, limit is 4096)
  page.add (source is rest.data, length is rest.length)
  page.number (value is total)
```

`span` corresponds to C++'s `string_view`. Because mereo has no functions, a
method cannot return a fresh instance, so the operations that would manufacture
a sub-view — `substr`, `first`, `subspan` — are absent; C++'s own mutators
`remove_prefix` and `remove_suffix` take their place as `skip` and `trim`, with
`take` for the front. All three clamp, where C++ leaves an over-long argument
undefined.

An absent byte answers with the region's `length` rather than a sentinel. C++
needs `npos` because `size_t` has no spare value; the offset one past the end is
the length, and it is the offset a caller would resume from anyway.

Every `builder` method checks that the write fits before it writes. The 39
hand-written copy-and-advance pairs it replaced in the corpus checked nothing.

## Containers

A **container** is a buffer that carries its own fill level:

```
  data is container of 4096 bytes    -- data.data, data.count, data.size
```

## Checked and unchecked access

Both ends are available, and a third option usually beats them. `span.at`
checks its bound and fails naming the step; `[v.data + i]` does not check. But
bounding a loop by the same length the check tests lets the compiler prove the
check redundant and delete it, keeping the safety for nothing; and where the
bound differs, one `ensure` before the loop does the same. [Performance](performance.md)
measures all three.
