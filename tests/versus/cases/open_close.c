/* open_close -- one owned descriptor, closed on every path out.
   Written from the job: open it, read it, write what came back, and close it
   whether the program ends normally or on any of the three failures. This is
   the hand-written form of what mereo derives. */
#define TWIN_INTERRUPT   /* it owns a descriptor */
#include "_twin.h"

__attribute__((force_align_arg_pointer, externally_visible))
void _start() {
    IGNORE_SIGPIPE();
    CLEANUP_ON_INTERRUPT();

    unsigned char buffer[64];
    long count = 0;
    int terminal = 1;
    long status = 0, sink = 0;

    int source = _sys3(SYS_open, (long)"lorem_ipsum.txt", 0, 0);
    if (__builtin_expect(!(source >= 0), 0)) goto err_open;

    count = _sys3(SYS_read, source, (long)buffer, 11);
    if (__builtin_expect(!(count >= 0), 0)) goto err_read;

    sink = _sys3(SYS_write, terminal, (long)buffer, count);
    if (__builtin_expect(!(sink == count), 0)) goto err_write;

release_source:
    _sys1(SYS_close, source);
out:
    _exit_group(status);

err_open:
    if (source == -4 || source == -32) goto out;
    RECORD("open_close: 1: source \"lorem_ipsum.txt\": ", source);
    status = 1;
    goto out;

err_read:
    if (count == -4 || count == -32) goto release_source;
    RECORD("open_close: 2: read source: ", count);
    status = 1;
    goto release_source;

err_write:
    if (sink == -4 || sink == -32) goto release_source;
    RECORD("open_close: 3: write terminal: ", sink);
    status = 1;
    goto release_source;
}
