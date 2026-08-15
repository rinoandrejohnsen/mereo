#!/usr/bin/env python3
"""Every byte of every .mereo file must land in a highlighter class, and none
may fall through to `other`.

A highlighter fails quietly: a construct it has no rule for is still printed,
just unstyled, and nobody notices until the page looks wrong. This is the cheap
mechanical version of noticing -- it caught `"/hello".size` (a member on a
string literal, which had no rule) the first time it ran.

It also asserts the token stream REBUILDS the source exactly, so a rule cannot
silently drop or duplicate text.

Usage: python3 tools/check_highlight.py [ROOT]     -> exit 0 if all classified
"""

import collections
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


KATE_DIR = pathlib.Path.home() / ".local/share/org.kde.syntax-highlighting/syntax"


def check_kate(hl, xml_path):
    """The Kate definition must know every word the compiler does.

    This is the drift that let `mereo.xml` sit at version 14 through three
    grammar changes: nothing tied it to the language. It is also why Kate
    rendered two files unalike -- its rules still keyed on `where`.

    Also reports when the INSTALLED copy differs, because Kate reads that one
    and caches it by `version`: editing the repo copy changes nothing until it
    is copied over AND the version is bumped."""
    import re
    import xml.etree.ElementTree as ET
    out = []
    if not xml_path.exists():
        return [f"{xml_path} is missing"]
    text = xml_path.read_text()
    # XML well-formedness, because a broken definition still INSTALLS -- Kate
    # just silently falls back to no highlighting. `--` inside a comment ends
    # the comment in XML, and prose about the language keeps producing one.
    try:
        ET.fromstring(text)
    except ET.ParseError as e:
        return [f"mereo.xml is not well-formed: {e}"]
    # a word is "known" if a LIST holds it or a RULE names it -- `is` is
    # positional (bold at a line end, plain mid-line) so it cannot be a list
    known = set(re.findall(r"<item>([^<]+)</item>", text))
    for rule in re.findall(r'String="([^"]*)"', text):
        known |= set(re.findall(r"[A-Za-z_]\w*", rule))
    want = (hl.STRUCTURE | hl.FLOW | set(hl.RESERVED) | set(hl.CLOBBERABLE)
            | set(hl.VIEW_WORDS))
    missing = sorted(want - known)
    if missing:
        out.append("mereo.xml does not know: " + ", ".join(missing))
    version = re.search(r'<language[^>]*version="(\d+)"', text)
    if not version:
        out.append("mereo.xml has no version attribute -- Kate caches by it")
    # Only a call into a shipped LIBRARY is drawn as one unit, the way Lua
    # draws `string.format` and not `t.go`. Kate cannot follow an `include`, so
    # its heads are written into the rule by hand; mereohl derives them. They
    # have to say the same thing, and a colour comparison cannot check it --
    # the function colour differs between themes.
    rule = re.search(r'String="\\b\(\?:([\w|]+)\)\(\?=', text)
    if rule is None:
        out.append("mereo.xml has no library-call rule -- a dotted call would "
                   "either always or never be drawn as one unit")
    else:
        listed = set(rule.group(1).split("|"))
        derived = set()
        for lib in ("linux.mereo", "core.mereo"):
            f = xml_path.parent.parent / lib
            if f.exists():
                derived |= hl.namespaces_of(f.read_text(), f.resolve())
        derived = {d for d in derived if d in listed or d in ("linux", "text", "json")}
        if listed - derived:
            out.append(f"mereo.xml lists library heads mereohl does not know: "
                       f"{sorted(listed - derived)}")
    installed = KATE_DIR / "mereo.xml"
    if installed.exists() and installed.read_text() != text:
        iv = re.search(r'version="(\d+)"', installed.read_text())
        out.append(f"the copy Kate reads ({installed}) differs -- reinstall it, "
                   f"and bump `version` past {iv.group(1) if iv else '?'} or Kate "
                   "will keep the cached rules")
    return out


# Lua bolds every keyword, and the definition follows it -- so what is bold is
# the reserved vocabulary plus the name a line declares.
BOLD = {"structure", "decl", "namespace_decl"}
ITALIC = {"comment", "inside"}


def check_bold(hl, root):
    """The editor and the tool must bold the SAME words.

    Bold is the one thing a reader cannot ignore, so the two engines drifting
    on it is worse than either being wrong alone. Kate is checked through
    ksyntaxhighlighter6, the same library Kate itself links -- skipped when it
    is not installed, which is most machines that are not this one.

    It also catches a trap the Python scanner does not have: a Kate rule
    anchored with `^` starts at column 0 and eats the indentation, so it beats
    a keyword rule that could only match further along the line. That is how
    `acquire (path) is` came out as a declaration rather than a lifecycle role.
    """
    import re
    import shutil
    import subprocess
    if not shutil.which("ksyntaxhighlighter6"):
        return []
    out = []
    for f in sorted(root.rglob("*.mereo")):
        if "attic" in f.parts:
            continue
        src = f.read_text()
        toks = list(hl.tokens(src, hl.namespaces_of(src, f.resolve())))
        r = subprocess.run(["ksyntaxhighlighter6", "-s", "Mereo", "-f", "ansi",
                            str(f)], capture_output=True, text=True)
        for label, classes, pat in (
                ("bolds", BOLD, r"\x1b\[38;2;[0-9]+;[0-9]+;[0-9]+;1m([^\x1b]*)"),
                ("italicises", ITALIC,
                 r"\x1b\[38;2;[0-9]+;[0-9]+;[0-9]+(?:;1)?;3m([^\x1b]*)")):
            # words, not whole tokens: Kate reports a styled RUN and a comment
            # is one token here, so the two only line up word by word
            mine = {w for k, t in toks if k in classes
                    for w in re.findall(r"\w+", t)}
            kate = set()
            for m in re.finditer(pat, r.stdout):
                kate.update(re.findall(r"\w+", m.group(1)))
            if mine != kate:
                out.append(f"{f}: mereohl {label} {sorted(mine - kate)[:5]}, "
                           f"Kate {label} {sorted(kate - mine)[:5]}")
    return out


def check_colours(hl, root):
    """mereohl's LIGHT theme must be the colour Kate actually paints.

    Bold and italic were already compared; this compares the hue, which is what
    makes docs/mereo.html look like the editor rather than merely resemble it.
    Kate is asked through ksyntaxhighlighter6 with the theme by name, and the
    answer is indexed by character offset -- aligning on token text does not
    work, because the two engines split runs differently.

    Skipped when ksyntaxhighlighter6 is absent, like the other Kate checks."""
    import re
    import shutil
    import subprocess
    import collections
    if not shutil.which("ksyntaxhighlighter6"):
        return []
    want = hl.THEMES["light"]["tok"]
    seen = collections.defaultdict(collections.Counter)
    for name in ("examples/ls.mereo", "examples/stat.mereo", "linux.mereo",
                 "core.mereo"):
        f = root / name
        if not f.exists():
            continue
        src = f.read_text()
        out = subprocess.run(["ksyntaxhighlighter6", "-s", "Mereo", "-t",
                              "Breeze Light", "-f", "ansi", str(f)],
                             capture_output=True, text=True).stdout
        out = out.replace("\x1b[K", "")
        styles, cur = [], None
        for m in re.finditer(r"\x1b\[([0-9;]*)m|([^\x1b]+)", out):
            if m.group(1) is not None:
                g = m.group(1).split(";")
                if g[0] == "38" and len(g) >= 5:
                    cur = "#%02x%02x%02x" % (int(g[2]), int(g[3]), int(g[4]))
                elif m.group(1) in ("0", ""):
                    cur = None
            else:
                styles.extend([cur] * len(m.group(2)))
        if len(styles) < len(src) - 2:
            continue
        off = 0
        for kind, tok in hl.tokens(src, hl.namespaces_of(src, f.resolve())):
            if kind != "space" and off < len(styles):
                seen[kind][styles[off]] += 1
            off += len(tok)
    out = []
    for kind, counts in sorted(seen.items()):
        kate = counts.most_common(1)[0][0]
        mine = want.get(kind, (None,))[0]
        if kate and mine and kate.lower() != mine.lower():
            out.append(f"`{kind}` is {mine} in mereohl's light theme and "
                       f"{kate} in Kate")
    return out


def main(argv):
    hl = load("mereohl")
    root = pathlib.Path(argv[0]) if argv else HERE.parent
    kinds, files, bad = collections.Counter(), 0, []
    for f in sorted(root.rglob("*.mereo")):
        if "attic" in f.parts:
            continue
        files += 1
        src = f.read_text()
        rebuilt = []
        for kind, tok in hl.tokens(src, hl.namespaces_of(src, f.resolve())):
            kinds[kind] += len(tok)
            rebuilt.append(tok)
            if kind == "other" and tok.strip():
                bad.append((f, tok))
        joined = "".join(rebuilt)
        if joined != src:
            print(f"  {f}: the token stream does not rebuild the source "
                  f"({len(joined)} chars vs {len(src)})")
            return 1
    if bad:
        for f, tok in bad[:10]:
            print(f"  {f}: {tok!r} has no highlighter rule")
        print(f"check_highlight: {len(bad)} unclassified character(s)")
        return 1
    if not files:
        print("check_highlight: no .mereo files found -- the gate is vacuous")
        return 1
    problems = (check_kate(hl, HERE / "mereo.xml") + check_bold(hl, root)
                + check_colours(hl, root))
    for p in problems:
        print(f"  {p}")
    if problems:
        return 1
    print(f"  highlighting: {files} files, {sum(kinds.values())} chars, "
          f"{len(kinds)} classes, none unstyled; mereo.xml agrees and is installed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
