/* two_resources -- two owned descriptors, released in reverse on every path.
   Written from the job, and this is the case C gets wrong: a failure between
   the two opens must close ONE, a failure after both must close BOTH in
   reverse, and the normal exit must do the same. Hand-written, that is a
   release ladder whose entry point depends on how far you got -- which is what
   mereo derives, and why it needs no drop flags to do it.

   Descriptors are `int`, which is what the kernel returns and what close(2)
   takes. That costs a sign-extension wherever one is handed to a syscall --
   the same one mereo pays, for the same reason. */
#define TWIN_INTERRUPT   /* it owns descriptors */
#include "_twin.h"

__attribute__((force_align_arg_pointer, externally_visible))
void _start() {
    IGNORE_SIGPIPE();
    CLEANUP_ON_INTERRUPT();

    unsigned char buffer[64];
    long count = 0;
    int terminal = 1;
    long status = 0, sink = 0;

    int first = _sys3(SYS_open, (long)"lorem_ipsum.txt", 0, 0);
    if (__builtin_expect(!(first >= 0), 0)) goto err_first;

    int second = _sys3(SYS_open, (long)"lorem_ipsum.txt", 0, 0);
    if (__builtin_expect(!(second >= 0), 0)) goto err_second;

    count = _sys3(SYS_read, second, (long)buffer, 11);
    if (__builtin_expect(!(count >= 0), 0)) goto err_read;

    sink = _sys3(SYS_write, terminal, (long)buffer, count);
    if (__builtin_expect(!(sink == count), 0)) goto err_write;

release_second:
    _sys1(SYS_close, second);
release_first:
    _sys1(SYS_close, first);
out:
    _exit_group(status);

err_first:
    if (first == -4 || first == -32) goto out;
    RECORD("two_resources: 1: first \"lorem_ipsum.txt\": ", first);
    status = 1;
    goto out;

err_second:
    if (second == -4 || second == -32) goto release_first;
    RECORD("two_resources: 2: second \"lorem_ipsum.txt\": ", second);
    status = 1;
    goto release_first;

err_read:
    if (count == -4 || count == -32) goto release_second;
    RECORD("two_resources: 3: read second: ", count);
    status = 1;
    goto release_second;

err_write:
    if (sink == -4 || sink == -32) goto release_second;
    RECORD("two_resources: 4: write terminal: ", sink);
    status = 1;
    goto release_second;
}
