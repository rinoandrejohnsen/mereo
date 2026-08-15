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

void _start() {
    long capacity = 4096;
    char buffer[4096];
    long count = 0;
    long written = 0;
    long input_descriptor = 0;
    long terminal_descriptor = 1;
    long _status = 0;

    count = syscall3(0, input_descriptor, (long)buffer, capacity);
    if (__builtin_expect(!(count >= 0), 0)) goto error_1;

    if (count == 0) goto arm_0_nothing;
    if (count == 1) goto arm_0_single;

    written = syscall3(1, terminal_descriptor, (long)"many bytes\n", 11);
    if (__builtin_expect(!(written >= 0), 0)) goto error_2;

visit_0_back:

exit:
    syscall1(60, _status);
    __builtin_unreachable();

error_1:
    syscall3(1, 2, (long)"visit: 1: read input: ", 22);
    _write_value(count);
    _status = 1;
    __asm__("# stage 1" : "+r"(_status));
    goto exit;

error_2:
    syscall3(1, 2, (long)"visit: 2: write terminal \"many bytes\\n\": ", 41);
    _write_value(written);
    _status = 1;
    __asm__("# stage 2" : "+r"(_status));
    goto exit;

error_3:
    syscall3(1, 2, (long)"visit: 3: write terminal \"nothing\\n\": ", 38);
    _write_value(written);
    _status = 1;
    __asm__("# stage 3" : "+r"(_status));
    goto exit;

error_4:
    syscall3(1, 2, (long)"visit: 4: write terminal \"one byte\\n\": ", 39);
    _write_value(written);
    _status = 1;
    __asm__("# stage 4" : "+r"(_status));
    goto exit;

arm_0_nothing:
    written = syscall3(1, terminal_descriptor, (long)"nothing\n", 8);
    if (__builtin_expect(!(written >= 0), 0)) goto error_3;
    goto visit_0_back;

arm_0_single:
    written = syscall3(1, terminal_descriptor, (long)"one byte\n", 9);
    if (__builtin_expect(!(written >= 0), 0)) goto error_4;
    goto visit_0_back;
}
