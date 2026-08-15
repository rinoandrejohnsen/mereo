// proposal_6 (C++ port of fast.c): every variable lives in ONE global object;
// _start gets no frame, no stack-protector canary, no stack buffer. Built with
// g++ this emits the same _start/buffer assembly as the C original (see below).

static inline void raw1(long n,long a){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a):"rcx","r11","memory");(void)r;}
static inline long raw2(long n,long a,long b){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a),"S"(b):"rcx","r11","memory");return r;}
static inline long raw3(long n,long a,long b,long c) {long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a),"S"(b),"d"(c):"rcx","r11","memory");return r;}

#define SYS(dst, call, divert) do { \
dst = (call); \
if (__builtin_expect((dst) < 0, 0)) { goto divert; } \
} while (0)

char  buffer[4096];

extern "C" void _start(void){
  long code = 0, fd, count;

  SYS(fd, raw2(2, (long)"lorem_ipsum.txt", 0),         do_error_1);

  SYS(count, raw3(0, fd, (long)buffer, sizeof buffer), do_error_2);

  SYS(count, raw3(1, 1, (long)buffer, count),          do_error_3);

  unwind_open:
  raw1(3, fd);
  exit:
  raw1(60, -code);
  __builtin_unreachable();

  do_error_1:
  code = 1;
  goto exit;
  do_error_2:
  code = 2;
  goto unwind_open;
  do_error_3:
  code = 3;
  goto unwind_open;
}
