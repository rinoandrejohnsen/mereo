# The exam: `loglyze`

One program, written twice — once in hand-optimised freestanding C, once in
idiomatic mereo — reading the same bytes and producing the same bytes.

## What it does

Reads NCSA Common Log Format on stdin and writes a summary on stdout.

```
127.0.0.1 - frank [10/Oct/2000:13:55:36 -0700] "GET /apache_pb.gif HTTP/1.0" 200 2326
```

Fields, in order: host, ident, authuser, `[date]`, `"request"`, status, bytes.
Only three are used — the **path** inside the request, the **status**, and the
**bytes** — but the whole line must be walked to find them, which is the point.

## Output, exactly

```
requests <total>
bytes <sum of the bytes field, - counting 0>
malformed <lines that did not parse>
1xx <n>
2xx <n>
3xx <n>
4xx <n>
5xx <n>
top
<count> <path>
...
```

`top` lists the ten most frequent paths, most frequent first. Ties break by the
path that was **seen first**. Fewer than ten distinct paths lists all of them.

## What counts as malformed

A line is malformed if any of these fails, and it is then counted and skipped:

* no `"` opening the request, or no closing `"`
* the request has no space, so no path can be cut from it
* the status is not exactly three digits
* the bytes field is neither `-` nor a run of digits
* the path is longer than 255 bytes

A line longer than 8192 bytes is truncated at 8192 and treated as a line; the
remainder is discarded up to the next newline. A final line with no newline is
processed. An empty line is malformed.

## Limits, which are the interesting part

* the read buffer is 64 KiB, and a line may straddle any number of reads
* at most 4096 distinct paths are tracked; the 4097th and beyond are counted
  into `requests` and their status, but not into `top`
* a path is at most 255 bytes; the arena holding them is 1 MiB
* all storage is fixed and declared. Neither program allocates.

## Why this program

It is not a toy: a straddling read buffer, a bounded arena, an open-addressed
table, and a parser walking hostile bytes. Every access is indexed by something
derived from input, which is exactly what the access analysis is for.
