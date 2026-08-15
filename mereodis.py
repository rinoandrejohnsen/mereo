#!/usr/bin/env python3
"""mereodis -- read a mereo binary back as C, one line per instruction.

    python3 mereodis.py BINARY [SOURCE.c]

BINARY must be built with -g (the mereo flags plus -g): the DWARF carries every
scalar/buffer name with its rsp-relative slot, and every label (error_*,
release_*, loop tops, exit) with its address -- the whole source mapping is in
the binary. SOURCE.c, when given, interleaves the generated-C lines above the
instructions they compiled to (via the DWARF line table).

The rendering is deliberately 1-1: one C-ish statement per instruction,
register names kept, memory through a register shown as mereo brackets
([rax] one byte, [rax : 8] a word), stack slots shown by name. cmp/test
fuse with their jump into a single `if (...) goto label;`.

Function-free makes this sound: rsp never moves after the prologue, so one
offset->name table covers the whole flat body.
"""

import re
import subprocess
import sys

# ---------------------------------------------------------------- objdump

def run(args):
    return subprocess.run(args, capture_output=True, text=True).stdout


def dwarf_names(binary):
    """-> (vars: {rsp_offset: name}, labels: {addr: name}, pairs: [(addr, name)])
    from --dwarf=info.

    SEVERAL labels can share an address -- `pick_road_0:` immediately followed by
    `loop3:` when a road's first statement opens a loop -- so `labels` (one name
    per address, for annotating a disassembly line) necessarily drops some.
    `pairs` keeps every one, which is what a checker asking "is this road still
    in the binary?" needs: mereocheck read the lossy map and reported a road that
    was laid out perfectly as dissolved.

    Inlined instances (the always_inline syscall wrappers) carry no name of
    their own -- they point at the abstract DIE via DW_AT_abstract_origin --
    so this is two passes: DIE offset -> name first, then locations."""
    text = run(["objdump", "--dwarf=info", binary]).splitlines()
    dienames = {}
    for line in text:
        m = re.match(r"\s*<\d+><([0-9a-f]+)>: Abbrev Number", line)
        if m:
            off = m.group(1)
            continue
        m = re.search(r"DW_AT_name\s*:(?:.*:)?\s*(\S+)\s*$", line)
        if m:
            dienames[off] = m.group(1)

    vars_, labels, pairs = {}, {}, []
    die, name = None, None
    for line in text:
        m = re.match(r"\s*<\d+><[0-9a-f]+>: Abbrev Number: \d+ \(DW_TAG_(\w+)\)", line)
        if m:
            die, name = m.group(1), None
            continue
        m = re.search(r"DW_AT_name\s*:(?:.*:)?\s*(\S+)\s*$", line)
        if m:
            name = m.group(1)
            continue
        m = re.search(r"DW_AT_abstract_origin\s*:\s*<0x([0-9a-f]+)>", line)
        if m:
            name = dienames.get(m.group(1), name)
            continue
        if die in ("variable", "formal_parameter") and name:
            m = re.search(r"DW_OP_breg7 \(rsp\): (-?\d+)", line)
            if m:
                vars_.setdefault(int(m.group(1)), name)
                continue
        if die == "label" and name and "DW_AT_low_pc" in line:
            m = re.search(r"DW_AT_low_pc\s*:\s*0x([0-9a-f]+)", line)
            if m:
                labels[int(m.group(1), 16)] = name
                pairs.append((int(m.group(1), 16), name))
    return vars_, labels, pairs


def dwarf_lines(binary):
    """-> {addr: source_line_number} from the DWARF line table."""
    text = run(["objdump", "--dwarf=decodedline", binary])
    table = {}
    for line in text.splitlines():
        m = re.match(r"\S+\s+(\d+)\s+0x([0-9a-f]+)", line)
        if m:
            table.setdefault(int(m.group(2), 16), int(m.group(1)))
    return table


def rodata(binary):
    """-> (base_addr, bytes) of .rodata, for resolving string immediates."""
    text = run(["objdump", "-s", "-j", ".rodata", binary])
    base, data = None, bytearray()
    for line in text.splitlines():
        m = re.match(r"\s*([0-9a-f]+) ((?:[0-9a-f]{2,8} ?){1,4}) ", line)
        if m:
            if base is None:
                base = int(m.group(1), 16)
            for word in m.group(2).split():
                data.extend(bytes.fromhex(word))
    return base, bytes(data)


def instructions(binary):
    """-> ([(addr, mnemonic, operands)], {addr: symbol}) from the disassembly."""
    text = run(["objdump", "-d", "--no-show-raw-insn", binary])
    out, syms = [], {}
    for line in text.splitlines():
        m = re.match(r"^([0-9a-f]+) <(\S+)>:$", line)
        if m:
            syms[int(m.group(1), 16)] = m.group(2)
            continue
        m = re.match(r"\s+([0-9a-f]+):\s+(\S+)(?:\s+(.*?))?(?:\s*#\s*(.*))?$", line)
        if m:
            out.append((int(m.group(1), 16), m.group(2),
                        (m.group(3) or "").strip(), m.group(4) or ""))
    return out, syms

# ---------------------------------------------------------------- rendering

SYSCALLS = {0: "read", 1: "write", 2: "open", 3: "close", 8: "lseek",
            9: "mmap", 11: "munmap", 13: "rt_sigaction", 15: "rt_sigreturn",
            41: "socket", 42: "connect", 43: "accept", 49: "bind",
            50: "listen", 62: "kill", 74: "fsync", 107: "geteuid",
            231: "exit_group"}

JCC = {"je": "==", "jne": "!=", "jg": ">", "jge": ">=", "jl": "<",
       "jle": "<=", "ja": "u>", "jae": "u>=", "jb": "u<", "jbe": "u<=",
       "js": "< 0", "jns": ">= 0"}

SETCC = {"sete": "==", "setne": "!=", "setg": ">", "setge": ">=",
         "setl": "<", "setle": "<=", "seta": "u>", "setae": "u>=",
         "setb": "u<", "setbe": "u<="}

WIDTH = {"b": 1, "w": 2, "l": 4, "q": 8}

REG8 = {"al", "bl", "cl", "dl", "sil", "dil", "spl", "bpl",
        "r8b", "r9b", "r10b", "r11b", "r12b", "r13b", "r14b", "r15b"}


def canon(name):
    """A register name -> its 64-bit canonical form (eax->rax, r10d->r10),
    so constant tracking survives width changes. Non-registers pass through."""
    if name in ("eax", "ebx", "ecx", "edx", "esi", "edi", "ebp", "esp"):
        return "r" + name[1:]
    if re.fullmatch(r"r\d+d", name):
        return name[:-1]
    return name


def reg_width(tok):
    """The width a bare register name implies (for suffix-less mov)."""
    t = tok.lstrip("%")
    if t in REG8:
        return 1
    if t.startswith("e") or t.endswith("d"):
        return 4
    if t in ("ax", "bx", "cx", "dx", "si", "di", "bp", "sp"):
        return 2
    return 8


class Renderer:
    def __init__(self, vars_, labels, ro_base, ro_data, syms=None):
        self.vars = vars_          # rsp offset -> name
        self.offs = sorted(vars_)  # for buffer-interior lookup
        self.labels = labels       # addr -> name
        self.syms = syms or {}     # addr -> symbol (for address immediates)
        self.ro_base, self.ro_data = ro_base, ro_data
        self.insn_addrs = set()    # every instruction start (set by main)
        self.pending_cmp = None    # (lhs, rhs) awaiting a jcc
        self.last_eax_imm = None   # for naming the syscall
        self.consts = {}           # slot name -> last constant stored (-O0
                                   # spills the syscall nr through a slot)

    # -- operands ---------------------------------------------------------

    def slot(self, off):
        """An rsp-relative offset -> the variable name (or name+k inside a
        buffer, bounded by the next variable's slot)."""
        if off in self.vars:
            return self.vars[off]
        prev = [o for o in self.offs if o < off]
        nxt = [o for o in self.offs if o > off]
        if prev and (not nxt or off < nxt[0]):
            base = prev[-1]
            return f"{self.vars[base]}+{off - base}"
        return f"rsp+{off}"

    def imm(self, tok):
        v = int(tok.lstrip("$"), 16) if "0x" in tok else int(tok.lstrip("$"))
        if v >= 1 << 63:
            v -= 1 << 64            # immediates are signed 64-bit
        if v in self.syms and v >= 0x10000:
            return f"&{self.syms[v]}"    # (low PIE addresses collide with
                                         #  plain small constants -- skip)
        if (self.ro_base is not None
                and self.ro_base <= v < self.ro_base + len(self.ro_data)):
            raw = self.ro_data[v - self.ro_base:]
            s = raw.split(b"\0", 1)[0]
            if 0 < len(s) <= 80 and all(32 <= b < 127 or b in (9, 10) for b in s):
                return '"' + s.decode().replace("\n", "\\n") + '"'
        return str(v)

    def operand(self, tok, size=8):
        tok = tok.strip()
        if not tok:
            return tok
        if tok.startswith("$"):
            return self.imm(tok)
        if tok.startswith("%"):
            return tok[1:]
        m = re.match(r"^(-?0x[0-9a-f]+|-?\d+)?\(%rsp\)$", tok)
        if m:
            return self.slot(int(m.group(1) or "0", 16 if "0x" in (m.group(1) or "") else 10))
        m = re.match(r"^(-?0x[0-9a-f]+|-?\d+)?\(%(\w+)(?:,%(\w+)(?:,(\d+))?)?\)$", tok)
        if m:                       # memory through a register -> mereo brackets
            disp, base, idx, scale = m.groups()
            addr = base
            if idx:
                addr += f" + {idx}" + (f"*{scale}" if scale and scale != "1" else "")
            if disp:
                d = int(disp, 16 if "0x" in disp else 10)
                if d:
                    addr += f" + {d}" if d > 0 else f" - {-d}"
            return f"[{addr}]" if size == 1 else f"[{addr} : {size}]"
        if re.match(r"^0x[0-9a-f]+$", tok):
            return tok              # a jump target, handled by the caller
        return tok

    def target(self, tok):
        addr = int(tok.split()[0], 16)
        if addr in self.labels:
            return self.labels[addr]
        if addr in self.syms:
            return self.syms[addr]
        if addr not in self.insn_addrs:
            # the target is padding (a skipped nop): the next real label names
            # it -- but never skip over an actual instruction
            for a in range(addr + 1, addr + 5):
                if a in self.labels:
                    return self.labels[a]
                if a in self.syms:
                    return self.syms[a]
                if a in self.insn_addrs:
                    break
        return f"L_{addr:x}"

    # -- instructions ------------------------------------------------------

    def line(self, addr, mnem, ops, comment=""):
        """One instruction -> a C-ish statement (or None to skip silently)."""
        parts = self._split(ops)

        if "(%rip)" in ops and comment and mnem in ("lea", "leaq"):
            m = re.match(r"([0-9a-f]+)", comment)
            if m:                # objdump resolves rip-relative in its comment
                return (f"{self.operand(parts[1])} = "
                        f"&{self.imm('$0x' + m.group(1))};")

        # a held cmp/test fuses with the jcc(s)/setcc(s) that follow -- flags
        # persist across jumps and moves, and -O2 hangs SEVERAL jumps off one
        # test (test; js error; je road), so consuming does not clear it
        if mnem in JCC and self.pending_cmp:
            lhs, rhs, _ = self.pending_cmp
            self.pending_cmp = (lhs, rhs, True)
            cond = JCC[mnem]
            if cond in ("< 0", ">= 0"):
                return f"if ({lhs} {cond}) goto {self.target(parts[0])};"
            return f"if ({lhs} {cond} {rhs}) goto {self.target(parts[0])};"
        if mnem in SETCC and self.pending_cmp:
            lhs, rhs, _ = self.pending_cmp
            self.pending_cmp = (lhs, rhs, True)
            return (f"{self.operand(parts[0])} = "
                    f"({lhs} {SETCC[mnem]} {rhs});")

        if mnem in ("cmp", "cmpq", "cmpl", "cmpw", "cmpb",
                    "test", "testq", "testl", "testw", "testb"):
            a, b = parts
            size = WIDTH.get(mnem[-1], 8) if mnem not in ("cmp", "test") else 8
            if mnem.startswith("test") and a == b:
                self.pending_cmp = (self.operand(a, size), "0", False)
            else:                   # AT&T: cmp SRC,DST tests DST ? SRC
                self.pending_cmp = (self.operand(b, size),
                                    self.operand(a, size), False)
            return None

        # flag-neutral instructions carry the compare forward; anything else
        # clobbers it -- a compare no one consumed is surfaced once, honestly
        if self.pending_cmp and not mnem.startswith(
                ("mov", "lea", "push", "pop", "nop", "j")):
            lhs, rhs, used = self.pending_cmp
            self.pending_cmp = None
            if not used:
                rest = self.line(addr, mnem, ops, comment)
                return f"_flags = {lhs} - {rhs};" + ("\n" + rest if rest else "")

        if mnem.startswith("j"):
            if parts[0].startswith("*"):     # indirect (a PLT stub's jump)
                m = re.search(r"<([^>+]+?)(?:@plt)?>", ops)
                where = m.group(1) if m else self.operand(parts[0][1:])
                return f"goto *{where};"
            if mnem == "jmp":
                return f"goto {self.target(parts[0])};"
            return f"if ({mnem}) goto {self.target(parts[0])};"

        if mnem == "syscall":
            name = SYSCALLS.get(self.last_eax_imm)
            self.last_eax_imm = None
            self.consts.pop("rax", None)     # the return overwrites rax
            tag = f"        // {name}" if name else ""
            return f"rax = syscall(rax, rdi, rsi, rdx, r10, r8, r9);{tag}"

        if mnem in ("mov", "movq", "movl", "movw", "movb", "movabs", "movabsq"):
            src, dst = parts
            if mnem in ("mov", "movabs"):   # width from the register side
                size = min(reg_width(t) for t in (src, dst) if t.startswith("%")) \
                    if any(t.startswith("%") for t in (src, dst)) else 8
            else:
                size = WIDTH.get(mnem[-1], 8)
            src_c, dst_c = self.operand(src, size), self.operand(dst, size)
            # track constants through slots AND registers: -O0 spills the
            # syscall nr through a slot; -O3 moves it between registers
            dk, sk = canon(dst_c), canon(src_c)
            if src.startswith("$"):
                self.consts[dk] = int(src.lstrip("$"), 16 if "0x" in src else 10)
            elif sk in self.consts:
                self.consts[dk] = self.consts[sk]
            else:
                self.consts.pop(dk, None)
            if dk == "rax":
                self.last_eax_imm = self.consts.get("rax")
            return f"{dst_c} = {src_c};"
        if mnem in ("movzbl", "movzbq", "movzwl"):
            src, dst = parts
            return f"{self.operand(dst)} = {self.operand(src, WIDTH[mnem[4]])};"
        if mnem in ("movslq", "movsbl", "movsbq"):
            src, dst = parts
            return f"{self.operand(dst)} = (signed){self.operand(src, WIDTH[mnem[4]])};"
        if mnem in ("lea", "leaq"):
            src, dst = parts
            inner = self.operand(src, size=0)
            if inner.startswith("["):
                inner = inner[1:-1].split(" : ")[0]
                return f"{self.operand(dst)} = {inner};"
            return f"{self.operand(dst)} = &{inner};"

        BIN = {"add": "+", "sub": "-", "imul": "*", "and": "&", "or": "|",
               "xor": "^", "shl": "<<", "sal": "<<", "sar": ">>", "shr": "u>>"}
        base = mnem if mnem in BIN else (
            mnem[:-1] if mnem[:-1] in BIN and mnem[-1] in "qlwb" else mnem)
        if base in BIN and len(parts) == 2:
            src, dst = parts
            d, s = self.operand(dst), self.operand(src)
            if base == "xor" and s == d:
                self.consts[canon(d)] = 0
                if canon(d) == "rax":
                    self.last_eax_imm = 0
                return f"{d} = 0;"
            self.consts.pop(canon(d), None)
            return f"{d} {BIN[base]}= {s};"
        if base in BIN and len(parts) == 3:      # 3-operand imul
            a, b, dst = parts
            return (f"{self.operand(dst)} = "
                    f"{self.operand(b)} {BIN[base]} {self.operand(a)};")

        if mnem.startswith("cmov") and len(parts) == 2:
            cc = mnem[4:]
            cond = {"ns": ">= 0", "s": "< 0", "e": "== 0", "ne": "!= 0"}.get(cc, cc)
            return (f"if ({cond}) {self.operand(parts[1])} = "
                    f"{self.operand(parts[0])};")
        if base in ("imul", "mul") and len(parts) == 1:  # widening multiply
            return f"rdx:rax = rax * {self.operand(parts[0])};"
        if mnem in ("neg", "negq"):
            return f"{self.operand(parts[0])} = -{self.operand(parts[0])};"
        if mnem in ("not", "notq"):
            return f"{self.operand(parts[0])} = ~{self.operand(parts[0])};"
        if mnem in ("idiv", "idivq"):
            s = self.operand(parts[0])
            return f"rax = rdx:rax / {s};  rdx = rdx:rax % {s};"
        if mnem in ("cqto", "cqo"):
            return "rdx = sign(rax);"
        if mnem in ("cltq", "cdqe"):
            return "rax = (long)eax;"
        if mnem in ("call", "callq"):
            m = re.search(r"<([^>+]+?)(?:@plt)?>", ops)
            if m:
                callee = m.group(1)
            elif parts[0].startswith("*"):   # indirect call through a register
                callee = "*" + self.operand(parts[0][1:])
            else:
                callee = self.target(parts[0])
            self.consts.clear()              # a call clobbers everything
            self.last_eax_imm = None
            return f"rax = {callee}();"
        if mnem == "leave":
            return "// leave (rsp = rbp; pop rbp)"
        if mnem in ("push", "pop") or mnem.startswith(("push", "pop")):
            return f"// {mnem} {ops}"
        if mnem in ("ud2",):
            return "unreachable();"
        if mnem in ("nop", "nopw", "nopl", "endbr64", "cs", "data16"):
            return None
        if mnem == "ret":
            return "return;"

        return f"// {mnem} {ops}"           # anything unrecognized, verbatim

    @staticmethod
    def _split(ops):
        """Split operands on commas not inside parens."""
        parts, depth, cur = [], 0, ""
        for ch in ops:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if ch == "," and depth == 0:
                parts.append(cur)
                cur = ""
            else:
                cur += ch
        if cur:
            parts.append(cur)
        return parts

# ---------------------------------------------------------------- main

def main():
    args = [a for a in sys.argv[1:] if a not in ("--bare", "-b")]
    bare = len(args) < len(sys.argv) - 1     # --bare: statements and labels
    if not args:                             # only -- no addresses, no source
        sys.exit("usage: mereodis.py [--bare] BINARY [SOURCE.c]   "
                 "(build the binary with -g)")
    binary = args[0]
    source = args[1] if len(args) > 1 else None
    if bare:
        source = None

    vars_, labels, _pairs = dwarf_names(binary)
    if not vars_ and not labels:
        print(f"mereodis: warning: no DWARF slot names in {binary} "
              "(optimized libc code keeps values in registers)", file=sys.stderr)
    ro_base, ro_data = rodata(binary)
    insns, syms = instructions(binary)
    r = Renderer(vars_, labels, ro_base, ro_data, syms)
    r.insn_addrs = {a for a, _, _, _ in insns}

    srclines = None
    linemap = {}
    if source:
        srclines = open(source).read().splitlines()
        linemap = dwarf_lines(binary)

    # anchor lines for jump targets that carry no name of their own
    anon = set()
    for addr, mnem, ops, _ in insns:
        if mnem.startswith("j") and ops and not ops.startswith("*"):
            t = r.target(ops)
            if t.startswith("L_"):
                anon.add(int(t[2:], 16))

    last_src = None
    for addr, mnem, ops, comment in insns:
        if addr in syms:
            print(f"\n{syms[addr]}:")
        elif addr in labels:
            print(f"\n{labels[addr]}:")
        elif addr in anon:
            print(f"L_{addr:x}:")
        if source and addr in linemap:
            ln = linemap[addr]
            if ln != last_src and 0 < ln <= len(srclines):
                text = srclines[ln - 1].strip()
                if text and not text.startswith("//"):
                    print(f"                                        // {ln}: {text}")
                last_src = ln
        stmt = r.line(addr, mnem, ops, comment)
        if stmt:
            for s in stmt.split("\n"):
                if bare:
                    print(f"    {s}")
                else:
                    print(f"    {s:<60} // {addr:x}")


if __name__ == "__main__":
    main()
