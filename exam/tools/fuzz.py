#!/usr/bin/env python3
"""Adversarial input for loglyze: the shapes a log never has and a peer might."""
import random, sys

def one(r):
    k = r.randint(0, 13)
    if k == 0:  return b""
    if k == 1:  return b'"'
    if k == 2:  return b'no quotes here at all'
    if k == 3:  return b'x "GET" 200 5'                       # no space in request
    if k == 4:  return b'x "GET /p HTTP/1.1" 20 5'            # 2-digit status
    if k == 5:  return b'x "GET /p HTTP/1.1" 2000 5'          # 4-digit
    if k == 6:  return b'x "GET /p HTTP/1.1" 2x0 5'           # non-digit
    if k == 7:  return b'x "GET /p HTTP/1.1" 200 12x'         # bad bytes
    if k == 8:  return b'x "GET /p HTTP/1.1" 200 -'
    if k == 9:  return b'x "GET ' + b'/' * r.randint(250, 300) + b' HTTP/1.1" 200 5'
    if k == 10: return b'x "GET /p HTTP/1.1" 200'             # missing bytes
    if k == 11: return bytes(r.randrange(1, 256) for _ in range(r.randint(1, 200)))
    if k == 12: return b'x   "GET  /p  HTTP/1.1"   200   ' + str(r.randint(0, 10**12)).encode()
    return (b'h - - [d] "GET /p%d HTTP/1.1" %d %d'
            % (r.randint(0, 30), r.choice([200, 301, 404, 500, 100]), r.randint(0, 1000)))

r = random.Random(int(sys.argv[1]))
n = r.randint(1, 400)
body = b"\n".join(one(r) for _ in range(n))
if r.random() < 0.5:
    body += b"\n"
if r.random() < 0.08:                       # a line far past LINE_MAX
    body = b'x "GET /' + b'a' * 9000 + b' HTTP/1.1" 200 5\n' + body
sys.stdout.buffer.write(body)
