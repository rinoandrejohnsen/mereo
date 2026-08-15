/* span_scan -- read a block, cut it at the first ':', write the head.
   Written from the job, the way C does it: an address and a length carried as
   two separate variables, and a scan loop, because there is no memchr without
   a libc. The comparison is against a mereo `span`, which names that pair. */
#include "_twin.h"

static inline __attribute__((always_inline))
long _scan(const unsigned char *p, long len, long b) {
    long i = 0;
    while (i < len && (long)p[i] != b) i++;
    return i;
}

__attribute__((force_align_arg_pointer, externally_visible))
void _start() {
    IGNORE_SIGPIPE();

    unsigned char block[64];
    long count = 0;
    int input = 0, terminal = 1;
    long status = 0, sink = 0;

    count = _sys3(SYS_read, input, (long)block, 64);
    if (__builtin_expect(!(count >= 0), 0)) goto err_read;

    /* the pair a span replaces */
    const unsigned char *data = block;
    long length = count;

    long n = _scan(data, length, 58);
    if (n < length) length = n;          /* take: clamped, as the span's is */

    sink = _sys3(SYS_write, terminal, (long)data, length);
    if (__builtin_expect(!(sink == length), 0)) goto err_write;

out:
    _exit_group(status);

err_read:
    if (count == -32) goto out;
    RECORD("span_scan: 1: read input: ", count);
    status = 1;
    goto out;

err_write:
    if (sink == -32) goto out;
    RECORD("span_scan: 2: write terminal: ", sink);
    status = 1;
    goto out;
}
