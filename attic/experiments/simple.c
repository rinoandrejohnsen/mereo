static inline long syscall1(long n, long a1) {
    long ret;
    __asm__ volatile (
        "syscall"
        : "=a" (ret)
        : "a" (n), "D" (a1)
        : "rcx", "r11", "memory"
    );
    return ret;
}

static inline long syscall2(long n, long a1, long a2) {
    long ret;
    __asm__ volatile (
        "syscall"
        : "=a" (ret)
        : "a" (n), "D" (a1), "S" (a2)
        : "rcx", "r11", "memory"
    );
    return ret;
}

static inline long syscall3(long n, long a1, long a2, long a3) {
    long ret;
    __asm__ volatile (
        "syscall"
        : "=a" (ret)
        : "a" (n), "D" (a1), "S" (a2), "d" (a3)
        : "rcx", "r11", "memory"
    );
    return ret;
}

void _start() {
    long code = 1; // open failed

    long fd = syscall2(2, (long)"lorem_ipsum.txt", 0); // sys_open, O_RDONLY
    if (fd < 0) goto exit;                             // open failed: nothing to close

    code = 2; // read failed
    char buffer[4096];

    long count = syscall3(0, fd, (long)buffer, sizeof(buffer)); // sys_read
    if (count < 0) goto close;                         // read error (0 == EOF is fine)

    code = 3; // write failed
    long write_result = syscall3(1, 1, (long)buffer, count); // sys_write to stdout
    if (write_result < 0) goto close;                  // write error

    code = 0; // success

close:                          // single shared cleanup; open-failure skips it
    syscall1(3, fd); // sys_close
exit:
    syscall1(60, code); // sys_exit with the stage code
    __builtin_unreachable();
}
