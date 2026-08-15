mereo has no functions. Reuse is by **splicing**: a template is copied into each
place it is used, with its locals renamed. There is no call, no return, no stack
frame and no calling convention.

```ada
shout (area, length) is
  i is 0
  fix goes
    c is [area + i : 1]
    c is c - 32 when c >= 97 && c <= 122
    [area + i : 1] is c
    i is i + 1
    repeat fix when i < length
  end
end
```

Used twice, that yields two copies, each with its own `i` and `c`. A syscall is
a template too: `terminal.write (...)` splices a `syscall` instruction in place.

## Ports

A template's parameters are **ports**, wired by name at each use. A port's
direction is derived from what the body does with it — read it and it is an
input, assign it and it is an output — so directions are not declared
separately. Because ports are matched by name, adding one to a template does not
disturb existing uses, but *renaming* one breaks every use, which is why
`core.mereo` adds a separate template rather than a `base` port to an existing
one.

## Groups

Templates that belong together are gathered into a stateless group and reached
through its name:

```ada
  text.find (data is block, length is count, byte is 10, offset is at)
```

A group holds no state and acquires nothing; it exists so related work has one
name. The byte layer of `core.mereo` is such a group.

## What splicing costs and forbids

Splicing has no frame, so:

- **Recursion is refused**, in those terms — *"mereo is function-free, so a
  procedure cannot recurse"*.
- There are **no function pointers** and no dynamic dispatch, so every branch
  target is visible in the source.
- Code **size grows with use**, since each use is a copy. In exchange, there is
  no cost to weigh in deciding whether reuse is worthwhile: an unused definition
  emits nothing at all.

A template body that opens with a declaration, a loop or a block is a general
**procedure**, spliced whole. A body that is a single call is a simple
delegation, and the restriction to one call is what lets the release ladder be
derived for a resource's `acquire` and `release`.

## Raw instructions

A template may be a machine instruction rather than mereo steps, with operands
bound to registers by name:

```ada
population_count is pure assembly "popcnt %[source], %[result]"
  source in register
  result out register
end
```

`pure` marks an instruction with no side effects, so the C compiler may fold,
hoist or delete it; without it the instruction is volatile. `clobbers` names
what the instruction destroys — registers, condition codes, or `memory` as a
barrier. A system call is the special case `assembly "syscall"`, and `final`
marks one that does not return.
