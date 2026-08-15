static inline __attribute__((always_inline)) long syscall1(long n, long a1) {
    long ret;
    __asm__ volatile ("syscall" : "=a"(ret) : "a"(n), "D"(a1) : "rcx", "r11", "memory");
    return ret;
}

static inline __attribute__((always_inline)) long syscall3(long n, long a1, long a2, long a3) {
    long ret;
    __asm__ volatile ("syscall" : "=a"(ret) : "a"(n), "D"(a1), "S"(a2), "d"(a3) : "rcx", "r11", "memory");
    return ret;
}

static inline __attribute__((always_inline)) long syscall4(long n, long a1, long a2, long a3, long a4) {
    long ret;
    register long r10 __asm__("r10") = a4;
    __asm__ volatile ("syscall" : "=a"(ret) : "a"(n), "D"(a1), "S"(a2), "d"(a3), "r"(r10) : "rcx", "r11", "memory");
    return ret;
}

__asm__(
  ".globl mereo_sigstub\n"
  "mereo_sigstub:\n"
  "  orq $0x4002, 296(%rdx)\n"  /* uc_sigmask |= SIGINT|SIGTERM   */
  "  add $8, %rsp\n"            /* drop the unused pretcode slot  */
  "  movl $15, %eax\n"          /* __NR_rt_sigreturn              */
  "  syscall\n"
);
extern void mereo_sigstub(void);

static inline __attribute__((always_inline)) void _write_value(long _e) {
    char _d[8];
    long _n = _e < 0;
    long _i;
    if (_n) _e = -_e;
    _d[1] = '0' + _e / 10000 % 10;
    _d[2] = '0' + _e / 1000 % 10;
    _d[3] = '0' + _e / 100 % 10;
    _d[4] = '0' + _e / 10 % 10;
    _d[5] = '0' + _e % 10;
    _d[6] = '\n';
    _i = 5 - (_e >= 10) - (_e >= 100) - (_e >= 1000) - (_e >= 10000);
    _d[_i - 1] = '-';
    _i = _i - _n;
    syscall3(1, 2, (long)_d + _i, 7 - _i);
}

void _run(long _entry);

__attribute__((naked)) void _start(void) {
    __asm__(
        "mov %rsp, %rdi\n"       /* entry pointer (-> argc) */
        "jmp _run\n"
    );
}

__attribute__((force_align_arg_pointer))
void _run(long _entry) {
    long capacity = 4096;
    char buffer[4096];
    long count = 0;
    long written = 0;
    long terminal_descriptor = 1;
    long source_descriptor = -1;
    long _status = 0;

    long _argc = *(long *)_entry;
    char **_argv = (char **)(_entry + 8);

    long _sigign[4] = { 1, 0, 0, 0 };  /* SIG_IGN */
    syscall4(13, 13, (long)_sigign, 0, 8);  /* SIGPIPE */

    long _sigact[4] = { (long)mereo_sigstub, 0x4000004, 0, 0 };
    syscall4(13, 2, (long)_sigact, 0, 8);   /* SIGINT  */
    syscall4(13, 15, (long)_sigact, 0, 8);  /* SIGTERM */

    source_descriptor = syscall3(2, (long)_argv[1], 0, 0);
    if (__builtin_expect(!(source_descriptor >= 0), 0)) goto error_1_source;

    count = syscall3(0, source_descriptor, (long)buffer, capacity);
    if (__builtin_expect(!(count >= 0), 0)) goto error_2_read_source;

    written = syscall3(1, terminal_descriptor, (long)buffer, count);
    if (__builtin_expect(!(written == count), 0)) goto error_3_write_terminal;

release_source:
    syscall1(3, source_descriptor);
exit:
    syscall1(231, _status);
    __builtin_unreachable();

error_1_source:
    if (source_descriptor == -4 || source_descriptor == -32) goto exit;   /* -EINTR/EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"argcat: 1: source: ", 19);
    _write_value(source_descriptor);
    _status = 1;
    __asm__("# stage 1" : "+r"(_status));
    goto exit;

error_2_read_source:
    if (count == -4 || count == -32) goto release_source;   /* -EINTR/EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"argcat: 2: read source: ", 24);
    _write_value(count);
    _status = 1;
    __asm__("# stage 2" : "+r"(_status));
    goto release_source;

error_3_write_terminal:
    if (written == -4 || written == -32) goto release_source;   /* -EINTR/EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"argcat: 3: write terminal: ", 27);
    _write_value(written);
    _status = 1;
    __asm__("# stage 3" : "+r"(_status));
    goto release_source;
}
