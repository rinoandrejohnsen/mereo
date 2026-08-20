#!/usr/bin/env python3
"""mereoprove -- how many accesses could the compiler prove in range?

A MEASUREMENT, not a compiler pass. It answers one question: when a C
programmer writes `p[i]` with no check, they are holding a proof in their head;
how much of that proof is recoverable from a mereo program's text?

It runs on the post-splice IR -- the flat step list `expand_procedures` hands to
`plan`, which is where such a pass would eventually live -- and classifies every
access `[base + index : width]`:

  proved            index bounded, and hi + width <= the backing's size
  OUT               index bounded, and it does NOT fit
  bound-unresolved  a bound exists but this prototype cannot chase it
  data-dependent    no bound in scope at all
  opaque-base       the backing itself did not resolve

WHAT IT KNOWS: constant indices; induction variables bounded at the top
(`loop_exit X >= B`) or at the bottom (`loop_end cond X < B`), each corrected for
increments that happen before the access; affine indices (`off is i * 8`);
reaching definitions, so a name assigned in three loops is read as the one that
reaches the use; syscall contract upper bounds (`ensure count <= capacity`); and
spans, whose `data` resolves back to the buffer they were adopted over.

WHAT IT DOES NOT KNOW, and these are the whole of the gap:

  * `ensure` is not read as a premise. The programmer writes the missing fact
    and the analysis ignores it -- which is why the TLS transcript index is
    still unproved even though the bound is stated on the line above it.
  * upper bounds only, no lower bounds, so any subtraction is refused.
  * no fixpoint across a template's ports.

Usage:  tools/mereoprove.py FILE...        one line per unproved access
        tools/mereoprove.py --tally FILE... corpus totals
"""
import sys, json, re
sys.path.insert(0, "/home/rino/Projects/mereo")
import mereoc

ACC  = re.compile(r"\[([^\[\]]*)\]")
CMPX = re.compile(r"^\s*(.+?)\s*(<=|>=|==|!=|<|>)\s*(.+?)\s*$")
STR  = re.compile(r'^"(.*)"$', re.S)
TOK  = re.compile(r"[A-Za-z_][\w.]*|\d+|<<|>>|[-+*/%&|^()]")
INC  = re.compile(r"^\s*([\w.]+)\s*\+\s*(\d+)\s*$")
STASH = {}

def const(e):
    if e is None: return None
    e = str(e).strip()
    try: return int(e, 0)
    except Exception: pass
    if re.fullmatch(r"[\d\s+*\-()]+", e):
        try: return int(eval(e, {"__builtins__": {}}, {}))
        except Exception: return None
    return None

def strings(st):
    out = []
    for k, v in st.items():
        if k in ("type","name","method","inst","label","pname","kind","op"): continue
        if isinstance(v, str): out.append(v)
        elif isinstance(v, list):
            for it in v:
                if isinstance(it, str): out.append(it)
                elif isinstance(it, (list, tuple)):
                    out += [x for x in it if isinstance(x, str)]
    return out

def analyse(definitions, slots):
    steps = STASH["steps"]
    bufs = {s["name"]: const(s["size"]) for s in slots if s["kind"] == "buffer"}
    inst = {s["name"]: s for s in slots if s["kind"] == "instance"}

    def psize(n):
        d = definitions.get(inst[n]["definition"]) if n in inst else None
        return d.get("psize") if d else None

    # ---------- contract upper bounds: an out-port bounded by an argument
    cbound = {}
    for st in steps:
        if st.get("type") not in ("call", "bare"): continue
        conns = dict((c[0], c[1]) for c in st.get("conns", []) if len(c) >= 2)
        prim = mereoc.PRIMITIVES.get(st.get("op") or st.get("method"), {})
        for cl in (prim.get("contract") or []):
            raw = cl if isinstance(cl, str) else (cl[0] if cl else "")
            m = CMPX.match(str(raw))
            if not m or m.group(2) not in ("<=", "<"): continue
            tgt = conns.get(m.group(1).replace(" as signed", "").strip())
            cap = conns.get(m.group(3).strip(), m.group(3).strip())
            if tgt and const(cap) is not None: cbound[tgt] = const(cap)

    copy = {}
    for i, st in enumerate(steps):
        if st.get("type") == "assign" and isinstance(st.get("expr"), str):
            copy.setdefault(st["name"], []).append((i, st["expr"].strip()))

    # ---------- loops, position-aware
    # pair start/end positionally; a loop's bound may sit at the TOP
    # (`loop_exit X >= B`) or at the BOTTOM (`loop_end cond X < B`).
    stack, loops = [], []
    for i, st in enumerate(steps):
        t = st.get("type")
        if t == "loop_start": stack.append(i)
        elif t == "loop_end" and stack:
            s = stack.pop()
            loops.append((s, i, st.get("cond"), st.get("back", False)))
    binding = {}                       # step -> {name: (bound_expr, extra)}
    for s, e, endcond, back in loops:
        bounds = {}
        if back and endcond:
            m = CMPX.match(str(endcond))
            if m and m.group(2) in ("<", "<="):
                bounds[m.group(1).strip()] = (m.group(3).strip(), s)
        depth = 0
        for i in range(s + 1, e):
            t = steps[i].get("type")
            if t == "loop_start": depth += 1
            elif t == "loop_end": depth -= 1
            elif t == "loop_exit" and depth == 0 and steps[i].get("cond"):
                m = CMPX.match(str(steps[i]["cond"]))
                if m and m.group(2) in (">=", ">"):
                    bounds[m.group(1).strip()] = (m.group(3).strip(), i)
        # where is each bounded name incremented, and by how much
        for name, (bexpr, from_i) in bounds.items():
            incs = []
            for i in range(s + 1, e):
                st = steps[i]
                if st.get("type") == "assign" and st.get("name") == name:
                    m = INC.match(str(st.get("expr", "")))
                    if m and m.group(1) == name: incs.append((i, int(m.group(2))))
                    else: incs.append((i, None))     # opaque write: give up
            for i in range(from_i, e):
                extra, ok = 0, True
                for pos, k in incs:
                    if pos < i:
                        if k is None: ok = False; break
                        extra += k
                if ok: binding.setdefault(i, {})[name] = (bexpr, extra)

    inner_loop = {}
    for s_, e_, _c, _b in sorted(loops, key=lambda L: L[1] - L[0]):
        for i in range(s_, e_ + 1): inner_loop.setdefault(i, (s_, e_))

    def reaching(n, at):
        """definitions of `n` that can reach step `at`: the nearest one before
        it, plus any inside the innermost enclosing loop (the back edge)."""
        defs = copy.get(n) or []
        before = [(i, e) for i, e in defs if i < at]
        out = [before[-1][1]] if before else []
        lp = inner_loop.get(at)
        if lp:
            out += [e for i, e in defs if lp[0] < i < lp[1] and i != (before[-1][0] if before else -1)]
        return out or ([e for _i, e in defs] if not before else out)

    # ---------- interval upper bound of an index expression
    def ub(e, bnd, at, seen=()):
        e = str(e).strip()
        if not e: return None
        k = const(e)
        if k is not None: return k if k >= 0 else None
        toks = TOK.findall(e)
        if len(toks) == 1 and re.match(r"[A-Za-z_]", toks[0]):
            n = toks[0]
            if n in seen: return None
            if n in bnd:
                bexpr, extra = bnd[n]
                b = ub(bexpr, bnd, at, seen + (n,))
                return None if b is None else b - 1 + extra
            if n in cbound: return cbound[n]
            cands = reaching(n, at)
            if not cands: return None
            vals = [ub(c, bnd, at, seen + (n,)) for c in cands]
            return None if any(v is None for v in vals) else max(vals)
        if re.search(r"[-/%|]", e): return None          # not monotone: refuse
        names = sorted({t for t in toks if re.match(r"[A-Za-z_]", t)})
        env = {}
        for n in names:
            v = ub(n, bnd, at, seen)
            if v is None: return None
            env[n] = v
        expr = e
        for n in sorted(names, key=len, reverse=True):
            expr = re.sub(r"(?<![\w.])" + re.escape(n) + r"(?![\w.])", str(env[n]), expr)
        if not re.fullmatch(r"[\d\s+*&^()<>]*", expr): return None
        try: return int(eval(expr, {"__builtins__": {}}, {}))
        except Exception: return None

    def base_of(e, depth=0):
        e = e.strip()
        if depth > 6: return None, None
        m = STR.match(e)
        if m:
            try: return "literal", len(m.group(1).encode().decode("unicode_escape"))
            except Exception: return "literal", len(m.group(1))
        if e in bufs: return e, bufs[e]
        if e in inst: return e, psize(e)
        if "." in e:
            a, _, f = e.partition(".")
            p = (inst.get(a, {}).get("pending") or {}).get(f)
            if p: return base_of(p[0], depth + 1)
        return None, None

    out = []
    for i, st in enumerate(steps):
        for s in strings(st):
            for inner in ACC.findall(s):
                body, sep, w = inner.rpartition(":")
                if not sep: body, w = inner, "1"
                width = const(w) or 1
                lhs, _, idx = body.partition("+")
                bname, size = base_of(lhs)
                if size is None:
                    out.append(["opaque-base", lhs.strip(), inner]); continue
                bnd = binding.get(i, {})
                hi = ub(idx.strip(), bnd, i) if idx.strip() else 0
                if hi is None:
                    first = re.split(r"[^\w.]", idx.strip())[0]
                    kind = "bound-unresolved" if (first in bnd or first in copy) else "data-dependent"
                    out.append([kind, bname, inner]); continue
                out.append([("proved" if hi + width <= size else "OUT"), bname, inner])
    STASH["rows"] = out
    raise Done()

class Done(Exception): pass
class Skipped(Exception): pass

_h = mereoc.hoist_guard_bounds
def keep(steps, slots):
    steps = _h(steps, slots); STASH["steps"] = steps; return steps
mereoc.hoist_guard_bounds = keep
mereoc.check_slots = analyse


def classify(path):
    STASH.clear()
    try:
        mereoc.transpile(mereoc.load(path, set(), []), "x")
    except Done:
        return STASH.get("rows", [])
    except SystemExit:
        # a refusal test: mereoc rejected it before the analysis ran
        raise Skipped()
    return STASH.get("rows", [])


if __name__ == "__main__":
    import collections
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tally_only = "--tally" in sys.argv
    if not args:
        sys.exit(__doc__.strip().splitlines()[-2].strip())
    tally, skipped = collections.Counter(), []
    for path in args:
        try:
            rows = classify(path)
        except Skipped:
            skipped.append(path); continue
        except Exception:
            skipped.append(path); continue
        tally.update(r[0] for r in rows)
        if not tally_only:
            for kind, base, expr in rows:
                if kind != "proved":
                    print(f"{path}: {kind:<17} [{expr}]   (backing {base})")
    total = sum(tally.values()) or 1
    print(f"\n{len(args) - len(skipped)} programs, {sum(tally.values())} accesses")
    for k, v in tally.most_common():
        print(f"  {k:<18} {v:5}   {100 * v / total:5.1f}%")
    if skipped:
        print(f"  ({len(skipped)} skipped -- refusal tests and programs needing arguments)")
