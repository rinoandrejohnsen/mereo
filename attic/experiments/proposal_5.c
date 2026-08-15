// proposal_5: reconfigurable program-counter machine + label-passing error handling.
//
// The path is an array of LABEL ADDRESSES walked by pc++ (direct-threaded), with NO
// per-step checks. A failing syscall reconfigures the path: it splices the divert
// label -- named at the call site, like proposal_4 -- into program[pc], so the walk
// flows into the cleanup cascade. Only the syscall touches error state. Because the
// carried dependency is pc++ (a counter), not state=table[state], there's no
// recurrence -- so this stays fast, unlike the Mealy machine. Build -nostartfiles.

static inline long raw1(long n,long a){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a):"rcx","r11","memory");return r;}
static inline long raw2(long n,long a,long b){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a),"S"(b):"rcx","r11","memory");return r;}
static inline long raw3(long n,long a,long b,long c){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a),"S"(b),"d"(c):"rcx","r11","memory");return r;}

char buffer[4096];

// run a syscall; on error, stash -errno and splice the divert label into the path.
#define SYS(dst, call, divert) do { \
    dst = (call); \
    if (__builtin_expect((dst) < 0, 0)) { code = (dst); program[pc] = &&divert; } \
} while (0)
#define NEXT() goto *program[pc++]

void _start(void){
    // static -> lives in .data (loader-initialized), avoiding a movaps to a stack
    // that the kernel hands _start at a different alignment than GCC assumes.
    static void *program[6] = { &&do_open, &&do_read, &&do_write, &&do_close };
    int  pc = 0;
    long code = 0, fd, count;

    NEXT();                                    // start walking the path

do_open:
    SYS(fd,    raw2(2, (long)"lorem_ipsum.txt", 0),        do_halt);   // open fail -> halt (no fd)
    NEXT();
do_read:
    SYS(count, raw3(0, fd, (long)buffer, sizeof buffer),   do_close);  // read fail -> close
    NEXT();
do_write:
    SYS(count, raw3(1, 1, (long)buffer, count),            do_close);  // write fail -> close
    NEXT();
do_close:
    raw1(3, fd);                               // fall through to halt
do_halt:
    raw1(60, -code);                           // exit(errno); 0 on success
    __builtin_unreachable();
}
