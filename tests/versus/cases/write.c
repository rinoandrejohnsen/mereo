/* write -- one syscall, fully checked.
   Written from the job: ignore SIGPIPE, write the whole message, treat a short
   write as a failure naming the step, and treat EPIPE as a clean exit. */
#include "_twin.h"

__attribute__((force_align_arg_pointer, externally_visible))
void _start() {
    IGNORE_SIGPIPE();

    unsigned char message[13] = {104,101,108,108,111,44,32,119,111,114,108,100,10};
    int terminal = 1;
    long status = 0;
    long r = _sys3(SYS_write, terminal, (long)message, 13);
    if (__builtin_expect(!(r == 13), 0)) goto err_write;
out:
    _exit_group(status);
err_write:
    if (r == -32) goto out;                 /* -EPIPE: graceful shutdown */
    RECORD("write: 1: write terminal: ", r);
    status = 1;
    goto out;
}
