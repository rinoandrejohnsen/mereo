Every program here is in the repository and is compiled by the documentation
build, so none can drift from the language.

## Hello world

```
include "linux.mereo"

program is
  message is "hello, world\n"

  terminal is already linux.file (descriptor is 1)

  terminal.write (buffer is message, count is message.size)

end
```

## Reading a file

The `close` is absent because it is derived; `source` belongs to the program's
scope and is released when that scope ends, on any path out.

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

## Requiring an argument

```
include "linux.mereo"

program (arguments) is
  argc is arguments.count
  ensure argc >= 2
end
```

With no argument the check fails, a record naming the step goes to standard
error, and the status is non-zero. With one, the program exits zero.

## Splitting input on a byte

Two views doing the work: a `span` names the block being read and is narrowed in
place, a `builder` fills the output and checks that each append fits. No offset
arithmetic appears at any call site.

```
include "linux.mereo"
include "core.mereo"

program is
  capacity is 65536
  block is capacity bytes
  room is capacity bytes
  count is 0
  n is 0
  k is 0

  input is already linux.file (descriptor is 0)

  terminal is already linux.file (descriptor is 1)

  input.read (buffer is block, capacity is capacity, count is count)

  rest is already span (data is block, length is count)
  page is already builder (data is room, count is 0, limit is capacity)

  lines goes
    leave lines when rest.length == 0

    rest.find (byte is 10, offset is n)
    line is already span (data is rest.data, length is n)
    rest.skip (count is n + 1)

    line.find (byte is 61, offset is k)
    key is already span (data is line.data, length is k)
    line.skip (count is k + 1)

    page.add (source is key.data, length is key.length)
    page.add (source is " -> ", length is 4)
    page.add (source is line.data, length is line.length)
    page.byte (value is 10)

    repeat lines
  end

  terminal.write (buffer is page.data, count is page.count)

end
```

```
$ printf 'host=localhost\nport=8080\n' | ./span
host -> localhost
port -> 8080
```

A last line without a newline and a line without an `=` both come out correctly
with no special case, because `find` answers with the region's length when the
byte is absent and the narrowing operations clamp.

## Larger programs

One program in the repository is of a size that exercises the language rather
than demonstrating it: a **TLS client**, which implements the handshake and
record layer including its own field arithmetic. The coreutils-shaped
examples — `ls`, `stat`, `basename`, `head`, `wc -l`, `getenv` — are checked
against the system's own versions where a comparison is meaningful.
