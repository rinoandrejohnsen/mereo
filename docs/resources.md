# Resources and lifetimes

A **resource** is a definition that owns something and releases it when its
scope ends. This is the behaviour C++ gets from destructors, obtained without
destructors, without an unwinder and without a runtime.

```
include "linux.mereo"

program is
  buffer is 64 bytes
  count is 0

  terminal is already linux.file (descriptor is 1)

  source is linux.file (path is "lorem_ipsum.txt", flags is 0, mode is 0)

  source.read (buffer is buffer, capacity is 11, count is count)

  terminal.write (buffer is buffer, count is count)

end
```

Nothing above says `close`. Run it and the close is there:

```
linux.open("lorem_ipsum.txt", O_RDONLY)  = 3
linux.read(3, "Lorem ipsum", 11)
linux.write(1, "Lorem ipsum", 11)
linux.close(3)                                  <- the scope ended
```

## Owning and borrowing

Three words distinguish what an instance does with the thing it names:

| Form | Meaning |
| --- | --- |
| `NAME is CLASS (...)` | acquires it, and releases it at the scope's end |
| `NAME is adopted CLASS (...)` | takes ownership of something already open, and releases it |
| `NAME is already CLASS (...)` | borrows it; releases nothing |

`already linux.file (descriptor is 1)` names standard output without ever
closing it. `adopted` is for a descriptor obtained some other way — the two ends
of a pipe, for instance — which the tower should still close.

## The release tower

Cleanup is emitted as a ladder of labels, entered at the point matching how far
acquisition had progressed:

```c
    goto release_server;      /* failed before the client existed */
release_client:
    _assembly_close(client_descriptor);
release_server:
    _assembly_close(server_descriptor);
```

Every exit enters it: reaching `end`, a `leave`, a failed `ensure`, or an
interrupt. Nothing records progress at run time — a generated program holding
several descriptors contains no boolean guard — because the label jumped to
*is* the record, resolved when the program was compiled.

The order is reverse of acquisition, and is checked against equivalent C++
binaries with real destructors by running both under `strace` and comparing the
`close` sequence, on normal paths and on fault-injected ones.

## One acquisition per resource

`acquire` must be exactly one call. That restriction is what makes the tower
derivable, and it is enforced. To own a second thing, layer it — `NAME extends
THIS is` — so each layer acquires one thing and the tower releases them in
reverse.

## Interruption

A program that owns something installs a handler for `SIGINT` and `SIGTERM`
whose stub simply returns, so the interrupted system call comes back `EINTR`,
the ordinary failure path runs, and the tower releases what is open on the way
out. A program that owns nothing installs no such handler, and correspondingly
does not test for `EINTR` — there is none to see.

## What ownership may not do

The restrictions are the price of the guarantee, and they are real:

- ownership cannot be transferred conditionally, which is what a drop flag
  would otherwise have to record;
- a resource cannot be handed to a template as a value, which is why
  `linux.files` takes a path rather than a directory to work relative to;
- a resource cannot be stored in a data structure.
