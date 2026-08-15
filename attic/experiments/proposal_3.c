// proposal_3: error handling via non-local exit (longjmp).
//
// The happy path has no checks. A failing syscall "throws" by longjmp-ing back to
// the single setjmp boundary. The inner frame (run_copy) carries NO error logic and
// does NO return-value propagation -- the jump blasts straight through it, which is
// what longjmp buys over a local goto. Uses GCC's freestanding __builtin_setjmp /
// __builtin_longjmp (no libc). Build -nostartfiles.

static inline long raw1(long n,long a){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a):"rcx","r11","memory");return r;}
static inline long raw2(long n,long a,long b){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a),"S"(b):"rcx","r11","memory");return r;}
static inline long raw3(long n,long a,long b,long c){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a),"S"(b),"d"(c):"rcx","r11","memory");return r;}

static void *recovery[5];          // __builtin_setjmp buffer (>= 5 words)
static volatile long eh_errno;     // longjmp only carries 1, so pass the errno here

// "throw": a failed syscall jumps non-locally back to the boundary.
static long try2(long n,long a,long b){
    long r = raw2(n,a,b);
    if (__builtin_expect(r < 0, 0)) { eh_errno = r; __builtin_longjmp(recovery, 1); }
    return r;
}
static long try3(long n,long a,long b,long c){
    long r = raw3(n,a,b,c);
    if (__builtin_expect(r < 0, 0)) { eh_errno = r; __builtin_longjmp(recovery, 1); }
    return r;
}

// inner operation: NOTHING about errors here. On failure the jump skips straight
// past this frame to the boundary -- so it must publish the fd it acquired, or the
// recovery block can't release it (longjmp runs no cleanup of skipped frames).
static __attribute__((noinline)) void run_copy(volatile long *fd_slot, char *buf){
    long fd = try2(2, (long)"lorem_ipsum.txt", 0);   // open
    *fd_slot = fd;                                   // publish for cleanup
    long count = try3(0, fd, (long)buf, 4096);       // read  (may jump)
    try3(1, 1, (long)buf, count);                    // write (may jump)
    raw1(3, fd);                                     // close
    *fd_slot = -1;                                   // released cleanly
}

void _start(void){
    volatile long fd = -1;     // volatile: must survive the longjmp for cleanup
    char buffer[4096];

    if (__builtin_setjmp(recovery) == 0){
        run_copy(&fd, buffer);
        raw1(60, 0);                       // success
    } else {
        if (fd >= 0) raw1(3, fd);          // unwind: close the fd run_copy leaked
        raw1(60, -eh_errno);               // exit with the errno
    }
    __builtin_unreachable();
}
