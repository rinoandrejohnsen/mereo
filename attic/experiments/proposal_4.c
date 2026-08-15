// maybe.c, made to compile. The syscall "wrapper" checks its own result and, on
// failure, jumps to a cleanup label named at the call site -- so the happy path has
// no visible checks. A C function can't take a label or goto into its caller, so
// this is a statement-expression macro instead: it expands inside _start where the
// labels live, making `goto lbl` an ordinary forward jump. No setjmp, no dispatch,
// no reserved register -- this compiles to essentially the same code as simple.c.

#define sys1(n, a1, lbl) ({ long _r; \
    __asm__ volatile("syscall":"=a"(_r):"a"(n),"D"(a1):"rcx","r11","memory"); \
    if (__builtin_expect(_r < 0, 0)) goto lbl; _r; })
#define sys2(n, a1, a2, lbl) ({ long _r; \
    __asm__ volatile("syscall":"=a"(_r):"a"(n),"D"(a1),"S"(a2):"rcx","r11","memory"); \
    if (__builtin_expect(_r < 0, 0)) goto lbl; _r; })
#define sys3(n, a1, a2, a3, lbl) ({ long _r; \
    __asm__ volatile("syscall":"=a"(_r):"a"(n),"D"(a1),"S"(a2),"d"(a3):"rcx","r11","memory"); \
    if (__builtin_expect(_r < 0, 0)) goto lbl; _r; })

// cleanup-path syscalls don't route on error (a failing close/exit shouldn't loop us).
static inline long raw1(long n, long a1){ long r; \
    __asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a1):"rcx","r11","memory"); return r; }

char buffer[4096];

void _start(void){
    long code = 1;                                            // open failed
    long fd = sys2(2, (long)"lorem_ipsum.txt", 0, exit);      // open fail -> exit (no fd yet)

    code = 2;                                                 // read failed
    long count = sys3(0, fd, (long)buffer, sizeof buffer, close);

    code = 3;                                                 // write failed
    (void)sys3(1, 1, (long)buffer, count, close);

    code = 0;                                                 // success
close:                                                        // open-failure skips this
    raw1(3, fd);                                              // sys_close
exit:
    raw1(60, code);                                           // sys_exit with the stage code
    __builtin_unreachable();
}
