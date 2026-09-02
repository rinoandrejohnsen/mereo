A program on a Unix system owes its surroundings a short list of things. Close
what you open. Do not die halfway through holding a lock or a temporary file.
Say on standard error what went wrong, say it in the exit status, and say it
about the right descriptor. Do not report a broken pipe as a fault of your own.
Do not lose output because you were interrupted before a buffer was flushed. Do
not pass on half a stream and call it success.

Most languages leave that list to the programmer and provide the tools —
destructors, `defer`, `atexit`, signal handlers, `errno`. mereo makes the list
structural: **there is no way to write the program that gets it wrong**,
because the mechanisms that would otherwise be separate are one path.

## Before the first step

**The three standard descriptors are made to be the three standard
descriptors.** A program started with one of them closed gets that number back
from its own `open` — descriptors are handed out lowest-free-first — and from
then on everything it writes to "standard output" goes into the file it opened,
and its diagnostics into whatever took descriptor 2. Nothing in the program can
see this: the numbers 0, 1 and 2 are all it has to go on. So a program that can
open anything checks first, in one `poll` (a closed descriptor answers
`POLLNVAL` whatever was asked for, and a zero timeout cannot block), and opens
`/dev/null` over any gap, upward, so each lands on the number it is meant to
have.

**`SIGPIPE` is always ignored.** The default disposition kills the process when
the reader of a pipe goes away, which is why a naive program in a pipeline dies
silently and takes its cleanup with it. Ignoring it turns that into an ordinary
`EPIPE` from the write, which the program can then handle like anything else.

**`SIGHUP`, `SIGINT` and `SIGTERM` are caught — but only when the program owns
something, and only where they are not already ignored.** A program that holds
nothing has nothing to clean up, so the default disposition is correct and
nothing is installed. A program that holds a descriptor installs a stub that
simply *returns*:

```
poll([{fd=0}, {fd=1}, {fd=2}], 3, 0)                  = 0
rt_sigaction(SIGPIPE, {sa_handler=SIG_IGN, …}, NULL)  = 0
rt_sigaction(SIGHUP,  NULL, {sa_handler=SIG_DFL, …})  = 0
rt_sigaction(SIGHUP,  {sa_handler=0x4000f0, …}, NULL) = 0
rt_sigaction(SIGINT,  NULL, {sa_handler=SIG_DFL, …})  = 0
rt_sigaction(SIGINT,  {sa_handler=0x4000f0, …}, NULL) = 0
rt_sigaction(SIGTERM, NULL, {sa_handler=SIG_DFL, …})  = 0
rt_sigaction(SIGTERM, {sa_handler=0x4000f0, …}, NULL) = 0
```

Returning is the whole trick. The interrupted system call comes back `EINTR`,
which is a failure like any other, and failure already has somewhere to go.

The disposition is **read before it is written**. An inherited `SIG_IGN` is an
instruction from whoever started the program — it is what `nohup` sets, and what
a shell without job control leaves on a background job so a terminal Ctrl-C does
not reach it — and taking the signal anyway would overrule a decision that was
not the program's to make. Only `SIG_DFL` and `SIG_IGN` survive an `execve`, so
`SIG_IGN` is the one value worth testing for.

SIGHUP belongs with the other two because it is what closing a terminal window
and dropping a connection send: leaving it at its default would make the
ordinary way a session ends the one way the tower does not run. SIGQUIT keeps
its default on purpose — dumping core is the whole point of it, and a program
that tidied up first would be hiding the state someone asked to see.

## The single path out

That is where the mechanisms meet. A signal becomes an error; an error enters
the release tower; the tower is the only way out:

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
handler was written, no flag recorded that the file was open. The same tower
serves the normal exit, a failed check and an interrupt, so no path skips it.

## Saying what happened

Two errno values end a program **without** a diagnostic, because neither is a
fault in the program. They are not the same event, and they do not end the same
way.

**`EPIPE`** — the reader of a pipe has gone. Nobody is waiting to hear about it.
Release everything and exit **0**:

```
$ ./hello | head -c 0
$ echo $?
0
```

**`EINTR`** — an interrupt arrived. Somebody *is* waiting to hear about it, and
a wait status of 0 would tell a shell loop, `xargs`, `make` and any supervisor
that the work finished. So the tower runs exactly as before, and then, with
everything released, the program puts the signal's default disposition back,
unblocks it and sends it to itself. The parent reads the status it would have
read had mereo never caught the signal:

```
$ ./holder ; echo $?        # ^C while it is blocked
130                         # ...and WIFSIGNALED, which 130 alone is not
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

## Neither half of a transfer is short

`file.write` carries `ensure written == count`: a write that moved fewer bytes
than it was given is a failure, not a thing to shrug at. `file.fill` is the same
refusal on the way in — it reads until the buffer is full or the stream ends, so
`count < capacity` means end of stream and nothing else. Plain `file.read` still
hands back whatever had arrived, which is what a program wanting to react to
each block as it comes wants; the difference is that the complete read now has a
name, so a filter that reads once is a choice rather than an oversight.

A stream whose length is not known still wants the outer refill loop, because
every read is bounded by the buffer it was given. `examples/wcl.mereo` is the
shape.

## What it does not do

The list is short and worth stating plainly:

- **`EINTR` means wind down, not retry.** The handler is installed without
  `SA_RESTART`, deliberately, because the point is to reach the cleanup. A
  program that should survive a signal and carry on has no way to say so yet.
- **Ctrl-Z leaves the terminal as the program set it.** SIGTSTP keeps its
  default, so the process stops as it should — but a program driving a terminal
  in raw mode is stopped with those settings still applied, and the shell that
  gets the terminal back has no echo and no line buffering until the program is
  continued. Restoring across a stop needs a resource to be able to say what
  "suspended" means for it, which is a language question and not a runtime one.
- **`SIGQUIT` and the user signals keep their defaults**, so a program that
  should reload on a signal cannot be written.
- **Inherited descriptors are not touched.** What the parent passed in stays
  open; mereo closes what the program itself acquires. The guard above repairs
  descriptors 0, 1 and 2 when they are *missing* — it does not reach for what
  is there.
- **No daemonising, no `umask`, no working-directory discipline.** These are
  policy, and a program that wants them calls for them itself.

## See also

- [Resources and lifetimes](Resources) — the release tower
- [Error handling](Errors) — `ensure`, and the record
- [Control flow](Control-flow) — `leave program`, and where the tower is entered
