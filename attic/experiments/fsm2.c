// fsm.c, recurrence broken: keep the explicit state register + goto *h[state],
// but assign `state` the CONSTANT successor per transition instead of reading
// nxt[state][in]. No 2-D tables; step N+1 no longer depends on step N.
static inline long sc1(long n, long a1){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a1):"rcx","r11","memory");return r;}
static inline long sc2(long n, long a1, long a2){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a1),"S"(a2):"rcx","r11","memory");return r;}
static inline long sc3(long n, long a1, long a2, long a3){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a1),"S"(a2),"d"(a3):"rcx","r11","memory");return r;}

enum { S_OPEN, S_READ, S_WRITE, S_OK, S_CLOSE, S_HALT, NSTATES };
#define DISPATCH() goto *h[state]

void _start(void) {
    long fd, count, code;
    int  state = S_OPEN;
    char buffer[4096];
    static const void* h[NSTATES] = {
        [S_OPEN]=&&do_open,
        [S_READ]=&&do_read,
        [S_WRITE]=&&do_write,
        [S_OK]=&&do_ok,
        [S_CLOSE]=&&do_close,
        [S_HALT]=&&do_halt,
    };

    DISPATCH();

    do_open:
        code = 1;
        fd = sc2(2, (long)"lorem_ipsum.txt", 0);
        state = (fd < 0) ? S_HALT : S_READ;
        DISPATCH();
    do_read:
        code = 2;
        count = sc3(0, fd, (long)buffer, sizeof buffer);
        state = (count < 0) ? S_CLOSE : S_WRITE;
        DISPATCH();
    do_write:
        code = 3;
        state = (sc3(1, 1, (long)buffer, count) < 0) ? S_CLOSE : S_OK;
        DISPATCH();
    do_ok:
        code = 0;
        state = S_CLOSE;
        DISPATCH();
    do_close:
        sc1(3, fd);
        state = S_HALT;
        DISPATCH();
    do_halt:
        sc1(60, code);
        __builtin_unreachable();
}
