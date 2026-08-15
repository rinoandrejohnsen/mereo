#!/usr/bin/env python3
"""old mereo syntax -> new. One-shot migration.

  use "x"                     -> include "x"
  program with a is           -> program (a) is
  f with a and b is           -> f (a, b) is
  write t where / b is c      -> t.write (b is c)
  open system where / ...     -> linux:open (...)
  exit system                 -> linux:exit
  scan where / ...            -> scan (...)
  x is already file where /.. -> x is already file (...)
  r is assembly "s" where     -> r is assembly "s"      (body stays indented)
  count of arguments          -> arguments.count
  size of msg                 -> msg.size
  port of host is 8080        -> host.port is 8080
  every block                 -> ...gains an `end`

Indentation still carries structure; `end` is a closer the compiler checks.
"""
import re
import sys
import pathlib

WIDTH = 79


def uncomment(line):
    """(code, comment) split, quote-aware -- a `#` inside a string is data.
    The comment carries its own COLUMN so a trailing note stays where the
    author lined it up; `retail` puts it back, or two spaces out if the
    rewritten code has grown past it."""
    q, i = False, 0
    while i < len(line):
        c = line[i]
        if c == '"' and (i == 0 or line[i - 1] != "\\"):
            q = not q
        elif c == "#" and not q:
            return line[:i].rstrip(), _Tail(i, line[i:])
        i += 1
    return line.rstrip(), _Tail(0, "")


class _Tail(str):
    """The trailing comment, remembering the column it sat at."""
    def __new__(cls, col, text):
        o = super().__new__(cls, text)
        o.col = col
        return o


def retail(line, tail):
    if not tail:
        return line
    return line + " " * max(tail.col - len(line), 2) + str(tail)


def dots(expr):
    """`FIELD of INST` -> `INST.FIELD`, and `size of X` -> `X.size`.

    `container of N bytes` is left alone: it is a DECLARATION form, like
    `N bytes` or `constant "..."`, not a member access."""
    if re.search(r"\bcontainer of \b", expr):
        return expr
    expr = re.sub(r'\bsize of ("(?:\\.|[^"\\])*")', r"\1.size", expr)
    expr = re.sub(r"\bsize of (\w+)", r"\1.size", expr)
    return re.sub(r"\b(\w+) of (\w+)", r"\2.\1", expr)


def render(head, binds, ind, tail):
    """A call and its arguments: one line if it fits, else one per line aligned
    under the `(`. A binding that carried a trailing comment keeps it, and
    forces the multi-line form -- the comment belongs to that argument, and
    there is nowhere to put it on a joined line."""
    if not binds:
        return [retail(" " * ind + head, tail)]
    notes = any(t for _, t in binds)
    one = " " * ind + head + " (" + ", ".join(b for b, _ in binds) + ")"
    if not notes and (len(one) <= WIDTH or len(binds) == 1):
        return [retail(one, tail)]
    pad = " " * (ind + len(head) + 2)
    # the header's own note has nowhere to sit once the first argument's note
    # occupies the end of that line, so it moves to its own line above
    out = [" " * ind + str(tail)] if tail else []
    for k, (b, t) in enumerate(binds):
        line = (" " * ind + head + " (" if k == 0 else pad) + b
        line += ")" if k == len(binds) - 1 else ","
        out.append(retail(line, t) if t else line)
    return out


def convert(text):
    lines = text.split("\n")
    out, opens, i = [], [], 0          # opens: indents of blocks awaiting `end`

    def close_to(ind):
        """Emit `end` for every block this line dedents out of. Placed after
        the block's last CODE line, so a trailing blank or a comment that
        introduces what comes next stays outside."""
        while opens and ind <= opens[-1]:
            at = len(out)
            while at > 0 and (not out[at - 1].strip()
                              or out[at - 1].lstrip().startswith("#")):
                at -= 1
            out.insert(at, " " * opens.pop() + "end")

    while i < len(lines):
        raw = lines[i]
        code, tail = uncomment(raw)
        s = code.strip()
        if not s:
            out.append(raw)
            i += 1
            continue
        ind = len(code) - len(code.lstrip())
        close_to(ind)

        def gather(start):
            """The `where` block's bindings: the lines at +4 under it."""
            binds, j = [], start
            while j < len(lines):
                c2, t2 = uncomment(lines[j])
                if not c2.strip():
                    # a blank inside a binding block ends it only if what
                    # follows is not another binding
                    k = j
                    while k < len(lines) and not uncomment(lines[k])[0].strip():
                        k += 1
                    if k >= len(lines):
                        break
                    c3 = uncomment(lines[k])[0]
                    if len(c3) - len(c3.lstrip()) != ind + 4:
                        break
                    j = k
                    continue
                if c2.lstrip().startswith("#"):
                    break
                if len(c2) - len(c2.lstrip()) != ind + 4 or " is " not in c2:
                    break
                binds.append((dots(c2.strip()), t2))
                j += 1
            return binds, j

        # --- include
        if s.startswith('use "'):
            out.append(retail(" " * ind + s.replace("use ", "include ", 1), tail))
            i += 1
            continue

        # --- a declaration whose `where` opens a BODY, not an argument list
        m = re.match(r'^(\w+ is (?:pure |final )?assembly "(?:\\.|[^"\\])*"'
                     r'|\w+ is helper \w+) where$', s)
        if m:
            out.append(retail(" " * ind + m.group(1), tail))
            opens.append(ind)
            i += 1
            continue

        # --- `or continue where` / `or where`
        m = re.match(r"^or( continue)? where$", s)
        if m:
            binds, j = gather(i + 1)
            out += render("or continue" if m.group(1) else "or", binds, ind, tail)
            i = j
            continue

        # --- construction:  NAME is [already |adopted ]CLASS where
        m = re.match(r"^(\w+) is (already |adopted )?(\w+)"
                     r"((?: aligned \d+)?(?: in \w+)?) where$", s)
        if m:
            binds, j = gather(i + 1)
            head = f"{m.group(1)} is {m.group(2) or ''}{m.group(3)}{m.group(4)}"
            out += render(head, binds, ind, tail)
            i = j
            continue

        # --- a syscall:  PRIM system where / PRIM system
        m = re.match(r"^(\w+) system where$", s)
        if m:
            binds, j = gather(i + 1)
            out += render(f"linux:{m.group(1)}", binds, ind, tail)
            i = j
            continue
        m = re.match(r"^(\w+) system$", s)
        if m:
            out.append(retail(" " * ind + f"linux:{m.group(1)}", tail))
            i += 1
            continue

        # --- a method on an instance:  METHOD RECEIVER where
        m = re.match(r"^(\w+) (\w+) where$", s)
        if m:
            binds, j = gather(i + 1)
            out += render(f"{m.group(2)}.{m.group(1)}", binds, ind, tail)
            i = j
            continue

        # --- a free-standing template, or a bare primitive:  NAME where
        m = re.match(r"^(\w+) where$", s)
        if m:
            binds, j = gather(i + 1)
            out += render(m.group(1), binds, ind, tail)
            i = j
            continue

        # --- port declarations:  NAME with a and b is  /  program with a is
        m = re.match(r"^(\w+) with (\w+(?: and \w+)*) is$", s)
        if m:
            out.append(retail(
                " " * ind + f"{m.group(1)} ({m.group(2).replace(' and ', ', ')}) is",
                tail))
            opens.append(ind)
            i += 1
            continue

        # --- everything else: dot the field accesses, and note block openers
        s2 = dots(s)
        out.append(retail(" " * ind + s2, tail))
        if re.search(r"\bgoes$", s2) or s2 == "scope" or re.search(r" is$", s2):
            opens.append(ind)
        i += 1

    close_to(0)
    while opens:
        at = len(out)
        while at > 0 and (not out[at - 1].strip()
                          or out[at - 1].lstrip().startswith("#")):
            at -= 1
        out.insert(at, " " * opens.pop() + "end")
    return "\n".join(out)


if __name__ == "__main__":
    for path in sys.argv[1:]:
        p = pathlib.Path(path)
        p.write_text(convert(p.read_text()))
