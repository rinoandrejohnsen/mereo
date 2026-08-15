/* index_safe -- the same sum, with the bounds check written out.
   Written from the job: verify the index against the length before every read,
   and on failure report the step and exit non-zero, which is what mereo's
   `ensure` does. This is C's `.at()`, hand-rolled, because freestanding C has
   no vector to borrow one from. */
#include "_twin.h"

__attribute__((force_align_arg_pointer, externally_visible))
void _start() {
    IGNORE_SIGPIPE();

    unsigned char block[4096];
    unsigned char word[8];
    long total = 0, count = 0, b = 0;
    int input = 0, terminal = 1;
    long status = 0, sink = 0;

    count = _sys3(SYS_read, input, (long)block, 4096);
    if (__builtin_expect(!(count >= 0), 0)) goto err_read;

    const unsigned char *data = block;
    long length = count;

    for (long i = 0; i < length; i = i + 1) {
        if (__builtin_expect(!(i < length), 0)) goto err_at;
        b = data[i];
        total = total + b;
    }

    *(unsigned long *)word = (unsigned long)total;

    sink = _sys3(SYS_write, terminal, (long)word, 8);
    if (__builtin_expect(!(sink == 8), 0)) goto err_write;
out:
    _exit_group(status);
err_read:
    if (count == -32) goto out;
    RECORD("index_safe: 1: read input: ", count);
    status = 1;
    goto out;
err_at:
    RECORD("index_safe: 2: at: ", b);
    status = 1;
    goto out;
err_write:
    if (sink == -32) goto out;
    RECORD("index_safe: 3: write terminal: ", sink);
    status = 1;
    goto out;
}
