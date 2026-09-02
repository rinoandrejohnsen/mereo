/* The freestanding scaffolding every twin needs, written once: the syscalls,
   the entry point's obligations, and the error record. mereo emits the same
   set as MACROS, and so does this -- a `static inline
   __attribute__((always_inline))` function is not the same thing to GCC, and
   the difference showed up here: the `early return (on trees)` predictor marks
   the branch guarding an early `return` unlikely, which lays the caller out
   around a function boundary that inlining then removes. Comparing mereo's
   macros against the twin's functions would have measured that heuristic
   rather than the two programs. A C programmer targeting -nostdlib writes this
   scaffolding before writing anything else; which of the two forms they reach
   for is exactly the choice being held equal.

   Two rules come with a macro and are kept by hand below: a parameter carries
   no type, so each is used as `(long)(x)` where the prototype used to convert
   it; and a parameter is TEXT, so the names are underscored to stay out of the
   way of whatever a twin calls its own variables. */

/* `RECORD` is the shape of mereo's failure report -- "PROGRAM: STAGE: STEP: "
   then the negative errno and a newline -- because a twin that skipped the
   report would be doing less work than the program it is compared against. */
#define SYS_read 0
#define SYS_write 1
#define SYS_open 2
#define SYS_close 3
#define SYS_poll 7
#define SYS_rt_sigaction 13
#define SYS_rt_sigprocmask 14
#define SYS_getpid 39
#define SYS_kill 62
#define SYS_exit_group 231

/* One wrapper per ARITY, because the ABI has one per arity: a call that takes
   one argument sets rdi and nothing else, and padding it out to three would
   emit two register loads the kernel never reads. */
#define _sys1(_n, _a) ({                                                  \
    long _r;                                                              \
    __asm__ volatile ("syscall" : "=a"(_r)                                \
        : "a"((long)(_n)), "D"((long)(_a)) : "rcx", "r11", "memory");     \
    _r; })

#define _sys3(_n, _a, _b, _c) ({                                          \
    long _r;                                                              \
    __asm__ volatile ("syscall" : "=a"(_r)                                \
        : "a"((long)(_n)), "D"((long)(_a)), "S"((long)(_b)),              \
          "d"((long)(_c)) : "rcx", "r11", "memory");                      \
    _r; })

#define _sigaction(_sig, _act) ({                                         \
    long _r;                                                              \
    register long _r10 __asm__("r10") = 8;   /* sizeof(sigset_t) */       \
    __asm__ volatile ("syscall" : "=a"(_r)                                \
        : "a"(SYS_rt_sigaction), "D"((long)(_sig)), "S"((long)(_act)),    \
          "d"(0), "r"(_r10) : "rcx", "r11", "memory");                    \
    _r; })

/* the same syscall asked the other way: what is the disposition now, change
   nothing. Its own wrapper, not a third parameter, so a twin that never asks is
   compiled exactly as it was before the question existed. */
#define _sigquery(_sig, _old) ({                                         \
    long _r;                                                              \
    register long _r10 __asm__("r10") = 8;   /* sizeof(sigset_t) */       \
    __asm__ volatile ("syscall" : "=a"(_r)                                \
        : "a"(SYS_rt_sigaction), "D"((long)(_sig)), "S"(0),               \
          "d"((long)(_old)), "r"(_r10) : "rcx", "r11", "memory");         \
    _r; })

#define _sigprocmask(_how, _set) ({                                       \
    long _r;                                                              \
    register long _r10 __asm__("r10") = 8;   /* sizeof(sigset_t) */       \
    __asm__ volatile ("syscall" : "=a"(_r)                                \
        : "a"(SYS_rt_sigprocmask), "D"((long)(_how)), "S"((long)(_set)),  \
          "d"(0), "r"(_r10) : "rcx", "r11", "memory");                    \
    _r; })

/* no `__attribute__((noreturn))` on a macro -- the trailing
   __builtin_unreachable() is what told the optimizer that anyway */
#define _exit_group(_s) do {                                              \
    __asm__ volatile ("syscall" : : "D"((long)(_s)), "a"(SYS_exit_group)  \
                      : "rcx", "r11", "memory");                          \
    __builtin_unreachable();                                              \
} while (0)

#define _write_value(_e) do {                                             \
    char _d[24];                                                          \
    long _v = (long)(_e), _n = _v < 0, _i = 22;                           \
    unsigned long _u = _n ? -(unsigned long)_v : (unsigned long)_v;       \
    _d[23] = '\n';                                                        \
    do { _d[_i] = '0' + _u % 10; _u = _u / 10; _i = _i - 1; } while (_u); \
    if (_n) { _d[_i] = '-'; _i = _i - 1; }                                \
    _sys3(SYS_write, 2, (long)_d + _i + 1, 23 - _i);                      \
} while (0)

/* ignore SIGPIPE: a closed pipe must come back as EPIPE, not kill the process */
#define IGNORE_SIGPIPE() \
    do { long _ign[4] = { 1, 0, 0, 0 }; _sigaction(13, (long)_ign); } while (0)

/* A program that OPENS anything must first make sure 0, 1 and 2 are what their
   numbers say. Started with one of them closed, its own `open` is handed that
   number -- descriptors go out lowest-free-first -- and everything it writes to
   "standard output" then lands in the file it opened. One poll answers for all
   three (POLLNVAL comes back for a closed descriptor whatever was asked for,
   and a zero timeout cannot block); repairs go upward so each open lands on the
   number it is meant to have. Twins that open nothing must not use this, for
   the same reason they must not install the interrupt stub. */
#define GUARD_STDFD()                                                     \
    do {                                                                  \
        struct { int fd; short events, revents; } _p[3] =                 \
            { { 0, 0, 0 }, { 1, 0, 0 }, { 2, 0, 0 } };                    \
        if (_sys3(SYS_poll, (long)_p, 3, 0) > 0)                          \
            for (long _i = 0; _i < 3; _i++)                               \
                if ((_p[_i].revents & 0x20)                               \
                    && _sys3(SYS_open, (long)"/dev/null", 2, 0) != _i)     \
                    _exit_group(1);                                       \
    } while (0)

/* A program that HOLDS something must not be killed mid-flight by Ctrl-C -- the
   descriptors it owns would outlive the cleanup it was about to run. What a
   freestanding program can do is catch the shutdown signals with a stub that
   simply RETURNS: the interrupted syscall comes back EINTR, the ordinary error
   path takes over, and the cleanup runs on the way out. The stub masks all
   three on entry so a second Ctrl-C cannot re-enter it, and records which one
   arrived, because the cleanup has to end by dying of it.
   Twins that own nothing must not define this -- the stub is real code, and
   emitting it unused would be the twin doing MORE than the program it is
   compared against, which is the same dishonesty in the other direction. */
#ifdef TWIN_INTERRUPT
__attribute__((externally_visible)) volatile long twin_signo;
__asm__(
  ".globl twin_sigstub\n"
  "twin_sigstub:\n"
  "  movl %edi, twin_signo(%rip)\n"  /* which signal asked us to stop */
  "  orq $0x4003, 296(%rdx)\n"       /* uc_sigmask |= HUP|INT|TERM */
  "  add $8, %rsp\n"                 /* drop the unused pretcode slot */
  "  movl $15, %eax\n"               /* __NR_rt_sigreturn */
  "  syscall\n"
);
extern void twin_sigstub(void);

/* SIGHUP belongs with the other two: it is what a closed terminal and a dropped
   connection send, so leaving it at its default would mean the ordinary way a
   session ends is the one way the cleanup does not run. And none of the three
   is taken over where it arrived already IGNORED -- that is what `nohup` sets,
   and what a shell without job control leaves on a background job, and it is
   not the program's decision to overrule. Reading the disposition first costs a
   syscall and leaves no window in which the ignore is not in force. */
#define CLEANUP_ON_INTERRUPT()                                        \
    do { long _act[4] = { (long)twin_sigstub, 0x4000004, 0, 0 };      \
         long _old[4] = { 0, 0, 0, 0 };                               \
         _sigquery(1,  (long)_old);                                   \
         if (_old[0] != 1) _sigaction(1,  (long)_act);     /* HUP  */ \
         _sigquery(2,  (long)_old);                                   \
         if (_old[0] != 1) _sigaction(2,  (long)_act);     /* INT  */ \
         _sigquery(15, (long)_old);                                   \
         if (_old[0] != 1) _sigaction(15, (long)_act);                \
    } while (0)                                           /* TERM */

/* Once the cleanup has run, die the way you were asked to. A wait status of 0
   after a Ctrl-C tells a shell loop, `xargs` and any supervisor that the work
   finished; only WIFSIGNALED tells them what happened. So put the default
   disposition back, unblock, and send the signal to yourself. */
#define DIE_AS_ASKED(sig)                                             \
    do { if (sig) {                                                   \
        long _dfl[4] = { 0, 0, 0, 0 }, _none = 0;                     \
        _sigaction((sig), (long)_dfl);                             \
        _sigprocmask(2, (long)&_none);            /* SIG_SETMASK, {} */ \
        _sys3(SYS_kill, _sys1(SYS_getpid, 0), (sig), 0);              \
    } } while (0)
#endif

#define RECORD(s, e) \
    do { _sys3(SYS_write, 2, (long)(s), sizeof(s) - 1); _write_value(e); } while (0)
