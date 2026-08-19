#!/usr/bin/env python3
"""`is` for declarations, `goes` for statements. One-shot migration.

  program is                  -> program goes
  program (arguments) is      -> program (arguments) goes
  f (a, b) is                 -> f (a, b) goes          a free-standing template
  read (buffer, count) is     -> read (buffer, count) goes    a method
  acquire is / release is     -> acquire goes / release goes
  linux contains              -> linux is

  file is                     unchanged -- a definition
  open is assembly "syscall"  unchanged -- a primitive DECLARATION
  tag is 1 bytes              unchanged -- a field

The rule the language ends up with is one question asked of every block: does
its body RUN? If it does it is a `goes` -- the program, templates, methods,
loops, roads, scopes. If it declares, it is an `is` -- namespaces, views,
groups, resources, primitives.

That also removes an ambiguity rather than moving it. `acquire is` and `file is`
used to be the same line with different meanings decided by what enclosed them,
which is why a definition written inside a definition was silently read as a
method. Afterwards the keyword says which is meant.

WHAT MAKES THIS TRACTABLE is that the answer depends only on what a line's
PARENT block is, so one pass with an indent stack is enough:

  file      -> `program`/`NAME (ports) is` run;  `NAME is` declares
  namespace -> everything declares
  definition-> `NAME is` and `NAME (ports) is` are methods, so they run
  code      -> statements; leave the whole subtree alone

Comments keep their column: `goes` is two characters longer than `is`, so an
aligned trailing note is put back where the author had it when it still fits,
and pushed out by the minimum otherwise.
"""
import pathlib
import re
import sys

BLOCK = re.compile(r"^(?P<name>\w+)"
                   r"(?: \((?P<ports>[^)]*)\))?"
                   r"(?: extends (?P<base>[\w.]+(?: and [\w.]+)*))?"
                   r" (?P<word>is|contains)$")


def uncomment(line):
    """(code, column, comment) -- quote-aware, so `--` inside a string is data."""
    q = i = 0
    while i < len(line):
        c = line[i]
        if c == '"' and (i == 0 or line[i - 1] != "\\"):
            q = not q
        elif c == "-" and not q and line[i:i + 2] == "--":
            return line[:i].rstrip(), i, line[i:]
        i += 1
    return line.rstrip(), 0, ""


def retail(code, col, comment):
    if not comment:
        return code
    return code + " " * max(col - len(code), 2) + comment


def migrate(src):
    out, stack = [], []          # stack of (open_indent, kind)
    for raw in src.splitlines():
        code, col, comment = uncomment(raw)
        if not code.strip():
            out.append(raw)
            continue
        ind = len(code) - len(code.lstrip())
        while stack and stack[-1][0] >= ind:
            stack.pop()
        parent = stack[-1][1] if stack else "file"
        s = code.strip()

        if parent == "code":                 # statements: the subtree is not ours
            out.append(raw)
            continue

        m = BLOCK.fullmatch(s)
        if not m:                            # a field, a state slot, an operand,
            out.append(raw)                  # `NAME is assembly "..."`, a call...
            if re.match(r"^\w+ is (?:assembly|final assembly)\b", s):
                stack.append((ind, "code"))  # its body declares operands
            continue

        name, ports, word = m.group("name"), m.group("ports"), m.group("word")
        runs = (parent == "definition"       # a method
                or (parent == "file" and (name == "program" or ports is not None)))

        if word == "contains":
            new, kind = s[:-len("contains")] + "is", "namespace"
        elif runs:
            new, kind = s[:-len("is")] + "goes", "code"
        else:
            new, kind = s, "definition"

        out.append(retail(" " * ind + new, col, comment))
        stack.append((ind, kind))
    return "\n".join(out) + ("\n" if src.endswith("\n") else "")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    changed = 0
    for arg in argv[1:]:
        p = pathlib.Path(arg)
        before = p.read_text()
        after = migrate(before)
        if after != before:
            p.write_text(after)
            changed += 1
    print(f"migrated {changed} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
