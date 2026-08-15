mereo's design follows from one commitment — that what is written is what the
machine does — and from the constraints accepted to keep it. There is no
runtime, so nothing happens that the source does not say; no allocator, so
memory is where it was declared; and no functions, so control flow is visible in
the text rather than in a call graph.

## Etymology

The name comes from **mereology**, the study of part–whole relationships, from
Greek *μέρος* (*méros*), "part". The project began under the working name
Mereology-Oriented Programming, whose first-order principle was that everything
is a part and that programs are built by fusing smaller parts into larger
wholes.

Little of that formal apparatus survives in the language as it now stands, but
the idea it was named for does: the **scope** is mereo's part, a named region
that owns what it holds and releases it on the way out, and every other
construct — a loop, a branch road, a template, the program itself — is one.

## Everything is a scope

The language has one organising construct. `NAME goes` opens a named scope, and
every other form of control flow is made from it:

- a **loop** is a scope whose body ends by repeating itself;
- an **`if`** is a scope with an entry condition;
- a **branch road** is a scope selected by a guard;
- a **template** is a scope spliced into its use site;
- the **program** is a scope.

Two jumps operate on scopes by name — `repeat NAME` returns to the top, `leave
NAME` continues past the bottom — and both release exactly what that scope
holds. There is no `break`, no `continue` and no `goto`, because there is
nothing for them to mean that naming a scope does not already say.

## Lifetimes are derived, not registered

A resource is acquired in exactly one step. That restriction is what makes the
rest possible: the transpiler always knows how far acquisition has progressed,
so cleanup is emitted as a ladder of labels entered at the point matching the
progress made, and no state is kept at runtime to record it.

```c
    goto release_server;      /* failed before the client existed */
release_client:
    _assembly_close(client_descriptor);
release_server:
    _assembly_close(server_descriptor);
```

Every exit enters that ladder — reaching `end`, a `leave`, a failed check, or an
interrupt. A generated program holding several descriptors contains no boolean
guard of any kind. The cost of the guarantee is the restriction that buys it:
ownership cannot be transferred conditionally, a resource cannot be handed to a
template as a value, and none can be stored in a data structure.

## Failure is derived from what failed

`ensure` states what must hold. When it does not, mereo releases what is live,
writes a record naming the step to standard error, and exits non-zero. Neither
`end` nor `leave program` accepts a status, so a non-zero exit means exactly one
thing: something failed, and both the code and the message came from *what*
failed. There is no exception, no error enum and no result type to inspect at a
call site — the `ensure` is the inspection. Where failure is expected rather
than exceptional, `or continue` repairs it in place.

## Types belong to accesses, not to variables

A value in mereo is a machine word with no type. What carries a type is the
*access* — how many bytes, signed or not, in which byte order:

```ada
  c is [buffer + i : 1]                 -- one byte
  n is [header + 4 : 2] as big          -- two, big-endian
```

A [view](Memory) names those readings once so a record describes itself, but
it converts nothing and copies nothing: it is a statement about bytes that
already exist. Nothing is coerced silently, because there is nothing to coerce.

## Optimisation claims are checked, not hinted

`LABEL likely goes` keeps the common case inline and moves the rest past the
program's exit. The build then disassembles the binary it produced and fails if
that layout was not achieved, so the construct is a claim the toolchain verifies
rather than a hint the compiler may ignore.

The same principle covers safety. A bounds check is not something to switch off
for speed; it is something to state once so the compiler can prove it redundant.
Bounding a loop by the same length the check tests removes the check from the
binary entirely — see [Performance](Performance), which measures both.

## What was deliberately left out

The absences are load-bearing rather than incidental:

| Absent | Because |
| --- | --- |
| Functions, recursion, function pointers | splicing has no frame to recurse in or point at |
| Dynamic allocation | there is no libc, and a freestanding program's memory is where it was declared |
| Exceptions, error values | `ensure` derives the status and the message from the failure |
| Generics | everything is bytes; there is no type parameter to vary |
| A garbage collector, a runtime | nothing may run that the program did not write |
| Separate compilation | a program is one translation unit |

The libraries follow the same rule. `core.mereo` carries three of C's thirteen
`ctype` questions and no `memmove`; both absences are recorded in the source with
the same reason, which is that nothing has wanted one yet.
