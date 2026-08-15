/* branch_hand.c -- branch.mereo written BY HAND as freestanding C: no libc,
 * the transpiler's own syscall wrappers (copied verbatim), entry at _start.
 * Same behavior and error contract as the mereo version: read stdin, report
 * nothing / one byte / many bytes, any failure writes one stderr record and
 * exits 1, -EINTR/-EPIPE are a graceful exit 0, short writes are failures.
 *
 * The hand-vs-generated comparison: a human factors the error path into a
 * `die` helper and writes a loop itoa; the transpiler duplicates cold blocks
 * per stage with static strings and a branchless bounded decimal.
 *
 *     gcc -O3 -g -static -nostdlib -fno-stack-protector -o branch_hand branch_hand.c
 *     python3 mereodis.py --bare branch_hand
 */

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

static long strlen_(const char *s)
{
    long n = 0;
    while (s[n])
        n++;
    return n;
}

/* one stderr record -- "branch: <what>: <value>\n" -- then exit 1 */
static __attribute__((noreturn)) void die(const char *what, long value)
{
    char digits[24];
    long i = 24, neg = value < 0;

    if (neg)
        value = -value;
    do {
        digits[--i] = '0' + value % 10;
        value /= 10;
    } while (value);
    if (neg)
        digits[--i] = '-';

    syscall3(1, 2, (long)"branch: ", 8);
    syscall3(1, 2, (long)what, strlen_(what));
    syscall3(1, 2, (long)": ", 2);
    syscall3(1, 2, (long)digits + i, 24 - i);
    syscall3(1, 2, (long)"\n", 1);
    syscall1(231, 1);
    __builtin_unreachable();
}

__attribute__((force_align_arg_pointer))
void _start(void)
{
    char buffer[4096];
    long sigign[4] = { 1, 0, 0, 0 };            /* SIG_IGN */
    const char *msg;
    long len;

    syscall4(13, 13, (long)sigign, 0, 8);       /* ignore SIGPIPE */

    long count = syscall3(0, 0, (long)buffer, 4096);
    if (__builtin_expect(count < 0, 0)) {
        if (count == -4 || count == -32)        /* -EINTR/-EPIPE: graceful */
            goto out;
        die("read", count);
    }

    if (count == 0) {
        msg = "nothing\n";
        len = 8;
    } else if (count == 1) {
        msg = "one byte\n";
        len = 9;
    } else {
        msg = "many bytes\n";
        len = 11;
    }

    long written = syscall3(1, 1, (long)msg, len);
    if (__builtin_expect(written != len, 0)) {
        if (written == -4 || written == -32)
            goto out;
        die("write", written);
    }

out:
    syscall1(231, 0);
    __builtin_unreachable();
}
