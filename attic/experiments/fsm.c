// explicit state register + 2-D transition matrix (Mealy machine)
static inline long sc1(long n, long a1){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a1):"rcx","r11","memory");return r;}
static inline long sc2(long n, long a1, long a2){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a1),"S"(a2):"rcx","r11","memory");return r;}
static inline long sc3(long n, long a1, long a2, long a3){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a1),"S"(a2),"d"(a3):"rcx","r11","memory");return r;}

enum { S_OPEN, S_READ, S_WRITE, S_CLOSE, S_HALT, NSTATES };
#define SIGN(x)    ((unsigned long)(x) >> 63)
#define DISPATCH() goto *handler[state]

void _start(void) {
    long fd, count, code, in;
    int  state;
    char buffer[4096];

    static const unsigned char nxt[NSTATES][2] = {
        [S_OPEN]  = { S_READ,  S_HALT  },
        [S_READ]  = { S_WRITE, S_CLOSE },
        [S_WRITE] = { S_CLOSE, S_CLOSE },
        [S_CLOSE] = { S_HALT,  S_HALT  },
        [S_HALT]  = { S_HALT,  S_HALT  },
    };
    static const long out[NSTATES][2] = {
        [S_OPEN]  = { 0, 1 },
        [S_READ]  = { 0, 2 },
        [S_WRITE] = { 0, 3 },
    };
    static const void* handler[NSTATES] = {
        [S_OPEN]=&&do_open, [S_READ]=&&do_read, [S_WRITE]=&&do_write,
        [S_CLOSE]=&&do_close, [S_HALT]=&&do_halt,
    };

    state = S_OPEN;
do_open:
    fd    = sc2(2, (long)"lorem_ipsum.txt", 0);
    in    = SIGN(fd);
    code = out[state][in];
    state = nxt[state][in];
    DISPATCH();
do_read:
    count = sc3(0, fd, (long)buffer, sizeof buffer);
    in    = SIGN(count);
    code = out[state][in];
    state = nxt[state][in];
    DISPATCH();
do_write:
    in    = SIGN(sc3(1, 1, (long)buffer, count));
    code = out[state][in];
    state =
    nxt[state][in];
    DISPATCH();
do_close:
    sc1(3, fd); state = nxt[state][0];
    DISPATCH();
do_halt:
    sc1(60, code); __builtin_unreachable();
}
