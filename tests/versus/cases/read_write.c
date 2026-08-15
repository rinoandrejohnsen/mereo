/* read_write -- stdin to stdout, both calls checked.
   Written from the job: read's contract is a non-negative count; write's is
   that every byte moved; EPIPE ends the program cleanly. Nothing is owned, so
   no interrupt stub is installed and EINTR cannot arise -- checking for it
   would be work this program has no reason to do. */
#include "_twin.h"

__attribute__((force_align_arg_pointer, externally_visible))
void _start() {
    IGNORE_SIGPIPE();

    unsigned char buffer[4096];
    long count = 0;
    int input = 0, terminal = 1;
    long status = 0, sink = 0;

    count = _sys3(SYS_read, input, (long)buffer, 4096);
    if (__builtin_expect(!(count >= 0), 0)) goto err_read;

    sink = _sys3(SYS_write, terminal, (long)buffer, count);
    if (__builtin_expect(!(sink == count), 0)) goto err_write;

out:
    _exit_group(status);

err_read:
    if (count == -32) goto out;      /* -EPIPE */
    RECORD("read_write: 1: read input: ", count);
    status = 1;
    goto out;

err_write:
    if (sink == -32) goto out;       /* -EPIPE */
    RECORD("read_write: 2: write terminal: ", sink);
    status = 1;
    goto out;
}
