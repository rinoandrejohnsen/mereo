# Syntax and semantics

Word-based on purpose: 42 reserved words, no punctuation-heavy operators
outside arithmetic. Indentation is structural. `end` closes a block and is
checked against the indentation rather than replacing it.

## A complete program

```
include "linux.mereo"

program goes
  message is "hello, world\n"

  terminal is already linux.file (descriptor is 1)

  terminal.write (buffer is message, count is message.size)

end
```

784 bytes, static. There is no `print` — `linux.write` sends bytes,
`linux.read` receives them. Reaching `end` exits with status zero.

## Lexical structure

Comments run `--` to end of line, as in Lua and Ada. There is no block form:

```
  -- one line, and that is the only kind
```

String literals are double-quoted and carry a compile-time `.size`:

```
  message is "hello\n"
  count is message.size          -- 6, folded at compile time
```

## Bindings

`NAME is VALUE` binds a name. One form for both: the first mention declares.

```
  total is 0
  total is total + 1
```

A buffer is declared with a size in bytes. Its name *is* its address:

```
  block is 4096 bytes
  digits is 24 bytes
```

## Arguments are wired by name

Every argument is labelled and matched by name. Order carries no meaning:

```
  text.find (data is block, length is count, byte is 10) (at is offset)
```

There is no return value. A call has **two argument lists**: what it reads,
then what it writes. In the first, the port is on the left — `length is count`
puts `count` into the port `length`. In the second the sentence turns round,
because the traffic does: `at is offset` puts the port `offset` into `at`.

Direction is not something the lists declare — mereo derives it from the body,
by whether the port is read or assigned — so the lists **display** it, and a
port displayed on the wrong side is refused by name. That is why the second
list is not optional: a result written on the left would read as something the
call consumes, which is the one thing it never does.

A call whose every port is a result has an empty first list, and says so:

```
  given.number () (want is value)
```

A port the call both reads and writes stays in the first list: it is a
mutation, and the value going in is as real as the value coming out.

## Conditions

Operators, never words — `==`, `!=`, `<`, `>=`, `&&`, `||` — so a condition
cannot read as prose:

```
  ensure argc >= 2
  leave scan when c == 32
```

## Namespaces

A namespace has no keyword: it is an `is` block holding a **definition**.
Templates alone do not make one — that is a group. A field makes it neither: a
namespace has members, not bytes. The syscall library puts everything under
`linux`; the computation library uses none, so its groups are reached bare:

```
  linux.files.remove (name is "scratch", flags is 0)
  text.find (data is block, length is count, byte is 10, offset is at)
```

Qualified from outside, bare from within. The same name in two namespaces is
**two things**: declarations are keyed by full path, so `alpha.rec` and
`beta.rec` never meet.

Namespaces nest. A nested one reaches the enclosing members bare:

```
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

In groups: block openers and closers (`is`,
`goes`, `end`, `scope`, `program`), the two jumps (`leave`,
`repeat`), declarations (`bytes`, `constant`, `already`, `adopted`, `extends`,
`helper`, `assembly`, `pure`, `final`), checks and repair (`ensure`, `fails`,
`failures`, `or`, `continue`, `when`, `likely`, `branchless`), and the words
that describe memory and machine detail (`as`, `in`, `out`, `to`, `high`,
`low`, `whole`, `atomic`, `volatile`, `fence`, `clobbers`, `register`).
