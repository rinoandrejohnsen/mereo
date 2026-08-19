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

**No ownership transfer.** A resource cannot be transferred conditionally or
stored in a data structure. It is released at the end of the scope that acquired
it, and its name ends there with it. This is the restriction that
removes drop flags: what a scope holds is known where it is written, so the
release point is a label rather than a runtime decision. It is why `linux`
offers a stateless `channel` for pipes as well as a resource that owns one — two
descriptors have two lifetimes, and closing the write end to signal end-of-input
while still reading is the ordinary way to use a pipe.

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

**One spelling, two meanings.** `slot is 8 bytes` is storage in a program body
and a register word as a resource's state field, because a state field is a run
of bytes only when it is wider than a register. Both rules are right on their
own; sharing a spelling is not, and the collision compiles rather than
complaining.

**No editor support beyond highlighting.** There is no language server. Syntax
highlighting for Kate and a standalone highlighter are kept in step with the
compiler by a gate.

## Scale

The corpus is small. The largest program is a TLS client; the rest are examples
and tests. Every line of it comes from the project itself, with no outside users
and no independent implementation, so no figure in this article should be read
as describing behaviour at a scale the language has not been used at.
