mereo has no `while`, no `if` and no `switch`. It has scopes and two jumps, and
every control structure is built from them.

## Scopes

`NAME goes` opens a named scope; `end` closes it. The name exists so the two
jumps can address it:

| | goes to | releases |
| --- | --- | --- |
| `repeat NAME` | the first step of `NAME` | everything `NAME` holds |
| `leave NAME` | the step after `NAME` | everything `NAME` holds |

Both release the same thing, because both leave the region; they differ only in
where they continue. A scope that acquires something releases it on either.

## Loops

A loop is a scope that ends by repeating itself:

```
  scan goes
    c is [block + i : 1]
    leave scan when c == 32
    i is i + 1
    repeat scan when i < count
  end
```

Putting the `leave` first gives a `while`, in which the body may run zero times;
leaving it at the bottom gives a do-while. A loop that opens a file each pass
closes it each pass, without being told.

## Nesting

Because both jumps name their target, a jump from an inner scope may address an
outer one, and no flag is needed to carry the decision outwards:

```
include "linux.mereo"

program is
  row is 0
  col is 0

  terminal is already linux.file (descriptor is 1)

  rows goes
    col is 0
    cols goes
      terminal.write (buffer is "#", count is 1)
      col is col + 1
      leave rows when row == 1      -- out of BOTH scopes at once
      repeat cols when col < 3
    end
    terminal.write (buffer is "\n", count is 1)
    row is row + 1
    repeat rows when row < 3
  end

  terminal.write (buffer is "\n", count is 1)

end
```

```
###
#
```

The first row runs to three marks and starts a second. The `leave rows` in the
inner scope then ends **both** — had it said `leave cols`, only the inner one
would have ended and the outer would have gone round again. The two are the same
jump, differing only in the name they give.

Either would also have released whatever the scopes it leaves were holding.

**A jump may only target a scope it sits inside** — an ancestor, never a sibling
and never one already closed. That rule is what keeps the releases derivable:
the live set where the jump lands is that scope's entry set, which is a subset
of the live set at the jump by construction, so the difference is exactly what
to let go of. A jump anywhere else could arrive with a live set that depends on
the path taken, and recording that is a drop flag.

## Conditionals

An `if` is a scope with a condition where the name would be. It is anonymous
because nothing jumps to it:

```
  count == 0 goes
    message is "nothing\n"
  end
```

### There is no `else`

There does not need to be one. An `else` is a scope the `if` **leaves early**:

```
include "linux.mereo"

program (arguments) is
  x is arguments.count

  output is already linux.file (descriptor is 1)

  main goes
    x == 2 goes
      output.write (buffer is "hello from if\n", count is 14)
      leave main
    end

    output.write (buffer is "hello from else\n", count is 16)
  end
end
```

The outer scope is the whole conditional; the inner one is the `if`; whatever
follows it is the `else`, reached only by not leaving. That lowers to exactly
what C's `if`/`else` lowers to — one test, one jump:

```c
    if (!((x == 2))) goto past_2;      /* the only test */
    ...the if arm...
    goto main_done;                    /* skip the else */
past_2:
    ...the else arm...
main_done:
```

`leave main` is the ordinary jump, so it also releases anything the `if` arm had
taken, on its way past the `else`.

Two scopes with opposite conditions work too, and read fine for two independent
questions — but they are two conditions, and **both are evaluated**, because
nothing relates them:

```
  argc == 1 goes
    ...
  end

  argc != 1 goes
    ...
  end
```

For a chain of alternatives where one arm is the common case, the construct is
the **crossroad** described in the next section, which has the others dispatched
rather than tested in turn. It is written inside out compared with C: the
`likely` road is the **`else`**, the default that runs inline, and each `when`
road is a condition moved out of the way.

Where the arms only choose a *value*, neither form is needed.

### Choosing a value

`when` states a dependence and lets the target lower it however it can:

```
  offset is i when [data + i] == byte
```

Several clauses form a cascade, first match winning, and the value is left
unchanged if none match:

```
  my_number is 40 when argument_count > 2 or
               50 when argument_count > 1
```

`branchless` *requires* that no branch be emitted, and is refused where the
machine could not honour it. Reach for it only when the condition is genuinely
unpredictable: on a well-predicted branch a conditional move is pure overhead,
and a plain cascade lets the compiler choose.

## Branches and roads

Where one case is common and the rest are exceptions, a **crossroad** keeps the
common road inline and moves the others past the program's exit, rejoining at
the label:

```
  name likely goes                -- the common case, inline
    out_ptr is comp_at
    out_len is comp_len
  end

  output.write (buffer is out_ptr, count is out_len)

  name when path.length == 0 goes -- an exception, past the merge
    out_ptr is arg
    out_len is 0
  end
```

Each road only *selects*; the work after the merge is written once. Roads are
scopes, so a road that acquires something releases it before rejoining.

"Inline" and "moved away" are claims about the emitted machine code, so the
build disassembles the binary and fails if the layout was not achieved. A
crossroad may be nested inside a cold road, and the guarantee still holds: the
inner dispatch sits where its enclosing road does, and its own roads go past it.

## Ending the program

Reaching the program's `end` releases everything and returns zero. `leave
program` is the way out from the middle, and takes no status:

```
  leave program when nothing_to_do
```

`repeat program` goes back to the program's first step — past the entry views
and the signal dispositions, which are settled once and are not part of what
repeats:

```
  repeat program when i < 3
```

Like every other `repeat`, it releases what the scope holds on the way, and
since the program's entry set is empty that is everything live. It cannot enter
the [release tower](Resources) the way `leave program` does, because the
tower ends at the exit and this has somewhere else to go, so the releases are
emitted at the jump instead — one open and one close per pass, with the
descriptor reused rather than leaked.

A scalar keeps its value across the jump, because a declaration is not a step.
That is what lets such a loop end.

Where a number is a *result* rather than a failure — as with `test` — the
program calls the kernel itself with `linux.exit (status is bits)`.
