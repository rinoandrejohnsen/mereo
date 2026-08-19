#!/usr/bin/env python3
"""Retired syntax in .mereo COMMENTS.

`docs/build.py` refuses to ship a retired spelling in the documentation. The
library's comments are documentation too -- `linux.mereo` carries a worked
example above nearly every resource, and those are what a reader copies -- but
nothing checked them, so the 2026-08-14 surface change left twenty-odd snippets
written in a syntax that no longer compiles. Someone following the `ppoll`
comment would have written `descriptor of watched is here` and been refused by
the parser, with the library itself as the source of the mistake.

The difficulty is that `of`, `where`, `use` and `system` are ordinary English,
and these files are mostly prose. So a line is only examined when it is
CODE-SHAPED:

  * an indented snippet -- `--` followed by three or more spaces, which is the
    convention every worked example in core/linux already follows; prose gets
    exactly one space, and
  * anything inside `backticks`, wherever it appears.

That split is what `docs/build.py` settled on for the same reason, and it is
why "the end of the directory" in a sentence is left alone while
`length of info` in a snippet is not.
"""
import pathlib
import re
import sys

# `X of Y` is also how English says it, and these files are mostly English. What
# separates the retired projection from the preposition is what follows `of`: a
# projection names an INSTANCE, so a determiner or a quantifier there means the
# line is a sentence ("the end of the directory", "a length of zero") and not a
# member read.
ENGLISH = "(?:" + "|".join("""
    the a an that this these those it its their his her our your my
    two three four five six nine ten zero one all both each every
    any some no what which course them us here now there
""".split()) + ")"

#   (pattern, what is true now)
RETIRED = [
    (r"\bsize of \w+",
     "a size is `X.size` -- the compile-time member, not a phrase"),
    (rf"\b\w+ of (?!{ENGLISH}\b)\w+\b",
     "projection reads `INSTANCE.FIELD` -- not `FIELD of INSTANCE`"),
    (rf"\b\w+ from (?!{ENGLISH}\b)\w+",
     "projection reads `INSTANCE.FIELD` -- neither `from` nor `of`"),
    (r"\b\w+ \w+ where\s*$",
     "a call's arguments ride in its own parentheses: `RECEIVER.METHOD (a is b)`"),
    (r"\bprogram with \w+",
     "the argument view is a parameter: `program (arguments) is`"),
    (r"\buse \"",
     'a library is pulled in with `include "..."`'),
    (r"\b\w+ system\b",
     "a syscall is `linux.NAME (...)`"),
]

SNIPPET = re.compile(r"^\s*--\s{3,}(?P<code>\S.*)$")
SPAN = re.compile(r"`([^`\n]+)`")


def scan(root):
    files = ["core.mereo", "linux.mereo"]
    for sub in ("examples", "tests/progs", "programs"):
        files += sorted(str(p.relative_to(root))
                        for p in (root / sub).rglob("*.mereo"))

    bad = []
    for rel in files:
        path = root / rel
        if not path.exists():
            continue
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if "--" not in line:
                continue
            # the two code-shaped contexts, examined; prose, skipped
            fragments = []
            m = SNIPPET.match(line)
            if m:
                fragments.append(m.group("code"))
            comment = line[line.index("--"):]
            fragments += SPAN.findall(comment)

            for frag in fragments:
                for pattern, truth in RETIRED:
                    if re.search(pattern, frag):
                        bad.append((rel, n, frag.strip(), truth))
                        break
    return bad


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                        else pathlib.Path(__file__).resolve().parent.parent)
    bad = scan(root)
    for rel, n, frag, truth in bad:
        print(f"  {rel}:{n}: retired syntax in a comment: {frag}")
        print(f"      now: {truth}")
    n_files = len({b[0] for b in bad})
    if bad:
        print(f"comments: {len(bad)} retired spelling(s) in {n_files} file(s)")
        return 1
    print("comments: no retired syntax in .mereo comments")
    return 0


if __name__ == "__main__":
    sys.exit(main())
