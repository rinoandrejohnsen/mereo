#!/usr/bin/env python3
"""The language server must answer, and must not paint.

Two halves, and the second is the one that matters. The INDEX is checked
against every .mereo in the tree -- a symbol whose range escapes its parent, or
whose name is not at the column it claims, is a wrong "go to definition" that
nobody notices until they follow it. The SERVER is then driven over real stdio,
the way Kate drives it, because a language server that works when imported as a
module and hangs on the wire has not worked.

The capability check is a standing invariant rather than a test: Kate applies
LSP semantic tokens over the syntax highlighting, and mereo's colours come from
tools/mereo.xml. A server that declares `semanticTokensProvider` or
`documentHighlightProvider` starts repainting text the XML already owns, so
declaring either is a FAILURE here, not a feature.

Usage: python3 tools/check_lsp.py [ROOT]      -> exit 0 if the server holds up
"""

import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
# The floor is measured, not aspirational: 1463 of 1470 dotted names in the
# corpus resolve. The seven that do not are six in files that are REFUSED on
# purpose (`port_needs_instance`, `new_on_scalar`, `port_receiver`) and one
# port used as a receiver, which needs the call site to say what it holds.
RESOLVE_FLOOR = 99.0


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def files_of(root):
    return [f for f in sorted(root.rglob("*.mereo")) if "attic" not in f.parts]


def check_index(lsp, root):
    """Every symbol inside its parent, inside its file, and at its column."""
    out, files, total = [], 0, 0
    for f in files_of(root):
        files += 1
        text = f.read_text()
        lines = text.splitlines()
        try:
            syms, _ = lsp.index(text, str(f))
        except Exception as e:
            out.append(f"{f}: the indexer raised {type(e).__name__}: {e}")
            continue

        def check(sym, lo, hi):
            nonlocal total
            total += 1
            if not lo <= sym.line <= sym.end_line <= hi:
                out.append(f"{f}:{sym.line + 1}: `{sym.name}` spans "
                           f"{sym.line + 1}-{sym.end_line + 1}, outside "
                           f"{lo + 1}-{hi + 1}")
            elif sym.line < len(lines):
                at = lines[sym.line][sym.col:sym.col + len(sym.name)]
                if at != sym.name:
                    out.append(f"{f}:{sym.line + 1}: `{sym.name}` is recorded "
                               f"at column {sym.col}, which holds {at!r}")
            for c in sym.children:
                check(c, sym.line, sym.end_line)
        for s in syms:
            check(s, 0, max(0, len(lines) - 1))
    return out, files, total


_DOTTED = re.compile(r"\b((?:\w+\.)+\w+)\b")


def check_resolution(lsp, root):
    """A dotted name the resolver cannot follow is a definition it cannot
    offer, so the rate IS the feature. Measured over the whole corpus."""
    project = lsp.Project()
    project.root = str(root)
    hit = miss = 0
    misses = []
    for f in files_of(root):
        doc = project.doc(str(f))
        if doc is None:
            continue
        res = lsp.Resolver(project, doc)
        for n, line in enumerate(doc.lines):
            code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', lsp._uncomment(line))
            for m in _DOTTED.finditer(code):
                parts = m.group(1).split(".")
                if parts[-1] == "size" or parts[0].isdigit():
                    continue          # `.size` is a compile-time number
                if res.qualified(parts, n):
                    hit += 1
                else:
                    miss += 1
                    misses.append(f"{f.name}:{n + 1} {m.group(1)}")
    total = hit + miss
    rate = 100.0 * hit / total if total else 0.0
    out = []
    if rate < RESOLVE_FLOOR:
        out.append(f"only {rate:.1f}% of {total} dotted names resolve "
                   f"(floor {RESOLVE_FLOOR}%): " + ", ".join(misses[:8]))
    return out, hit, total, rate


class Client:
    """Just enough LSP to be an editor."""

    def __init__(self, root):
        self.proc = subprocess.Popen(
            [sys.executable, str(root / "mereolsp.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, cwd=str(root))
        self.next_id = 0
        self.replies, self.notes = {}, []
        self.lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        stream = self.proc.stdout
        while True:
            headers = {}
            while True:
                line = stream.readline()
                if not line:
                    return
                line = line.decode("ascii", "replace").strip()
                if not line:
                    break
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()
            size = int(headers.get("content-length", 0))
            msg = json.loads(stream.read(size).decode("utf-8"))
            with self.lock:
                if "id" in msg and "method" not in msg:
                    self.replies[msg["id"]] = msg
                else:
                    self.notes.append(msg)

    def _send(self, obj):
        body = json.dumps(obj).encode("utf-8")
        self.proc.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
        self.proc.stdin.flush()

    def request(self, method, params, timeout=60):
        self.next_id += 1
        mine = self.next_id
        self._send({"jsonrpc": "2.0", "id": mine, "method": method,
                    "params": params})
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.lock:
                if mine in self.replies:
                    return self.replies.pop(mine).get("result")
            time.sleep(0.01)
        raise TimeoutError(f"{method} went unanswered")

    def notify(self, method, params):
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def wait_publish(self, uri, timeout=60):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.lock:
                for msg in list(self.notes):
                    if (msg.get("method") == "textDocument/publishDiagnostics"
                            and msg["params"]["uri"] == uri):
                        self.notes.remove(msg)
                        return msg["params"]["diagnostics"]
            time.sleep(0.02)
        return None

    def close(self):
        try:
            self.request("shutdown", {}, timeout=5)
            self.notify("exit", {})
        except Exception:
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def uri_of(path):
    return "file://" + str(path)


# What the compiler derives, spot-checked at the source. A method with a
# procedure body (`text.find`), one that binds a primitive and inherits its
# direction (`linux.file.read`), one that answers TWICE (`json.text`), and one
# that answers nothing (`builder.add`).
KNOWN_PORTS = {
    "text.find": {"data": "in", "length": "in", "byte": "in", "offset": "out"},
    "linux.file.read": {"buffer": "in", "capacity": "in", "count": "out"},
    "linux.file.write": {"buffer": "in", "count": "in", "written": "out"},
    "json.text": {"key": "in", "keylen": "in", "start": "out", "vlen": "out"},
    "builder.add": {"source": "in", "length": "in"},
}


def check_ports(root):
    """The direction table, straight out of the compile worker."""
    job = {"path": str(root / "examples/upper.mereo"), "overlay": {}}
    done = subprocess.run(
        [sys.executable, str(root / "mereolsp.py"), "--compile"],
        input=json.dumps(job), capture_output=True, text=True, timeout=120)
    try:
        answer = json.loads(done.stdout or "{}")
    except json.JSONDecodeError:
        return [f"the compile worker did not answer with JSON: "
                f"{done.stdout[:120]!r}"]
    if answer.get("error"):
        return [f"examples/upper.mereo stopped compiling: {answer['error']}"]
    table = answer.get("ports") or {}
    if not table:
        return ["the compile worker brought back no port directions -- the "
                "hook on mereoc's `derive_port_needs` is not firing"]
    out = []
    for name, want in KNOWN_PORTS.items():
        got = table.get(name)
        if got is None:
            out.append(f"the port table has no `{name}`")
        elif got != want:
            out.append(f"`{name}` came back {got}, not {want}")
    return out


def check_server(root):
    """Drive it the way Kate does: over stdio, with a real handshake."""
    out = []
    client = Client(root)
    try:
        answer = client.request("initialize", {"rootUri": uri_of(root),
                                               "processId": os.getpid()})
        caps = answer["capabilities"]
        for painter in ("semanticTokensProvider", "documentHighlightProvider"):
            if painter in caps:
                out.append(f"the server declares {painter} -- tools/mereo.xml "
                           "owns the colours, and a declared painter overwrites "
                           "them (see mereolsp.py's docstring)")
        for wanted in ("definitionProvider", "hoverProvider",
                       "documentSymbolProvider", "completionProvider",
                       "referencesProvider", "signatureHelpProvider"):
            if wanted not in caps:
                out.append(f"the server does not declare {wanted}")
        client.notify("initialized", {})

        prog = root / "examples/upper.mereo"
        text = prog.read_text()
        lines = text.splitlines()
        client.notify("textDocument/didOpen", {"textDocument": {
            "uri": uri_of(prog), "languageId": "mereo", "version": 1,
            "text": text}})

        syms = client.request("textDocument/documentSymbol",
                              {"textDocument": {"uri": uri_of(prog)}})
        if not syms or syms[0]["name"] != "program":
            out.append(f"documentSymbol on {prog.name} gave {syms!r:.90}, "
                       "not a `program`")
        elif not syms[0]["children"]:
            out.append("the program has no children in the outline")

        def where(needle, word):
            for n, line in enumerate(lines):
                if needle in line:
                    return {"line": n, "character": line.index(word)}
            raise AssertionError(f"{needle!r} is not in {prog.name} any more")

        # a definition that stays inside the file proves nothing: these two
        # cross an `include`, one into each library.
        for needle, word, target in (("already linux.file", "file",
                                      "linux.mereo"),
                                     ("text.upper", "upper", "core.mereo"),
                                     ("input.read", "read", "linux.mereo")):
            spot = where(needle, word)
            got = client.request("textDocument/definition",
                                 {"textDocument": {"uri": uri_of(prog)},
                                  "position": spot})
            if not got:
                out.append(f"`{needle}` has no definition")
            elif os.path.basename(got["uri"]) != target:
                out.append(f"`{needle}` resolves to "
                           f"{os.path.basename(got['uri'])}, not {target}")

        spot = where("text.upper", "upper")
        hover = client.request("textDocument/hover",
                               {"textDocument": {"uri": uri_of(prog)},
                                "position": spot})
        value = (hover or {}).get("contents", {}).get("value", "")
        if "upper (data, length) goes" not in value:
            out.append(f"hover over `text.upper` said {value!r:.80}")

        # the completion this language wants: a callee's ports, by name
        for n, line in enumerate(lines):
            if "input.read (" in line:
                spot = {"line": n, "character": line.index("(") + 1}
                break
        got = client.request("textDocument/completion",
                             {"textDocument": {"uri": uri_of(prog)},
                              "position": spot})
        ports = sorted(i["label"] for i in got["items"])
        if ports != ["buffer", "capacity", "count"]:
            out.append(f"completing `input.read (` offered {ports}, not "
                       "file.read's three ports")

        # diagnostics, on a clean file and then on a broken buffer
        clean = client.wait_publish(uri_of(prog))
        if clean is None:
            out.append("no diagnostics were published for a clean file")
        elif clean:
            out.append(f"{prog.name} compiles, but the server reported "
                       f"{clean[0]['message']!r:.70}")
        # ---- which port is the OUT port -------------------------------
        # The compiler derives this and the server takes it from there. If
        # `derive_port_needs` is ever renamed the hook stops firing silently,
        # and every direction below goes quiet -- which is what this catches.
        for n, line in enumerate(lines):
            if "input.read (" in line:
                spot = {"line": n, "character": line.index("(") + 1}
                break
        got = client.request("textDocument/completion",
                             {"textDocument": {"uri": uri_of(prog)},
                              "position": spot})
        marked = {i["label"]: i["detail"] for i in got["items"]}
        if "out-port" not in marked.get("count", ""):
            out.append(f"`count` is file.read's out-port, and completion "
                       f"called it {marked.get('count')!r}")
        for inport in ("buffer", "capacity"):
            if "out-port" in marked.get(inport, ""):
                out.append(f"`{inport}` is an input, and completion called it "
                           "an out-port")
        order = [i["sortText"] for i in got["items"]]
        if order != sorted(order):
            out.append("port completion does not keep the declared order")

        hover = client.request("textDocument/hover",
                               {"textDocument": {"uri": uri_of(prog)},
                                "position": where("input.read", "read")})
        said = (hover or {}).get("contents", {}).get("value", "")
        if "**out** — `count`" not in said:
            out.append(f"hover over `input.read` did not name `count` as the "
                       f"out-port: {said!r:.90}")

        sig = client.request("textDocument/signatureHelp",
                             {"textDocument": {"uri": uri_of(prog)},
                              "position": spot})
        first = (sig or {}).get("signatures", [{}])[0]
        if first.get("documentation") != "answers in count":
            out.append("signatureHelp on `input.read (` said "
                       f"{first.get('documentation')!r}, not `answers in count`")

        broken = text.replace("count is 0", "count is 0\n  ghost is 1", 1)
        client.notify("textDocument/didChange", {
            "textDocument": {"uri": uri_of(prog), "version": 2},
            "contentChanges": [{"text": broken}]})
        found = client.wait_publish(uri_of(prog))
        if not found:
            out.append("an unread scalar produced no diagnostic")
        else:
            first = found[0]
            if "ghost" not in first["message"]:
                out.append(f"the diagnostic was {first['message']!r:.70}")
            if first["range"]["start"]["line"] != 21:
                out.append("the diagnostic landed on line "
                           f"{first['range']['start']['line'] + 1}, not 22")

        # ---- a primitive and a resource of the SAME name ----------------
        # `linux` holds both `socket is assembly "syscall"` and `socket is`,
        # the only such pair in the project. The compiler keeps them in
        # separate tables; an index has one, so which is meant comes from the
        # shape of the line and from which one has the member being asked for.
        srv = root / "examples/server.mereo"
        srv_lines = srv.read_text().splitlines()
        client.notify("textDocument/didOpen", {"textDocument": {
            "uri": uri_of(srv), "languageId": "mereo", "version": 1,
            "text": srv.read_text()}})
        lib_lines = (root / "linux.mereo").read_text().splitlines()

        def resolves(predicate, word):
            for n, line in enumerate(srv_lines):
                if predicate(line):
                    got = client.request(
                        "textDocument/definition",
                        {"textDocument": {"uri": uri_of(srv)},
                         "position": {"line": n, "character": line.index(word)}})
                    if not got:
                        return line.strip(), None
                    at = got["range"]["start"]["line"]
                    return line.strip(), lib_lines[at].strip()
            return None, None

        said, landed = resolves(
            lambda l: l.strip().startswith("server is linux.socket"), "socket")
        if landed != "socket is":
            out.append(f"`{said}` resolves to {landed!r}, not the socket "
                       "RESOURCE -- the primitive of the same name won")
        said, landed = resolves(
            lambda l: l.strip().startswith("client is adopted"), "socket")
        if landed != "socket is":
            out.append(f"`{said}` resolves to {landed!r}, not the socket "
                       "resource")
        said, landed = resolves(
            lambda l: "server.bind" in l and not l.strip().startswith("--"),
            "bind")
        if landed != "bind (address, length, result) goes":
            out.append(f"`{said}` resolves to {landed!r}, not the method")

        # a LIBRARY has no `program`, so it is compiled through one that uses
        # it -- the path that makes core.mereo diagnosable at all
        lib = root / "core.mereo"
        lib_text = lib.read_text()
        client.notify("textDocument/didOpen", {"textDocument": {
            "uri": uri_of(lib), "languageId": "mereo", "version": 1,
            "text": lib_text}})
        if client.wait_publish(uri_of(lib)) is None:
            out.append("core.mereo produced no diagnostics either way -- the "
                       "host-program path is not running")
        else:
            # a PARSE fault, so any host catches it. A fault only the
            # elaborator would see (an unread local, say) is found only by a
            # host that actually splices that template, and which host a
            # library gets is not something this gate should depend on.
            anchor = "  find (data, length, byte, offset) goes"
            hurt = lib_text.replace(anchor, anchor + "\n    n gose 1", 1)
            if hurt == lib_text:
                out.append("core.mereo no longer has the `find` header this "
                           "gate breaks on purpose -- pick another anchor")
            client.notify("textDocument/didChange", {
                "textDocument": {"uri": uri_of(lib), "version": 2},
                "contentChanges": [{"text": hurt}]})
            said = client.wait_publish(uri_of(lib))
            if not said:
                out.append("a broken core.mereo produced no diagnostic -- the "
                           "library is compiled through a host program, and "
                           "that path is not running")
            elif said[0]["range"]["start"]["line"] != lib_text.count(
                    "\n", 0, lib_text.index(anchor)) + 1:
                out.append("the core.mereo diagnostic landed on line "
                           f"{said[0]['range']['start']['line'] + 1}, not on "
                           "the line that was broken")
    finally:
        client.close()
    return out


def main(argv):
    root = pathlib.Path(argv[0]).resolve() if argv else ROOT
    lsp = load(root / "mereolsp.py", "mereolsp")
    problems, files, symbols = check_index(lsp, root)
    resolution, hit, total, rate = check_resolution(lsp, root)
    problems += resolution
    problems += check_ports(root)
    problems += check_server(root)
    for p in problems:
        print(f"  {p}")
    if problems:
        print(f"check_lsp: {len(problems)} problem(s)")
        return 1
    print(f"  language server: {files} files, {symbols} symbols, "
          f"{hit}/{total} dotted names resolved ({rate:.1f}%); "
          "port directions from the compiler; answers over stdio and declares "
          "no painter")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
