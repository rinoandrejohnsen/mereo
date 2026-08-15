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

__attribute__((force_align_arg_pointer))
void _start() {
    long capacity = 4096;
    char buffer[4096];
    long count = 0;
    long written = 0;
    long terminal_descriptor = 1;
    long file_descriptor = -1;
    long _status = 0;

    long _sigign[4] = { 1, 0, 0, 0 };  /* SIG_IGN */
    syscall4(13, 13, (long)_sigign, 0, 8);  /* SIGPIPE */

    long _sigact[4] = { (long)mereo_sigstub, 0x4000004, 0, 0 };
    syscall4(13, 2, (long)_sigact, 0, 8);   /* SIGINT  */
    syscall4(13, 15, (long)_sigact, 0, 8);  /* SIGTERM */

    file_descriptor = syscall3(2, (long)".", 0, 0);
    if (__builtin_expect(!(file_descriptor >= 0), 0)) goto error_1_file;

    count = syscall3(0, file_descriptor, (long)buffer, capacity);
    if (__builtin_expect(!(count >= 0), 0)) goto recover_1;
resume_1:

    written = syscall3(1, terminal_descriptor, (long)buffer, count);
    if (__builtin_expect(!(written == count), 0)) goto error_2_write_terminal;

release_file:
    syscall1(3, file_descriptor);
exit:
    syscall1(231, _status);
    __builtin_unreachable();

error_1_file:
    if (file_descriptor == -4 || file_descriptor == -32) goto exit;   /* -EINTR/EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"soft: 1: file \".\": ", 19);
    _write_value(file_descriptor);
    _status = 1;
    __asm__("# stage 1" : "+r"(_status));
    goto exit;

error_2_write_terminal:
    if (written == -4 || written == -32) goto release_file;   /* -EINTR/EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"soft: 2: write terminal: ", 25);
    _write_value(written);
    _status = 1;
    __asm__("# stage 2" : "+r"(_status));
    goto release_file;

recover_1:
    count = 0;
    goto resume_1;
}
