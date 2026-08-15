#include <stdio.h>

// Define dummy opcodes for our virtual machine
enum Opcodes {
  OP_INCREMENT,
  OP_DECREMENT,
  OP_PRINT,
  OP_HALT
};

void run_interpreter(const int* bytecode) {
  int accumulator = 0;
  int pc = 0; // Program counter

  // 1. Create a jump table populated with label addresses
  static const void* dispatch_table[] = {
    [OP_INCREMENT] = &&do_increment,
    [OP_DECREMENT] = &&do_decrement,
    [OP_PRINT] = &&do_print,
    [OP_HALT] = &&do_halt
  };

  // 2. Define a macro helper to handle our next jump
  #define DISPATCH() goto *dispatch_table[bytecode[pc++]]

  // 3. Kick off the execution loop by jumping to the very first opcode
  DISPATCH();

  // --- Instruction Handlers ---

  do_increment:
    accumulator += 1;
    DISPATCH(); // Jump directly to the next instruction

  do_decrement:
    accumulator -= 1;
    DISPATCH(); // Jump directly to the next instruction

  do_print:
    printf("Current Accumulator Value: %d\n", accumulator);
    DISPATCH(); // Jump directly to the next instruction

  do_halt:
    printf("Execution Finished.\n");
    return;
}

int main() {
  // Array of bytecode instructions to execute sequentially
  int program[] = {
    OP_INCREMENT,
    OP_DECREMENT,
    OP_PRINT,
    OP_HALT
  };

  run_interpreter(program);

  return 0;
}
