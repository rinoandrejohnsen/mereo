Every form in the language on one page. Each links to the section that explains it.

## Shape of a program

```ada
include "linux.mereo"          -- everything the kernel does, behind `linux.`
include "core.mereo"           -- ...and everything that needs none, unqualified

program is                     -- ...or `program (arguments) is`
  ...steps...
end                            -- reaching `end` ENDS the program, status 0

leave program                  -- ...the same, from the middle. No status:
                               -- a non-zero one means something FAILED
linux.exit (status is code)    -- ...unless you tell the KERNEL a number
                               -- yourself, which is a last step like any other
```

Indentation is **2 spaces per level**, and every block ends with `end` under
its opener. A call's arguments are not a block — they ride in its parentheses.
See [`program is`](Syntax).

## Values and memory

```ada
count is 0                     -- a scalar -- one machine word, signed
buf is 4096 bytes              -- a backing: its name is its ADDRESS
buf is 4096 bytes in static    -- ...or `in stack`, `in register`
msg is "hello\n"               -- a literal backing
msg is constant "hello\n"      -- ...read-only, in .rodata
raw is constant bytes 0xe3, 0xb0     -- ...given byte by byte
n is msg.size                  -- a COMPILE-TIME number
```

Numbers: `42`, `-1`, `0x2f`, `0b1011`. There is no named constant yet.
See [Buffers](Memory),
[Scalars](Memory), [Storage](Memory).

## Reading and writing memory

A value has no type; the **access** does.

```ada
c is [buf + i : 1]             -- load 1 byte
n is [hdr + 4 : 2] as big      -- 2 bytes, big-endian
v is [rec + 8 : 8] as signed   -- readings: signed unsigned big little
[buf + i : 1] is c             --           float whole volatile
[buf + i : 1] is c when ok     -- a conditional store -- may not write at all
```

See [Views](Memory).

## Namespaces

```ada
linux contains                 -- a file may declare several; what it declares
  file is                      -- outside one is global
    ...
  end
end
```

`linux.mereo` puts its whole kernel surface behind `linux.`; `core.mereo`
declares no namespace, so its byte layer is `text.find (...)`, unqualified.
A name inside a namespace is reached with a dot, and a bare one that belongs to
a namespace is refused by name.

## Scopes and jumps

```ada
NAME goes                      -- a scope: bounds a lifetime, offers two labels
  ...
end
scope                          -- the same, unnamed -- nothing jumps to it
end
GUARD goes                     -- ...and with a condition: mereo's `if`
end

repeat NAME                    -- -> the top of NAME
leave NAME                     -- -> past the bottom of NAME
repeat NAME when COND          -- either one, conditionally
leave program                  -- release everything, exit 0
```

Both jumps release everything the scope holds, innermost first. A **loop** is a
scope whose body ends by repeating. See [Scopes](Control-flow),
[Loops](Control-flow).

## Branches

```ada
LABEL likely goes              -- the common case, inline
  ...set values...
end

...shared steps, written once...

LABEL when GUARD goes          -- the exceptions, past the exit
  ...set the same values...
end
```

Roads only *select*; the spine acts once. `leave LABEL` inside a road rejoins
the merge early. See [Choosing a path](Control-flow).

## Conditions

Written in **operators, never words** — so a condition can never be mistaken for
an assignment:

```
  ==  !=  <  >  <=  >=          &&  ||          ( )
```

`x == 2` is a test; `x is 2` sets `x`. See [`ensure`](Errors).

## A value that depends on a condition

```ada
n is 40 when argc > 2 or       -- first clause that holds wins;
     50 when argc > 1          -- if none do, n keeps its value
n is 40 when argc > 2 branchless   -- require a cmov, no branch
```

See [Choosing a value](Control-flow).

## Templates

```ada
shout (area, length) is        -- free-standing: called by its own name
  ...
end

text is                        -- ...or gathered in a group
  find (data, byte, offset) is
    ...
  end
end

shout (area is buf, length is 5)  -- use it -- ports wired BY NAME
text.find (data is buf, byte is 10, offset is at)  -- a group's template names the group
```

Spliced, not called: locals are renamed per use, and a port's direction is
derived (read it → input, assign it → output). See
[Templates](Templates).

## Resources

```ada
file is                        -- define one
  descriptor is 4 bytes as signed
  acquire (path) is
    open system where ...
  end
  release is
    close system where ...
  end
  read (buffer, count) is
    ...
  end
end

source is linux.file (path is "x.txt")  -- own one -- released at the scope's end
linux.file.already (descriptor is 1)  -- borrow one -- nothing to release
NAME is adopted linux.file (descriptor is fd)  -- take ownership of something already open
source.read (buffer is buf)    -- call a method
```

See [Defining a resource](Resources), [`open`](Library).

## Files and directories

```ada
-- statx -> a 256-byte block
linux.files.inspect (name is "/etc/passwd",
               buffer is meta,
               mask is 2047,   -- STATX_BASIC_STATS
               flags is 0)     -- ...256 = the symlink itself
info is meta as linux.file_status    -- length/mode/links/uid/inode/modify_seconds of
bits is meta + 28 as linux.file_mode  -- kind of, owner_read, setuid, sticky ...

source.status (buffer is meta, mask is 2047)  -- ...or ask the OPEN file, not its name

folder is linux.directory (path is "/etc")  -- O_DIRECTORY; the scope closes it
folder.read (buffer is block, capacity is block.size, count is count)  -- getdents64: BYTES, and 0 means the end

-- ...make_directory, rename, make_link,
linux.files.remove (name is "scratch",  --    make_symlink, read_link, permit,
              flags is 0)      --    reachable, enter
```

Every `files` method takes a `result` out-port, so `or continue` can repair it.
See [Files and directories](Library).

## Time

```ada
span is ticks as linux.timespec      -- seconds of, nanoseconds of
linux.clock.elapsed (buffer is ticks)  -- since boot -- measure with this one
linux.clock.now (buffer is ticks)    -- wall time
linux.clock.wait (request is ticks, remain is 0)  -- sleep
```

## Views over bytes

```ada
sockaddr_in is                 -- a LAYOUT view: byte fields, in order
  family is 2 bytes
  port is 2 bytes as big
  address is 4 bytes
end

local_mode is                  -- a FLAG view: named bits
  echo is bit 3
  canonical is bits 1 to 2
end

host is block as linux.sockaddr_in   -- lay a view over bytes
host.port is 8080              -- read and write its fields
```

An address and a length, named once instead of passed as two arguments —
`span` reads, `builder` appends and checks that it fits:

```ada
rest is already span (data is block, length is count)
rest.find (byte is 10, offset is n)   -- `n` is rest.length if absent
part is already span (data is rest.data, length is n)   -- narrow
rest.skip (count is n + 1)     -- remove_prefix; `trim` drops from the back,
                               -- `take` keeps the front. All three clamp
rest.starts (other is "GET ", other_length is 4, result is ok)

page is already builder (data is room, count is 0, limit is 4096)
page.add (source is part.data, length is part.length)
page.number (value is 42)      -- and `hex`, `byte`, `pad`
```

See [Layout views](Memory), [Flag views](Memory),
[Container](Memory), [Span and builder](Memory).

## Failure

```ada
ensure count >= 1              -- must hold, or: release, report, exit non-zero
ensure a > 2 && b > 3          -- each conjunct reports separately

source.read                    -- a step that may fail...
    ...
or continue (count is 0)       -- ...carry on with these values instead

source is linux.file (path is "a.txt")  -- ...or try a different construction
or (path is "b.txt")
```

The record on stderr names the program, the stage and the failing step. See
[`ensure`](Errors).

## Naming rules

A name is `\w+`, and may not:

- be a mereo reserved word (`is`, `goes`, `end`, `when`, `leave`, …)
- start with a digit or an underscore
- be a **C keyword** (`int`, `while`, `return`, …) — a name becomes a C
  identifier as written
- for a **scope, crossroad or template**, look like a label the emitter makes:
  `NAME_done`, `release_NAME`, `past_N`, `error_*`, `LABEL_road_N`

Slots are exempt from the last rule: C keeps labels and variables in separate
namespaces, so a *scalar* called `release_doc` is fine.

## Building

```sh
./build.sh                          # every program, hot/cold layout verified
./build.sh examples/branch.mereo    # just one
./test.sh                           # parity + black box + the build gate
python3 docs/build.py               # this guide -> docs/mereo.html and wiki/
```
