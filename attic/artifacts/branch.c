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
    long message = 0;
    long length = 0;
    long input_descriptor = 0;
    long terminal_descriptor = 1;
    long _status = 0;

    long _sigign[4] = { 1, 0, 0, 0 };  /* SIG_IGN */
    syscall4(13, 13, (long)_sigign, 0, 8);  /* SIGPIPE */

    count = syscall3(0, input_descriptor, (long)buffer, capacity);
    if (__builtin_expect(!(count >= 0), 0)) goto error_1_read_input;

    if (__builtin_expect(count == 0, 0)) goto report_road_0;
    if (__builtin_expect(count == 1, 0)) goto report_road_1;

    message = (long)"many bytes\n";

    length = 11;

report:

    written = syscall3(1, terminal_descriptor, message, length);
    if (__builtin_expect(!(written == length), 0)) goto error_2_write_terminal;

exit:
    syscall1(231, _status);
    __builtin_unreachable();

report_road_0:
    message = (long)"nothing\n";
    length = 8;
    __asm__("# report_road_0" : "+r"(message), "+r"(length));
    goto report;

report_road_1:
    message = (long)"one byte\n";
    length = 9;
    __asm__("# report_road_1" : "+r"(message), "+r"(length));
    goto report;

error_1_read_input:
    if (count == -32) goto exit;   /* -EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"branch: 1: read input: ", 23);
    _write_value(count);
    _status = 1;
    __asm__("# stage 1" : "+r"(_status));
    goto exit;

error_2_write_terminal:
    if (written == -32) goto exit;   /* -EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"branch: 2: write terminal: ", 27);
    _write_value(written);
    _status = 1;
    __asm__("# stage 2" : "+r"(_status));
    goto exit;
}
