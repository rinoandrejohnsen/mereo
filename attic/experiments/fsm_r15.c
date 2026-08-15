// proposal_1 (fsm_const) MERGED with the r15 error-status ABI.
//
// The dispatch is already in our path every step, so we let it BE the r15
// boundary check. Handlers carry no error logic: a forward syscall latches its
// -errno into r15 branchlessly (cmovs), and each dispatch routes on r15 to that
// state's unwind target. r15 is sticky (holds the first failure) and carries the
// real errno out to exit. Build with -ffixed-r15.

register long volatile eh_error asm("r15");   // 0 = ok; <0 = -errno of first failure (sticky)

// forward-path syscall: run it, then latch a negative result into r15 with no
// branch. cmovs fires only when rax<0, so a success leaves r15 untouched.
// %0 == eh_error (r15) is declared "+r" so GCC KNOWS the asm writes it; without
// this it folds `eh_error != 0` to false and deletes every check.
static inline long sc2(long n, long a, long b){
    long r = n;
    __asm__ volatile(
        "syscall \n\t"
        "test %%rax, %%rax \n\t"
        "cmovs %%rax, %0"
        : "+r"(eh_error), "+a"(r)
        : "D"(a), "S"(b)
        : "rcx","r11","memory","cc");
    return r;
}
static inline long sc3(long n, long a, long b, long c){
    long r = n;
    __asm__ volatile(
        "syscall \n\t"
        "test %%rax, %%rax \n\t"
        "cmovs %%rax, %0"
        : "+r"(eh_error), "+a"(r)
        : "D"(a), "S"(b), "d"(c)
        : "rcx","r11","memory","cc");
    return r;
}
// cleanup-path syscall: raw, never touches r15 (preserve the first error).
static inline long raw1(long n, long a){
    long r; __asm__ volatile("syscall"
        : "=a"(r) : "a"(n), "D"(a) : "rcx","r11","memory");
    return r;
}

enum { S_OPEN, S_READ, S_WRITE, S_CLOSE };

void _start(void){
    long fd, count;
    char buffer[4096];

    // [state][ r15 set? ] -> next handler.  col 0 = forward, col 1 = unwind target.
    static const void *const h[][2] = {
        [S_OPEN]  = { &&do_read,  &&do_halt  },   // open failed: nothing to close
        [S_READ]  = { &&do_write, &&do_close },   // fd is open -> close it
        [S_WRITE] = { &&do_close, &&do_close },   // exit code lives in r15
        [S_CLOSE] = { &&do_halt,  &&do_halt  },
    };
    #define NEXT(here) goto *h[here][eh_error != 0]

    eh_error = 0;

do_open:
    fd = sc2(2, (long)"lorem_ipsum.txt", 0);          // open(path, O_RDONLY)
    NEXT(S_OPEN);
do_read:
    count = sc3(0, fd, (long)buffer, sizeof buffer);  // read
    NEXT(S_READ);
do_write:
    sc3(1, 1, (long)buffer, count);                   // write to stdout
    NEXT(S_WRITE);
do_close:
    raw1(3, fd);                                      // close (no latch)
    NEXT(S_CLOSE);
do_halt:
    raw1(60, -eh_error);                              // exit(errno); 0 on success
    __builtin_unreachable();
}
