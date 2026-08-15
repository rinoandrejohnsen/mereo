static inline long syscall1(long n, long a1) {
  long ret;
  __asm__ volatile (
    "syscall"
    : "=a" (ret)
    : "a" (n), "D" (a1)
    : "rcx", "r11", "memory"
  );
  return ret;
}

static inline long syscall2(long n, long a1, long a2) {
  long ret;
  __asm__ volatile (
    "syscall"
    : "=a" (ret)
    : "a" (n), "D" (a1), "S" (a2)
    : "rcx", "r11", "memory"
  );
  return ret;
}

static inline long syscall3(long n, long a1, long a2, long a3) {
  long ret;
  __asm__ volatile (
    "syscall"
    : "=a" (ret)
    : "a" (n), "D" (a1), "S" (a2), "d" (a3)
    : "rcx", "r11", "memory"
  );
  return ret;
}

enum Opcodes {
  OP_INIT = 0,
  OP_READ = 1,
  OP_WRITE = 2,
  OP_CLOSE = 3,
  OP_HALT = 4
};

#define DISPATCH() goto *dispatch_table[bytecode[state]]

unsigned char bytecode[] = { OP_INIT, OP_READ, OP_WRITE, OP_CLOSE, OP_HALT };

void _start() {
  int fd;
  long code;
  char buffer[4096];
  long count;
  long written;
  enum Opcodes state;

  static const void* dispatch_table [] = {
    &&init,
    &&file_open,
    &&read_file,
    &&close,
    &&halt
  };

  //DISPATCH();

  init:
  code = 1;
  fd = syscall2(2, (long)"lorem_ipsum.txt", 0); // sys_open, O_RDONLY
  if (__builtin_expect(fd < 0, 0)) { state = OP_HALT; } else { state = OP_READ; }
  DISPATCH();

  file_open:
  code = 2;
  count = syscall3(0, fd, (long)buffer, sizeof(buffer)); // sys_read
  if (__builtin_expect(count < 0, 0)) {  state = OP_CLOSE; } else { state = OP_WRITE; }
  DISPATCH();

  read_file:
  code = 3;
  written =  syscall3(1, 1, (long)buffer, count);
  if (__builtin_expect(written > 0, 1)) { code = 0; }
  state = OP_CLOSE;
  DISPATCH();

  close:
  syscall1(3, fd); // sys_close
  state = OP_HALT;
  DISPATCH();

  halt:
  syscall1(60, code); // sys_exit
  __builtin_unreachable();
}
