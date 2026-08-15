# StructAsm: Prototype 5 (Data Structure Language)

## Core Philosophy
StructAsm Prototype 5 completely bridges the gap between a programming language and a parseable data structure. By structuring the code as a sequential YAML-like format, the language *is* the Abstract Syntax Tree (AST). 

It removes all compiler magic regarding code reordering. The execution flows perfectly top-to-bottom, explicitly modeling the happy path, the resource cleanup cascade, and the terminal exit state.

## The Architecture
The entire machine is a single data object with two main top-level keys:

1. **`flow:`** - The linear physical layout of the machine. It contains `state` blocks (execution), `unwind` blocks (cleanup cascade), and a terminal `state: exit`.
2. **`faults:`** - The aspect-oriented routing table. It maps specific API calls to their failure conditions.

---

## Example Syntax

```yaml
machine: process_image

# ==========================================
# 1. THE LINEAR EXECUTION & CASCADE
# ==========================================
flow:
  state: init
    call: open_file
  
  state: file_open
    call: allocate_buffer
    
  state: buffer_allocated
    call: parse_headers
    
  # The Unwind Cascade (Success & Failure paths fall through here)
  unwind: buffer_allocated
    call: deallocate_buffer
    
  unwind: file_open
    call: close_file
    
  # The Explicit Terminal State
  state: exit
    call: linux_exit


# ==========================================
# 2. THE ERROR ROUTING RULES
# ==========================================
faults:
  open_file:
    condition: result < 0
    # Compiler implicitly routes this fault to -> state: exit
    
  allocate_buffer:
    condition: result == 0
    # Compiler implicitly routes this fault to -> unwind: file_open
    
  parse_headers:
    condition: carry == 1
    # Compiler implicitly routes this fault to -> unwind: buffer_allocated
```

---

## How It Compiles (Parse & Emit)

Because the syntax is a strict data structure, writing a compiler for it is trivial. The compiler simply loads the YAML and emits x86-64 instructions line-by-line.

1. **Linear Layout:** The `flow` array is written to the executable exactly as it appears. 
2. **Fault Injection:** When emitting `call: allocate_buffer`, the compiler checks the `faults` dictionary. Finding a match, it injects `test rax, rax` and `jz .fault_allocate_buffer`.
3. **The Cascade:** The compiler emits `.unwind_buffer_allocated:` and `.unwind_file_open:` labels sequentially, naturally building the cascading epilogue without any complex AST reordering.
4. **Safety Verification:** Before emitting any code, the data structure can be fed into formal verification scripts to mathematically prove that every acquired resource is successfully mapped to an unwind block.
