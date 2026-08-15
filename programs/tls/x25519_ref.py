# Reference gf ops, transcribed from crypto.h++ detail::. i64 semantics hold in
# Python for the bounded values TweetNaCl produces (no i64 overflow).
def car(o):
    for i in range(16):
        o[i] += (1 << 16); c = o[i] >> 16
        o[(i+1) * (1 if i < 15 else 0)] += c - 1 + 37*(c-1)*(1 if i == 15 else 0)
        o[i] -= c << 16
def sel(p, q, b):
    c = ~(b - 1)
    for i in range(16):
        t = c & (p[i] ^ q[i]); p[i] ^= t; q[i] ^= t
def A(o,a,b):
    for i in range(16): o[i] = a[i] + b[i]
def Z(o,a,b):
    for i in range(16): o[i] = a[i] - b[i]
def M(o,a,b):
    t = [0]*31
    for i in range(16):
        for j in range(16): t[i+j] += a[i]*b[j]
    for i in range(15): t[i] += 38*t[i+16]
    for i in range(16): o[i] = t[i]
    car(o); car(o)
def S(o,a): M(o,a,a)
def inv(o,inp):
    c = inp[:]
    for a in range(253, -1, -1):
        S(c,c)
        if a != 2 and a != 4: M(c,c,inp)
    for a in range(16): o[a] = c[a]
def unpack(o,n):
    for i in range(16): o[i] = n[2*i] + (n[2*i+1] << 8)
    o[15] &= 0x7fff
def pack(o,n):
    t = n[:]; car(t); car(t); car(t)
    for _ in range(2):
        m = [0]*16
        m[0] = t[0] - 0xffed
        for i in range(1,15):
            m[i] = t[i] - 0xffff - ((m[i-1] >> 16) & 1); m[i-1] &= 0xffff
        m[15] = t[15] - 0x7fff - ((m[14] >> 16) & 1)
        b = (m[15] >> 16) & 1; m[14] &= 0xffff
        sel(t, m, 1 - b)
    for i in range(16):
        o[2*i] = t[i] & 0xff; o[2*i+1] = (t[i] >> 8) & 0xff
def x25519(scalar, point):
    z = list(scalar); z[31] = (z[31] & 127) | 64; z[0] &= 248
    x = [0]*16; unpack(x, point)
    a=[0]*16; b=list(x); c=[0]*16; d=[0]*16; e=[0]*16; f=[0]*16
    a[0]=d[0]=1
    _121665=[0xDB41,1]+[0]*14
    for i in range(254, -1, -1):
        r = (z[i>>3] >> (i&7)) & 1
        sel(a,b,r); sel(c,d,r)
        A(e,a,c); Z(a,a,c); A(c,b,d); Z(b,b,d)
        S(d,e); S(f,a); M(a,c,a); M(c,b,e); A(e,a,c); Z(a,a,c)
        S(b,a); Z(c,d,f); M(a,c,_121665); A(a,a,d); M(c,c,a); M(a,d,f); M(d,b,x); S(b,e)
        sel(a,b,r); sel(c,d,r)
    inv(c, c); M(a, a, c)
    out = [0]*32; pack(out, a); return bytes(out)
if __name__ == "__main__":
    sc = bytes.fromhex("a546e36bf0527c9d3b16154b82465edd62144c0ac1fc5a18506a2244ba449ac4")
    pt = bytes.fromhex("e6db6867583030db3594c1a424b15f7c726624ec26b3353b10a903a6d0ab1c4c")
    got = x25519(sc, pt).hex()
    exp = "c3da55379de9c6908e94ea4df28d084f32eccf03491c71f754b4075577a28552"
    print("x25519 =", got)
    print("expect =", exp)
    print("REFERENCE OK" if got == exp else "REFERENCE WRONG")
