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
    long input_descriptor = 0;
    long view_data = (long)buffer;
    long view_length = 0;
    long _status = 0;

    long _sigign[4] = { 1, 0, 0, 0 };  /* SIG_IGN */
    syscall4(13, 13, (long)_sigign, 0, 8);  /* SIGPIPE */

    count = syscall3(0, input_descriptor, (long)buffer, capacity);
    if (__builtin_expect(!(count >= 0), 0)) goto error_1_read_input;

    view_length = count;

    written = syscall3(1, 1, view_data, view_length);
    if (__builtin_expect(!(written >= 0), 0)) goto error_2_show_view;

exit:
    syscall1(231, _status);
    __builtin_unreachable();

error_1_read_input:
    if (count == -32) goto exit;   /* -EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"span: 1: read input: ", 21);
    _write_value(count);
    _status = 1;
    __asm__("# stage 1" : "+r"(_status));
    goto exit;

error_2_show_view:
    if (written == -32) goto exit;   /* -EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"span: 2: show view: ", 20);
    _write_value(written);
    _status = 1;
    __asm__("# stage 2" : "+r"(_status));
    goto exit;
}
