// proposal_7: proposal_4 (maybe.c) with NO stack -- every variable in ONE global
// struct ("Universe"). Same statement-expression macro goto-cleanup, but
// code/fd/count/buffer live in global .bss instead of registers. Carries stage
// codes (1/2/3) like proposal_4, not the real errno.

#define sys2(n, a1, a2, lbl) ({ long _r; \
    __asm__ volatile("syscall":"=a"(_r):"a"(n),"D"(a1),"S"(a2):"rcx","r11","memory"); \
    if (__builtin_expect(_r < 0, 0)) goto lbl; _r; })
#define sys3(n, a1, a2, a3, lbl) ({ long _r; \
    __asm__ volatile("syscall":"=a"(_r):"a"(n),"D"(a1),"S"(a2),"d"(a3):"rcx","r11","memory"); \
    if (__builtin_expect(_r < 0, 0)) goto lbl; _r; })
static inline long raw1(long n, long a1){ long r; \
    __asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a1):"rcx","r11","memory"); return r; }

static struct universe {
    long code, fd, count;
    char buffer[4096];
} M;

void _start(void){
    M.code = 1;                                                   // open failed
    M.fd   = sys2(2, (long)"lorem_ipsum.txt", 0, exit);           // open fail -> exit (no fd yet)

    M.code = 2;                                                   // read failed
    M.count = sys3(0, M.fd, (long)M.buffer, sizeof M.buffer, close);

    M.code = 3;                                                   // write failed
    (void)sys3(1, 1, (long)M.buffer, M.count, close);

    M.code = 0;                                                   // success
close:                                                           // open-failure skips this
    raw1(3, M.fd);                                               // sys_close
exit:
    raw1(60, M.code);                                            // sys_exit with the stage code
    __builtin_unreachable();
}
