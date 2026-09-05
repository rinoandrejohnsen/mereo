#!/usr/bin/env python3
"""mereolsp -- a language server for mereo, over stdio.

WHAT IT DOES NOT DO IS HIGHLIGHTING, and that is a measured decision rather
than a gap. Kate 26.08's LSP client maps a server's semantic tokens onto seven
attributes (`semantic_tokens_legend.cpp`: DataType, Keyword, Variable,
Preprocessor, Function, Constant, Comment), each taking its colour AND its
bold/italic from the theme's own style, and it discards the modifier field
outright -- `// auto mod = data[i + 4];` in `lspsemantichighlighting.cpp`. Of
the twelve looks mereo's scheme uses, three are reachable that way. So
`tools/mereo.xml` keeps the colours, this serves everything the XML cannot
know, and nothing here draws: `documentHighlightProvider` and
`semanticTokensProvider` are deliberately NOT declared, because a server that
declares them starts repainting text the highlighter already owns.

What it serves instead is what a language server is actually for:

  DIAGNOSTICS   mereoc's own refusals, on the line they name, as you type.
                Run in a SUBPROCESS -- mereoc keeps module-level state
                (`CONSTANTS`, `FIELD_SIZES`) that `transpile` does not clear,
                so a second run in the same interpreter would see the first
                run's declarations. A fresh interpreter cannot drift.
                Measured: 95 ms for a typical program, 609 ms for the TLS
                client, against a 300 ms debounce.
  SYMBOLS       the outline: namespaces, resources, methods, templates, named
                scopes, slots and view fields, nested as the source nests them.
  DEFINITION    a name -> where it was declared, across `include`s.
  HOVER         what a name is, with a template's ports and an instance's type.
  COMPLETION    a callee's PORT NAMES inside its argument list, members after a
                dot, and names in scope. Ports are the one this language wants
                most: every mereo argument is `port is value` and the port
                names belong to the callee, which is the thing an editor knows
                and a reader does not.
  REFERENCES    every mention, for a rename done by hand.

The word lists come from the compiler (`RESERVED`, `VIEW_WORDS`) the way
`tools/mereohl.py` takes them, so a keyword added there cannot go unknown here.

    python3 mereolsp.py              serve on stdin/stdout
    python3 mereolsp.py --compile    the diagnostics worker (internal)

Wire it into Kate with ~/.config/kate/lspclient/settings.json:

    {"servers": {"mereo": {"command": ["python3", "<repo>/mereolsp.py"],
                           "highlightingModeRegex": "^Mereo$",
                           "rootIndicationFileNames": ["build.sh"]}}}
"""

import importlib.util
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent


_MEREOC = None


def _load_mereoc():
    """The compiler, imported as a module, once. `tools/mereohl.py` does the same
    thing for the same reason: the keyword lists have ONE home."""
    global _MEREOC
    if _MEREOC is None:
        spec = importlib.util.spec_from_file_location("mereoc",
                                                      HERE / "mereoc.py")
        _MEREOC = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_MEREOC)
    return _MEREOC


try:
    _COMPILER = _load_mereoc()
    RESERVED, VIEW_WORDS = _COMPILER.RESERVED, _COMPILER.VIEW_WORDS
except Exception as _e:                    # the server still serves without it
    print(f"mereolsp: mereoc.py did not import ({_e})", file=sys.stderr)
    RESERVED = set()
    VIEW_WORDS = {"signed", "unsigned", "big", "little", "float", "whole",
                  "volatile"}


# --------------------------------------------------------------- diagnostics
#
# The worker runs as `mereolsp.py --compile`, reads a job on stdin and writes
# the answer on stdout. It is a separate process per run, which is what keeps
# mereoc's module state from leaking between edits, and it means a compiler
# crash costs one diagnostic rather than the session.

def compile_worker():
    """{"path": ..., "overlay": {path: text}} -> {"diagnostics": [...]}.

    The overlay is what the EDITOR holds, which is not what is on disk: a
    buffer is diagnosed unsaved. mereoc reads its sources through `open` in
    `load()`, so shadowing that one name in the module's globals redirects
    every read without touching the compiler."""
    job = json.load(sys.stdin)
    overlay = {os.path.realpath(k): v for k, v in job.get("overlay", {}).items()}
    # the answer goes on the REAL stdout; anything the compiler decides to
    # print goes to stderr, where it cannot corrupt the frame.
    answer, sys.stdout = sys.stdout, sys.stderr
    mereoc = _load_mereoc()

    def _open(path, *args, **kwargs):
        real = os.path.realpath(path)
        if real in overlay:
            return io.StringIO(overlay[real])
        return io.open(path, *args, **kwargs)

    mereoc.open = _open                    # found before builtins in load()
    ports = {}
    _derive = mereoc.derive_port_needs

    def _watch(definitions):
        """`plan()` derives every port's direction and then throws the working
        set away. Wrapping the derivation is how the answer gets out without
        the server re-deriving it -- and re-deriving it is exactly the drift
        the highlighter already learned not to risk."""
        _derive(definitions)
        try:
            ports.update(port_table(mereoc, definitions))
        except Exception:
            pass                           # a table is a bonus, never a fault

    mereoc.derive_port_needs = _watch
    path = job["path"]
    prog = os.path.basename(path)
    prog = prog[:-6] if prog.endswith(".mereo") else prog
    try:
        sources = mereoc.load(path, set(), [])
        mereoc.transpile(sources, prog)
    except SystemExit as e:
        json.dump({"ports": ports, "error": str(e)}, answer)
        return
    except RecursionError:
        json.dump({"ports": ports, "error": "mereoc: error: recursion limit -- the file is "
                            "probably mid-edit"}, answer)
        return
    except Exception as e:                 # a crash is a diagnostic too
        json.dump({"ports": ports, "error": f"mereoc: error: {type(e).__name__}: {e}"},
                  answer)
        return
    json.dump({"ports": ports, "error": None}, answer)


def port_table(mereoc, definitions):
    """callable -> {port: "in" | "out"}, from the compiler's own two answers.

    A port's direction is never declared, and mereoc knows it two ways. For a
    TEMPLATE it is derived from the body -- read the port and it is an input,
    assign it and it is an output -- which `derive_port_needs` has just left in
    `port_needs`. For a PRIMITIVE it is written down (`written out rax`), and a
    method that binds one inherits it through `bind`: the parameter wired to
    the primitive's single out-port is this method's out-port.

    Measured over the corpus reachable from one program: 133 callables, 110
    out-ports, 19 with none -- `builder.add`, every `acquire`, `linux.exit`."""
    prims = getattr(mereoc, "PRIMITIVES", None) or {}
    table = {}
    for name, prim in prims.items():
        row = {port: "in" for kind, port in prim.get("args") or []
               if kind != "const"}
        if prim.get("out"):
            row[prim["out"]] = "out"
        table[name] = row
    for dname, defn in definitions.items():
        for mname, meth in (defn.get("methods") or {}).items():
            params = meth.get("params") or []
            outs = {port for port, kinds in (meth.get("port_needs") or {}).items()
                    if "out" in kinds}
            prim = prims.get(meth.get("prim") or "")
            if prim and prim.get("out"):
                bound = (meth.get("bind") or {}).get(prim["out"])
                if bound and bound[0] in params:
                    outs.add(bound[0])
            table[f"{dname}.{mname}"] = {p: ("out" if p in outs else "in")
                                         for p in params}
    return table


# `mereoc: error: [FILE: ][line N: ]MESSAGE`. 288 of mereoc's 305 refusals
# carry a line; the rest are about the file as a whole (an import cycle, a
# missing include) and land on line 1. The FILE is a basename -- `CURRENT_FILE`
# is set per source in `transpile` -- and is absent entirely for the checks
# that run after the parse loop, which is why a missing one means "the file
# being compiled".
_ERROR = re.compile(r"^mereoc: error: (?:([\w.\-]+\.mereo): )?"
                    r"(?:line (\d+): )?(.*)$", re.S)
# `no program goes` is not a fault in a LIBRARY -- it is how a library ends.
# Reaching it means every declaration in the file parsed and checked.
_LIBRARY_OK = "no `program goes`"


def parse_error(text):
    """mereoc's one-line refusal -> (basename or None, line or None, message)."""
    m = _ERROR.match(text.strip())
    if not m:
        return None, None, text.strip()
    return m.group(1), int(m.group(2)) if m.group(2) else None, m.group(3)


# ---------------------------------------------------------------- the index
#
# LSP SymbolKind. Named rather than numbered at the use sites, because a bare
# 5 in a symbol tree is unreadable and wrong in a way nothing catches.
NAMESPACE, CLASS, METHOD, PROPERTY, FIELD = 3, 5, 6, 7, 8
CONSTRUCTOR, FUNCTION, VARIABLE, CONSTANT, KEY, STRUCT, ARRAY = 9, 12, 13, 14, 20, 23, 18


class Sym:
    """One declared thing, with the block it owns.

    `end_line` is what makes the tree usable for more than an outline: it is
    how a position finds the innermost declaration containing it, which is how
    a bare name is resolved to the nearest binding rather than to a same-named
    one in another method."""

    __slots__ = ("name", "kind", "detail", "line", "col", "end_line",
                 "children", "ports", "type_of", "doc", "container",
                 "attached")

    def __init__(self, name, kind, line, col, detail="", ports=None,
                 type_of=None):
        self.name, self.kind, self.detail = name, kind, detail
        self.line, self.col, self.end_line = line, col, line
        # Fields ATTACHED to this name later in the file. Not children: a child
        # lives inside its parent's block and an attached field is written
        # after it, so nesting them would put the outline's ranges wrong. They
        # answer `X.field` and nothing else.
        self.attached = []
        self.children, self.ports, self.type_of = [], ports or [], type_of
        self.doc, self.container = "", None

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    def holds(self, line):
        return self.line <= line <= self.end_line


# Every line shape that DECLARES. Order matters: the first that matches wins,
# and the general `NAME is` block opener has to come after the forms that also
# end in `is` but mean something else.
_PRIMITIVE = re.compile(r'^(\w+) is (?:(?:pure|final) )*assembly "')
_HELPER = re.compile(r"^(\w+) is helper \w+$")
_TEMPLATE = re.compile(r"^(\w+) \((.*)\) goes$")
_NOARG_METHOD = re.compile(r"^(release|acquire)(?: \((.*)\))? goes$")
_PROGRAM = re.compile(r"^program(?: \((.*)\))? goes$")
_SCOPE = re.compile(r"^(\w+)(?: likely)? goes$")
_BLOCK = re.compile(r"^(\w+) is$")
_EXTENDS = re.compile(r"^(\w+) extends ((?:\w+\.)*\w+) is$")
_FIELD_BYTES = re.compile(r"^(\w+) is (\d+|\w+(?:\.size)?) bytes\b(.*)$")
_FIELD_BIT = re.compile(r"^(\w+) is bits? (\d+)(?: to (\d+))?$")
_INSTANCE = re.compile(r"^(\w+) is (?:(already|adopted|new) )?"
                       r"((?:\w+\.)*\w+)(?: \(|$)")
# the trailing `(...)` is a view initialiser -- `host is block as sockaddr_in
# (family is 2)` -- and a PROMOTION (`page is page as builder (count is 0)`)
# is the same form with the backing's own name on the right.
_AS_VIEW = re.compile(r"^(\w+) is (.+?) as ((?:\w+\.)*\w+)(?: \((.*)\))?$")
_BIND = re.compile(r"^(\w+) is (.+)$")
_INCLUDE = re.compile(r'^include "([^"]*)"$')


def _depth(code, start=0):
    """Parenthesis depth after `code`, ignoring what is inside a string."""
    d, inq = start, False
    for i, c in enumerate(code):
        if c == '"' and (i == 0 or code[i - 1] != "\\"):
            inq = not inq
        elif not inq and c == "(":
            d += 1
        elif not inq and c == ")":
            d -= 1
    return d


def _code_lines(text):
    """(indent, 0-based line number, code) per LOGICAL line -- blanks and
    whole-line comments dropped, and an open argument list joined to what
    closes it.

    Two rules from the compiler, for the same reasons it has them. The comment
    rule is `_uncomment`'s: a `--` outside a string literal, because a line
    carrying a literal may also carry a note. The continuation rule is the one
    place a mereo line continues -- without it the second line of
    `open (path is path,` / `flags is flags)` reads as a declaration of
    `flags`, and every wired port becomes a phantom slot."""
    phys, out, i = text.splitlines(), [], 0
    while i < len(phys):
        code = _uncomment(phys[i]).rstrip()
        if not code.strip():
            i += 1
            continue
        indent, n, acc = len(code) - len(code.lstrip()), i, code.strip()
        d = _depth(code)
        while d > 0 and i + 1 < len(phys):
            i += 1
            nxt = _uncomment(phys[i]).strip()
            acc += " " + nxt
            d = _depth(nxt, d)
        out.append((indent, n, acc))
        i += 1
    return out


def _uncomment(line):
    inq = False
    for i, c in enumerate(line):
        if c == '"':
            inq = not inq
        elif c == "-" and line[i + 1:i + 2] == "-" and not inq:
            return line[:i].rstrip()
    return line


def _ports(arglist):
    return [p.strip() for p in arglist.split(",") if p.strip()]


def _kind_of_block(sym):
    """What a `NAME is` block turned out to be, decided by what it HOLDS.

    mereo has no keyword for any of these -- a namespace, a resource, a group
    of templates and a view are all `NAME is` and an indented body, which is
    the language's economy and the indexer's one real question. The body
    answers it: a lifecycle method makes it a resource, byte or bit fields make
    it a view, anything else is a namespace."""
    kinds = {c.kind for c in sym.children}
    if any(c.name in ("acquire", "release") for c in sym.children):
        return CLASS
    if kinds and kinds <= {FIELD}:
        return STRUCT              # bytes and nothing else: a view
    if FIELD in kinds:
        return CLASS               # state AND methods: `span`, `builder`
    return NAMESPACE               # templates only: `text`, `bits`


def index(text, path=""):
    """The file's declarations, nested as the source nests them.

    Structure is INDENTATION (`end` is a closer mereoc checks against it), so
    the walk is by indent: a body is every following line indented past its
    opener. That also means a half-written file still indexes -- the outline
    does not blink out while a block is missing its `end`."""
    lines = _code_lines(text)
    includes = []
    for indent, n, code in lines:
        m = _INCLUDE.match(code)
        if m:
            includes.append((m.group(1), n))
        elif indent == 0 and not code.startswith("include"):
            break                      # the include block ends at first content

    def block(i, indent):
        """Symbols declared at `indent`, from line i. -> (syms, next i).

        A body sits at `indent + 2` and its `end` sits back at `indent`, so
        this stops AT the `end` and leaves it for whoever opened the block --
        which is what makes a top-level `end` close its own definition instead
        of the file."""
        out = []
        while i < len(lines):
            ind, n, code = lines[i]
            if ind < indent or code == "end":
                break
            if ind > indent:           # a continuation line, or a stray body
                i += 1
                continue
            sym, opens = _declared(code, n, ind)
            i += 1
            if (not opens and i < len(lines)
                    and lines[i][0] > ind and lines[i][2] != "end"):
                # a shape this indexer does not know, but the indentation says
                # it opens a block. Believing the indentation is what stops one
                # unknown form from handing its `end` to an enclosing block and
                # truncating the rest of the file -- which is exactly what
                # `tty extends file is` did before it was recognised.
                opens = True
            if not opens:
                if sym is not None:
                    out.append(sym)
                continue
            children, i = block(i, indent + 2)
            end_line = lines[i - 1][1] if i else n
            if i < len(lines) and lines[i][0] == indent and lines[i][2] == "end":
                end_line = lines[i][1]
                i += 1
            if sym is None:
                # `scope` and a guard declare no name of their own, so what
                # they hold belongs to the nearest named ancestor -- which is
                # where a reader looks for it.
                out += children
                continue
            sym.children = children
            for child in children:
                # `tty extends file` means `linux`'s file, because that is
                # where `tty` is written. Without the container the name is
                # resolved at the top level, where no `file` exists.
                child.container = sym
            sym.end_line = end_line
            if sym.kind is None:
                sym.kind = _kind_of_block(sym)
            out.append(sym)
        return out, i

    syms, _ = block(0, 0)

    # ATTACHED fields. `buffer.count is 0` gives a name that already exists a
    # member, where it is first written -- so the line declares nothing on its
    # own and the walk above passes over it. Hang the field on the host it
    # names, once, at its first mention.
    hosts = {}

    def collect(ss):
        for sym in ss:
            hosts.setdefault(sym.name, sym)
            collect(sym.children)

    collect(syms)
    for ind, n, code in lines:
        m = re.match(r"^(\w+)\.(\w+) is (.+)$", code)
        if m is None:
            continue
        host = hosts.get(m.group(1))
        if host is None or any(c.name == m.group(2)
                               for c in host.children + host.attached):
            continue
        col = ind + code.index(".") + 1
        host.attached.append(Sym(m.group(2), FIELD, n, col, m.group(3)))
    return syms, includes


def _declared(code, n, indent):
    """One line -> (Sym or None, does it open a block).

    A guard (`count == 0 goes`) opens a block and declares nothing, which is
    why the two answers are separate."""
    col = indent

    def at(name):
        return code.index(name) + col

    m = _PROGRAM.match(code)
    if m:
        s = Sym("program", FUNCTION, n, at("program"), "the program",
                _ports(m.group(1) or ""))
        return s, True
    m = _NOARG_METHOD.match(code)
    if m:
        kind = CONSTRUCTOR if m.group(1) == "acquire" else METHOD
        s = Sym(m.group(1), kind, n, at(m.group(1)),
                "lifecycle", _ports(m.group(2) or ""))
        return s, True
    m = _TEMPLATE.match(code)
    if m:
        ports = _ports(m.group(2))
        s = Sym(m.group(1), FUNCTION, n, at(m.group(1)),
                "(" + ", ".join(ports) + ")", ports)
        return s, True
    m = _PRIMITIVE.match(code) or _HELPER.match(code)
    if m:
        return Sym(m.group(1), FUNCTION, n, at(m.group(1)), "primitive"), True
    m = _EXTENDS.match(code)
    if m:
        # `type_of` is what carries inheritance: a method not found on `tty` is
        # looked for on `file`, which is exactly what the language does.
        return Sym(m.group(1), CLASS, n, at(m.group(1)),
                   f"extends {m.group(2)}", type_of=m.group(2)), True
    m = _BLOCK.match(code)
    if m:
        s = Sym(m.group(1), None, n, at(m.group(1)))
        return s, True
    m = _SCOPE.match(code)
    if m:
        return Sym(m.group(1), KEY, n, at(m.group(1)), "scope"), True
    if code == "scope" or code.endswith(" goes"):
        return None, True              # anonymous scope, or a guard
    m = _FIELD_BIT.match(code)
    if m:
        detail = (f"bits {m.group(2)} to {m.group(3)}" if m.group(3)
                  else f"bit {m.group(2)}")
        return Sym(m.group(1), FIELD, n, at(m.group(1)), detail), False
    m = _FIELD_BYTES.match(code)
    if m:
        return Sym(m.group(1), FIELD, n, at(m.group(1)),
                   f"{m.group(2)} bytes{m.group(3)}"), False
    m = _INSTANCE.match(code)
    if m and (m.group(2) or "(" in code) and not m.group(3).isdigit():
        how = m.group(2) or "owned"
        return Sym(m.group(1), VARIABLE, n, at(m.group(1)),
                   f"{how} {m.group(3)}", type_of=m.group(3)), False
    m = _AS_VIEW.match(code)
    if m and m.group(3) not in VIEW_WORDS:
        # `as signed` is a READING of bytes; `as linux.file_status` is a view,
        # and only the second one brings members with it.
        detail = (f"promoted to {m.group(3)}" if m.group(2) == m.group(1)
                  else f"{m.group(2)} as {m.group(3)}")
        return Sym(m.group(1), VARIABLE, n, at(m.group(1)), detail,
                   type_of=m.group(3)), False
    m = _BIND.match(code)
    if m:
        # a name bound at the LEFT MARGIN is a constant: the one binding the
        # language folds at compile time.
        kind = CONSTANT if col == 0 else VARIABLE
        value = m.group(2)
        # `work is linux.terminal_settings` takes no arguments, so nothing but
        # the shape of the value says it is a construction. A bare name is
        # carried as a possible type and checked when a member is asked for --
        # `n is at` names a scalar, and a scalar answers no members.
        kind_of = value if re.fullmatch(r"(?:\w+\.)*\w+", value) else None
        return Sym(m.group(1), kind, n, at(m.group(1)), value,
                   type_of=kind_of), False
    return None, False


# ------------------------------------------------------------- the project
#
# A mereo file is not an island: a program reaches `linux.file` and `text.find`
# through `include`, so every answer here -- a definition, a hover, a member
# list -- has to cross files. The graph is small (two libraries and a program)
# and the parse is a line scan, so the whole thing is re-read rather than
# incrementally maintained. Measured on this repo: 230 files, 42 ms.

class Doc:
    __slots__ = ("path", "text", "lines", "syms", "includes", "stamp")

    def __init__(self, path, text):
        self.path, self.text = path, text
        self.lines = text.splitlines()
        syms, incs = index(text, path)
        self.syms = syms
        base = os.path.dirname(path) or "."
        self.includes = [os.path.realpath(os.path.join(base, t))
                         for t, _ in incs]
        self.stamp = time.monotonic()

    @classmethod
    def synthetic(cls, path, text):
        """A Doc over text that is not a mereo file, so it is NOT indexed as
        one. `mereoc.py` arrives this way: it is where the entry views are
        defined, so it is where `go to definition` on one should land."""
        d = cls.__new__(cls)
        d.path, d.text, d.lines = path, text, text.splitlines()
        d.syms, d.includes, d.stamp = [], [], time.monotonic()
        return d

    def top(self):
        return {s.name: s for s in self.syms}

    def enclosing(self, line):
        """The declarations containing `line`, outermost first. A bare name is
        resolved against these before the file's top level, so a port called
        `count` finds ITS method's port and not another method's."""
        out, here = [], self.syms
        while True:
            for s in here:
                if s.holds(line) and s.children:
                    out.append(s)
                    here = s.children
                    break
            else:
                return out


_ENTRY = None


def entry_views():
    """`arguments`, `environment`, `auxiliary` -> synthetic symbols.

    The kernel leaves these on the stack and mereoc knows their fields as a
    TABLE (`VIEW_FIELDS`), not as source, so nothing an indexer reads declares
    them. Taken from the compiler for the same reason the keywords are: a
    field added there must not go unknown here."""
    global _ENTRY
    if _ENTRY is not None:
        return _ENTRY
    _ENTRY = {}
    fields = getattr(_COMPILER, "VIEW_FIELDS", None) if _COMPILER else None
    if not fields:
        return _ENTRY
    src = (HERE / "mereoc.py").read_text()
    line = src[:src.index("VIEW_FIELDS = {")].count("\n") if \
        "VIEW_FIELDS = {" in src else 0
    doc = Doc.synthetic(str(HERE / "mereoc.py"), src)
    for view, members in fields.items():
        sym = Sym(view, STRUCT, line, 0, "an entry view the kernel leaves")
        sym.end_line = line
        for name in members:
            sym.children.append(Sym(name, FIELD, line, 0, f"{view} field"))
        _ENTRY[view] = (sym, doc)
    return _ENTRY


class Project:
    """Every .mereo the session has looked at, plus what the editor holds
    unsaved. A buffer always wins over the file on disk."""

    def __init__(self):
        self.root = None
        self.buffers = {}                  # path -> text as the editor has it
        self.cache = {}                    # path -> (mtime or None, Doc)
        self._hosts = (0.0, {})

    def text_of(self, path):
        if path in self.buffers:
            return self.buffers[path]
        try:
            with open(path) as f:
                return f.read()
        except OSError:
            return None

    def doc(self, path):
        path = os.path.realpath(path)
        if path in self.buffers:
            key = ("buffer", len(self.buffers[path]), self.buffers[path][:64])
        else:
            try:
                key = os.stat(path).st_mtime_ns
            except OSError:
                return None
        cached = self.cache.get(path)
        if cached and cached[0] == key:
            return cached[1]
        text = self.text_of(path)
        if text is None:
            return None
        doc = Doc(path, text)
        self.cache[path] = (key, doc)
        return doc

    def reachable(self, path, seen=None):
        """`path` and everything it includes, depth first. The order matters
        for name resolution: the file itself shadows what it imports."""
        seen = set() if seen is None else seen
        real = os.path.realpath(path)
        if real in seen:
            return []
        seen.add(real)
        doc = self.doc(real)
        if doc is None:
            return []
        out = [doc]
        for inc in doc.includes:
            out += self.reachable(inc, seen)
        return out

    def hosts(self):
        """file -> a program that includes it.

        A library has no `program`, so compiling it alone gets as far as "no
        `program goes`" and stops. Compiling a program that USES it exercises
        the same declarations for real, which is the difference between
        checking that `core.mereo` parses and checking that it still compiles.
        Rebuilt at most every 5 seconds; the scan reads only each file's
        include block, which ends at its first line of content."""
        now = time.monotonic()
        if now - self._hosts[0] < 5.0 and self._hosts[1]:
            return self._hosts[1]
        found = {}
        root = self.root or str(HERE)
        for f in sorted(pathlib.Path(root).rglob("*.mereo")):
            if "attic" in f.parts or "build" in f.parts:
                continue
            doc = self.doc(str(f))
            if doc is None or "program" not in doc.top():
                continue
            deps = self.reachable(doc.path)
            for dep in deps:
                best = found.get(dep.path)
                if best is None or len(deps) > best[1]:
                    found[dep.path] = (doc.path, len(deps))
        found = {k: v[0] for k, v in found.items()}
        self._hosts = (now, found)
        return found


# ------------------------------------------------------------- resolution

_WORD = re.compile(r"\w+")


def chain_at(line, ch):
    """The dotted name under the cursor, and which part of it that is.

    `linux.files.remove` with the cursor on `files` gives (['linux','files',
    'remove'], 1, start, end) -- enough to resolve the prefix and to know what
    range to underline."""
    if not line:
        return None
    i = ch
    if i >= len(line) or not (line[i].isalnum() or line[i] == "_"):
        i = max(0, i - 1)
    if i >= len(line) or not (line[i].isalnum() or line[i] == "_"):
        return None
    start = i
    while start > 0 and (line[start - 1].isalnum() or line[start - 1] == "_"):
        start -= 1
    end = i
    while end + 1 < len(line) and (line[end + 1].isalnum()
                                   or line[end + 1] == "_"):
        end += 1
    end += 1
    # walk left over `.name` groups, and right over the rest of the chain
    head = start
    while head >= 2 and line[head - 1] == "." and (line[head - 2].isalnum()
                                                   or line[head - 2] == "_"):
        head -= 2
        while head > 0 and (line[head - 1].isalnum() or line[head - 1] == "_"):
            head -= 1
    tail = end
    while tail < len(line) and line[tail] == "." and tail + 1 < len(line) \
            and (line[tail + 1].isalnum() or line[tail + 1] == "_"):
        tail += 1
        while tail < len(line) and (line[tail].isalnum() or line[tail] == "_"):
            tail += 1
    whole = line[head:tail]
    parts = whole.split(".")
    at = line[head:start].count(".")
    return parts, at, start, end


class Resolver:
    def __init__(self, project, doc):
        self.p, self.doc = project, doc
        self._flat = self._host = None
        self._depth = 0

    def scope_names(self, line):
        """Everything visible at `line`: the enclosing declarations' children,
        innermost last so they shadow, then the file's own top level."""
        names = {}
        for s in self.doc.syms:
            names[s.name] = (s, self.doc)
        for encl in self.doc.enclosing(line):
            for c in encl.children:
                names[c.name] = (c, self.doc)
            for port in encl.ports:
                names.setdefault(port, (Sym(port, VARIABLE, encl.line,
                                            encl.col, "port"), self.doc))
        return names

    def imported(self):
        names = {}
        for d in self.p.reachable(self.doc.path)[1:]:
            for s in d.syms:
                names.setdefault(s.name, (s, d))
        return names

    def anywhere(self):
        """Every name the file declares, at any depth.

        The last resort, and it exists because a template is SPLICED rather
        than called: `client.mereo`'s `receive` names `link`, which is a
        resource the PROGRAM owns, declared 109 lines further down. No scope
        rule reaches it, and an editor that answers "no definition" there is
        wrong about a name the reader can see."""
        if self._flat is None:
            self._flat = {}
            for top in self.doc.syms:
                for sym in top.walk():
                    self._flat.setdefault(sym.name, (sym, self.doc))
        return self._flat

    def hosted(self):
        """What a PROGRAM that includes this file can see.

        `linux.mereo` writes `text.find` and includes nothing -- `text` lives
        in `core.mereo`, and the two only meet in a program that includes
        both. Resolving through a host is what makes a library file navigable
        on its own terms."""
        if self._host is None:
            self._host = {}
            host = self.p.hosts().get(self.doc.path)
            if host and host != self.doc.path:
                for d in self.p.reachable(host):
                    if d.path == self.doc.path:
                        continue
                    for s in d.syms:
                        self._host.setdefault(s.name, (s, d))
        return self._host

    def candidates(self, name, line):
        """Everything `name` could mean, nearest first."""
        out = []
        for where in (self.scope_names(line), self.imported(), self.anywhere(),
                      self.hosted(), entry_views()):
            hit = where.get(name)
            if hit is not None and not any(hit[0] is o[0] for o in out):
                out.append(hit)
        return out

    def lookup(self, name, line):
        got = self.candidates(name, line)
        return got[0] if got else None

    def members(self, sym, doc, name):
        """EVERY thing `sym.name` could mean, nearest first.

        More than one is not hypothetical. `linux` holds a `socket` PRIMITIVE
        and a `socket` RESOURCE -- the compiler keeps primitives and
        definitions in separate tables, so the language allows it, and it is
        the only such pair in the project. An index has no two tables, so the
        one that was meant is the one that HAS the member being asked for."""
        out = [(c, doc) for c in sym.children + sym.attached if c.name == name]
        # an INSTANCE reaches its type's methods: `source.read` is `file`'s
        # `read`, and the instance is only where the state lives.
        if sym.type_of and self._depth < 8:
            self._depth += 1
            try:
                parts = sym.type_of.split(".")
                targets = []
                if sym.container is not None and len(parts) == 1:
                    targets += self.members(sym.container, doc, parts[0])
                targets += self.resolutions(parts)
                for target, where in targets:
                    if target is not sym:
                        out += self.members(target, where, name)
            finally:
                self._depth -= 1
        return out

    def member(self, sym, doc, name):
        got = self.members(sym, doc, name)
        return got[0] if got else None

    def resolutions(self, parts, line=0):
        """Every thing a dotted chain could name, nearest first.

        A candidate that cannot carry the whole chain contributes nothing: a
        slot called `text` cannot answer `.copy`, so the GROUP called `text` is
        what was meant."""
        if not parts:
            return []
        out = []
        for sym, where in self.candidates(parts[0], line):
            here = [(sym, where)]
            for part in parts[1:]:
                step = []
                for one, doc in here:
                    step += self.members(one, doc, part)
                here = step
                if not here:
                    break
            out += here
        return out

    def qualified(self, parts, line=0):
        """A dotted chain -> the thing it names, seen from `line`, or None."""
        got = self.resolutions(parts, line)
        return got[0] if got else None

    def at(self, line_no, ch):
        """What the cursor is on -> (Sym, Doc, range) or None."""
        line = self.doc.lines[line_no] if line_no < len(self.doc.lines) else ""
        got = chain_at(line, ch)
        if not got:
            return None
        parts, at, start, end = got
        found = self.resolutions(parts[:at + 1], line_no)
        if not found:
            return None
        # `link is linux.socket (...)` names the RESOURCE; a bare
        # `linux.socket (...)` step names the PRIMITIVE of that name. Both are
        # legal, and only the shape of the line says which -- so where the line
        # is a construction, prefer what can BE constructed. Keying on "has
        # members" would not do it: a primitive's asm operands are members too.
        chain = ".".join(parts[:at + 1])
        if re.match(r"^\s*\w+ is (?:already |adopted |new )?"
                    + re.escape(chain) + r"\b", line):
            found.sort(key=lambda hit: hit[0].kind not in (CLASS, STRUCT,
                                                           NAMESPACE))
        return found[0][0], found[0][1], (start, end)


# ---------------------------------------------------------------- the wire
#
# LSP over stdio: `Content-Length: N`, a blank line, then N bytes of JSON.
# Nothing else may reach stdout -- a stray print corrupts the stream and the
# client goes quiet with no error, so every message this server has to say
# goes to stderr, which Kate shows in the LSP output tab.

def log(*a):
    print("mereolsp:", *a, file=sys.stderr, flush=True)


def read_message(stream):
    headers = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        line = line.decode("ascii", "replace").strip()
        if not line:
            break
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    length = int(headers.get("content-length", 0))
    if length <= 0:
        return None
    return json.loads(stream.read(length).decode("utf-8"))


def uri_to_path(uri):
    parsed = urllib.parse.urlparse(uri)
    return os.path.realpath(urllib.parse.unquote(parsed.path))


def path_to_uri(path):
    return "file://" + urllib.parse.quote(os.path.realpath(path))


def rng(l0, c0, l1, c1):
    return {"start": {"line": l0, "character": c0},
            "end": {"line": l1, "character": c1}}


def qualified_name(sym):
    """`read` inside `file` inside `linux` -> `linux.file.read`, which is how
    the compiler keys it."""
    parts, cur = [], sym
    while cur is not None:
        parts.append(cur.name)
        cur = cur.container
    return ".".join(reversed(parts))


def sym_range(sym, doc):
    last = doc.lines[sym.end_line] if sym.end_line < len(doc.lines) else ""
    return rng(sym.line, sym.col, sym.end_line, len(last))


def name_range(sym):
    return rng(sym.line, sym.col, sym.line, sym.col + len(sym.name))


KIND_WORD = {NAMESPACE: "namespace", CLASS: "resource", METHOD: "method",
             FIELD: "field", CONSTRUCTOR: "acquire", FUNCTION: "template",
             VARIABLE: "slot", CONSTANT: "constant", KEY: "scope",
             STRUCT: "view", PROPERTY: "property", ARRAY: "buffer"}


# --------------------------------------------------------------- the server

class Server:
    def __init__(self):
        self.project = Project()
        self.out = sys.stdout.buffer
        self.lock = threading.Lock()
        self.running = True
        self.published = {}                # path -> the uris it last touched
        self.ports = {}                    # callable -> {port: "in"|"out"}
        self.pending = {}
        self.wake = threading.Event()
        self.stamp = 0.0
        threading.Thread(target=self._diagnose_loop, daemon=True).start()

    # ------------------------------------------------------------ transport
    def send(self, obj):
        body = json.dumps(obj).encode("utf-8")
        with self.lock:
            self.out.write(b"Content-Length: %d\r\n\r\n" % len(body))
            self.out.write(body)
            self.out.flush()

    def reply(self, req_id, result):
        self.send({"jsonrpc": "2.0", "id": req_id, "result": result})

    def notify(self, method, params):
        self.send({"jsonrpc": "2.0", "method": method, "params": params})

    def serve(self):
        stream = sys.stdin.buffer
        while self.running:
            try:
                msg = read_message(stream)
            except Exception as e:
                log("bad message:", e)
                continue
            if msg is None:
                break
            try:
                self.dispatch(msg)
            except Exception as e:
                import traceback
                log("handler failed:", traceback.format_exc())
                if "id" in msg:
                    self.send({"jsonrpc": "2.0", "id": msg["id"],
                               "error": {"code": -32603, "message": str(e)}})

    def dispatch(self, msg):
        method = msg.get("method")
        params = msg.get("params") or {}
        handler = getattr(self, "on_" + method.replace("/", "_")
                          .replace("$", "dollar"), None)
        if handler is None:
            if "id" in msg:                # a request MUST be answered
                self.reply(msg["id"], None)
            return
        result = handler(params)
        if "id" in msg:
            self.reply(msg["id"], result)

    # ------------------------------------------------------------ lifecycle
    def on_initialize(self, params):
        root = params.get("rootUri") or params.get("rootPath")
        folders = params.get("workspaceFolders") or []
        if not root and folders:
            root = folders[0].get("uri")
        if root:
            self.project.root = (uri_to_path(root) if root.startswith("file:")
                                 else root)
        log("root:", self.project.root)
        return {
            "capabilities": {
                "textDocumentSync": {"openClose": True, "change": 1,
                                     "save": {"includeText": False}},
                "documentSymbolProvider": True,
                "definitionProvider": True,
                "hoverProvider": True,
                "referencesProvider": True,
                "completionProvider": {"triggerCharacters": ["."]},
                "signatureHelpProvider": {"triggerCharacters": ["(", ","]},
                # NOT declared, on purpose: documentHighlightProvider and
                # semanticTokensProvider both PAINT, and tools/mereo.xml owns
                # the colours. See the module docstring.
            },
            "serverInfo": {"name": "mereolsp", "version": "1"},
        }

    def on_initialized(self, params):
        return None

    def on_shutdown(self, params):
        return None

    def on_exit(self, params):
        self.running = False
        return None

    def on_dollar_setTrace(self, params):
        return None

    # ------------------------------------------------------------ documents
    def _sync(self, uri, text):
        path = uri_to_path(uri)
        self.project.buffers[path] = text
        self.schedule(path)
        return path

    def on_textDocument_didOpen(self, params):
        d = params["textDocument"]
        self._sync(d["uri"], d.get("text", ""))
        return None

    def on_textDocument_didChange(self, params):
        changes = params.get("contentChanges") or []
        if changes:                        # full sync: the last one is the file
            self._sync(params["textDocument"]["uri"], changes[-1]["text"])
        return None

    def on_textDocument_didSave(self, params):
        self.schedule(uri_to_path(params["textDocument"]["uri"]))
        return None

    def on_textDocument_didClose(self, params):
        path = uri_to_path(params["textDocument"]["uri"])
        self.project.buffers.pop(path, None)
        self.clear(path)
        return None

    def _doc(self, params):
        return self.project.doc(uri_to_path(params["textDocument"]["uri"]))

    def _pos(self, params):
        p = params["position"]
        return p["line"], p["character"]

    def directions(self, sym):
        """{port: "in" | "out"} for a template or method, from the compiler.

        Empty until the first successful compile of something that reaches it,
        and the last good table is kept -- a file mid-edit should not make the
        editor forget which port an answer lands in."""
        if not sym.ports:
            return {}
        row = self.ports.get(qualified_name(sym))
        if row is None and sym.container is None:
            # a free-standing template is its own definition: `dump.dump`
            row = self.ports.get(f"{sym.name}.{sym.name}")
        return row or {}

    def signature(self, sym):
        """`text.find (data, length, byte) -> offset`, or None if unknown."""
        dirs = self.directions(sym)
        if not dirs:
            return None
        ins = [p for p in sym.ports if dirs.get(p) != "out"]
        outs = [p for p in sym.ports if dirs.get(p) == "out"]
        return "(" + ", ".join(ins) + ")" + (" -> " + ", ".join(outs)
                                             if outs else "")

    # -------------------------------------------------------------- symbols
    def on_textDocument_documentSymbol(self, params):
        doc = self._doc(params)
        if doc is None:
            return []

        def out(sym):
            return {"name": sym.name,
                    "detail": self.signature(sym) or sym.detail,
                    "kind": sym.kind or NAMESPACE,
                    "range": sym_range(sym, doc),
                    "selectionRange": name_range(sym),
                    "children": [out(c) for c in sym.children]}
        return [out(s) for s in doc.syms]

    # ----------------------------------------------------------- definition
    def on_textDocument_definition(self, params):
        doc = self._doc(params)
        if doc is None:
            return None
        line, ch = self._pos(params)
        # an `include` line points at a FILE, and jumping to it is the one
        # navigation a reader wants there.
        text = doc.lines[line] if line < len(doc.lines) else ""
        m = _INCLUDE.match(text.strip())
        if m:
            target = os.path.realpath(
                os.path.join(os.path.dirname(doc.path), m.group(1)))
            if os.path.exists(target):
                return {"uri": path_to_uri(target), "range": rng(0, 0, 0, 0)}
            return None
        hit = Resolver(self.project, doc).at(line, ch)
        if hit is None:
            return None
        sym, where, _ = hit
        return {"uri": path_to_uri(where.path), "range": name_range(sym)}

    # ---------------------------------------------------------------- hover
    def on_textDocument_hover(self, params):
        doc = self._doc(params)
        if doc is None:
            return None
        line, ch = self._pos(params)
        hit = Resolver(self.project, doc).at(line, ch)
        if hit is None:
            return None
        sym, where, (start, end) = hit
        decl = (where.lines[sym.line].strip()
                if sym.line < len(where.lines) else sym.name)
        body = ["```mereo", decl, "```"]
        kind = KIND_WORD.get(sym.kind, "name")
        if sym.ports:
            dirs = self.directions(sym)
            if dirs:
                ins = [p for p in sym.ports if dirs.get(p) != "out"]
                outs = [p for p in sym.ports if dirs.get(p) == "out"]
                if ins:
                    body.append("**in** — " + ", ".join(f"`{p}`" for p in ins))
                body.append("**out** — " + (", ".join(f"`{p}`" for p in outs)
                                            if outs else "*nothing*"))
            else:
                body.append("**ports** — "
                            + ", ".join(f"`{p}`" for p in sym.ports))
        if sym.type_of:
            body.append(f"a `{sym.type_of}`")
        body.append(f"*{kind}* in `{os.path.basename(where.path)}`")
        return {"contents": {"kind": "markdown", "value": "\n\n".join(body)},
                "range": rng(line, start, line, end)}

    # ----------------------------------------------------------- references
    def on_textDocument_references(self, params):
        doc = self._doc(params)
        if doc is None:
            return []
        line, ch = self._pos(params)
        got = chain_at(doc.lines[line] if line < len(doc.lines) else "", ch)
        if not got:
            return []
        parts, at, _, _ = got
        name = parts[at]
        word = re.compile(rf"\b{re.escape(name)}\b")
        out = []
        for d in self.project.reachable(doc.path):
            for n, text in enumerate(d.lines):
                code = _uncomment(text)
                for m in word.finditer(code):
                    out.append({"uri": path_to_uri(d.path),
                                "range": rng(n, m.start(), n, m.end())})
        return out

    # ----------------------------------------------------------- completion
    def on_textDocument_completion(self, params):
        doc = self._doc(params)
        if doc is None:
            return {"isIncomplete": False, "items": []}
        line_no, ch = self._pos(params)
        line = doc.lines[line_no] if line_no < len(doc.lines) else ""
        before = line[:ch]
        res = Resolver(self.project, doc)
        items = []

        # 1. after a dot: the members of whatever is to its left.
        m = re.search(r"((?:\w+\.)*\w+)\.\w*$", before)
        if m:
            hit = res.qualified(m.group(1).split("."), line_no)
            if hit:
                sym, where = hit
                target = sym
                if sym.type_of:
                    t = res.qualified(sym.type_of.split("."), line_no)
                    if t:
                        target, where = t
                for c in target.children:
                    items.append(self._item(c, where))
            return {"isIncomplete": False, "items": items}

        # 2. inside an argument list: the callee's PORTS, minus the ones this
        #    call has already bound. This is the completion the language wants
        #    most -- every argument is `port is value`, and the port names
        #    belong to the callee.
        call = self._open_call(doc, line_no, ch)
        if call:
            name, bound, _ = call
            hit = res.qualified(name.split("."), line_no)
            if hit and hit[0].ports:
                dirs = self.directions(hit[0])
                for rank, port in enumerate(hit[0].ports):
                    if port in bound:
                        continue
                    out = dirs.get(port) == "out"
                    item = {"label": port, "kind": 5,
                            # ports are wired BY NAME, so order carries no
                            # meaning -- but the DECLARED order is how the
                            # library reads, and a client sorts by sortText or
                            # it sorts alphabetically.
                            "sortText": f"{rank:03d}",
                            "detail": ("out-port of " if out else "port of ")
                                      + name,
                            "insertText": f"{port} is "}
                    if out:
                        item["documentation"] = ("the answer lands here -- it "
                                                 "must be wired to a scalar "
                                                 "slot")
                    items.append(item)
                return {"isIncomplete": False, "items": items}

        # 3. otherwise: what is in scope here, then the reserved words.
        for name, (sym, where) in res.scope_names(line_no).items():
            items.append(self._item(sym, where))
        for name, (sym, where) in res.imported().items():
            items.append(self._item(sym, where))
        for word in sorted(RESERVED):
            items.append({"label": word, "kind": 14, "detail": "reserved"})
        return {"isIncomplete": False, "items": items}

    def on_textDocument_signatureHelp(self, params):
        """What the call being written takes, and where its answer lands.

        The active parameter is found by NAME, not by position: mereo wires
        every argument by name and order carries no meaning, so highlighting
        the third parameter because the cursor is after the second comma would
        be confidently wrong."""
        doc = self._doc(params)
        if doc is None:
            return None
        line_no, ch = self._pos(params)
        call = self._open_call(doc, line_no, ch)
        if not call:
            return None
        name, _, tail = call
        hit = Resolver(self.project, doc).qualified(name.split("."), line_no)
        if not hit or not hit[0].ports:
            return None
        sym = hit[0]
        dirs = self.directions(sym)
        label = f"{name} (" + ", ".join(sym.ports) + ")"
        active = None
        typing = re.search(r"(\w+)(?:\s+is\b[^,]*)?\s*$", tail)
        if typing and typing.group(1) in sym.ports:
            active = sym.ports.index(typing.group(1))
        outs = [p for p in sym.ports if dirs.get(p) == "out"]
        info = {
            "label": label,
            "parameters": [
                {"label": p,
                 "documentation": ("out-port: the answer lands here"
                                   if dirs.get(p) == "out" else "in")}
                for p in sym.ports],
        }
        if dirs:
            info["documentation"] = ("answers in " + ", ".join(outs) if outs
                                     else "answers nothing")
        if active is not None:
            info["activeParameter"] = active
        result = {"signatures": [info], "activeSignature": 0}
        if active is not None:
            result["activeParameter"] = active
        return result

    def _item(self, sym, where):
        return {"label": sym.name,
                "kind": {NAMESPACE: 9, CLASS: 7, METHOD: 2, FUNCTION: 3,
                         FIELD: 5, VARIABLE: 6, CONSTANT: 21, STRUCT: 22,
                         KEY: 6, CONSTRUCTOR: 4}.get(sym.kind, 6),
                "detail": sym.detail or KIND_WORD.get(sym.kind, ""),
                "documentation": os.path.basename(where.path)}

    def _open_call(self, doc, line_no, ch):
        """The call the cursor is inside -> (name, ports already bound, tail).

        An argument list is the one place a mereo line continues, so the scan
        walks backwards across lines until the parens balance."""
        here = doc.lines[line_no][:ch] if line_no < len(doc.lines) else ""
        text = "\n".join(doc.lines[max(0, line_no - 40):line_no] + [here])
        depth, i = 0, len(text) - 1
        while i >= 0:
            c = text[i]
            if c == ")":
                depth += 1
            elif c == "(":
                if depth == 0:
                    break
                depth -= 1
            i -= 1
        if i < 0:
            return None
        head = re.search(r"((?:\w+\.)*\w+)\s*$", text[:i])
        if not head:
            return None
        bound = set(re.findall(r"(\w+)\s+is\b", text[i:]))
        return head.group(1), bound, text[i + 1:]

    # ---------------------------------------------------------- diagnostics
    def schedule(self, path):
        self.pending[path] = time.monotonic()
        self.stamp = time.monotonic()
        self.wake.set()

    def clear(self, path):
        for uri in self.published.pop(path, ()):  # nothing left to complain of
            self.notify("textDocument/publishDiagnostics",
                        {"uri": uri, "diagnostics": []})

    def _diagnose_loop(self):
        DEBOUNCE = 0.3
        while True:
            self.wake.wait()
            while time.monotonic() - self.stamp < DEBOUNCE:
                time.sleep(0.05)
            self.wake.clear()
            paths, self.pending = list(self.pending), {}
            for path in paths:
                try:
                    self.diagnose(path)
                except Exception:
                    import traceback
                    log("diagnose failed:", traceback.format_exc())

    def diagnose(self, path):
        doc = self.project.doc(path)
        if doc is None:
            return
        # A file with no `program` is a library: compile it through one that
        # uses it, so its declarations are checked for real.
        target = path
        if "program" not in doc.top():
            target = self.project.hosts().get(path, path)
        job = {"path": target,
               "overlay": dict(self.project.buffers)}
        try:
            done = subprocess.run(
                [sys.executable, os.path.abspath(__file__), "--compile"],
                input=json.dumps(job), capture_output=True, text=True,
                timeout=30)
        except subprocess.TimeoutExpired:
            log("mereoc timed out on", target)
            return
        if done.returncode != 0:
            log("worker failed:", done.stderr.strip()[:400])
            return
        try:
            answer = json.loads(done.stdout or "{}")
        except json.JSONDecodeError:
            log("worker said:", done.stdout[:200])
            return
        if answer.get("ports"):
            # keep the last good one: a file mid-edit must not make the editor
            # forget which port an answer lands in
            self.ports = answer["ports"]
        error = answer.get("error")
        touched = set()
        if error and _LIBRARY_OK not in error:
            base, line, message = parse_error(error)
            where = path
            if base:                       # the error names a file: find it
                for d in self.project.reachable(target):
                    if os.path.basename(d.path) == base:
                        where = d.path
                        break
            uri = path_to_uri(where)
            hit = self.project.doc(where)
            n = max(0, (line or 1) - 1)
            text = hit.lines[n] if hit and n < len(hit.lines) else ""
            touched.add(uri)
            self.notify("textDocument/publishDiagnostics", {
                "uri": uri,
                "diagnostics": [{
                    "range": rng(n, len(text) - len(text.lstrip()),
                                 n, max(1, len(text))),
                    "severity": 1,
                    "source": "mereoc",
                    "message": message,
                }]})
        # clear whatever this file last complained about and no longer does
        for uri in self.published.get(path, set()) - touched:
            self.notify("textDocument/publishDiagnostics",
                        {"uri": uri, "diagnostics": []})
        if path_to_uri(path) not in touched:
            self.notify("textDocument/publishDiagnostics",
                        {"uri": path_to_uri(path), "diagnostics": []})
        self.published[path] = touched


def main(argv):
    if argv and argv[0] == "--compile":
        compile_worker()
        return 0
    Server().serve()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
