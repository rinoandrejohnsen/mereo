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

```ada
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

```ada
include "linux.mereo"

program goes
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

## `NAME is VALUE` declares and assigns, and which one is not written

This is the spelling to understand before the rest of the page. `NAME is VALUE`
**opens** the name if nothing has opened it, and **assigns** it if something
has. Nothing in the line says which, and there is no second spelling that does —
no `new`, no `let`. What decides is whether the name exists, and for a scalar
that means *anywhere in the program*, since scalars are one flat set.

Two of the three ways this can go wrong are caught:

| | |
| --- | --- |
| reading a name nothing ever opens | **refused** — `unknown name 'ghost'` |
| a name opened and written but never read | **refused** — so a misspelled assignment target is caught, because the misspelling is what nothing reads |
| meaning a fresh temp when the name already exists | **accepted**, and it assigns the existing one |

The third is the one to know about. Inside a scope, a line that reads like a
declaration is an assignment to whatever that name already is:

```ada
  n is 1
  s goes
    n is 2          -- the outer n, assigned
  end
                    -- mereo: n is 2.   C++: n is 1.
```

And because a scalar's value is whatever anyone last wrote, a scope can read one
a **sibling** left behind:

```ada
  one goes
    v is 7
    t is t + v
  end
  two goes
    t is t + v      -- v is 7 here, from `one`
    v is 100
  end
                    -- mereo prints 14. C++ warns `v is used uninitialized`.
```

That is the cost of the flat set, and it buys something real: a scope reads its
surroundings without plumbing anything through ports. The sharpest case — two
nested loops counted by the same scalar, where the inner one **resets** it — is
refused outright ([Safety](Safety) has it).

### The flat set stops at a template

A **template is where the flat set ends**, and this is what keeps the rule
usable. Its locals are not the caller's: each splice gets its own, renamed per
**call site**, so the same template used twice has two of everything.

```ada
label (answer) goes
  my_name is 3           -- the template's own
  my_name is my_name + 1
  answer is my_name
end

program goes
  my_name is 100         -- the program's
  s goes
    my_name is 200       -- a plain scope: ASSIGNS the program's
  end
  label (answer is got)  -- a splice: its my_name is a fresh variable
```

`my_name` ends as 200 and `got` as 4, and the emitted C says why:

```
    long my_name = 100;          /* the program's        */
    long label_1_my_name = 3;    /* the splice's, renamed */
```

Two calls give `label_1_my_name` and `label_2_my_name`. The isolation runs both
ways: a template cannot read or write a caller's scalar it has no port for —
writing one opens a local of its own, and reading one is a read of nothing. What
it *can* see beyond its ports is a top-level constant, which is a number rather
than storage.

It covers everything a splice declares, not just scalars — two calls to a
template holding `scratch is 8 bytes` give `fill_1_scratch` and `fill_2_scratch`
— and it nests: a template calling a template keeps both sets of locals apart.
Inside one splice the ordinary rule applies again, so a scope there assigns the
template's local exactly as a scope in the program assigns the program's.

**So the rule is one sentence: the program body is a flat set of names, each
splice is another, and scopes divide neither.**

So the habit is narrower than the flat set makes it sound: **inside a program, a
scalar opened in a scope is not private — name it as though it were not. Inside
a template, it is.**

## Names in a scope, against C and C++

A scope here controls **when things happen and when they are released**. It does
not control what a name means. C and C++ use the same braces for both; mereo
separates them, and the difference shows up in five places.

**A scalar declared in a scope is visible outside it.** There is one flat set of
scalars per program, so `NAME is VALUE` opens a name wherever it is written and
that name is live everywhere. This is what lets a scope read its surroundings
without plumbing anything through ports.

**So there is no shadowing.** Inside a scope, `n is 2` where `n` already exists
is an *assignment*, not a new declaration:

```ada
  n is 1
  s goes
    n is 2          -- the outer n, assigned
  end
                    -- mereo: n is 2.   C++: n is 1.
```

Both programs compile and the same-looking code gives different answers. C++
would warn at `-Wshadow`; mereo cannot, because the name really is the same
name.

**Sibling scopes share a scalar's storage.** Two scopes each opening `v` compile
to one `long v`, and the second can read what the first left — including without
declaring it at all. The one shape of this that bites in practice is guarded:
two nested loops counted by the same scalar, where the inner **resets** it, is
refused ([Safety](Safety) has the case).

**Order of declaration does not matter.** A scalar is live above the line that
opens it, initialiser included, so `n is m + 1` written before `m is 5` reads 5.
In C that is an error; here the text is a set of declarations and a sequence of
steps, and only the steps are ordered.

**Buffers, instances and template locals are not like this.** A buffer or an
instance may not reuse a name a sibling scope used — that is refused as *not
unique* — and a template's locals are private to its splice, so no caller sees
them. An owned resource used after the scope that acquired it is refused by
name, since its release already ran.

The reason for that first rule is worth stating, because it looks arbitrary
beside the scalars: **each of these is one declaration in one function**, so two
of them cannot share a name however far apart the scopes are. A scalar is the
exception that proves it — `v is 5` written twice is one declaration and an
assignment, not two declarations, so there is nothing for a uniqueness check to
compare, and that is exactly why it shares silently where a buffer cannot.

Where a scope wants a scalar of its own and means it, say so:

```ada
  s goes
    new v is 5      -- refused if `v` is already taken
  end
```

`new` is the half of `NAME is VALUE` that was missing: the plain form opens the
name or assigns it and nothing says which, while `new` says which and is
refused when the name is not free.

| | mereo | C / C++ |
| --- | --- | --- |
| scalar declared in a block | visible after it | block-scoped |
| same name in a block | assigns the outer one | shadows it |
| two sibling blocks, same scalar | one variable | two variables |
| use before the declaration line | reads the value | an error |
| buffer or instance reusing a name | refused | shadows |
| template / function locals | private | private |
| namespaces | as C++, checked against it | — |

The last row is not a hedge: `tests/namespaces` builds the same nine cases in
both languages — nested and sibling namespaces, outward lookup, shadowing,
reopening, qualified access at every depth — and requires identical output, with
answers chosen so a wrong resolution gives a different number.

## Conditionals

An `if` is a scope with a condition where the name would be. It is anonymous
because nothing jumps to it:

```ada
  count == 0 goes
    message is "nothing\n"
  end
```

### There is no `else`

There does not need to be one. An `else` is a scope the `if` **leaves early**:

```ada
include "linux.mereo"

program (arguments) goes
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

```ada
  argc == 1 goes
    ...
  end

  argc != 1 goes
    ...
  end
```

For a chain of alternatives, each arm is a conditional scope that `leave`s the
one around it — described in the next section. There is no `else` keyword,
because there is nothing for one to do.

Where the arms only choose a *value*, neither form is needed.

### Choosing a value

`when` states a dependence and lets the target lower it however it can:

```ada
  offset is i when [data + i] == byte
```

Several clauses form a cascade, first match winning, and the value is left
unchanged if none match:

```ada
  my_number is 40 when argument_count > 2 or
               50 when argument_count > 1
```

`branchless` *requires* that no branch be emitted, and is refused where the
machine could not honour it. Reach for it only when the condition is genuinely
unpredictable: on a well-predicted branch a conditional move is pure overhead,
and a plain cascade lets the compiler choose.

## If, else if, else

An arm is a conditional scope that takes its path and leaves. Whatever follows
it in the enclosing scope is the other path, so the **`else` is not a keyword**
— it is the code the guards did not jump over:

```ada
  pick goes
    path.length == 0 goes           -- if
      out_ptr is arg
      out_len is 0
      leave pick
    end
    comp_len == 0 goes              -- else if
      out_ptr is root
      out_len is 1
      leave pick
    end
    out_ptr is comp_at              -- else
    out_len is comp_len
  end

  output.write (buffer is out_ptr, count is out_len)
```

Each arm only *selects*; the work after is written once. Arms are scopes, so an
arm that acquires something releases it before the flow rejoins — which is what
`tests/scopes` checks against the equivalent C++ block, arm for arm.

### `likely`

A guard is predicted **not taken** unless it says otherwise, which makes the
fall-through the hot path — and the fall-through is the `else`. That is what a
guard written to step over an exceptional case wants, and it needs no annotation
to get it.

`likely` on a guard predicts it the other way, and means exactly what it means
in C:

```ada
  ready likely goes        -- if (__builtin_expect(ready, 1))
    ...
  end
```

It rides on a condition and nowhere else: `likely` on a named scope is refused,
because there is no branch to predict.

## Ending the program

Reaching the program's `end` releases everything and returns zero. `leave
program` is the way out from the middle, and takes no status:

```ada
  leave program when nothing_to_do
```

`repeat program` goes back to the program's first step — past the entry views
and the signal dispositions, which are settled once and are not part of what
repeats:

```ada
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
