/* branch_c.c -- branch.mereo, written as careful standard C with libc.
 *
 * Same behavior: read stdin, report nothing / one byte / many bytes,
 * full error handling (read failure, write failure, short writes),
 * SIGPIPE ignored with EPIPE treated as a graceful shutdown, exit 0/1.
 *
 * The comparison artifact for the mereo thesis: compile with
 *     gcc -O3 -g -o branch_c branch_c.c
 * and read it back with
 *     python3 mereodis.py --bare branch_c
 */
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

static int write_all(int fd, const char *buf, size_t n)
{
    while (n > 0) {
        ssize_t w = write(fd, buf, n);
        if (w < 0) {
            if (errno == EINTR)
                continue;
            return -1;
        }
        buf += w;
        n -= (size_t)w;
    }
    return 0;
}

int main(void)
{
    char buffer[4096];
    const char *msg;

    signal(SIGPIPE, SIG_IGN);

    ssize_t count = read(0, buffer, sizeof buffer);
    if (count < 0) {
        fprintf(stderr, "branch: read: %s\n", strerror(errno));
        return 1;
    }

    if (count == 0)
        msg = "nothing\n";
    else if (count == 1)
        msg = "one byte\n";
    else
        msg = "many bytes\n";

    if (write_all(1, msg, strlen(msg)) < 0) {
        if (errno == EPIPE)
            return 0;
        fprintf(stderr, "branch: write: %s\n", strerror(errno));
        return 1;
    }
    return 0;
}
