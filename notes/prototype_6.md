# StructAsm: Prototype 6 (MOP + ASM Language)

## Core Philosophy
Prototype 6 transforms the language from a sequential execution flow into a **Mereology-Oriented Abstract State Machine**. It bridges the gap between a parseable data structure and formal systems theory. The code *is* the Abstract Syntax Tree (AST), but instead of modeling linear control flow, it mathematically models the **Ontology** (parts and wholes) and the **Transition Rules** (concurrent behavior).

It removes arbitrary loops, sequential gotos, and class encapsulation. Execution is the continuous, parallel evaluation of structural rules against a Universal Whole.

## The Architecture
The entire machine is a single data object with three main top-level keys:

1. **`ontology:`** - Defines the structural components (Atoms) and how they fuse into Wholes (Parts). This maps to General Systems Theory's hierarchical structure.
2. **`rules:`** - The Abstract State Machine (ASM) transitions. Rules are independent blocks that define structural guards (Parthood) and synchronous updates.
3. **`universe:`** - The initial instantiation of the Universal State.

---

## Example Syntax (File Processor)

```yaml
machine: file_processor

# ==========================================
# 1. THE ONTOLOGY (Mereological Structure)
# ==========================================
ontology:
  atoms:
    - fd: Int
    - buffer: ByteArray[4096]
    - bytes_read: Int
    - exit_code: Int
    - stage: Enum[INIT, OPENED, READ, EXIT]
  
  parts:
    # A Part is purely the fusion of its structural atoms
    - AppState: fd + buffer + bytes_read + exit_code + stage


# ==========================================
# 2. THE RULES (ASM Transitions)
# ==========================================
# Rules execute continuously and concurrently. If a guard matches, 
# the transition is evaluated synchronously at the tick boundary.
rules:
  open_file:
    guard:
      require: Parthood(AppState, target)
      condition: stage(target) == INIT
    transition:
      # Synchronous assignments (:= semantics)
      - fd(target) := sys_open("lorem_ipsum.txt", O_RDONLY)
      - exit_code(target) := if fd < 0 then 1 else 0
      - stage(target) := if fd < 0 then EXIT else OPENED
      
  read_file:
    guard:
      require: Parthood(AppState, target)
      condition: stage(target) == OPENED
    transition:
      - bytes_read(target) := sys_read(fd(target), buffer(target), 4096)
      - exit_code(target) := if bytes_read < 0 then 2 else 0
      - stage(target) := if bytes_read < 0 then EXIT else READ

  close_file:
    guard:
      require: Parthood(AppState, target)
      condition: stage(target) == READ
    transition:
      - _ := sys_close(fd(target))
      - stage(target) := EXIT

  terminate:
    guard:
      require: Parthood(AppState, target)
      condition: stage(target) == EXIT
    transition:
      - _ := sys_exit(exit_code(target))


# ==========================================
# 3. THE UNIVERSE (Initial State)
# ==========================================
universe:
  main: AppState(fd: -1, bytes_read: 0, exit_code: 0, stage: INIT)
```

---

## How It Compiles (Parse & Emit)

Because the syntax is a strict data structure, writing a compiler for it is highly deterministic. The compiler translates mereology and ASM into optimal, lock-free C/Assembly:

1. **Flattened Memory:** The `ontology` array maps perfectly to C `structs`. `AppState` becomes a contiguous block of memory containing `fd`, `buffer`, etc. Parthood requirements resolve to zero-cost static byte-offsets.
2. **Double Buffering:** The compiler generates a `current_state` and `next_state` buffer to fulfill the ASM synchronous `transition` blocks.
3. **Guard Evaluation:** The compiler maps every `rule` into a standalone function that accepts a pointer to the `current_state`. The `guard` block acts as the initial `if` statement.
4. **Auto-Concurrency via Disjointness:** Before emitting the tick loop, the compiler checks the `transition` blocks for all rules. If it proves mathematically that `open_file` and another rule do not write to overlapping parts, it automatically emits them as parallel threads. 
5. **No Cleanup Cascades Required:** The state machine naturally handles cleanup. If `sys_read` fails, the state transitions to `EXIT`, and the system elegantly terminates based on the deterministic matching of rules, eliminating the need for complex `.unwind` labels or `goto` statements.
