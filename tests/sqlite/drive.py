#!/usr/bin/env python3
"""Differential test for programs/sqlite/read.mereo's `open`.

The databases are made by the real sqlite3, so the bytes under test are the
bytes SQLite actually writes -- there is no hand-rolled fixture to be wrong in
the same way the reader is. The oracle re-reads the header here from the
published format, and the mereo probe is compared against it.

The malformed half matters as much: a reader fed something that is not a
database, or is a database from a newer format, must SAY SO rather than
answer confidently from whatever the bytes happened to contain.

Usage: python3 tests/sqlite/drive.py PROBE_BINARY
"""

import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile

MAGIC = b"SQLite format 3\x00"


def expected(buf):
    """The same rules programs/sqlite/read.mereo applies, in the same order."""
    n = len(buf)
    if n < 100:
        return "R -1\n"
    if buf[0:15] != MAGIC[0:15] or buf[15] != 0:
        return "R -2\n"
    raw = int.from_bytes(buf[16:18], "big")
    page_size = 65536 if raw == 1 else raw
    if page_size < 512 or page_size > 65536 or (page_size & (page_size - 1)):
        return "R -3\n"
    read_version = buf[19]
    if read_version > 2:
        return "R -4\n"
    reserved = buf[20]
    encoding = int.from_bytes(buf[56:60], "big")
    if encoding < 1 or encoding > 3:
        return "R -5\n"
    claimed = int.from_bytes(buf[28:32], "big")
    counter = int.from_bytes(buf[24:28], "big")
    valid_for = int.from_bytes(buf[92:96], "big")
    page_count = claimed if (claimed and counter == valid_for) else n // page_size
    if page_count * page_size > n:
        return "R -6\n"
    user_version = int.from_bytes(buf[60:64], "big")
    cookie = int.from_bytes(buf[40:44], "big")
    return (f"R 0\n"
            f"P {page_size} N {page_count} E {encoding}\n"
            f"V {read_version} S {reserved}\n"
            f"U {user_version} C {cookie}\n")


def run(probe, buf):
    done = subprocess.run([probe], input=buf, capture_output=True, timeout=30)
    if done.returncode != 0:
        return f"<exit {done.returncode}>"
    return done.stdout.decode("ascii", "replace")


def make(tmp, name, setup):
    """A database the real sqlite3 wrote -> its bytes."""
    path = os.path.join(tmp, name)
    con = sqlite3.connect(path)
    for stmt in setup:
        con.execute(stmt)
    con.commit()
    con.close()
    return pathlib.Path(path).read_bytes()


def corpus(tmp):
    out = []
    for size in (512, 1024, 4096, 8192, 16384, 32768, 65536):
        out.append((f"page size {size}", make(tmp, f"p{size}.db", [
            f"PRAGMA page_size={size}",
            "CREATE TABLE t(a INTEGER PRIMARY KEY, b TEXT)",
            "INSERT INTO t VALUES (1,'x'),(2,'yy'),(3,'zzz')"])))
    out.append(("empty database", make(tmp, "empty.db", [])))
    out.append(("one empty table", make(tmp, "one.db", ["CREATE TABLE t(a)"])))
    out.append(("utf-16le", make(tmp, "u16.db", [
        "PRAGMA encoding='UTF-16le'", "CREATE TABLE t(a TEXT)",
        "INSERT INTO t VALUES ('hello')"])))
    out.append(("user_version + application_id", make(tmp, "ver.db", [
        "CREATE TABLE t(a)", "PRAGMA user_version=4242",
        "PRAGMA application_id=99"])))
    out.append(("WAL, so read version 2", make(tmp, "wal.db", [
        "CREATE TABLE t(a)", "PRAGMA journal_mode=WAL",
        "INSERT INTO t VALUES (1)"])))
    out.append(("many rows, several pages", make(tmp, "big.db", [
        "PRAGMA page_size=512", "CREATE TABLE t(a INTEGER PRIMARY KEY, b TEXT)"]
        + [f"INSERT INTO t VALUES ({k},'{'v'*60}')" for k in range(200)])))
    return out


MUTATIONS = [
    ("magic broken", lambda b: b"SQLibe format 3\x00" + b[16:]),
    ("magic not NUL-terminated", lambda b: b[:15] + b"X" + b[16:]),
    ("page size 0", lambda b: b[:16] + b"\x00\x00" + b[18:]),
    ("page size 100, not a power of two", lambda b: b[:16] + (100).to_bytes(2,"big") + b[18:]),
    ("page size 256, below the floor", lambda b: b[:16] + (256).to_bytes(2,"big") + b[18:]),
    ("read version 3, a newer format", lambda b: b[:19] + b"\x03" + b[20:]),
    ("text encoding 0", lambda b: b[:56] + (0).to_bytes(4,"big") + b[60:]),
    ("text encoding 4", lambda b: b[:56] + (4).to_bytes(4,"big") + b[60:]),
    ("page count larger than the file",
     lambda b: b[:24] + (7).to_bytes(4,"big") + (99999).to_bytes(4,"big") + b[32:92]
               + (7).to_bytes(4,"big") + b[96:]),
]


def main(argv):
    if not argv:
        print("usage: drive.py PROBE_BINARY")
        return 1
    probe = argv[0]
    bad, n = [], 0
    with tempfile.TemporaryDirectory() as tmp:
        made = corpus(tmp)
        for label, buf in made:
            n += 1
            if expected(buf) != run(probe, buf):
                bad.append((label, buf[:32], expected(buf), run(probe, buf)))
            for cut in (0, 1, 15, 16, 50, 99, 100, 101):
                if cut <= len(buf):
                    n += 1
                    piece = buf[:cut]
                    if expected(piece) != run(probe, piece):
                        bad.append((f"{label} cut to {cut}", piece[:32],
                                    expected(piece), run(probe, piece)))
            for mlabel, mutate in MUTATIONS:
                n += 1
                broken = mutate(buf)
                if expected(broken) != run(probe, broken):
                    bad.append((f"{label}: {mlabel}", broken[:32],
                                expected(broken), run(probe, broken)))
        n += 1
        junk = b"not a database" * 40
        if expected(junk) != run(probe, junk):
            bad.append(("plain junk", junk[:32], expected(junk), run(probe, junk)))
    for label, head, want, got in bad[:6]:
        print(f"  {label}")
        print(f"    bytes {head!r:.60}")
        print(f"    want  {want.strip()!r:.70}")
        print(f"    got   {got.strip()!r:.70}")
    if bad:
        print(f"  sqlite header: {len(bad)} of {n} cases disagree")
        return 1
    print(f"  sqlite header: {n} cases agree, over {len(made)} databases "
          "written by the real sqlite3")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
