/* index_fast -- the same sum, indexed the way C does it when the caller holds
   the invariant: `p[i]`, no check. Written from the job. */
#include "_twin.h"

__attribute__((force_align_arg_pointer, externally_visible))
void _start() {
    IGNORE_SIGPIPE();

    unsigned char block[4096];
    unsigned char word[8];
    long total = 0, count = 0;
    int input = 0, terminal = 1;
    long status = 0, sink = 0;

    count = _sys3(SYS_read, input, (long)block, 4096);
    if (__builtin_expect(!(count >= 0), 0)) goto err_read;

    const unsigned char *data = block;
    for (long i = 0; i < 4000; i = i + 1) total = total + data[i];

    *(unsigned long *)word = (unsigned long)total;

    sink = _sys3(SYS_write, terminal, (long)word, 8);
    if (__builtin_expect(!(sink == 8), 0)) goto err_write;
out:
    _exit_group(status);
err_read:
    if (count == -32) goto out;
    RECORD("index_fast: 1: read input: ", count);
    status = 1;
    goto out;
err_write:
    if (sink == -32) goto out;
    RECORD("index_fast: 2: write terminal: ", sink);
    status = 1;
    goto out;
}
