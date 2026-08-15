/* loop_sum -- the first hundred squares, summed, written out as eight raw
   bytes. Written from the job: a counted loop, a store, one checked write. */
#include "_twin.h"

__attribute__((force_align_arg_pointer, externally_visible))
void _start() {
    IGNORE_SIGPIPE();

    unsigned char word[8];
    long total = 0;
    int terminal = 1;
    long status = 0, sink = 0;

    for (long i = 1; i <= 100; i = i + 1) total = total + i * i;

    *(unsigned long *)word = (unsigned long)total;

    sink = _sys3(SYS_write, terminal, (long)word, 8);
    if (__builtin_expect(!(sink == 8), 0)) goto err_write;
out:
    _exit_group(status);
err_write:
    if (sink == -32) goto out;
    RECORD("loop_sum: 1: write terminal: ", sink);
    status = 1;
    goto out;
}
