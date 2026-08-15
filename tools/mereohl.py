#!/usr/bin/env python3
"""mereohl -- .mereo -> highlighted HTML, or ANSI for a terminal.

Usage: mereohl.py [--dark|--light|--ansi] FILE.mereo [MORE.mereo ...]

The scheme is Kate's Lua one, sampled from how the editor actually draws a Lua
file under Breeze Light rather than reasoned about:

  keywords bold in the text colour, identifiers blue, a call purple, symbols
  magenta, numbers gold, strings red, comments grey.

Four places depart from it, each because mereo differs from Lua in a way that
matters:

  A DECLARED NAME is purple and bold. Lua leaves `function fib_iter` plain and
  colours only built-in calls; a scope reading as a scope at a glance -- `page
  goes` -- is worth the ink. It keeps that look wherever the name is used, so
  `leave page` and `repeat page` match their declaration.

  `is` DOES TWO JOBS and its position says which. Ending a line it opens a
  body, exactly as `goes` does, and carries the same weight; anywhere else it
  binds a value and is drawn as the operator it is, beside `+` and `==`. 428
  openers against 4635 bindings.

  ONLY A LIBRARY CALL IS ONE UNIT. Lua merges `string.format` because that name
  is a listed built-in, not because it has a dot -- a user's `t.go(1)` keeps
  its parts. So `linux.file` is one purple run and `folder.read` is a blue
  receiver and a purple call.

  A PORT NAME IS PLAIN. Ruby would colour it, as it colours `key:`, and that
  was the first instinct here. But every mereo argument has a label, so
  colouring them all said nothing their position did not -- and it made
  `count is count` unreadable.

The word lists come from the compiler itself (`from mereoc import RESERVED,
VIEW_WORDS, CLOBBERABLE`) so a keyword added there cannot go unhighlighted here.
The old highlighter kept its own copy and drifted by three renames.

Everything is one ordered token scan -- no line shapes, no "unrecognized line".
"""

import html
import importlib.util
import pathlib
import re
import sys

_spec = importlib.util.spec_from_file_location(
    "mereoc", pathlib.Path(__file__).resolve().parent.parent / "mereoc.py")
_mereoc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mereoc)
RESERVED, VIEW_WORDS, CLOBBERABLE = (_mereoc.RESERVED, _mereoc.VIEW_WORDS,
                                     _mereoc.CLOBBERABLE)

# Ada bolds reserved words because Ada's are sparse and mark structure. mereo's
# `is` is on nearly every line, often twice -- bolding it made a quarter of all
# visible code bold, and 69% of that was `is` alone. So the two jobs are split:
# what BOUNDS a block stays bold (that is what Ada's convention actually buys,
# the shape of the program at a glance), and the glue recedes.
STRUCTURE = {"goes", "end", "scope", "contains", "program", "failures",
             "include", "extends", "likely"}
# The Linux entry views are reserved, but they never act as keywords: in
# `program (arguments) is` one is a PARAMETER, and in `arguments.count` it is a
# receiver. They read as the names they are.
ENTRY_VIEWS = {"arguments", "environment", "auxiliary"}
# `is` binds a name to a value, or a header to its body. It is the language's
# one operator-shaped word, so it is coloured like an operator and never bold.
GLUE = {"is"}
# what moves, rather than what declares
FLOW = {"leave", "repeat", "when", "ensure", "or", "continue", "acquire",
        "release", "fails"}

# ---------------------------------------------------------------- the scanner
#
# Ordered: the first rule that matches at a position wins. A comment and a
# string come first so nothing inside either is read as code.
RULES = [
    ("comment",   r"--[^\n]*"),
    ("string",    r'"(?:[^"\\\n]|\\.)*"?'),
    ("number",    r"\b(?:0[xX][0-9a-fA-F_]+|0[bB][01_]+|\d[\d_]*\.\d[\d_]*|"
                  r"\d[\d_]*)\b"),
    # `buffer is x` INSIDE an argument list -- Ruby's `buffer:`. Matched before
    # the plain-word rule so the label is not read as an ordinary name.
    ("label",     r"(?<=[(,])\s*\w+(?=\s+is\b)"),
    # a namespace or a receiver, and the member reached through it
    ("qualified", r"\b\w+(?:\.\w+)+"),
    ("word",      r"\b\w+\b"),
    # a member on something that is not a word: `"/hello".size`
    ("dotted",    r"\.\w+"),
    ("operator",  r"==|!=|<=|>=|&&|\|\||<<|>>|[-+*/%&|^~<>()\[\]:,.]"),
    ("space",     r"\s+"),
    ("other",     r"."),
]
SCAN = re.compile("|".join(f"(?P<{k}>{v})" for k, v in RULES))


# A line that DECLARES: the name is the first word, and the line ends in `is`
# (a type, a resource, a method, a template) or is a bare `NAME goes` (a scope
# label something jumps to). Without this a method's DECLARATION and a CALL to
# it look identical -- `read (buffer, capacity, count) is` reads as a call and
# is not one, which is the most confusing thing a resource can do to a reader.
# A reference (`leave scan`, `verdict when ...`) stays plain: Lua's restraint.
DECL_LINE = re.compile(r"^\s*(\w+)(?: \([^)]*\))? is$|^\s*(\w+)(?: likely)? goes$")
# a PRIMITIVE declaration declares its name too, but its header ends in the
# asm template or the C helper's name rather than in `is`
DECL_PRIM = re.compile(r'^\s*\w+ is (?:(?:pure|final) )?assembly "'
                       r'|^\s*\w+ is helper \w+$')


def line_at(src, at):
    lo = src.rfind("\n", 0, at) + 1
    hi = src.find("\n", at)
    return src[lo:hi if hi != -1 else len(src)], lo


# A line that OPENS a block. Bold is spent on those, on the `end` that closes
# one, and on the two jumps -- and on nothing else. A keyword standing inside a
# block is italic instead: it is vocabulary, not structure.
OPENS = re.compile(r"(?: is| goes| contains)$|^scope$"
                   r'|^\w+ is (?:(?:pure|final) )?assembly "'
                   r"|^\w+ is helper \w+$")
# `include` opens no block, so the positional rule would make it italic. It is
# bold anyway: it is the file's own structure, the first thing in every one,
# and what it brings in is the reason the rest parses at all.
ALWAYS_BOLD = {"end", "leave", "repeat", "include"}


def classify(tok, kind, src, at):
    """A token's role. `word` is where the grammar actually speaks."""
    if kind != "word":
        return kind
    # A RESERVED word keeps its own colour wherever it stands -- Ada's rule.
    # `program is` declares nothing, and `acquire (path) is` declares a fixed
    # ROLE, not a name the author picked. Only a name the author picked is a
    # declaration, so this test comes first.
    line, lo = line_at(src, at)
    code = line.split("--")[0].rstrip() if '"' not in line else line.rstrip()
    _bold = tok in ALWAYS_BOLD or bool(OPENS.search(code.strip()))
    if tok in STRUCTURE or tok in FLOW:
        return "structure" if _bold else "inside"
    first = at == lo + len(line) - len(line.lstrip())
    if first and (DECL_LINE.match(code) or DECL_PRIM.match(code)):
        return "decl"          # ...including `read is assembly "syscall"`,
                               # which is an assignment by shape and a
                               # declaration in fact, so it is tested first
    # the first word of an ASSIGNMENT is a name, whatever the word: mereo lets
    # a slot be called `bits` or `cold`, and that line names a slot rather than
    # using the keyword. A header ending in `is` has no value after it, so a
    # declaration is untouched.
    if (at == lo + len(line) - len(line.lstrip())
            and re.match(rf"{re.escape(tok)}\s+is\s+\S", code.strip())):
        # `code` already has the comment stripped, so a trailing `--` cannot be
        # mistaken for a value here the way it could in Kate's line-shaped rule
        return "plain"
    if tok in GLUE:
        # `is` does two jobs and its position says which: at the END of a line
        # it opens a body, exactly as `goes` does, and carries the same weight.
        # Anywhere else it binds a name to a value, and recedes.
        return ("structure"
                if _bold or not code[at - lo + len(tok):].strip() else "bind")
    if re.fullmatch(rf"{re.escape(tok)} contains", code):
        return "namespace_decl"    # bold, like the name in any block opener
    # A scope NAME keeps that formatting wherever it is named: after `leave` or
    # `repeat`, and on the road header that reopens a crossroad. A name should
    # not change appearance between where it is declared and where it is used.
    if re.search(r"\b(?:leave|repeat) $", line[:at - lo]):
        return "decl"
    if first and re.match(rf"{re.escape(tok)} when .+ goes$", code.strip()):
        return "decl"
    if tok in VIEW_WORDS or tok in ("bit", "bits", "constant", "aligned",
                                    "assembly", "helper", "pure", "final",
                                    "adopted", "already", "static", "stack",
                                    "register", "noinline", "cold",
                                    "container", "volatile"):
        return "structure" if _bold else "inside"
    if tok in CLOBBERABLE:
        return "register"
    if tok in ENTRY_VIEWS:
        return "plain"
    if tok in RESERVED:
        return "structure" if _bold else "inside"
    # Lua's restraint: a name is plain unless it is being CALLED, and a call is
    # the one shape a scanner can see -- a name with an argument list after it.
    if re.match(r"\s*\(", src[at + len(tok):]):
        return "call"
    return "plain"


def namespaces_of(src, base):
    """Every `NAME contains` this file and its includes declare.

    Without this the head of a dotted name is guesswork: `linux.file` and
    `output.write` look identical to a scanner, and colouring an instance as a
    namespace is worse than not colouring it at all."""
    seen, found, todo = set(), set(), [base]
    while todo:
        path = todo.pop()
        if path in seen or not path.exists():
            continue
        seen.add(path)
        text = path.read_text()
        found |= set(re.findall(r"^(\w+) contains$", text, re.M))
        # ...and the top-level names an included file declares. Those are this
        # language's built-ins, the `string`/`math` of it, and a call into one
        # is the only dotted call Lua draws as a single unit.
        found |= set(re.findall(r"^(\w+) is$", text, re.M))
        for inc in re.findall(r'^include "([^"]+)"$', text, re.M):
            todo.append((path.parent / inc).resolve())
    return found


def tokens(src, spaces=frozenset()):
    for m in SCAN.finditer(src):
        kind, tok = m.lastgroup, m.group()
        if kind == "label":
            lead = tok[:len(tok) - len(tok.lstrip())]
            if lead:
                yield "space", lead
            yield "label", tok.strip()
            continue
        if kind == "dotted":
            yield "operator", "."
            yield ("call" if re.match(r"\s*\(", src[m.end():]) else "member"), tok[1:]
            continue
        if kind == "qualified":
            parts = tok.split(".")
            called = (re.match(r"\s*\(", src[m.end():]) is not None
                      and not DECL_LINE.match(line_at(src, m.start())[0]))
            for i, part in enumerate(parts):
                if i:
                    yield "operator", "."
                if i == 0:
                    # a NAMESPACE is coloured apart, so `linux.directory` does
                    # not read as one flat run; any other head is a receiver
                    yield ("namespace" if part in spaces else "plain"), part
                elif i == len(parts) - 1:
                    yield ("call" if called else "member"), part
                else:
                    yield "member", part
            continue
        yield classify(tok, kind, src, m.start()), tok


# ------------------------------------------------------------------- themes
#
# One rule set, three renderings. The light theme carries a print block; the
# dark one is what a terminal-coloured editor looks like.
THEMES = {
    # The LIGHT theme is Kate's Breeze Light, sampled from how it draws Lua --
    # keywords bold in the text colour, identifiers blue, a call purple,
    # symbols magenta, numbers gold, comments grey. The DARK one is the same
    # assignment of roles, in colours that hold up on a dark ground.
    "dark": {
        "page": ("#16181a", "#c9c2b6", "#1e2124", "#2c3033", "#8a8578"),
        "tok": {
            "structure": ("#e3dcd0", 1),
            "bind":      ("#c98fc9", 0),   # `is` binding: the operator it is
            "inside":    ("#e3dcd0", 0),   # a keyword standing in a block
            "decl":      ("#b48ead", 1),
            "call":      ("#b48ead", 0),
            "namespace": ("#d8b878", 0),   # the number colour
            "namespace_decl": ("#d8b878", 1),   # ...bold where it is declared
            "member":    ("#7fb3d5", 0),
            "label":     ("#7fb3d5", 0),   # a port belongs to the callee
            "register":  ("#5fb3d9", 0),
            "number":    ("#d8b878", 0),
            "string":    ("#d08f7a", 0),
            "operator":  ("#c98fc9", 0),
            "comment":   ("#6f6a5f", 0),
            "plain":     ("#c9c2b6", 0),
        },
    },
    "light": {
        # Kate's Breeze Light, MEASURED rather than transcribed: both engines
        # were run over the same files and the colour Kate gave each token
        # class was read off, character by character. docs/mereo.html uses this
        # theme, so a snippet in the guide is pixel-for-pixel the editor.
        "page": ("#ffffff", "#1f1c1b", "#ffffff", "#e2ded6", "#8a857c"),
        "tok": {
            "structure": ("#1f1c1b", 1),
            "inside":    ("#1f1c1b", 0),   # a keyword standing in a block
            "decl":      ("#644a9b", 1),
            "call":      ("#644a9b", 0),
            "namespace": ("#b08000", 0),
            "namespace_decl": ("#b08000", 1),
            "member":    ("#0057ae", 0),
            "label":     ("#0057ae", 0),
            "register":  ("#3daee9", 0),
            "number":    ("#b08000", 0),
            "string":    ("#bf0303", 0),
            "operator":  ("#ca60ca", 0),
            "bind":      ("#ca60ca", 0),
            "comment":   ("#898887", 0),
            "plain":     ("#1f1c1b", 0),
        },
    },
}

# Classes drawn in italic as well as their weight. `is` binding a value is
# bold AND italic; `is` opening a body is bold alone, so the two roles stay
# apart while both carry the column.
ITALIC = {"comment", "inside"}

ANSI = {"structure": "1;97", "bind": "95", "inside": "3;97", "decl": "1;35", "call": "35", "namespace": "33", "namespace_decl": "1;33",
        "member": "34", "label": "34", "register": "96", "number": "33",
        "string": "31", "operator": "95", "comment": "90", "plain": "0"}

PRINT_CSS = """@media print {
  body { max-width: none; margin: 0; font-size: 11px; }
  pre.code { border: 1px solid #ddd; background: none; }
  * { print-color-adjust: exact; -webkit-print-color-adjust: exact; }
}"""


def render_html(files, theme):
    bg, fg, panel, border, sub = theme["page"]
    css = [f"body{{background:{bg};color:{fg};font:14px/1.55 ui-monospace,"
           "SFMono-Regular,Menlo,Consolas,monospace;max-width:96ch;"
           "margin:2rem auto;padding:0 1rem}",
           f"h2{{font-size:1rem;color:{sub};font-weight:normal;margin:2rem 0 .4rem}}",
           f"pre.code{{background:{panel};border:1px solid {border};"
           "border-radius:6px;padding:1rem 1.1rem;overflow-x:auto}",
           "pre.code{counter-reset:l}",
           f".ln{{color:{border};user-select:none}}"]
    for name, (colour, bold) in theme["tok"].items():
        css.append(f".{name}{{color:{colour}"
                   + (";font-weight:600" if bold else "")
                   + (";font-style:italic" if name in ITALIC else "") + "}")
    out = ["<meta charset=\"utf-8\">", "<title>mereo</title>",
           "<style>" + "\n".join(css) + "\n" + PRINT_CSS + "</style>"]
    for path in files:
        p = pathlib.Path(path)
        src = p.read_text()
        spaces = namespaces_of(src, p.resolve())
        # a file's trailing newline is not a line -- numbering it left a blank
        # numbered row under every listing
        src = src[:-1] if src.endswith("\n") else src
        body, width = [], len(str(src.count("\n") + 1))
        line = 1
        body.append(f'<span class="ln">{line:>{width}} </span>')
        for kind, tok in tokens(src, spaces):
            for k, piece in enumerate(tok.split("\n")):
                if k:
                    line += 1
                    body.append(f'\n<span class="ln">{line:>{width}} </span>')
                if piece:
                    body.append(f'<span class="{kind}">{html.escape(piece)}</span>')
        out.append(f"<h2>{html.escape(str(path))}</h2>")
        out.append('<pre class="code">' + "".join(body) + "</pre>")
    return "\n".join(out)


def render_ansi(files):
    out = []
    for path in files:
        p = pathlib.Path(path)
        src = p.read_text()
        out.append(f"\033[1m== {path}\033[0m\n")
        for kind, tok in tokens(src, namespaces_of(src, p.resolve())):
            out.append(tok if kind in ("space", "other")
                       else f"\033[{ANSI[kind]}m{tok}\033[0m")
        out.append("\n")
    return "".join(out)


def main(argv):
    mode, files = "dark", []
    for a in argv:
        if a in ("--dark", "--light", "--ansi"):
            mode = a[2:]
        elif a.startswith("--"):
            sys.exit(f"mereohl: unknown option {a}")
        else:
            files.append(a)
    if not files:
        sys.exit("usage: mereohl.py [--dark|--light|--ansi] FILE.mereo ...")
    if mode == "ansi":
        sys.stdout.write(render_ansi(files))
    else:
        print(render_html(files, THEMES[mode]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
