mereo has no exceptions, no error enum and no result type. A program states what
must be true, and everything else — the cleanup, the exit status, the record on
standard error — is derived from the failure and from the scope it happened in.

## `ensure`

```
include "linux.mereo"

program (arguments) is
  argc is arguments.count
  ensure argc >= 2
end
```

Run with no argument the check fails, the program releases whatever is live,
writes a line naming the step, and exits non-zero. Run with one, it exits zero.

Every fallible step carries its own `ensure` from the primitive underneath, so a
call site does not test a result. `linux.file.write` requires that every byte
moved; the raw `linux.write` requires a non-negative count. That check costs two
instructions — a compare and a jump — and the record that names the failure sits
in the cold region past the program's exit, so it costs nothing on the path that
succeeds.

## The record

A failure writes the program, the stage, the step and the value:

```
two_resources: 3: read second: -9
```

The stage number is also the exit status's origin, and the same numbering
appears in the generated code as a marker the layout checker reads.

## The status is not yours to set

`leave program` takes no status, and neither does `end`:

- ending normally returns **0**;
- a failed `ensure` returns **non-zero**, with a record naming what failed.

So a non-zero status means exactly one thing, and there is no second way for a
program to come back non-zero. A `failures is` entry chooses *which* non-zero
code where the default does not suit. Where a number is a result rather than a
failure, the program calls the kernel itself — `linux.exit (status is bits)` —
and says so.

## Repairing an expected failure

Where a failure is ordinary rather than exceptional, `or continue` supplies the
values to carry on with:

```
  linux.files.remove (name is "scratch", flags is 0)
  or continue (result is 0)          -- fine if it was not there
```

This does not remove the check; it handles it. An alternative *construction* may
also be given, so a program can try a second way of obtaining something before
giving up.

## Clean shutdowns

Two errno values end a program without a diagnostic, because neither is a fault
in the program: `EPIPE`, when the reader of a pipe has gone, and `EINTR`, which
is how an interrupt reaches a program that owns something. Both route to the
release tower like any other exit.

## What this rules out

There is no way to observe a failure without handling it, no way to return an
error to a caller — there are no callers — and no way for a program to exit
non-zero silently. The cost is that a fallible operation must live in a resource
so its `ensure` has a tower to fail into, which is why the path operations in
`linux.mereo` are methods on a stateless group rather than free templates.
