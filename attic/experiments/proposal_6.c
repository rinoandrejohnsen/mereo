// proposal_6: proposal_5 with NO stack -- every variable lives in ONE global struct
// (the "Universe"). _start gets no frame, no stack-protector canary, no stack buffer;
// the whole machine is a single global object the dispatcher mutates in place.

static inline long raw1(long n,long a){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a):"rcx","r11","memory");return r;}
static inline long raw2(long n,long a,long b){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a),"S"(b):"rcx","r11","memory");return r;}
static inline long raw3(long n,long a,long b,long c){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a),"S"(b),"d"(c):"rcx","r11","memory");return r;}

static struct universe {
    void *program[6];
    int   pc;
    long  code, fd, count;
    char  buffer[4096];
} M;

#define SYS(dst, call, divert) do { \
    dst = (call); \
    if (__builtin_expect((dst) < 0, 0)) { M.code = (dst); M.program[M.pc] = &&divert; } \
} while (0)
#define NEXT() goto *M.program[M.pc++]

void _start(void){
    M.program[0] = &&do_open;
    M.program[1] = &&do_read;
    M.program[2] = &&do_write;
    M.program[3] = &&do_close;
    M.pc = 0;
    M.code = 0;
    NEXT();

do_open:
    SYS(M.fd,    raw2(2, (long)"lorem_ipsum.txt", 0),            do_halt);
    NEXT();
do_read:
    SYS(M.count, raw3(0, M.fd, (long)M.buffer, sizeof M.buffer), do_close);
    NEXT();
do_write:
    SYS(M.count, raw3(1, 1, (long)M.buffer, M.count),           do_close);
    NEXT();
do_close:
    raw1(3, M.fd);
do_halt:
    raw1(60, -M.code);
    __builtin_unreachable();
}
