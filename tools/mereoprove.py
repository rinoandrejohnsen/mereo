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
(`loop_exit X >= B`) or the bottom (`loop_end cond X < B`), corrected for
increments that happen before the access; affine indices (`off is i * 8`);
interval arithmetic with BOTH ends, so subtraction is usable; reaching
definitions with kills, each definition evaluated where it sits rather than at
the use; `ensure` read as a premise, propagated through an assignment that
stores the guarded expression (`ensure tlen + n <= tr.size` then `tlen is tlen +
n`); syscall contract clauses, reached through the method's `prim` and `bind`;
and mereo's branchless idiom -- `lt is i < 15` then `idx is idx * lt` -- by
case-splitting on the comparison, which a plain interval domain cannot do
because it loses the correlation between `i` and `lt`.

WHAT IT DOES NOT KNOW: no fixpoint across a template's ports (the `opaque-base`
rows), and no relational domain, so two variables constrained by a shared fact
are still handled one at a time.

SOUNDNESS is checked the way everything else here is: by planting violations.
A loop bound wider than its backing, an affine index that overflows, a syscall
capacity larger than the buffer, and an off-by-one in the branchless guard are
each reported OUT. Across the corpus exactly ONE access is reported OUT, and it
is `access_past_end.mereo`, which mereoc already refuses.

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
    # `buffer is capacity bytes` gives the size as a NAME. The emitter resolves
    # it through the scalar's init (see `buffer_size` in mereoc.py); so does a
    # reader, without noticing. Do the same.
    sinit = {s["name"]: s.get("init") for s in slots if s["kind"] == "scalar"}
    def bufsize(v):
        k = const(v)
        if k is not None: return k
        seen = set()
        while isinstance(v, str) and v in sinit and v not in seen:
            seen.add(v); v = sinit[v]
            k = const(v)
            if k is not None: return k
        return None
    bufs = {s["name"]: bufsize(s["size"]) for s in slots if s["kind"] == "buffer"}
    inst = {s["name"]: s for s in slots if s["kind"] == "instance"}

    # A resource's OWN state array is not a slot -- it lives on the definition
    # and is spliced to `<instance>_<field>`. Its size is in the layout.
    own = {}
    for sl in slots:
        if sl.get("kind") != "instance": continue
        d = definitions.get(sl.get("definition")) or {}
        lay = d.get("playout") or {}
        for fld in (d.get("arrays") or ()):
            ent = lay.get(fld)
            if ent and len(ent) >= 2:
                own[f"{sl['name']}_{fld}"] = ent[1]

    def psize(n):
        d = definitions.get(inst[n]["definition"]) if n in inst else None
        return d.get("psize") if d else None

    # ---------- contract bounds, from the primitive behind the method
    # A clause names the PRIMITIVE's ports (`count as signed <= capacity`).
    # A method reaches it through `prim` + `bind`, and the call site supplies
    # the arguments through `conns` -- so all three hops are needed.
    cbound, clow = {}, {}
    for idx, st in enumerate(steps):
        t = st.get("type")
        if t not in ("call", "bare"): continue
        conns = dict((c[0], c[1]) for c in st.get("conns", []) if len(c) >= 2)
        if t == "bare":
            prim, bind = mereoc.PRIMITIVES.get(st.get("op"), {}), None
        else:
            dname = (inst.get(st.get("inst")) or {}).get("definition")
            meth = ((definitions.get(dname) or {}).get("methods") or {}).get(st.get("method")) or {}
            prim = mereoc.PRIMITIVES.get(meth.get("prim"), {})
            bind = meth.get("bind") or {}
        def arg(port):
            """primitive port -> the expression written at the call site"""
            if bind is not None:
                b = bind.get(port)
                port = b[0] if isinstance(b, (list, tuple)) else (b or port)
            return conns.get(port)
        for cl in (prim.get("contract") or []):
            # a clause is already split: (lhs, op, rhs, line, mode)
            if isinstance(cl, (list, tuple)) and len(cl) >= 3:
                lhs, op, rhs = str(cl[0]).strip(), str(cl[1]).strip(), str(cl[2]).strip()
            else:
                m = CMPX.match(str(cl))
                if not m: continue
                lhs, op, rhs = (m.group(1).replace(" as signed", "").strip(),
                                m.group(2), m.group(3).replace(" as signed", "").strip())
            # only a clause on the OUT port says anything about a VALUE. One
            # on an in port is a requirement on the call -- mereoc decides it
            # when the program is read, and it bounds an argument, not a result.
            if lhs != prim.get("out"): continue
            tgt = arg(lhs)
            if not tgt: continue
            val = arg(rhs)
            if val is None: val = rhs
            # resolved lazily: the bound may be a name whose value is only
            # knowable at the call site
            if op in ("<=", "<"):
                cbound.setdefault(tgt, []).append((val, op == "<", idx))
            elif op in (">=", ">"):
                clow.setdefault(tgt, []).append((val, op == ">", idx))

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
    binding, desc = {}, {}
    for s, e, endcond, back in loops:
        bounds, lows = {}, {}
        # a COUNTING-DOWN loop: `i is 254` before it, `i is i - 1` inside, and
        # `repeat when i >= 0`. The ceiling is the value it started at.
        if back and endcond:
            m = CMPX.match(str(endcond))
            if m and m.group(2) in (">=", ">"):
                lows[m.group(1).strip()] = (m.group(3).strip(), s)
        if back and endcond:
            m = CMPX.match(str(endcond))
            if m and m.group(2) in ("<", "<="):
                bounds[m.group(1).strip()] = (m.group(3).strip(), s, (s, e))
        depth = 0
        for i in range(s + 1, e):
            t = steps[i].get("type")
            if t == "loop_start": depth += 1
            elif t == "loop_end": depth -= 1
            elif t == "loop_exit" and depth == 0 and steps[i].get("cond"):
                m = CMPX.match(str(steps[i]["cond"]))
                if m and m.group(2) in (">=", ">"):
                    bounds[m.group(1).strip()] = (m.group(3).strip(), i, (s, e))
        for name, (loexpr, from_i) in lows.items():
            decs, ok = [], True
            for i in range(s + 1, e):
                st = steps[i]
                if st.get("type") == "assign" and st.get("name") == name:
                    m = re.match(r"^\s*([\w.]+)\s*-\s*(\d+)\s*$", str(st.get("expr", "")))
                    if m and m.group(1) == name: decs.append((i, int(m.group(2))))
                    else: ok = False; break
            if not ok: continue
            entry = None
            cands = [(j, steps[j].get("expr")) for j in range(s)
                     if steps[j].get("type") == "assign" and steps[j].get("name") == name]
            if cands: entry = cands[-1]
            if entry is None: continue
            for i in range(s + 1, e):
                before = sum(k for pos, k in decs if pos < i)
                desc.setdefault(i, {})[name] = (entry, loexpr, before)

        # where is each bounded name incremented, and by how much
        for name, (bexpr, from_i, lp) in bounds.items():
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
                if ok: binding.setdefault(i, {})[name] = (bexpr, extra, lp)

    inner_loop = {}
    for s_, e_, _c, _b in sorted(loops, key=lambda L: L[1] - L[0]):
        for i in range(s_, e_ + 1): inner_loop.setdefault(i, (s_, e_))

    def reaching(n, at):
        """definitions of `n` that can reach step `at`: the nearest one before
        it, plus any inside the innermost enclosing loop (the back edge)."""
        defs = copy.get(n) or []
        before = [(i, e) for i, e in defs if i < at]
        lp = inner_loop.get(at)
        # a definition inside this loop, before the use, KILLS whatever the back
        # edge carried in -- it runs every iteration ahead of the use
        if before and lp and before[-1][0] > lp[0]:
            return [before[-1]]
        out = [before[-1]] if before else []
        if lp:
            out += [(i, e) for i, e in defs if lp[0] < i < lp[1] and i != (before[-1][0] if before else -1)]
        if out: return out
        ini = sinit.get(n)
        if not before and ini is not None: return [(-1, str(ini))]
        return list(defs)

    # ---------- facts asserted by `ensure`, propagated forward
    # A guard `A <= B` is a premise the programmer wrote down. It bounds the
    # EXPRESSION A, not just a name -- so when a later assignment stores exactly
    # that expression, the target inherits the bound. That is the common idiom:
    #
    #     ensure tlen + inner_len <= tr.size
    #     tlen is tlen + inner_len            -- tlen now <= tr.size
    #
    # A fact dies when anything it mentions is written.
    def names_in(e):
        return set(re.findall(r"[A-Za-z_][\w.]*", str(e)))

    facts, live = {}, {}          # live: expr -> (rhs, strict, siblings)
    for i, st in enumerate(steps):
        t = st.get("type")
        if t == "assign":
            tgt, ex = st.get("name"), str(st.get("expr", "")).strip()
            inherit = live.get(ex)
            for k in [k for k, v in live.items()
                      if tgt in names_in(k) or any(tgt in names_in(f[1]) for f in v)]:
                live.pop(k, None)
            if inherit: live[tgt] = list(inherit)
        elif t in ("call", "bare"):
            outs = set()
            for c in st.get("conns", []):
                if len(c) >= 2: outs |= names_in(c[1])
            for k in [k for k, v in live.items()
                      if outs & (names_in(k) | set().union(*(names_in(f[1]) for f in v)))]:
                live.pop(k, None)
        elif t == "guard" and st.get("cond"):
            m = CMPX.match(str(st["cond"]))
            if m and m.group(2) in ("<=", "<", ">=", ">"):
                lhs, op, rhs = m.group(1).strip(), m.group(2), m.group(3).strip()
                terms = [x.strip() for x in lhs.split("+")] if "-" not in lhs else []
                live.setdefault(lhs, []).append((op, rhs, []))
                if len(terms) > 1 and op in ("<=", "<"):
                    for x in terms:
                        live.setdefault(x, []).append((op, rhs, [y for y in terms if y != x]))
        if live:
            facts[i] = {k: list(v) for k, v in live.items()}

    # An instance whose bytes are never written keeps the values it was adopted
    # with, so `v.length` is the number in `already span (length is 17)`. If
    # anything stores into it -- `take` narrows a span that way -- give up.
    mutated = set()
    for st in steps:
        if st.get("type") not in ("store", "fstore", "atomic"): continue
        head = str(st.get("addr", "")).partition("+")[0].strip()
        if head in inst: mutated.add(head)
        for nm in inst:
            if re.match(rf"{re.escape(nm)}\b", head): mutated.add(nm)

    def adopted_field(e):
        if "." not in e: return None
        a, _, f = e.partition(".")
        if a not in inst or a in mutated: return None
        pend = (inst[a].get("pending") or {}).get(f)
        return pend[0] if pend else None

    def size_name(e):
        e = e.strip()
        if e.endswith(".size"):
            b = e[:-5]
            if b in bufs: return bufs[b]
            if b in inst: return psize(b)
        return None

    # ---------- interval arithmetic over the index expressions
    import ast
    UNK = (None, None)

    def join(a, b):
        lo = None if a[0] is None or b[0] is None else min(a[0], b[0])
        hi = None if a[1] is None or b[1] is None else max(a[1], b[1])
        return (lo, hi)

    def loop_lo(n, lp, seen=()):
        """the floor of a counting-up variable: the value it entered with.
        `ii is 1` before the loop makes `poff is ii * 8 - 8` non-negative --
        assuming 0 is sound but too loose to prove anything."""
        s_, e_ = lp
        for i in range(s_, e_):
            st = steps[i]
            if st.get("type") == "assign" and st.get("name") == n:
                ex = str(st.get("expr", "")).strip()
                if const(ex) is not None and const(ex) >= 0: continue
                if INC.match(ex) and INC.match(ex).group(1) == n: continue
                if re.fullmatch(r"[\w.]+\s*-\s*[\w.]+", ex):
                    a, b = [x.strip() for x in ex.split("-")]
                    if a == b: continue          # `mj is mj - mj`, a zeroing
                return None
        entry = [(j, steps[j].get("expr")) for j in range(s_)
                 if steps[j].get("type") == "assign" and steps[j].get("name") == n]
        if entry:
            j, ex = entry[-1]
            if (n, j) not in seen:
                v = iv(str(ex), j, seen + ((n, j),))[0]
                if v is not None and v >= 0: return v
        return 0

    ASSUME = {}

    def as_compare(nd, at, seen):
        """this node, or the definition behind it, as a comparison"""
        if isinstance(nd, ast.Compare): return nd
        if isinstance(nd, ast.Name):
            for d, ex in reaching(nd.id, at):
                try: n2 = ast.parse(str(ex), mode="eval").body
                except SyntaxError: continue
                if isinstance(n2, ast.Compare): return n2
        return None

    def assuming(cnode, at, seen):
        """the interval a comparison forces on its left operand, when true"""
        if len(cnode.ops) != 1 or not isinstance(cnode.left, ast.Name): return None, None
        try: rhs = ast.unparse(cnode.comparators[0])
        except Exception: return None, None
        r = iv(rhs, at, seen)
        op = cnode.ops[0]
        if isinstance(op, ast.Lt)  and r[1] is not None: return cnode.left.id, (None, r[1] - 1)
        if isinstance(op, ast.LtE) and r[1] is not None: return cnode.left.id, (None, r[1])
        if isinstance(op, ast.Gt)  and r[0] is not None: return cnode.left.id, (r[0] + 1, None)
        if isinstance(op, ast.GtE) and r[0] is not None: return cnode.left.id, (r[0], None)
        if isinstance(op, ast.Eq)  and r[0] == r[1] is not None: return cnode.left.id, r
        return None, None

    LOAD = re.compile(r"^\[[^\[\]]*?(?::\s*(\d+)\s*)?\]$")

    def tighten(key, cur, at, sn):
        lo, hi = cur
        for op, rhs, others in facts.get(at, {}).get(key, []):
            if op in ("<=", "<"):
                lows = [iv(t, at, sn)[0] for t in others]
                if any(l is None or l < 0 for l in lows): continue
                rh = iv(rhs, at, sn)[1]
                if rh is None: continue
                cap = rh - sum(lows) - (1 if op == "<" else 0)
                hi = cap if hi is None else min(hi, cap)
            else:
                rl = iv(rhs, at, sn)[0]
                if rl is None: continue
                flr = rl + (1 if op == ">" else 0)
                lo = flr if lo is None else max(lo, flr)
        return (lo, hi)

    ASSUME = {}

    def as_compare(nd, at, seen):
        """this node, or the definition behind it, as a comparison"""
        if isinstance(nd, ast.Compare): return nd
        if isinstance(nd, ast.Name):
            for d, ex in reaching(nd.id, at):
                try: n2 = ast.parse(str(ex), mode="eval").body
                except SyntaxError: continue
                if isinstance(n2, ast.Compare): return n2
        return None

    def assuming(cnode, at, seen):
        """the interval a comparison forces on its left operand, when true"""
        if len(cnode.ops) != 1 or not isinstance(cnode.left, ast.Name): return None, None
        try: rhs = ast.unparse(cnode.comparators[0])
        except Exception: return None, None
        r = iv(rhs, at, seen)
        op = cnode.ops[0]
        if isinstance(op, ast.Lt)  and r[1] is not None: return cnode.left.id, (None, r[1] - 1)
        if isinstance(op, ast.LtE) and r[1] is not None: return cnode.left.id, (None, r[1])
        if isinstance(op, ast.Gt)  and r[0] is not None: return cnode.left.id, (r[0] + 1, None)
        if isinstance(op, ast.GtE) and r[0] is not None: return cnode.left.id, (r[0], None)
        if isinstance(op, ast.Eq)  and r[0] == r[1] is not None: return cnode.left.id, r
        return None, None

    LOAD = re.compile(r"^\[[^\[\]]*?(?::\s*(\d+)\s*)?\]$")

    LOAD = re.compile(r"^\[[^\[\]]*?(?::\s*(\d+)\s*)?\]$")

    def iv(e, at, seen=()):
        e = str(e).strip()
        if not e: return UNK
        # `b is [block + i : 1]` makes b a BYTE. A skilled reader uses that
        # without thinking; the width is right there in the access.
        m = LOAD.match(e)
        if m:
            w = int(m.group(1) or 1)          # no `: N` means one byte
            return (0, (1 << (8 * w)) - 1) if w <= 4 else UNK
        # a width/sign modifier is not part of the arithmetic
        e = re.sub(r"\s+as\s+(unsigned|signed|big|little)\b", "", e).strip()
        k = const(e)
        if k is not None: return (k, k)
        sz = size_name(e)
        if sz is not None: return (sz, sz)
        af = adopted_field(e)
        if af is not None and (af, at) not in seen:
            return iv(af, at, seen + ((af, at),))
        bnd = binding.get(at, {})
        if re.fullmatch(r"[A-Za-z_][\w.]*", e):
            n = e
            if (n, at) in seen: return UNK
            sn = seen + ((n, at),)
            best = UNK
            if n in desc.get(at, {}):
                (ej, eexpr), loexpr, before = desc[at][n]
                hi = iv(str(eexpr), ej, sn)[1]
                lo = iv(loexpr, at, sn)[0]
                best = (None if lo is None else lo - before,
                        None if hi is None else hi - before)
            elif n in bnd:
                bexpr, extra, lp = bnd[n]
                b = iv(bexpr, at, sn)[1]
                best = (loop_lo(n, lp, sn), None if b is None else b - 1 + extra)
            elif n in cbound or n in clow:
                hi = lo = None
                for val, strict, idx in cbound.get(n, []):
                    v = iv(val, idx, sn)[1]
                    if v is None: continue
                    v -= 1 if strict else 0
                    hi = v if hi is None else min(hi, v)
                for val, strict, idx in clow.get(n, []):
                    v = iv(val, idx, sn)[0]
                    if v is None: continue
                    v += 1 if strict else 0
                    lo = v if lo is None else max(lo, v)
                best = (lo, hi)
            else:
                cands = reaching(n, at)
                if cands:
                    vals = [iv(c, d, sn) for d, c in cands]
                    acc = vals[0]
                    for v in vals[1:]: acc = join(acc, v)
                    best = acc
            best = tighten(n, best, at, sn)
            a = ASSUME.get(n)
            if a:
                best = (best[0] if a[0] is None else
                        (a[0] if best[0] is None else max(best[0], a[0])),
                        best[1] if a[1] is None else
                        (a[1] if best[1] is None else min(best[1], a[1])))
            return best
        try:
            node = ast.parse(e.replace("^", "|"), mode="eval").body
        except SyntaxError:
            return UNK
        def walk(nd):
            if isinstance(nd, ast.Constant):
                return (nd.value, nd.value) if isinstance(nd.value, int) else UNK
            if isinstance(nd, ast.Name): return iv(nd.id, at, seen)
            if isinstance(nd, ast.Attribute):
                try: src = ast.unparse(nd)
                except Exception: return UNK
                z = size_name(src)
                return (z, z) if z is not None else iv(src, at, seen)
            if isinstance(nd, ast.Compare):
                return (0, 1)          # mereo's branchless idiom: `lt is i < 15`
            if isinstance(nd, ast.BinOp):
                a, b = walk(nd.left), walk(nd.right)
                o = nd.op
                if isinstance(o, ast.Add):
                    return (None if a[0] is None or b[0] is None else a[0] + b[0],
                            None if a[1] is None or b[1] is None else a[1] + b[1])
                if isinstance(o, ast.Sub):
                    return (None if a[0] is None or b[1] is None else a[0] - b[1],
                            None if a[1] is None or b[0] is None else a[1] - b[0])
                if isinstance(o, ast.Mult):
                    for cs, other in ((nd.left, nd.right), (nd.right, nd.left)):
                        cn = as_compare(cs, at, seen)
                        if cn is None: continue
                        name, rng = assuming(cn, at, seen)
                        if name is None: continue
                        old = ASSUME.get(name)
                        ASSUME[name] = rng
                        try: t = iv(ast.unparse(other), at, seen)
                        finally:
                            if old is None: ASSUME.pop(name, None)
                            else: ASSUME[name] = old
                        if None in t: return UNK
                        return (min(0, t[0]), max(0, t[1]))
                    if None in a or None in b: return UNK
                    ps = [a[0]*b[0], a[0]*b[1], a[1]*b[0], a[1]*b[1]]
                    return (min(ps), max(ps))
                if isinstance(o, ast.BitAnd):
                    ks = [x for x in (b[1], a[1]) if x is not None and x >= 0]
                    return (0, min(ks)) if ks else UNK
                if isinstance(o, ast.LShift) and b[0] == b[1] and b[0] is not None:
                    return (None if a[0] is None else a[0] << b[0],
                            None if a[1] is None else a[1] << b[0])
                if isinstance(o, ast.RShift) and b[0] == b[1] and b[0] is not None:
                    return (None if a[0] is None else a[0] >> b[0],
                            None if a[1] is None else a[1] >> b[0])
                if isinstance(o, ast.Mod) and b[0] == b[1] and b[0]:
                    return (0, b[0] - 1)
                if isinstance(o, (ast.Div, ast.FloorDiv)) and b[0] == b[1] and b[0]:
                    return (None if a[0] is None else a[0] // b[0],
                            None if a[1] is None else a[1] // b[0])
                if isinstance(o, ast.BitOr):
                    if None in a or None in b or a[0] < 0 or b[0] < 0: return UNK
                    top = a[1] | b[1]
                    return (0, (1 << top.bit_length()) - 1)
            return UNK
        return tighten(e, walk(node), at, seen)

    def base_of(e, depth=0):
        e = e.strip()
        if depth > 6: return None, None
        m = STR.match(e)
        if m:
            try: return "literal", len(m.group(1).encode().decode("unicode_escape"))
            except Exception: return "literal", len(m.group(1))
        if e in bufs: return e, bufs[e]
        if e in own:  return e, own[e]
        if e in inst: return e, psize(e)
        if "." in e:
            a, _, f = e.partition(".")
            p = (inst.get(a, {}).get("pending") or {}).get(f)
            if p: return base_of(p[0], depth + 1)
        return None, None

    def resolve_base(expr, at, depth=0):
        """(name, size, offset-interval) -- chasing a scalar that HOLDS an
        address. `shmsg is sh_rec + 5` makes `[shmsg + 38]` an access into
        sh_rec at 43, which is how a reader takes it."""
        expr = expr.strip()
        bn, size = base_of(expr)
        if size is not None: return bn, size, (0, 0)
        if depth > 4 or not re.fullmatch(r"[A-Za-z_][\w.]*", expr):
            return None, None, None
        for d, ex in reaching(expr, at):
            ex = str(ex).strip()
            head, plus, tail = ex.partition("+")
            bn2, sz2, off2 = resolve_base(head, d, depth + 1)
            if sz2 is None: continue
            if not plus: return bn2, sz2, off2
            add = iv(tail, d)
            if None in add or None in off2: continue
            return bn2, sz2, (off2[0] + add[0], off2[1] + add[1])
        return None, None, None

    out = []
    for i, st in enumerate(steps):
        for s in strings(st):
            for inner in ACC.findall(s):
                body, sep, w = inner.rpartition(":")
                if not sep: body, w = inner, "1"
                width = const(w) or 1
                lhs, _, idx = body.partition("+")
                bname, size, off = resolve_base(lhs, i)
                if size is None:
                    out.append(["opaque-base", lhs.strip(), inner]); continue
                bnd = binding.get(i, {})
                lo, hi = iv(idx.strip(), i) if idx.strip() else (0, 0)
                if lo is not None and hi is not None:
                    lo, hi = lo + off[0], hi + off[1]
                if hi is None or lo is None or lo < 0:
                    first = re.split(r"[^\w.]", idx.strip())[0]
                    known = first in bnd or first in copy or first in facts.get(i, {})
                    kind = "bound-unresolved" if known else "data-dependent"
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
