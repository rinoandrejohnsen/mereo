#!/usr/bin/env python3
"""Differential test for programs/http/parse.mereo.

The parser is run as a black box -- `probe` reads a request on stdin and prints
the parse in hex -- against an ORACLE written here from the same rules
programs/http/parse.mereo documents. What that catches is IMPLEMENTATION
error: an off-by-one, a bound read the wrong way round, whitespace trimmed
from the wrong end, a truncation reported as malformed. What it cannot catch
is the two of them misreading the RFC in the same way, so the well-formed
half is ALSO cross-checked against Python's own header parser, which was
written by someone else from the same standard.

Four families:

  WELL-FORMED   the parse must match the oracle exactly
  TRUNCATED     every proper prefix of a well-formed request must be -2.
                This is the invariant the whole streaming contract rests on:
                a parser that answers -1 on a short read makes a server drop
                a request that was merely still arriving.
  MALFORMED     each mutation must be refused, and refused the same way
  RANDOM        must never crash, and must agree with the oracle

Usage: python3 tests/http/drive.py PROBE_BINARY
"""

import random
import subprocess
import sys

CR, LF, SP, HT, COLON, DEL = 13, 10, 32, 9, 58, 127
# what the probes pass as `line_limit`; a line longer than this is
# malformed, not incomplete
LINE_LIMIT = 8192
TOKEN_EXTRA = set(b"!#$%&'*+-.^_`|~")


def is_token(b):
    return (48 <= b <= 57 or 65 <= b <= 90 or 97 <= b <= 122
            or b in TOKEN_EXTRA)


class Incomplete(Exception):
    pass


class Malformed(Exception):
    pass


def oracle_request(buf):
    """-> (consumed, minor, method, path, [(name, value)]), or raise."""
    n = len(buf)
    i = 0

    def need(k):
        if i + k > n:
            raise Incomplete()

    # method
    start = i
    while True:
        if i >= n:
            raise Incomplete()
        if buf[i] == SP:
            break
        if not is_token(buf[i]):
            raise Malformed()
        i += 1
    method = buf[start:i]
    if not method:
        raise Malformed()
    i += 1

    # target
    start = i
    while True:
        if i >= n:
            raise Incomplete()
        if buf[i] == SP:
            break
        if buf[i] < 33 or buf[i] == DEL:
            raise Malformed()
        i += 1
    path = buf[start:i]
    if not path:
        raise Malformed()
    i += 1

    # `HTTP/1.` DIGIT CRLF -- ten bytes, so fewer than ten is not yet wrong
    need(10)
    if buf[i:i + 7] != b"HTTP/1.":
        raise Malformed()
    i += 7
    if not (48 <= buf[i] <= 57):
        raise Malformed()
    minor = buf[i] - 48
    i += 1
    if buf[i] != CR or buf[i + 1] != LF:
        raise Malformed()
    if i > LINE_LIMIT:
        raise Malformed()
    i += 2

    return _headers(buf, i, (minor, method, path))


def _headers(buf, i, carry):
    """The field lines and the empty line that ends them -- the half a request
    and a response share, split out here because parse.mereo splits it too."""
    n = len(buf)
    headers = []
    while True:
        line_at = i
        if i + 1 >= n:
            raise Incomplete()
        if buf[i] == CR and buf[i + 1] == LF:
            return (i + 2,) + carry + (headers,)

        start = i
        while True:
            if i >= n:
                raise Incomplete()
            if buf[i] == COLON:
                break
            if not is_token(buf[i]):
                raise Malformed()
            i += 1
        if i == start:
            raise Malformed()
        name = buf[start:i]
        i += 1

        while i < n and buf[i] in (SP, HT):
            i += 1
        if i >= n:
            raise Incomplete()

        value_at = i
        while True:
            if i >= n:
                raise Incomplete()
            if buf[i] == CR:
                break
            if (buf[i] < 32 and buf[i] != HT) or buf[i] == DEL:
                raise Malformed()
            i += 1
        if i + 1 >= n:
            raise Incomplete()
        if buf[i + 1] != LF:
            raise Malformed()
        if i - line_at > LINE_LIMIT:
            raise Malformed()
        value_end = i
        while value_end > value_at and buf[value_end - 1] in (SP, HT):
            value_end -= 1
        headers.append((name, buf[value_at:value_end]))
        if len(headers) > 128:
            raise Malformed()
        i += 2


def oracle_response(buf):
    """-> (consumed, minor, status, reason, [(name, value)]), or raise.

    The reason phrase is NOT trimmed: RFC 9112 §4 gives it no OWS rule, and
    parse.mereo keeps it verbatim for the same reason."""
    n = len(buf)
    i = 0
    if i + 15 > n:
        raise Incomplete()
    if buf[0:7] != b"HTTP/1.":
        raise Malformed()
    if not (48 <= buf[7] <= 57):
        raise Malformed()
    minor = buf[7] - 48
    if buf[8] != SP:
        raise Malformed()
    if not all(48 <= buf[9 + k] <= 57 for k in range(3)):
        raise Malformed()
    status = (buf[9] - 48) * 100 + (buf[10] - 48) * 10 + (buf[11] - 48)
    if buf[12] != SP:
        raise Malformed()
    i = 13
    start = i
    while True:
        if i >= n:
            raise Incomplete()
        b = buf[i]
        if not ((b >= 32 or b == HT) and b != DEL):
            break
        i += 1
    if i + 1 >= n:
        raise Incomplete()
    if buf[i] != CR or buf[i + 1] != LF:
        raise Malformed()
    if i > LINE_LIMIT:
        raise Malformed()
    reason = buf[start:i]
    return _headers(buf, i + 2, (minor, status, reason))


def expected_response(buf):
    try:
        used, minor, status, reason, headers = oracle_response(buf)
    except Incomplete:
        return "R -2\n"
    except Malformed:
        return "R -1\n"
    out = [f"R {used}", f"V {minor}", f"S {status}", f"X {reason.hex()}"]
    out += [f"H {a.hex()} {b.hex()}" for a, b in headers]
    return "\n".join(out) + "\n"


def expected(buf):
    """The oracle's answer in the probe's own output format."""
    try:
        used, minor, method, path, headers = oracle_request(buf)
    except Incomplete:
        return "R -2\n"
    except Malformed:
        return "R -1\n"
    out = [f"R {used}", f"V {minor}", f"M {method.hex()}", f"P {path.hex()}"]
    out += [f"H {a.hex()} {b.hex()}" for a, b in headers]
    return "\n".join(out) + "\n"


def run(probe, buf):
    done = subprocess.run([probe], input=buf, capture_output=True, timeout=30)
    if done.returncode != 0:
        return f"<exit {done.returncode}>"
    return done.stdout.decode("ascii", "replace")


WELL_FORMED = [
    b"GET / HTTP/1.1\r\n\r\n",
    b"GET / HTTP/1.0\r\n\r\n",
    b"POST /submit HTTP/1.1\r\nHost: example.com\r\n\r\n",
    b"GET /a?b=c&d=%20 HTTP/1.1\r\nHost: h\r\nAccept: */*\r\n\r\n",
    b"OPTIONS * HTTP/1.1\r\nHost: h\r\n\r\n",
    b"M-SEARCH /x HTTP/1.1\r\nA!#$%&'*+-.^_`|~: v\r\n\r\n",
    b"GET / HTTP/1.1\r\nEmpty:\r\n\r\n",
    b"GET / HTTP/1.1\r\nPad:   spaced   \r\n\r\n",
    b"GET / HTTP/1.1\r\nTab:\tvalue\t\r\n\r\n",
    b"GET / HTTP/1.1\r\nA: 1\r\nB: 2\r\nC: 3\r\nD: 4\r\nE: 5\r\n\r\n",
    b"GET /\x80\xff HTTP/1.1\r\nX: \xc3\xa9\r\n\r\n",
    b"DELETE /r/1 HTTP/1.9\r\nHost: h\r\nX-Long: " + b"v" * 300 + b"\r\n\r\n",
    b"GET / HTTP/1.1\r\n" + b"".join(b"H%d: %d\r\n" % (k, k)
                                    for k in range(60)) + b"\r\n",
]

MUTATIONS = [
    ("a target one byte over the line limit",
     lambda r: r.replace(b" / ", b" /" + b"a" * LINE_LIMIT + b" ", 1)),
    ("a header line over the line limit",
     lambda r: r.replace(b"\r\n\r\n", b"\r\nX: " + b"v" * LINE_LIMIT + b"\r\n\r\n", 1)),
    ("a target one byte UNDER the limit still parses",
     lambda r: r.replace(b" / ", b" /" + b"a" * (LINE_LIMIT - 20) + b" ", 1)),
    ("bare LF instead of CRLF", lambda r: r.replace(b"\r\n", b"\n")),
    ("CR without LF", lambda r: r.replace(b"\r\n", b"\r", 1)),
    ("no colon in a field line", lambda r: r.replace(b": ", b" ", 1)),
    ("empty field name", lambda r: r.replace(b"\r\n", b"\r\n: v\r\n", 1)),
    ("obs-fold continuation", lambda r: r.replace(b"\r\n\r\n",
                                                  b"\r\n  more\r\n\r\n")),
    ("space in the method", lambda r: b"BAD " + r),
    ("control byte in a value", lambda r: r.replace(b"\r\n\r\n",
                                                    b"\r\nX: a\x01b\r\n\r\n")),
    ("DEL in the target", lambda r: r.replace(b" HTTP/1.", b"\x7f HTTP/1.", 1)),
    ("version HTTP/2.", lambda r: r.replace(b"HTTP/1.", b"HTTP/2.", 1)),
    ("version not a digit", lambda r: r.replace(b"HTTP/1.1", b"HTTP/1.x", 1)),
    ("empty target", lambda r: r.replace(b"GET / ", b"GET  ", 1)),
    ("tab inside the method", lambda r: b"G\tET" + r[3:]),
]


WELL_FORMED_RESPONSES = [
    b"HTTP/1.1 200 OK\r\n\r\n",
    b"HTTP/1.0 404 Not Found\r\nServer: s\r\n\r\n",
    b"HTTP/1.1 204 \r\n\r\n",                       # an empty reason phrase
    b"HTTP/1.1 500 Internal Server Error\r\nX: 1\r\nY: 2\r\n\r\n",
    b"HTTP/1.9 302 Found\r\nLocation: /a?b=c\r\nEmpty:\r\n\r\n",
    b"HTTP/1.1 200 OK\r\nPad:   spaced   \r\nTab:\tv\t\r\n\r\n",
    b"HTTP/1.1 418 \xc3\xa9 tea\r\nX: \x80\xff\r\n\r\n",
    b"HTTP/1.1 301 Moved\r\n" + b"".join(b"H%d: %d\r\n" % (k, k)
                                        for k in range(40)) + b"\r\n",
]

RESPONSE_MUTATIONS = [
    ("a reason phrase over the line limit",
     lambda r: r.replace(b" OK\r\n", b" " + b"O" * LINE_LIMIT + b"\r\n", 1)),
    ("a header line over the line limit",
     lambda r: r.replace(b"\r\n\r\n", b"\r\nX: " + b"v" * LINE_LIMIT + b"\r\n\r\n", 1)),
    ("bare LF", lambda r: r.replace(b"\r\n", b"\n")),
    ("two-digit status", lambda r: r.replace(b" 200 ", b" 20 ", 1)),
    ("four-digit status", lambda r: r.replace(b" 200 ", b" 2000 ", 1)),
    ("non-digit status", lambda r: r.replace(b" 200 ", b" 2x0 ", 1)),
    ("no space after the status", lambda r: r.replace(b"200 OK", b"200OK", 1)),
    ("no reason phrase at all", lambda r: r.replace(b" 200 OK", b" 200", 1)),
    ("request line, not a status line", lambda r: b"GET / " + r),
    ("version HTTP/2.", lambda r: r.replace(b"HTTP/1.", b"HTTP/2.", 1)),
    ("control byte in the reason", lambda r: r.replace(b" OK", b" O\x01K", 1)),
    ("control byte in a value", lambda r: r.replace(b"\r\n\r\n",
                                                  b"\r\nX: a\x01b\r\n\r\n")),
    ("empty field name", lambda r: r.replace(b"\r\n", b"\r\n: v\r\n", 1)),
]



def expected_chunked(buf):
    """Mirror of probe_chunked.mereo: run the decoder to a stop and report the
    last result, whether it finished, and every body byte handed back."""
    n, i, body = len(buf), 0, bytearray()
    while True:
        # the chunk-size line
        value, digits = 0, 0
        while i < n:
            c = buf[i]
            if 48 <= c <= 57: d = c - 48
            elif 97 <= c <= 102: d = c - 87
            elif 65 <= c <= 70: d = c - 55
            else: break
            if digits >= 16:
                return f"R -1\nF 0\nB {body.hex()}\n"
            value = value * 16 + d
            digits += 1
            i += 1
        if i >= n:
            return f"R -2\nF 0\nB {body.hex()}\n"
        if digits == 0:
            return f"R -1\nF 0\nB {body.hex()}\n"
        while i < n and buf[i] != CR:
            i += 1                                   # a chunk extension
        if i + 1 >= n:
            return f"R -2\nF 0\nB {body.hex()}\n"
        if buf[i] != CR or buf[i + 1] != LF:
            return f"R -1\nF 0\nB {body.hex()}\n"
        i += 2

        if value == 0:                               # the trailer
            while True:
                if i + 1 >= n:
                    return f"R -2\nF 0\nB {body.hex()}\n"
                if buf[i] == CR:
                    if buf[i + 1] != LF:
                        return f"R -1\nF 0\nB {body.hex()}\n"
                    return f"R {i + 2}\nF 1\nB {body.hex()}\n"
                while i < n and buf[i] != CR:
                    i += 1
                if i + 1 >= n:
                    return f"R -2\nF 0\nB {body.hex()}\n"
                if buf[i + 1] != LF:
                    return f"R -1\nF 0\nB {body.hex()}\n"
                i += 2

        remaining = value                            # the chunk data
        while remaining:
            left = n - i
            if left == 0:
                return f"R -2\nF 0\nB {body.hex()}\n"
            take = min(remaining, left)
            body += buf[i:i + take]
            i += take
            remaining -= take
        if i + 1 >= n:
            return f"R -2\nF 0\nB {body.hex()}\n"
        if buf[i] != CR or buf[i + 1] != LF:
            return f"R -1\nF 0\nB {body.hex()}\n"
        i += 2


WELL_FORMED_CHUNKED = [
    b"0\r\n\r\n",
    b"5\r\nhello\r\n0\r\n\r\n",
    b"5\r\nhello\r\n6\r\n world\r\n0\r\n\r\n",
    b"1\r\na\r\n1\r\nb\r\n1\r\nc\r\n0\r\n\r\n",
    b"A\r\n0123456789\r\n0\r\n\r\n",
    b"a\r\n0123456789\r\n0\r\n\r\n",
    b"5;name=value\r\nhello\r\n0\r\n\r\n",
    b"5\r\nhello\r\n0\r\nX-Trailer: 1\r\nY: 2\r\n\r\n",
    b"100\r\n" + b"z" * 256 + b"\r\n0\r\n\r\n",
    b"3\r\n\x00\x01\xff\r\n0\r\n\r\n",
]

CHUNKED_MUTATIONS = [
    ("no hex digits", lambda r: b"\r\n" + r),
    ("bad size terminator", lambda r: r.replace(b"\r\n", b"\n", 1)),
    ("data shorter than the size", lambda r: r.replace(b"5\r\nhello", b"9\r\nhello", 1)),
    ("no CRLF after the data", lambda r: r.replace(b"hello\r\n", b"helloXY", 1)),
    ("trailer without CRLF", lambda r: r.replace(b"0\r\n\r\n", b"0\r\nX: 1\n\r\n", 1)),
    ("seventeen hex digits", lambda r: b"00000000000000005\r\nhello\r\n0\r\n\r\n"),
]


# ---------------------------------------------------------------- JSON -----
WS = (32, 9, 13, 10)


def expected_json(buf):
    """Mirror of programs/http/json.mereo, event for event."""
    n, i, depth, mode, out = len(buf), 0, 0, 0, []
    stack = []

    def sstring(at):
        """(start, size, next offset) or ('bad'|'short', ...)"""
        j = at + 1
        start = j
        while True:
            if j >= n: return ("short", 0, 0)
            c = buf[j]
            if c == 34: return (start, j - start, j + 1)
            if c < 32: return ("bad", 0, 0)
            if c == 92:
                j += 1
                if j >= n: return ("bad", 0, 0)
            j += 1

    while True:
        while i < n and buf[i] in WS:
            i += 1
        if i >= n:
            if depth == 0 and mode == 1:
                out.append(f"R {i}")
            else:
                out.append("R -2")
            return "\n".join(out) + "\n"
        c = buf[i]
        if c in (125, 93):
            if depth == 0 or mode == 2: out.append("R -1"); return "\n".join(out) + "\n"
            d = stack[depth - 1]
            if (c == 125 and d != 1) or (c == 93 and d != 0):
                out.append("R -1"); return "\n".join(out) + "\n"
            depth -= 1; stack.pop(); mode = 1
            out.append(f"E {2 if c == 125 else 4} {depth}  ")
            i += 1
            continue
        if c == 44:
            if mode != 1: out.append("R -1"); return "\n".join(out) + "\n"
            mode = 2; i += 1
            continue
        if mode == 1:
            out.append("R -1"); return "\n".join(out) + "\n"
        key = b""
        if depth and stack[depth - 1] == 1:
            if c != 34: out.append("R -1"); return "\n".join(out) + "\n"
            a, sz, nxt = sstring(i)
            if a == "bad": out.append("R -1"); return "\n".join(out) + "\n"
            if a == "short": out.append("R -2"); return "\n".join(out) + "\n"
            key = buf[a:a + sz]; i = nxt
            while i < n and buf[i] in WS: i += 1
            if i >= n: out.append("R -2"); return "\n".join(out) + "\n"
            if buf[i] != 58: out.append("R -1"); return "\n".join(out) + "\n"
            i += 1
            while i < n and buf[i] in WS: i += 1
            if i >= n: out.append("R -2"); return "\n".join(out) + "\n"
            c = buf[i]
        if c in (123, 91):
            if depth >= 256: out.append("R -1"); return "\n".join(out) + "\n"
            stack.append(1 if c == 123 else 0); depth += 1; mode = 0
            out.append(f"E {1 if c == 123 else 3} {depth} {key.hex()} ")
            i += 1
            continue
        if c == 34:
            a, sz, nxt = sstring(i)
            if a == "bad": out.append("R -1"); return "\n".join(out) + "\n"
            if a == "short": out.append("R -2"); return "\n".join(out) + "\n"
            out.append(f"E 5 {depth} {key.hex()} {buf[a:a+sz].hex()}")
            i = nxt; mode = 1
            continue
        if c in (116, 102, 110):
            word = {116: b"true", 102: b"false", 110: b"null"}[c]
            if i + len(word) > n: out.append("R -2"); return "\n".join(out) + "\n"
            if buf[i:i + len(word)] != word:
                out.append("R -1"); return "\n".join(out) + "\n"
            kind = {116: 7, 102: 8, 110: 9}[c]
            out.append(f"E {kind} {depth} {key.hex()} {word.hex()}")
            i += len(word); mode = 1
            continue
        at = i
        if c != 45 and not (48 <= c <= 57):
            out.append("R -1"); return "\n".join(out) + "\n"
        if c == 45: i += 1
        got = False
        while i < n and 48 <= buf[i] <= 57: got = True; i += 1
        if not got: out.append("R -1"); return "\n".join(out) + "\n"
        if i < n and buf[i] == 46:
            i += 1; got = False
            while i < n and 48 <= buf[i] <= 57: got = True; i += 1
            if not got: out.append("R -1"); return "\n".join(out) + "\n"
        if i < n and buf[i] in (101, 69):
            i += 1
            if i < n and buf[i] in (43, 45): i += 1
            got = False
            while i < n and 48 <= buf[i] <= 57: got = True; i += 1
            if not got: out.append("R -1"); return "\n".join(out) + "\n"
        out.append(f"E 6 {depth} {key.hex()} {buf[at:i].hex()}")
        mode = 1


WELL_FORMED_JSON = [
    b"{}", b"[]", b"0", b"-0", b'"x"', b"true", b"false", b"null",
    b'{"a":1}', b'{"a":1,"b":2}', b"[1,2,3]",
    b'{"a":[1,{"b":"c"}],"d":{"e":[]}}',
    b'  { "a" : "x\\ny" , "b" : -2.5e-3 }  ',
    b'[[[[1]]]]', b'{"k":"\\u0041\\t\\""}', b'[1.0,2E5,3e+7,-4.25]',
]

JSON_MUTATIONS = [
    ("trailing comma", lambda r: r.replace(b"}", b",}", 1) if b"}" in r else r),
    ("missing colon", lambda r: r.replace(b'":', b'" ', 1)),
    ("mismatched close", lambda r: r.replace(b"}", b"]", 1) if b"}" in r else r),
    ("bare control byte in a string", lambda r: r.replace(b'"x"', b'"\x01"', 1)),
    ("leading plus", lambda r: r.replace(b"1", b"+1", 1)),
    ("bare word", lambda r: r + b" nonsense"),
    ("unclosed string", lambda r: r.replace(b'"x"', b'"x', 1)),
    ("two values", lambda r: r + b" 1"),
]


def main(argv):
    if len(argv) < 4:
        print("usage: drive.py REQUEST RESPONSE CHUNKED JSON")
        return 1
    probe, probe_response, probe_chunked, probe_json = argv[:4]
    bad = []
    counts = {"well-formed": 0, "truncated": 0, "malformed": 0, "random": 0}

    def check(family, label, buf):
        counts[family] += 1
        want, got = expected(buf), run(probe, buf)
        if want != got:
            bad.append((family, label, buf, want, got))

    for k, req in enumerate(WELL_FORMED):
        check("well-formed", f"well-formed #{k}", req)
        for cut in range(len(req)):
            check("truncated", f"well-formed #{k} cut at {cut}", req[:cut])
        for name, mutate in MUTATIONS:
            try:
                broken = mutate(req)
            except Exception:
                continue
            if broken != req:
                check("malformed", f"#{k}: {name}", broken)

    def check_response(family, label, buf):
        counts[family] += 1
        want, got = expected_response(buf), run(probe_response, buf)
        if want != got:
            bad.append((family, label, buf, want, got))

    for k, res in enumerate(WELL_FORMED_RESPONSES):
        check_response("well-formed", f"response #{k}", res)
        for cut in range(len(res)):
            check_response("truncated", f"response #{k} cut at {cut}", res[:cut])
        for name, mutate in RESPONSE_MUTATIONS:
            broken = mutate(res)
            if broken != res:
                check_response("malformed", f"response #{k}: {name}", broken)

    def check_chunked(family, label, buf):
        counts[family] += 1
        want, got = expected_chunked(buf), run(probe_chunked, buf)
        if want != got:
            bad.append((family, label, buf, want, got))

    for k, body in enumerate(WELL_FORMED_CHUNKED):
        check_chunked("well-formed", f"chunked #{k}", body)
        for cut in range(len(body)):
            check_chunked("truncated", f"chunked #{k} cut at {cut}", body[:cut])
        for name, mutate in CHUNKED_MUTATIONS:
            broken = mutate(body)
            if broken != body:
                check_chunked("malformed", f"chunked #{k}: {name}", broken)

    def check_json(family, label, buf):
        counts[family] += 1
        want, got = expected_json(buf), run(probe_json, buf)
        if want != got:
            bad.append((family, label, buf, want, got))

    for k, doc in enumerate(WELL_FORMED_JSON):
        check_json("well-formed", f"json #{k}", doc)
        for cut in range(len(doc)):
            check_json("truncated", f"json #{k} cut at {cut}", doc[:cut])
        for name, mutate in JSON_MUTATIONS:
            broken = mutate(doc)
            if broken != doc:
                check_json("malformed", f"json #{k}: {name}", broken)

    rng = random.Random(20260902)
    alphabet = b"GET / HTTP1.\r\n:abc \t\x00\x7f\xff"
    for k in range(4000):
        size = rng.randrange(0, 60)
        check("random", f"random #{k}",
              bytes(rng.choice(alphabet) for _ in range(size)))
    for k in range(2000):
        size = rng.randrange(0, 60)
        check_response("random", f"random response #{k}",
                       bytes(rng.choice(alphabet) for _ in range(size)))
    for k in range(300):
        res = bytearray(rng.choice(WELL_FORMED_RESPONSES))
        for _ in range(rng.randrange(1, 4)):
            if res:
                res[rng.randrange(len(res))] = rng.randrange(256)
        check_response("random", f"mutated response #{k}", bytes(res))
    alpha2 = b"0123456789abcdefABCDEF;\r\n xyz"
    for k in range(2000):
        check_chunked("random", f"random chunked #{k}",
                      bytes(rng.choice(alpha2) for _ in range(rng.randrange(0, 40))))
    for k in range(300):
        body = bytearray(rng.choice(WELL_FORMED_CHUNKED))
        for _ in range(rng.randrange(1, 4)):
            if body:
                body[rng.randrange(len(body))] = rng.randrange(256)
        check_chunked("random", f"mutated chunked #{k}", bytes(body))
    alpha3 = b'{}[]",:0123456789.eE+- truefalsn\\\t\n'
    for k in range(3000):
        check_json("random", f"random json #{k}",
                   bytes(rng.choice(alpha3) for _ in range(rng.randrange(0, 30))))
    for k in range(500):
        doc = bytearray(rng.choice(WELL_FORMED_JSON))
        for _ in range(rng.randrange(1, 3)):
            if doc: doc[rng.randrange(len(doc))] = rng.randrange(256)
        check_json("random", f"mutated json #{k}", bytes(doc))
    for k in range(400):
        req = bytearray(rng.choice(WELL_FORMED))
        for _ in range(rng.randrange(1, 4)):
            if req:
                req[rng.randrange(len(req))] = rng.randrange(256)
        check("random", f"mutated #{k}", bytes(req))

    # An INDEPENDENT check of the happy path, so the two of us agreeing on a
    # misreading of the RFC does not pass unnoticed. Two adjustments, both
    # because `email.parser` implements MIME and not HTTP: it does not apply
    # HTTP's rule that a field value excludes leading and trailing OWS
    # (RFC 9112 s5), so its values are rstripped before comparing; and it
    # decodes a non-ASCII header into a Header object under a different
    # standard entirely, so requests carrying one sit this check out.
    import email.parser
    drift, crossed = [], 0
    for k, req in enumerate(WELL_FORMED):
        if any(b >= 0x80 for b in req):
            continue
        crossed += 1
        used, minor, method, path, headers = oracle_request(req)
        head = req[:used].split(b"\r\n", 1)[1]
        theirs = email.parser.BytesParser().parsebytes(head)
        mine = [(a.decode("latin-1").lower(), b.decode("latin-1"))
                for a, b in headers]
        others = [(a.lower(), v.strip(" \t")) for a, v in theirs.items()]
        if mine != others:
            drift.append((k, mine, others))

    total = sum(counts.values())
    for family, label, buf, want, got in bad[:6]:
        print(f"  {family}: {label}")
        print(f"    input {bytes(buf)!r:.80}")
        print(f"    want  {want.strip()!r:.80}")
        print(f"    got   {got.strip()!r:.80}")
    for k, mine, others in drift[:3]:
        print(f"  well-formed #{k} disagrees with Python's header parser:")
        print(f"    mereo  {mine}")
        print(f"    python {others}")
    if bad or drift:
        print(f"  http parser: {len(bad)} of {total} cases disagree, "
              f"{len(drift)} header sets differ from Python's")
        return 1
    print(f"  http+json: {total} cases agree (requests, responses, chunked, json) "
          + ", ".join(f"{v} {k}" for k, v in counts.items())
          + f"; {crossed} header sets match Python's own parser")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
