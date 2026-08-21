#!/usr/bin/env python3
"""The oracle: loglyze written the obvious way, to check the fast ones against.

Deliberately slow and literal. It reads bytes, never text, because the input is
arbitrary and the fast implementations are byte machines.
"""
import sys

LINE_MAX, PATH_MAX, TABLE_MAX, TOP = 8192, 255, 4096, 10


def run(data: bytes) -> bytes:
    requests = total_bytes = malformed = 0
    classes = [0] * 5
    order, counts = [], {}

    lines = data.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()

    for line in lines:
        line = line[:LINE_MAX]
        q1 = line.find(b'"')
        if q1 < 0:
            malformed += 1
            continue
        q2 = line.find(b'"', q1 + 1)
        if q2 < 0:
            malformed += 1
            continue
        req = line[q1 + 1:q2]
        sp = req.find(b" ")
        if sp < 0:
            malformed += 1
            continue
        rest = req[sp + 1:]
        sp2 = rest.find(b" ")
        path = rest if sp2 < 0 else rest[:sp2]
        if len(path) == 0 or len(path) > PATH_MAX:
            malformed += 1
            continue

        tail = line[q2 + 1:].split()
        if len(tail) < 2:
            malformed += 1
            continue
        status, nbytes = tail[0], tail[1]
        if len(status) != 3 or not status.isdigit():
            malformed += 1
            continue
        if nbytes == b"-":
            n = 0
        elif nbytes.isdigit():
            n = int(nbytes)
        else:
            malformed += 1
            continue

        requests += 1
        total_bytes += n
        c = status[0] - 48
        if 1 <= c <= 5:
            classes[c - 1] += 1
        if path in counts:
            counts[path] += 1
        elif len(counts) < TABLE_MAX:
            counts[path] = 1
            order.append(path)

    out = [b"requests %d" % requests, b"bytes %d" % total_bytes,
           b"malformed %d" % malformed]
    for i, name in enumerate((b"1xx", b"2xx", b"3xx", b"4xx", b"5xx")):
        out.append(b"%s %d" % (name, classes[i]))
    out.append(b"top")
    rank = sorted(range(len(order)), key=lambda i: (-counts[order[i]], i))
    for i in rank[:TOP]:
        out.append(b"%d %s" % (counts[order[i]], order[i]))
    return b"\n".join(out) + b"\n"


if __name__ == "__main__":
    sys.stdout.buffer.write(run(sys.stdin.buffer.read()))
