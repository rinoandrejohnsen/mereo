A **resource** is a definition that owns something and releases it when its
scope ends. This is the behaviour C++ gets from destructors, obtained without
destructors, without an unwinder and without a runtime.

```ada
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

## One thing owned, not one call

What is fixed is the number of things a resource **owns** — exactly one — not
the number of calls it takes to get there. `acquire` may be a sequence: open,
then bind, then set an option.

What the sequence must say is **where ownership begins**, and `acquired` says
it. The library's own socket does this:

```ada
transform is
  descriptor is 4 bytes as signed
  status is 8 bytes as signed

  acquire (domain, type, protocol, address, length) is
    linux.socket (domain is domain,
                  type is type,
                  protocol is protocol,
                  descriptor is descriptor)
    acquired
    linux.bind (descriptor is descriptor,
                address is address,
                length is length,
                result is status)
  end
end
```

That one marker **is** the ownership boundary. A fault *before* it releases
nothing, because nothing had been taken; a fault *after* it — a failed `bind`,
here — releases the one thing, so the descriptor is closed. The socket is opened
and bound in one acquisition, which is the point: there is no window in which a
`transform` exists without its algorithm attached.

Omit the marker from a multi-call acquire and it is refused, because the
boundary would be a guess:

```
'holder' acquires in several steps, so it must say which one takes ownership --
add `acquired` after that call
```

A **single-call** acquire needs no marker: the boundary is unambiguous. And
`release` carries no test at any step — a failed release cannot reroute
anything.

### When the boundary is not the call's own test

`acquired` keeps the test the primitive already carries — `linux.open` promises
`descriptor >= 0`, and that is what the boundary means. Where the boundary is
genuinely something else, `acquired when COND` states it:

```ada
    linux.open (path is path, flags is 0, mode is 0, descriptor is descriptor)
    acquired when descriptor >= 3
```

Note what that does: it **replaces** the primitive's own `ensure`, it does not
add to it. A condition looser than the call's own contract therefore discards
it silently, which is why the bare form is the one to reach for. Every
acquisition in this project uses it.

## Owning a second thing: layering

A sequence of calls gets *one* thing into a usable state. Owning a **second**
thing is a different question, and the answer is `NAME extends THIS is` — each
layer owns one thing, and the tower releases them in reverse.

`linux.tty` is the library's own example. A terminal is two things: a
descriptor, and the settings that were in force before the program touched them.
`file` already owns the first, so `tty` layers on it and owns only the second:

```ada
  tty extends file is
    backup is 36 bytes

    acquire is
      ioctl (descriptor is descriptor, request is 21505, argument is backup)
    end

    release is
      ioctl (descriptor is descriptor, request is 21506, argument is backup)
    end
  end
```

Each layer takes exactly one thing, so each is still statically known, and the
tower is still derived — now with two floors:

```c
release_console:
    _assembly_ioctl(console_descriptor, 21506, (long)console_backup);
release_console__0:
    _assembly_close(console_descriptor);
exit:
```

Restore, then close, in reverse order of acquisition. A program says only:

```ada
include "linux.mereo"

program is
  work is linux.terminal_settings

  console is linux.tty (path is "/dev/tty", flags is 2, mode is 0)

  console.snapshot (buffer is work)

end
```

and gets both. Interrupted mid-read with a `SIGTERM`, a real run does this:

```
(SIGTERM arrives)
ioctl(3, TCSETS, {…}) = 0      <- the original settings, put back
close(3)              = 0
```

`examples/keys.mereo` is the full program, built by the ordinary sweep.

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
