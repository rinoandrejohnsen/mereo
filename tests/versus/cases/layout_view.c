/* layout_view -- the same record, with the offsets written out.
   Written from the job: tag at 0 (2 bytes), a big-endian length at 2 (4 bytes,
   so it needs swapping both ways), flags at 6. This is what a layout view
   replaces, and what it has to not cost more than. */
#include "_twin.h"

__attribute__((force_align_arg_pointer, externally_visible))
void _start() {
    IGNORE_SIGPIPE();

    unsigned char block[8];
    unsigned char word[8];
    int terminal = 1;
    long status = 0, sink = 0;

    *(unsigned short *)(block + 0) = (unsigned short)4660;
    *(unsigned int *)(block + 2)   = __builtin_bswap32((unsigned int)305419896);
    *(unsigned char *)(block + 6)  = (unsigned char)255;

    long n = __builtin_bswap32(*(unsigned int *)(block + 2));

    *(unsigned long *)word = (unsigned long)n;

    sink = _sys3(SYS_write, terminal, (long)block, 7);
    if (__builtin_expect(!(sink == 7), 0)) goto err_first;

    sink = _sys3(SYS_write, terminal, (long)word, 8);
    if (__builtin_expect(!(sink == 8), 0)) goto err_second;

out:
    _exit_group(status);

err_first:
    if (sink == -32) goto out;
    RECORD("layout_view: 1: write terminal: ", sink);
    status = 1;
    goto out;

err_second:
    if (sink == -32) goto out;
    RECORD("layout_view: 2: write terminal: ", sink);
    status = 1;
    goto out;
}
