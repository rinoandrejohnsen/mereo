# Limitations

Some of what follows is deliberate and unlikely to change; some is unfinished.
They are separated here because the distinction matters when judging the
language.

## By design

**No functions, and so no recursion, no function pointers and no dynamic
dispatch.** Splicing has no frame to recurse in or to point at. Recursion is
refused by the transpiler in those terms. Every branch target is visible in the
source, and code size grows with each use of a template.

**No dynamic allocation.** There is no libc and no allocator; memory is where it
was declared. A program that needs a variable-sized working set must size a
buffer for the worst case or map pages itself.

**No ownership transfer.** A resource cannot be moved, handed to a template as a
value, or stored in a data structure. This is the restriction that removes drop
flags, and it has visible consequences: there is no `pipe` resource owning both
ends, because it could acquire the pair but could not hand either out. What
ships instead is a stateless `channel` whose one method makes the pair, with each
end adopted separately.

**One platform.** Linux on x86-64. The system call layer is written to that ABI.

**No generics, and everything is bytes.** There is no `span` of anything but
bytes, and an array of scalars would need one definition per element width.

**No separate compilation.** A program is a single translation unit.

**No concurrency.** There are no threads, no async, and no atomics beyond a
memory fence primitive.

## Unfinished

**A small library.** Two files, grown from measured demand. There is no
networking beyond raw sockets, no date handling, no formatted output beyond
decimal and hexadecimal, no sorting and no data structures.

**Language gaps found by writing real programs.** A run of seven, all of the
same shape — a view is a lens over a named backing, and several things wanted to
be a view but could not be. Six are closed: a view may now sit at an address
computed while running or over another view's field; a layout field may be a run
of text; the argument and environment vectors may be indexed by a value rather
than a literal; and a procedure body may both open with a memory store and call
a primitive, so one method can fill a record and then make the syscall that
takes it.

What remains of that run is the last one, and only half of it. A **procedure**
method may read its own state as bytes; a **single-call** method — an `acquire`
or a `release`, which resolve their arguments by name — may not. So
`linux.close (descriptor is [pair + 0 : 4])` is still refused, which is why
there is no `pipe` resource owning both ends: it can hand each one out but
cannot close them.

**One spelling, two meanings.** `slot is 8 bytes` is storage in a program body
and a register word as a resource's state field, because a state field is a run
of bytes only when it is wider than a register. Both rules are right on their
own; sharing a spelling is not, and the collision compiles rather than
complaining.

**A known code-size excess.** The stage markers that make the layout claim
checkable prevent the compiler merging otherwise identical error blocks. See
[Performance](performance.md).

**No editor support beyond highlighting.** A language server existed and was
removed; syntax highlighting for Kate and a standalone highlighter remain, kept
in step with the compiler by a gate.

## Scale

The corpus is small. The largest program is a TLS client; the rest are examples
and tests. Every line of it comes from the project itself, with no outside users
and no independent implementation, so no figure in this article should be read
as describing behaviour at a scale the language has not been used at.
