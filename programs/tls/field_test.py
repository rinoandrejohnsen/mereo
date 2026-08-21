import sys, subprocess, os
sys.path.insert(0, os.path.dirname(__file__))
import x25519_ref as R
DIR = os.path.dirname(os.path.abspath(__file__))

def limb_init(buf, vals):   # 16 signed 8-byte limbs
    return "\n".join(f"  [{buf} + {i*8} : 8] is {v}" for i, v in enumerate(vals))
def limb_check(buf, vals):  # diff |= (limb XOR expected)
    out = []
    for i, v in enumerate(vals):
        out += [f"  v is [{buf} + {i*8} : 8]", f"  d is v ^ {v}", "  diff is diff | d"]
    return "\n".join(out)
def byte_init(buf, data):
    return "\n".join(f"  [{buf} + {i} : 1] is {b}" for i, b in enumerate(data))
def byte_check(buf, data):
    out = []
    for i, b in enumerate(data):
        out += [f"  v is [{buf} + {i} : 1]", f"  d is v ^ {b}", "  diff is diff | d"]
    return "\n".join(out)

def run(label, decls, init_str, call, check_str):
    prog = (f'include "field.mereo"\n\nprogram is\n{decls}\n  diff is 0\n  v is 0\n'
            f'  d is 0\n\n{init_str}\n\n{call}\n\n{check_str}\n  ensure diff == 0\n'
            f'  linux:exit\nend\n')
    src = f"{DIR}/_t_{label}.mereo"; open(src, "w").write(prog)
    c = subprocess.run(["python3", f"{DIR}/../../mereoc.py", src], capture_output=True, text=True)
    if c.returncode:
        print(f"  {label:10} TRANSPILE FAIL: {c.stderr.strip().splitlines()[-1]}"); os.remove(src); return False
    open(f"/tmp/mbuild/_t_{label}.c", "w").write(c.stdout)
    b = subprocess.run(["gcc","-O2","-fwrapv","-nostdlib","-static","-fno-stack-protector",
                        "-fno-tree-loop-distribute-patterns",   # no libc to call
                        "-fwhole-program",                      # one TU, no library
                        "-fno-strict-aliasing",                 # bits are bits
                        "-o",f"/tmp/mbuild/_t_{label}",f"/tmp/mbuild/_t_{label}.c"], capture_output=True, text=True)
    os.remove(src)
    if b.returncode:
        print(f"  {label:10} BUILD FAIL: {b.stderr.strip().splitlines()[-1]}"); return False
    ok = subprocess.run([f"/tmp/mbuild/_t_{label}"]).returncode == 0
    print(f"  {label:10} {'ok' if ok else 'MISMATCH'}"); return ok

gf = lambda: "  {} is 128 bytes"
a = [i*3000 + 7  for i in range(16)]
b = [i*2000 + 11 for i in range(16)]
ok = True

o=[0]*16; R.A(o,a,b); ok &= run("add", "  ao is 128 bytes\n  bo is 128 bytes\n  oo is 128 bytes",
    limb_init("ao",a)+"\n"+limb_init("bo",b), "  field.add (o is oo, a is ao, b is bo)", limb_check("oo",o))
o=[0]*16; R.Z(o,a,b); ok &= run("sub", "  ao is 128 bytes\n  bo is 128 bytes\n  oo is 128 bytes",
    limb_init("ao",a)+"\n"+limb_init("bo",b), "  field.sub (o is oo, a is ao, b is bo)", limb_check("oo",o))
p=list(a); q=list(b); R.sel(p,q,1); ok &= run("swap1", "  po is 128 bytes\n  qo is 128 bytes",
    limb_init("po",a)+"\n"+limb_init("qo",b), "  field.swap (p is po, q is qo, bit is 1)", limb_check("po",p)+"\n"+limb_check("qo",q))
co=[i*70000-30000 for i in range(16)]; cc=list(co); R.car(cc); ok &= run("carry", "  co is 128 bytes",
    limb_init("co",co), "  field.carry (o is co)", limb_check("co",cc))
o=[0]*16; R.M(o,a,b); ok &= run("mul", "  ao is 128 bytes\n  bo is 128 bytes\n  oo is 128 bytes",
    limb_init("ao",a)+"\n"+limb_init("bo",b), "  field.mul (o is oo, a is ao, b is bo)", limb_check("oo",o))
o=[0]*16; R.S(o,a); ok &= run("sqr", "  ao is 128 bytes\n  oo is 128 bytes",
    limb_init("ao",a), "  field.mul (o is oo, a is ao, b is ao)", limb_check("oo",o))
ainv=[i+1 for i in range(16)]; o=[0]*16; R.inv(o,ainv); ok &= run("inv", "  ao is 128 bytes\n  oo is 128 bytes",
    limb_init("ao",ainv), "  field.invert (o is oo, a is ao)", limb_check("oo",o))
nb=list(range(32)); o=[0]*16; R.unpack(o,nb); ok &= run("unpack", "  no is 32 bytes\n  oo is 128 bytes",
    byte_init("no",nb), "  field.unpack (o is oo, n is no)", limb_check("oo",o))
g=[i*1234+5 for i in range(16)]; ob=[0]*32; R.pack(ob,g); ok &= run("pack", "  go is 128 bytes\n  ob is 32 bytes",
    limb_init("go",g), "  field.pack (o is ob, n is go)", byte_check("ob",ob))
print("ALL FIELD OPS OK" if ok else "SOME FAILED")
PY = None
