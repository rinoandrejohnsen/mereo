#!/usr/bin/env python3
"""Stitch docs/*.md into one self-contained page: python3 docs/build.py -> docs/mereo.html"""
import importlib.util
import re, pathlib

HERE = pathlib.Path(__file__).parent
# The article's sections, in reading order: the lead, then what the language is
# for, then its syntax and semantics, then the library, then how it is built and
# what that costs, and the reference material last. One file per section.
ORDER = ["index",
         "design",
         "syntax",
         "control-flow",
         "memory",
         "templates",
         "resources",
         "errors",
         "citizen",
         "library",
         "implementation",
         "performance",
         "limitations",
         "comparison",
         "examples",
         "syntax-summary"]


def esc_code(s):                       # code: escape everything literally
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# The guide's code blocks are highlighted by the SAME tokenizer the editor
# agrees with, in the SAME colours: mereohl's light theme holds Kate's Breeze
# Light values, measured off the editor rather than transcribed. The `pre`
# behind them is white for the same reason.
_hl_spec = importlib.util.spec_from_file_location(
    "mereohl", HERE.parent / "tools" / "mereohl.py")
mereohl = importlib.util.module_from_spec(_hl_spec)
_hl_spec.loader.exec_module(mereohl)
LIBS = set()
for _lib in ("linux.mereo", "core.mereo"):
    _f = HERE.parent / _lib
    if _f.exists():
        LIBS |= mereohl.namespaces_of(_f.read_text(), _f.resolve())
# ...and a bare CALL line, which is how a one-line snippet usually reads:
# `text.find (data is block, ...)`. The space before `(` is what separates it
# from C and from an strace transcript, neither of which writes one -- so
# `write(1, ...)` and `rt_sigaction(SIGPIPE, ...)` stay plain, as they should.
# Without this, a snippet that was only a call went unhighlighted in the guide
# and untagged in the wiki.
IS_MEREO = re.compile(r'^\s*(include "|\w+ is |.* goes$|scope$|ensure |repeat |'
                      r"leave |end$|--|[\w.]+ \()")


# ...and the palette those spans use, straight off the same theme table.
TOKEN_CSS = "\n".join(
    f".t-{name}{{color:{colour}"
    + (";font-weight:600" if bold else "")
    + (";font-style:italic" if name in mereohl.ITALIC else "") + "}"
    for name, (colour, bold) in mereohl.THEMES["light"]["tok"].items())


def highlight(code):
    """A mereo snippet -> HTML spans. Anything that does not look like mereo
    (a transcript, a shell line, the generated C) is escaped and left alone."""
    if not any(IS_MEREO.match(l) for l in code.split("\n")):
        return esc_code(code)
    out = []
    for kind, tok in mereohl.tokens(code, LIBS):
        if kind == "space":
            out.append(esc_code(tok))
        else:
            out.append(f'<span class="t-{kind}">{esc_code(tok)}</span>')
    return "".join(out)


def esc_prose(s):                      # prose: escape, but keep &entity; intact
    s = re.sub(r"&(?![A-Za-z]+;|#\d+;)", "&amp;", s)
    return s.replace("<", "&lt;").replace(">", "&gt;")


def inline(s):
    s = esc_prose(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\[([^\]]+)\]\(([a-z0-9-]+)\.md\)", r'<a href="#\2">\1</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    return s


def render(lines):
    out, para, i, n = [], [], 0, len(lines)

    def flush():
        if para:                       # join wrapped lines BEFORE markup, so a
            out.append("<p>" + inline(" ".join(para)) + "</p>")  # **span** across
            para.clear()               # a line wrap still pairs up


    while i < n:
        line = lines[i].rstrip("\n")
        s = line.strip()
        if s.startswith("```"):
            flush(); i += 1; code = []
            while i < n and not lines[i].strip().startswith("```"):
                code.append(lines[i].rstrip("\n")); i += 1
            i += 1
            out.append("<pre><code>" + highlight("\n".join(code)) + "</code></pre>")
        elif s.startswith("|"):
            flush(); rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip()); i += 1
            cells = lambda r: [c.strip() for c in r.strip("|").split("|")]
            t = ["<table><thead><tr>"]
            t += [f"<th>{inline(c)}</th>" for c in cells(rows[0])]
            t.append("</tr></thead><tbody>")
            for r in rows[2:]:
                t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells(r)) + "</tr>")
            t.append("</tbody></table>")
            out.append("".join(t))
        elif re.match(r"^#{1,6}\s", s):
            flush(); m = re.match(r"^(#{1,6})\s+(.*)$", s)
            tag = "h" + str(min(len(m.group(1)) + 1, 6))
            out.append(f"<{tag}>{inline(m.group(2))}</{tag}>")
            i += 1
        elif s == "---":
            flush(); out.append("<hr>"); i += 1
        elif s.startswith("> "):
            # An aside: something worth knowing that is not the thread of the
            # section. GitHub renders `>` as a blockquote natively, so the wiki
            # gets it for free and this is only the HTML half.
            flush(); note = []
            while i < n and lines[i].strip().startswith(">"):
                note.append(lines[i].strip()[1:].strip()); i += 1
            paras = []
            for chunk in " \n".join(note).split(" \n \n"):
                paras.append("<p>" + inline(" ".join(chunk.split())) + "</p>")
            out.append("<blockquote>" + "".join(paras) + "</blockquote>")
        elif s.startswith("- "):
            flush(); items = []
            while i < n:
                l = lines[i].rstrip("\n"); st = l.strip()
                if st.startswith("- "):
                    items.append(st[2:]); i += 1
                elif st and l.startswith("  ") and items:
                    items[-1] += " " + st; i += 1
                else:
                    break
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
        elif s == "":
            flush(); i += 1
        else:
            para.append(s); i += 1
    flush()
    return "\n".join(out)


def title(md, keep_markup=False):
    for l in md.splitlines():
        m = re.match(r"^#\s+(.*)$", l.strip())
        if m:
            return (m.group(1) if keep_markup
                    else re.sub(r"`([^`]+)`", r"\1", m.group(1)))
    return "?"


CSS = """
*{box-sizing:border-box}
body{margin:0;font:16px/1.65 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1b1f24;background:#fff}
#sidebar{position:fixed;top:0;left:0;width:250px;height:100vh;overflow:auto;background:#0f1729;color:#cbd5e1;padding:26px 18px}
#sidebar h1{font-size:17px;color:#fff;margin:0 0 6px;letter-spacing:.02em}
#sidebar .sub{font-size:12px;color:#64748b;margin:0 0 18px}
#sidebar ul{list-style:none;padding:0;margin:0}
#sidebar li{margin:1px 0}
#sidebar a{color:#94a3b8;text-decoration:none;display:block;padding:5px 10px;border-radius:6px;font-size:13.5px}
#sidebar a:hover{background:#1e293b;color:#fff}
main{margin-left:250px;max-width:780px;padding:44px 52px 140px}
main>h1{font-size:32px;margin:0 0 8px}
main>.lead{color:#64748b;margin:0 0 32px}
section{border-top:1px solid #eef1f4;padding-top:8px;margin-top:36px}
section:first-of-type{border-top:none;margin-top:0}
h2{font-size:26px;margin:18px 0 4px;padding-bottom:6px;border-bottom:2px solid #e2e8f0}
h3{font-size:19px;margin:26px 0 6px}
h4{font-size:15px;margin:18px 0 4px;color:#334155;text-transform:uppercase;letter-spacing:.04em}
p{margin:10px 0}
code{background:#f1f5f9;padding:2px 6px;border-radius:4px;font-size:.88em;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
pre{background:#ffffff;color:#1f1c1b;padding:16px 18px;border-radius:8px;overflow:auto;margin:12px 0;border:1px solid #e2ded6}
pre code{background:none;padding:0;color:inherit;font-size:13px;line-height:1.55}
table{border-collapse:collapse;width:100%;margin:14px 0;font-size:.94em}
th,td{border:1px solid #e2e8f0;padding:8px 12px;text-align:left;vertical-align:top}
th{background:#f8fafc;font-weight:600}
a{color:#2563eb;text-decoration:none}
a:hover{text-decoration:underline}
hr{border:none;border-top:1px solid #e2e8f0;margin:26px 0}
ul{padding-left:22px;margin:10px 0}
li{margin:4px 0}
strong{color:#0f172a}
blockquote{margin:18px 0;padding:12px 18px;background:#f8fafc;border-left:3px solid #94a3b8;border-radius:0 6px 6px 0}
blockquote p{margin:6px 0;font-size:.95em;color:#334155}
blockquote p:first-child{margin-top:0}
blockquote p:last-child{margin-bottom:0}
/* The lead's first table is the infobox: an encyclopedia article's summary
   panel, floated beside the opening paragraphs the way one is. Keyed on
   position rather than a class because the pages are plain markdown. */
#index table:first-of-type{float:right;width:310px;margin:0 0 16px 24px;font-size:.86em;
  background:#f8fafc;border:1px solid #cbd5e1;border-radius:6px;overflow:hidden}
#index table:first-of-type thead{display:none}
#index table:first-of-type td{border:none;border-bottom:1px solid #e2e8f0;padding:6px 10px}
#index table:first-of-type tr:last-child td{border-bottom:none}
#index table:first-of-type td:first-child{width:44%;color:#475569}
#index h2{clear:both}
@media (max-width:900px){#index table:first-of-type{float:none;width:100%;margin:12px 0}}
@media(max-width:820px){#sidebar{position:static;width:auto;height:auto}main{margin-left:0;padding:24px}}
"""

# ---------------------------------------------------------------- doc checks
# Rot in this guide has a shape: a rule changes, the body is rewritten, and a
# trailing Notes/Try-it bullet keeps asserting the old thing. All three
# contradictions found in the first full proofread lived in such a tail. So when
# a rule changes, retire its old phrasing HERE and the build refuses to ship it.
#
#   (pattern, what is true now, a regex for a legitimate mention or None)
RETIRED = [
    (r"one call each",
     "a resource owns one THING; `acquire`/`release` may take several steps", None),
    (r"condition is one comparison",
     "conditions combine with `&&` / `||`", None),
    (r"remember to update `count`",
     "`size of` follows the buffer, so nothing else to edit", None),
    (r"\b(?:initialize|finalize)\b",
     "renamed to `acquire` / `release`", r"were once"),
    (r"\b(?:FIELD|count|data|pointer) (?:from|of)\b",
     "projection reads `INSTANCE.FIELD` -- neither `from` nor `of`", None),
    # ---- the syntax change: the old spellings, retired. Each is kept to an
    # inline-code span or an indented snippet line, because `use`, `where`,
    # `of` and `system` are all ordinary English in prose.
    (r"`[^`\n]*\bsize of\b[^`\n]*`",
     "a size is `X.size` -- the compile-time member, not a phrase", None),
    (r"`[^`\n]*\buse \"[^`\n]*`",
     "a library is pulled in with `include \"...\"`", None),
    (r"`[^`\n]*\b\w+ \w* ?where\b[^`\n]*`",
     "a call's arguments ride in its own parentheses: `RECEIVER.METHOD (a is b)`",
     None),
    # `#` FOLLOWED BY SPACE OR END, which is what a comment marker looks like.
    # `#define` and `#DE` are C and x86 and are quoted here on purpose.
    (r"`[^`\n]*(?<![\w-])#(?:\s[^`\n]*)?`",
     "a comment starts with `--`, as Lua's does", None),
    (r"`\w+ system\b[^`\n]*`",
     "a syscall is `linux.NAME (...)`", None),
    (r"`[^`\n]*\blinux:[^`\n]*`",
     "a namespace is reached with a dot -- `linux.write`, not `linux:write`", None),
    (r"`(?:exit|read|write|open|close|statx|getdents64|socket|ioctl|mmap) \(",
     "a name declared in `namespace linux` is written `linux.NAME`", None),
    (r"`(?:is|as) (?:already |adopted )?(?:file|directory|mapping|clock|files|"
     r"channel|identity|process|sockaddr_in|file_status|file_mode|timespec|"
     r"poll_entry)\b",
     "a type declared in `namespace linux` is written `linux.TYPE`", None),
    (r"roads? (?:live|go) (?:past|after) `?exit`? in a template",
     "a template has no `exit`; its roads follow the crossroad", None),
    (r"\bstructs?\b",
     "the byte-grain kind is a LAYOUT view (mereo has no `struct`)", None),
    (r"[Vv]alue view",
     "the view that needs no declaration is a FUNDAMENTAL view", None),
    (r"[Ww]orking view",
     "the third kind of view is an OBJECT view", None),
    (r"\bclass(?:es)?\b",
     "mereo has no classes -- it is a `layout`, a `resource`, or a "
     "`template` group", None),
    (r"(?:\d+|N) bytes (?:signed|unsigned|big|little)",
     "a reading follows `as` -- `N bytes as signed`, the same word that reads a "
     "value or lays a view", None),
    (r"(?:already|adopted) (?:\w+|NAME|CLASS|VIEWCLASS) over ",
     "a view is laid with `BACKING as [adopted] VIEWCLASS` -- `already` now only "
     "borrows a resource, and a releasing lens is `as adopted CLASS`", None),
    # a CONDITION in the word form, in an inline-code span or an indented
    # snippet line. Kept narrow on purpose: `when` and `and` are ordinary
    # English, so the pattern has to see the mereo shape around them.
    (r"`[^`\n]*\b(?:when|ensure) +\w+ +(?:is|and|or) +[\w\"][^`\n]*`",
     "a CONDITION is written in operators (`==`, `&&`, `||`), never in the prose "
     "words -- those are what made a condition indistinguishable from an "
     "assignment, which `GUARD goes` cannot afford", None),
    (r"^\s{2,}(?:ensure|(?:leave|repeat) \w+ when|\w+ when) [^`\n]*\b(?:is|and|or)\b",
     "a CONDITION is written in operators, never in the prose words", None),
    (r"`is` (?:in a guard|for equals)",
     "`is` is not a condition operator; conditions use `==`", r"never|not a"),
]


def section_of(text, pos):
    """The `## ` heading a position falls under -- rot clusters in the tail."""
    heads = [(m.start(), m.group(1))
             for m in re.finditer(r"^## +(.*)$", text[:pos], re.M)]
    return heads[-1][1] if heads else "(intro)"


# Pages that QUOTE another language's vocabulary, where a retired mereo word is
# the subject rather than a slip. `comparison` has to be able to say `struct`.
QUOTES_ANOTHER_LANGUAGE = {"comparison"}
RETIRED_QUOTABLE = {r"\bstructs?\b", r"\bclass(?:es)?\b"}

def check_retired(pages):
    out = []
    for name, text in sorted(pages.items()):
        for pat, truth, allow in RETIRED:
            if name in QUOTES_ANOTHER_LANGUAGE and pat in RETIRED_QUOTABLE:
                continue        # it is naming C's construct, not mereo's
            for m in re.finditer(pat, text):
                line_no = text[:m.start()].count("\n") + 1
                line = text.splitlines()[line_no - 1]
                if allow and re.search(allow, line):
                    continue
                out.append(f"{name}.md:{line_no} [{section_of(text, m.start())}] "
                           f"says {m.group(0)!r} -- {truth}")
    return out


def check_links(pages):
    out = []
    for name, text in sorted(pages.items()):
        for m in re.finditer(r"\[([^\]]+)\]\(([a-z0-9-]+)\.md\)", text):
            if m.group(2) not in pages:
                out.append(f"{name}.md links to missing page {m.group(2)}.md")
        # `inline()` renders ONE link form -- `[label](slug.md)`. Any other lands
        # in the output as its own literal markdown, which nothing was checking:
        # a `[label](#anchor)` written here shipped as the characters
        # "[label](#anchor)" and neither the renderer nor this checker minded.
        for m in re.finditer(r"\[[^\]]+\]\([^)]*\)", text):
            if not re.fullmatch(r"\[[^\]]+\]\([a-z0-9-]+\.md\)", m.group(0)):
                line_no = text[:m.start()].count("\n") + 1
                out.append(f"{name}.md:{line_no} {m.group(0)!r} is not a link "
                           "the renderer understands -- it takes "
                           "`[label](slug.md)` and nothing else, so this would "
                           "ship as literal markdown")
    for name in sorted(set(pages) - set(ORDER)):
        out.append(f"{name}.md exists but is not in ORDER (it would not be built)")
    for name in [n for n in ORDER if n not in pages]:
        out.append(f"ORDER lists {name}, which has no page")
    return out


def _uncomment(line):
    """Drop a trailing `-- ...`, but only where it is outside a string."""
    q = False
    for i, c in enumerate(line):
        if c == '"':
            q = not q
        elif c == "-" and line[i + 1:i + 2] == "-" and not q:
            return line[:i]
    return line


def check_examples(pages):
    """Every complete program in the guide must still transpile."""
    import subprocess
    root, out = HERE.parent, []
    for name, text in sorted(pages.items()):
        # Fences are paired with their tag, not just matched as "```\n ... ```".
        # A TAGGED block (```c) opens with "```c\n", which the old pattern could
        # not see -- so its CLOSING fence was read as an opener, every later
        # fence was off by one, and a run of prose got handed to the transpiler.
        # It only ever surfaced when that prose happened to contain "program is".
        # mereo blocks are untagged, so the tag is captured and tagged blocks
        # are skipped rather than mispaired.
        blocks = [m.group(2) for m in
                  re.finditer(r"^```(\w*)\n(.*?)^```", text, re.S | re.M)
                  if not m.group(1)]
        for k, block in enumerate(blocks, 1):
            # `...` marks a sketch rather than a program -- but only in CODE.
            # An ellipsis inside a COMMENT ("...or 256 to report on the link")
            # used to disable the check for the whole block, which is how a
            # broken example shipped in files.md.
            code = "\n".join(_uncomment(l) for l in block.split("\n"))
            # A complete program opens with `program is` OR `program (PORTS)
            # is`. Matching the bare literal missed every example that takes
            # arguments -- they were printed, never compiled, and a broken one
            # would have shipped. Found by planting a bad `ensure` in one and
            # watching the build succeed.
            if not re.search(r"^program\b.*\bis$", block, re.M) or "..." in code:
                continue
            tmp = root / f"_doccheck_{name}_{k}.mereo"
            tmp.write_text(block)
            try:
                r = subprocess.run(["python3", str(root / "mereoc.py"), tmp.name],
                                   capture_output=True, text=True, cwd=root)
                if r.returncode:
                    last = (r.stderr.strip().splitlines() or [""])[-1]
                    out.append(f"{name}.md example {k} does not transpile: {last}")
            finally:
                tmp.unlink(missing_ok=True)
    return out



# ------------------------------------------------------------------ the wiki
# GitHub's wiki is a SEPARATE repository (`<repo>.wiki.git`) whose pages are
# markdown files at its root, named for their titles: `Foo-bar.md` is the page
# "Foo bar" at /wiki/Foo-bar. So the guide is emitted a second time, reshaped:
#
#   index.md          -> Home.md            the landing page
#   loops.md          -> Loops.md           slug title-cased, hyphens kept
#   [x](loops.md)     -> [x](Loops)         a wiki link carries no extension
#   _Sidebar.md                              rendered beside every page
#   _Footer.md                               rendered under every page
#
# Same sources, same checks -- the retired-phrasing list, the link check and
# the "every complete example still transpiles" check all run before either
# output is written, so the wiki cannot ship something the guide would refuse.
SIDEBAR = [
    ("Overview",             ["design"]),
    ("Syntax and semantics", ["syntax", "control-flow", "memory", "templates",
                              "resources", "errors", "citizen"]),
    ("Standard library",     ["library"]),
    ("Implementation",       ["implementation", "performance", "limitations"]),
    ("Reference",            ["comparison", "examples", "syntax-summary"]),
]

# ORDER and SIDEBAR are two lists of the same pages, and a page added to one and
# not the other builds cleanly while going missing from the wiki's navigation --
# which is exactly what happened to files.md. They must agree.
_side = [s for _, slugs in SIDEBAR for s in slugs]
_missing = [s for s in ORDER if s != "index" and s not in _side]
_extra = [s for s in _side if s not in ORDER]
if _missing or _extra:
    raise SystemExit(
        "docs/build.py: ORDER and SIDEBAR disagree -- "
        + (f"SIDEBAR is missing {_missing} " if _missing else "")
        + (f"SIDEBAR has unknown {_extra}" if _extra else ""))


def wiki_name(slug):
    """docs slug -> wiki page name. `index` is the wiki's landing page; every
    other slug keeps its hyphens and gains a capital, so `layout-views` is the
    page "Layout views" at a URL that still reads as one."""
    return "Home" if slug == "index" else slug[:1].upper() + slug[1:]


def to_wiki(text):
    """Rewrite intra-guide links: a wiki link is a page NAME, never a file.

    ...and drop the leading `# Title`. GitHub renders a wiki page's NAME as its
    heading, so a title in the content is the same words twice, one above the
    other. The HTML build needs that line -- it is where the section title comes
    from -- so the removal belongs here, in the wiki rewrite, rather than in the
    source."""
    text = re.sub(r"\A#\s+[^\n]*\n\n?", "", text)

    # Tag mereo blocks as Ada so GitHub colours them. GitHub has no mereo
    # grammar and adding one means a pull request to linguist, so the choice is
    # the nearest language it already knows -- and that was measured, not
    # guessed. Against the guide's own examples: Ada covers 395 of 554 keyword
    # occurrences (`is`, `end`, `when`, `in`, `out`, `and`, `or`, `constant`,
    # `exit`), takes `--` as a comment, and takes "..." as a STRING. SQL scored
    # marginally higher on keywords alone (415, it also has `as`) and was
    # rejected for the strings: SQL reads "..." as a quoted identifier, which
    # would leave all 38 of them uncoloured.
    #
    # Only blocks that look like mereo are tagged -- the same test the HTML
    # highlighter uses -- so shell transcripts, generated C and output samples
    # stay plain.
    # Fences are paired WITH their tag. Matching a bare "```\n" instead reads a
    # tagged block's CLOSING fence as an opener, and every fence after it is off
    # by one -- prose gets tagged and real examples get missed. That trap has
    # now been walked into twice in this file; see check_examples for the first.
    def _tag(m):
        if m.group(1):                       # already tagged (c, sh) -- leave it
            return m.group(0)
        body = m.group(2)
        looks = any(IS_MEREO.match(l) for l in body.split("\n"))
        return ("```ada\n" if looks else "```\n") + body + "```"
    text = re.sub(r"^```(\w*)\n(.*?)^```", _tag, text, flags=re.S | re.M)

    return re.sub(r"\]\(([a-z0-9-]+)\.md\)",
                  lambda m: f"]({wiki_name(m.group(1))})", text)


def check_wiki_links(out):
    """Every intra-wiki link must name a page that exists. The guide's own link
    check reads `.md` targets; a wiki link has no extension, so the rewrite gets
    its own check rather than being trusted."""
    names = {p.stem for p in out.glob("*.md")}
    bad = [(p.name, m.group(1)) for p in sorted(out.glob("*.md"))
           for m in re.finditer(r"\]\(([A-Za-z][\w-]*)\)", p.read_text())
           if m.group(1) not in names]
    if bad:
        for f, t in bad:
            print(f"  wiki: {f} links to missing page {t}")
        raise SystemExit(1)


def write_wiki(pages, out):
    out.mkdir(exist_ok=True)
    written = {f"{wiki_name(s)}.md" for s in ORDER} | {"_Sidebar.md", "_Footer.md"}
    # Remove what this run did NOT generate. The whole directory is output --
    # the footer says as much -- so a page left behind after a rename is a stale
    # copy of retired content that still links into the old structure, and the
    # link check cannot see it because nothing points at it any more.
    for stale in sorted(out.glob("*.md")):
        if stale.name not in written:
            stale.unlink()
    for slug in ORDER:
        (out / f"{wiki_name(slug)}.md").write_text(to_wiki(pages[slug]))
    side = ["**[mereo](Home)**", ""]
    for heading, slugs in SIDEBAR:
        side.append(f"**{heading}**")
        side += [f"- [{title(pages[s], keep_markup=True)}]({wiki_name(s)})"
                 for s in slugs]
        side.append("")
    (out / "_Sidebar.md").write_text("\n".join(side))
    (out / "_Footer.md").write_text(
        "Generated from `docs/` by `python3 docs/build.py` — edit the guide "
        "there, not here.\n")
    check_wiki_links(out)
    return len(ORDER) + 2

toc, sections = [], []
for name in ORDER:
    md = (HERE / f"{name}.md").read_text()
    toc.append((name, title(md)))
    sections.append(f'<section id="{name}">\n{render(md.splitlines())}\n</section>')

toc_html = "\n".join(f'<li><a href="#{n}">{esc_prose(t)}</a></li>' for n, t in toc)

doc = (
    '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
    "<title>mereo &mdash; Documentation</title>\n<style>" + CSS + TOKEN_CSS
    + "</style>\n</head>\n<body>\n"
    '<nav id="sidebar">\n<h1>mereo</h1>\n<p class="sub">documentation</p>\n<ul>\n'
    + toc_html + "\n</ul>\n</nav>\n<main>\n"
    '<h1>mereo Documentation</h1>\n'
    '<p class="lead">A tiny systems language for Linux &mdash; freestanding, no C library, '
    "no runtime. Every example on this page was compiled and run.</p>\n"
    + "\n".join(sections) + "\n</main>\n</body>\n</html>\n"
)

_pages = {p.stem: p.read_text() for p in HERE.glob("*.md")}
# architecture.md is not published here, but it describes the same language and
# has drifted twice (`struct`, `class`, `already ... over`) precisely because
# nothing checked it. Hold it to the retired-syntax list too.
_arch = HERE.parent / "notes" / "architecture.md"
_extra = {"../architecture": _arch.read_text()} if _arch.exists() else {}
_problems = (check_retired(_pages) + check_retired(_extra)
             + check_links(_pages) + check_examples(_pages))
if _problems:
    print(f"docs: {len(_problems)} problem(s) -- NOT written")
    for _p in _problems:
        print("  " + _p)
    raise SystemExit(1)

out = HERE / "mereo.html"
out.write_text(doc)
_n = write_wiki({s: (HERE / f"{s}.md").read_text() for s in ORDER},
                HERE.parent / "wiki")
print(f"wrote {out} ({len(doc):,} bytes, {len(ORDER)} sections; "
      f"{len(_pages)} pages checked)")
print(f"wrote {HERE.parent / 'wiki'}/ ({_n} pages, ready to push to the "
      f"repo's .wiki.git)")
