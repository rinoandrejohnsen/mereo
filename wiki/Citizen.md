A program on a Unix system owes its surroundings a short list of things. Close
what you open. Do not die halfway through holding a lock or a temporary file.
Say on standard error what went wrong, and say it in the exit status. Do not
report a broken pipe as a fault of your own. Do not lose output because you were
interrupted before a buffer was flushed.

Most languages leave that list to the programmer and provide the tools —
destructors, `defer`, `atexit`, signal handlers, `errno`. mereo makes the list
structural: **there is no way to write the program that gets it wrong**, because
the three mechanisms that would otherwise be separate are one path.

## Before the first step

Every program installs signal dispositions before it runs a step of its own.

**`SIGPIPE` is always ignored.** The default disposition kills the process when
the reader of a pipe goes away, which is why a naive program in a pipeline dies
silently and takes its cleanup with it. Ignoring it turns that into an ordinary
`EPIPE` from the write, which the program can then handle like anything else.

**`SIGINT` and `SIGTERM` are caught — but only when the program owns
something.** A program that holds nothing has nothing to clean up, so the
default disposition is correct and nothing is installed. A program that holds a
descriptor installs a stub that simply *returns*:

```
rt_sigaction(SIGPIPE, {sa_handler=SIG_IGN, …})
rt_sigaction(SIGINT,  {sa_handler=0x4000b0, …})
rt_sigaction(SIGTERM, {sa_handler=0x4000b0, …})
```

Returning is the whole trick. The interrupted system call comes back `EINTR`,
which is a failure like any other, and failure already has somewhere to go.

## The single path out

That is where the three mechanisms meet. A signal becomes an error; an error
enters the release tower; the tower is the only way out:

```
  a signal      ->  EINTR from the blocked call
  a failed call ->  its own errno
  a failed check->  ensure
                        |
                        v
              the release tower  ->  exit
```

Nothing branches around it. Pressing Ctrl-C while a program is blocked reading
does this, traced from a real run:

```
read(0, 0x7ffd4a817c80, 1) = ? ERESTARTSYS
close(3)                   = 0
```

The read was interrupted; the file that was open at that moment was closed. No
handler was written by the programmer, no flag recorded that the file was open,
and the same tower serves the normal exit, a failed check and an interrupt
alike — which is why there is no path on which it can be skipped.

## Saying what happened

Two errno values end a program **without** a diagnostic, because neither is a
fault in the program: `EPIPE`, when the reader of a pipe has gone, and `EINTR`,
which is how an interrupt arrives. Both release everything and exit **0**:

```
$ ./hello | head -c 0
$ echo $?
0
```

Everything else is a failure, and a failure writes one line to **standard
error** — never to standard output, which belongs to the program's actual work
— naming the program, the stage, the step and the value:

```
two_resources: 3: read second: -9
```

and exits non-zero. Since neither `end` nor `leave program` accepts a status, a
non-zero exit has exactly one meaning. See [Error handling](Errors).

## Nothing is buffered

There is no C library, so there is no `stdio` buffer, no `atexit`, and nothing
to flush. A write is a `write`:

```
write(1, "hello, world\n", 13) = 13
```

Output cannot be lost to an abnormal exit, because it was never held anywhere
but the kernel. The cost is the obvious one — a program that writes a byte at a
time makes a system call per byte, so building a line in a
[`builder`](Memory) and writing it once is the program's job, not the
runtime's.

## What it does not do

The list is short and worth stating plainly:

- **`EINTR` means wind down, not retry.** The handler is installed without
  `SA_RESTART`, deliberately, because the point is to reach the cleanup. A
  program that should survive a signal and carry on has no way to say so yet.
- **Only `SIGINT` and `SIGTERM` are caught.** `SIGHUP`, `SIGQUIT` and the user
  signals keep their defaults, so a program that should reload on `SIGHUP`
  cannot be written.
- **Inherited descriptors are not touched.** What the parent passed in stays
  open; mereo closes what the program itself acquires.
- **No daemonising, no `umask`, no working-directory discipline.** These are
  policy, and a program that wants them calls for them itself.

## See also

- [Resources and lifetimes](Resources) — the release tower
- [Error handling](Errors) — `ensure`, and the record
- [Control flow](Control-flow) — `leave program`, and where the tower is entered
