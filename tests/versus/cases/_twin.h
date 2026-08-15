/* The freestanding scaffolding every twin needs, written once: the syscalls,
   the entry point's obligations, and the error record. mereo emits the same
   set as static inline helpers, and a C programmer targeting -nostdlib writes
   exactly this before writing anything else.

   `_record` is the shape of mereo's failure report -- "PROGRAM: STAGE: STEP: "
   then the negative errno and a newline -- because a twin that skipped the
   report would be doing less work than the program it is compared against. */
#define SYS_read 0
#define SYS_write 1
#define SYS_open 2
#define SYS_close 3
#define SYS_exit_group 231
#define SYS_rt_sigaction 13

/* One wrapper per ARITY, because the ABI has one per arity: a call that takes
   one argument sets rdi and nothing else, and padding it out to three would
   emit two register loads the kernel never reads. */
static inline __attribute__((always_inline)) long _sys1(long n, long a) {
    long r;
    __asm__ volatile ("syscall" : "=a"(r)
        : "a"(n), "D"(a) : "rcx", "r11", "memory");
    return r;
}

static inline __attribute__((always_inline))
long _sys3(long n, long a, long b, long c) {
    long r;
    __asm__ volatile ("syscall" : "=a"(r)
        : "a"(n), "D"(a), "S"(b), "d"(c) : "rcx", "r11", "memory");
    return r;
}

static inline __attribute__((always_inline)) long _sigaction(long sig, long act) {
    long r;
    register long r10 __asm__("r10") = 8;   /* sizeof(sigset_t) */
    __asm__ volatile ("syscall" : "=a"(r)
        : "a"(SYS_rt_sigaction), "D"(sig), "S"(act), "d"(0), "r"(r10)
        : "rcx", "r11", "memory");
    return r;
}

static inline __attribute__((always_inline)) __attribute__((noreturn))
void _exit_group(long s) {
    __asm__ volatile ("syscall" : : "D"(s), "a"(SYS_exit_group)
                      : "rcx", "r11", "memory");
    __builtin_unreachable();
}

static inline __attribute__((always_inline)) void _write_value(long e) {
    char d[24];
    long n = e < 0, i = 22;
    unsigned long u = n ? -(unsigned long)e : (unsigned long)e;
    d[23] = '\n';
    do { d[i] = '0' + u % 10; u = u / 10; i = i - 1; } while (u);
    if (n) { d[i] = '-'; i = i - 1; }
    _sys3(SYS_write, 2, (long)d + i + 1, 23 - i);
}

/* ignore SIGPIPE: a closed pipe must come back as EPIPE, not kill the process */
#define IGNORE_SIGPIPE() \
    do { long _ign[4] = { 1, 0, 0, 0 }; _sigaction(13, (long)_ign); } while (0)

/* A program that HOLDS something must not be killed mid-flight by Ctrl-C -- the
   descriptors it owns would outlive the cleanup it was about to run. What a
   freestanding program can do is catch SIGINT/SIGTERM with a stub that simply
   RETURNS: the interrupted syscall comes back EINTR, the ordinary error path
   takes over, and the cleanup runs on the way out. The stub masks both signals
   on entry so a second Ctrl-C cannot re-enter it.
   Twins that own nothing must not define this -- the stub is real code, and
   emitting it unused would be the twin doing MORE than the program it is
   compared against, which is the same dishonesty in the other direction. */
#ifdef TWIN_INTERRUPT
__asm__(
  ".globl twin_sigstub\n"
  "twin_sigstub:\n"
  "  orq $0x4002, 296(%rdx)\n"   /* uc_sigmask |= SIGINT|SIGTERM */
  "  add $8, %rsp\n"             /* drop the unused pretcode slot */
  "  movl $15, %eax\n"           /* __NR_rt_sigreturn */
  "  syscall\n"
);
extern void twin_sigstub(void);
#define CLEANUP_ON_INTERRUPT()                                        \
    do { long _act[4] = { (long)twin_sigstub, 0x4000004, 0, 0 };      \
         _sigaction(2,  (long)_act);      /* SIGINT  */               \
         _sigaction(15, (long)_act); } while (0)   /* SIGTERM */
#endif

#define RECORD(s, e) \
    do { _sys3(SYS_write, 2, (long)(s), sizeof(s) - 1); _write_value(e); } while (0)
