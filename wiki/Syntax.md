mereo's surface is deliberately word-based: it has 42 reserved words, no
punctuation-heavy operators outside arithmetic, and a shape meant to be read
aloud. Indentation is structural, and `end` closes a block and is checked
against that indentation rather than replacing it.

## A complete program

```ada
include "linux.mereo"

program goes
  message is "hello, world\n"

  terminal is already linux.file (descriptor is 1)

  terminal.write (buffer is message, count is message.size)

end
```

This prints `hello, world` and links to a 784-byte static executable. There is
no `print`: `linux.write` sends bytes, `linux.read` receives them, and reaching
`end` ends the program with status zero.

## Lexical structure

Comments run from `--` to the end of the line, following Lua and Ada, and there
is no block comment form:

```ada
  -- one line, and that is the only kind
```

String literals are double-quoted and carry a compile-time `.size`:

```ada
  message is "hello\n"
  count is message.size          -- 6, folded at compile time
```

## Bindings

`NAME is VALUE` binds a name. The same form declares and assigns, and a name's
first mention is its declaration:

```ada
  total is 0
  total is total + 1
```

Buffers are declared with a size in bytes, and a buffer's name *is* its address:

```ada
  block is 4096 bytes
  digits is 24 bytes
```

## Arguments are wired by name

Every argument in a call is labelled, and arguments are matched by name rather
than by position, so the order at a call site carries no meaning:

```ada
  text.find (data is block, length is count, byte is 10, offset is at)
```

There is no return value. An **out-port** is a named place the answer is
written: `offset is at` means "put the offset in `at`". A step that answers
three things has three out-ports and no tuple.

## Conditions

Conditions are written in operators, never in words — `==`, `!=`, `<`, `>=`,
`&&`, `||` — so a condition cannot be confused with prose:

```ada
  ensure argc >= 2
  leave scan when c == 32
```

## Namespaces

A namespace has no keyword of its own: it is an `is` block that holds a
**definition**. Templates alone do not make one — a group is exactly a block of
templates — and a *field* makes it neither, since a namespace has members rather
than bytes. The system-call library places everything under `linux`; the
computation library deliberately uses none, so its groups are reached bare:

```ada
  linux.files.remove (name is "scratch", flags is 0)
  text.find (data is block, length is count, byte is 10, offset is at)
```

A name inside one is qualified from outside and bare from within, and the same
name in two namespaces is **two things** — declarations are keyed by their full
path, so `alpha.rec` and `beta.rec` never meet.

Namespaces nest, and a nested one reaches its enclosing namespace's members by
their bare names:

```ada
alpha is
  tally (value) goes
    value is value + 1
  end

  beta is
    reach (value) goes
      tally (value is value)     -- `alpha`'s, unqualified
    end
  end
end
```

reached from outside as `alpha.beta.reach (...)`.

## Reserved words

The reserved words fall into a few groups: block openers and closers (`is`,
`goes`, `end`, `scope`, `program`), the two jumps (`leave`,
`repeat`), declarations (`bytes`, `constant`, `already`, `adopted`, `extends`,
`helper`, `assembly`, `pure`, `final`), checks and repair (`ensure`, `fails`,
`failures`, `or`, `continue`, `when`, `likely`, `branchless`), and the words
that describe memory and machine detail (`as`, `in`, `out`, `to`, `high`,
`low`, `whole`, `atomic`, `volatile`, `fence`, `clobbers`, `register`).
