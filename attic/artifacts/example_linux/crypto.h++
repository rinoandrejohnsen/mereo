// crypto.h++ : TLS 1.3 crypto primitives via the Linux kernel crypto API (AF_ALG).
//
// The kernel does the actual algorithm work (hash/HMAC); we build the TLS 1.3
// key schedule (HKDF + HKDF-Expand-Label, RFC 5869 / RFC 8446 S7.1) on top in
// plain code. Freestanding, no libc, no exceptions -- same regime as linux.h++.
//
// NB: this is a learning implementation. It is fine for the key schedule (which
// is just HMAC), but the larger TLS client it feeds into is NOT production-grade,
// especially certificate validation.
# pragma once

# include "linux.h++"

namespace linux::crypto {

  constexpr long AF_ALG = 38, SOCK_SEQPACKET = 5, SOL_ALG = 279, ALG_SET_KEY = 1;

  struct sockaddr_alg {
    unsigned short salg_family;
    unsigned char  salg_type[14];
    unsigned int   salg_feat;
    unsigned int   salg_mask;
    unsigned char  salg_name[64];
  };

  inline void cstr_copy (unsigned char* d, const char* s) { while (*s) *d++ = (unsigned char) *s++; }

  // One-shot (optionally keyed) hash over the kernel crypto API. `name` is a
  // kernel algorithm, e.g. "sha256" or "hmac(sha256)". Returns digest length, or
  // -errno. The transform/op sockets are RAII-closed on return.
  inline long hash (const char* name,
                    const void* key, unsigned long key_len,
                    const void* data, unsigned long data_len,
                    void* out, unsigned long out_len) {
    file_descriptor tfm (call (calls::socket, AF_ALG, SOCK_SEQPACKET, 0L));
    if (! tfm.ok ()) return tfm.get ();

    sockaddr_alg sa {};
    sa.salg_family = AF_ALG;
    cstr_copy (sa.salg_type, "hash");
    cstr_copy (sa.salg_name, name);
    long r = call (calls::bind, tfm.get (), &sa, sizeof sa);
    if (failed (r)) return r;

    if (key) {
      r = call (calls::setsockopt, tfm.get (), SOL_ALG, ALG_SET_KEY, key, key_len);
      if (failed (r)) return r;
    }

    file_descriptor op (call (calls::accept, tfm.get (), 0L, 0L));
    if (! op.ok ()) return op.get ();

    r = call (calls::write, op.get (), data, data_len);   // single complete message -> finalizes
    if (failed (r)) return r;
    return call (calls::read, op.get (), out, out_len);
  }

  inline long sha256 (const void* data, unsigned long len, unsigned char out[32]) {
    return hash ("sha256", nullptr, 0, data, len, out, 32);
  }
  inline long hmac_sha256 (const void* key, unsigned long key_len,
                           const void* data, unsigned long len, unsigned char out[32]) {
    return hash ("hmac(sha256)", key, key_len, data, len, out, 32);
  }

  // -- HKDF (RFC 5869), SHA-256 --------------------------------------------------
  // HKDF-Extract(salt, IKM) = HMAC(salt, IKM). A null salt means a string of
  // HashLen zero bytes (the TLS 1.3 convention).
  inline void hkdf_extract (const void* salt, unsigned long salt_len,
                            const void* ikm, unsigned long ikm_len, unsigned char prk[32]) {
    unsigned char zero[32] = {};
    if (! salt) { salt = zero; salt_len = 32; }
    hmac_sha256 (salt, salt_len, ikm, ikm_len, prk);
  }

  // HKDF-Expand(PRK, info, L): T(i) = HMAC(PRK, T(i-1) | info | i).
  inline void hkdf_expand (const unsigned char prk[32],
                           const void* info, unsigned long info_len,
                           unsigned char* out, unsigned long out_len) {
    unsigned char t[32];
    unsigned long t_len = 0, done = 0;
    unsigned char counter = 1;
    while (done < out_len) {
      unsigned char buf[32 + 512 + 1];     // T(i-1) | info | counter  (info kept small)
      unsigned long p = 0;
      for (unsigned long i = 0; i < t_len; ++i)    buf[p++] = t[i];
      for (unsigned long i = 0; i < info_len; ++i) buf[p++] = ((const unsigned char*) info)[i];
      buf[p++] = counter;
      hmac_sha256 (prk, 32, buf, p, t);
      t_len = 32;
      unsigned long take = (out_len - done < 32) ? out_len - done : 32;
      for (unsigned long i = 0; i < take; ++i) out[done + i] = t[i];
      done += take;
      ++counter;
    }
  }

  // HKDF-Expand-Label (RFC 8446 S7.1):
  //   HkdfLabel = uint16 length | "tls13 "+label (1-byte len-prefixed)
  //                              | context        (1-byte len-prefixed)
  inline void hkdf_expand_label (const unsigned char secret[32], const char* label,
                                 const void* context, unsigned long context_len,
                                 unsigned char* out, unsigned long out_len) {
    unsigned char hl[2 + 1 + 255 + 1 + 255];
    unsigned long p = 0;
    hl[p++] = (unsigned char) (out_len >> 8);
    hl[p++] = (unsigned char) (out_len);
    unsigned long label_len = 0; while (label[label_len]) ++label_len;
    hl[p++] = (unsigned char) (6 + label_len);
    cstr_copy (hl + p, "tls13 "); p += 6;
    for (unsigned long i = 0; i < label_len; ++i) hl[p++] = (unsigned char) label[i];
    hl[p++] = (unsigned char) context_len;
    for (unsigned long i = 0; i < context_len; ++i) hl[p++] = ((const unsigned char*) context)[i];
    hkdf_expand (secret, hl, p, out, out_len);
  }

  // -- X25519 (Curve25519 ECDH, RFC 7748) ---------------------------------------
  // The kernel's kpp only registers ECDH-NIST (P-192/256/384), not curve25519, so
  // X25519 -- the group TLS 1.3 prefers -- is done here. Field arithmetic is
  // transcribed from TweetNaCl (Bernstein et al., public domain): 16 limbs of
  // radix 2^16 in i64. Compact and correct; not the fastest, fine for a handshake.
  namespace detail {
    using i64 = long long;
    using gf  = i64[16];

    inline void car (gf o) {
      for (int i=0;i<16;i++) { o[i] += (1LL<<16); i64 c = o[i]>>16;
        o[(i+1)*(i<15)] += c - 1 + 37*(c-1)*(i==15); o[i] -= c<<16; }
    }
    inline void sel (gf p, gf q, int b) {
      i64 c = ~((i64)b - 1);
      for (int i=0;i<16;i++) { i64 t = c & (p[i]^q[i]); p[i]^=t; q[i]^=t; }
    }
    inline void A (gf o, const gf a, const gf b) { for(int i=0;i<16;i++) o[i]=a[i]+b[i]; }
    inline void Z (gf o, const gf a, const gf b) { for(int i=0;i<16;i++) o[i]=a[i]-b[i]; }
    inline void M (gf o, const gf a, const gf b) {
      i64 t[31]; for(int i=0;i<31;i++) t[i]=0;
      for(int i=0;i<16;i++) for(int j=0;j<16;j++) t[i+j]+=a[i]*b[j];
      for(int i=0;i<15;i++) t[i]+=38*t[i+16];
      for(int i=0;i<16;i++) o[i]=t[i];
      car(o); car(o);
    }
    inline void S (gf o, const gf a) { M(o,a,a); }
    inline void inv (gf o, const gf in) {
      gf c; for(int a=0;a<16;a++) c[a]=in[a];
      for(int a=253;a>=0;a--){ S(c,c); if(a!=2&&a!=4) M(c,c,in); }
      for(int a=0;a<16;a++) o[a]=c[a];
    }
    inline void unpack (gf o, const unsigned char* n) {
      for(int i=0;i<16;i++) o[i]=n[2*i]+((i64)n[2*i+1]<<8);
      o[15]&=0x7fff;
    }
    inline void pack (unsigned char* o, const gf n) {
      gf m,t; for(int i=0;i<16;i++) t[i]=n[i];
      car(t); car(t); car(t);
      for(int j=0;j<2;j++){
        m[0]=t[0]-0xffed;
        for(int i=1;i<15;i++){ m[i]=t[i]-0xffff-((m[i-1]>>16)&1); m[i-1]&=0xffff; }
        m[15]=t[15]-0x7fff-((m[14]>>16)&1);
        int b=(int)((m[15]>>16)&1); m[14]&=0xffff;
        sel(t,m,1-b);
      }
      for(int i=0;i<16;i++){ o[2*i]=(unsigned char)(t[i]&0xff); o[2*i+1]=(unsigned char)((t[i]>>8)&0xff); }
    }
  }

  // out = scalar * point  (all 32-byte little-endian; RFC 7748 X25519).
  inline void x25519 (unsigned char out[32], const unsigned char scalar[32], const unsigned char point[32]) {
    using namespace detail;
    unsigned char z[32]; i64 x[80];
    for(int i=0;i<31;i++) z[i]=scalar[i];
    z[31]=(scalar[31]&127)|64; z[0]&=248;
    unpack(x, point);
    gf a,b,c,d,e,f, _121665={0xDB41,1};
    for(int i=0;i<16;i++){ b[i]=x[i]; d[i]=a[i]=c[i]=0; }
    a[0]=d[0]=1;
    for(int i=254;i>=0;--i){
      i64 r=(z[i>>3]>>(i&7))&1;
      sel(a,b,(int)r); sel(c,d,(int)r);
      A(e,a,c); Z(a,a,c); A(c,b,d); Z(b,b,d);
      S(d,e); S(f,a); M(a,c,a); M(c,b,e); A(e,a,c); Z(a,a,c);
      S(b,a); Z(c,d,f); M(a,c,_121665); A(a,a,d); M(c,c,a); M(a,d,f); M(d,b,x); S(b,e);
      sel(a,b,(int)r); sel(c,d,(int)r);
    }
    for(int i=0;i<16;i++){ x[i+16]=a[i]; x[i+32]=c[i]; x[i+48]=b[i]; x[i+64]=d[i]; }
    inv(x+32, x+32);
    M(x+16, x+16, x+32);
    pack(out, x+16);
  }

  // Public key for a private scalar: X25519(scalar, basepoint=9).
  inline void x25519_base (unsigned char out[32], const unsigned char scalar[32]) {
    unsigned char base[32]={}; base[0]=9;
    x25519(out, scalar, base);
  }

  // -- AES-GCM (the TLS 1.3 record cipher) via AF_ALG aead/gcm(aes) --------------
  // The AEAD interface is sendmsg-with-control-messages: ALG_SET_OP (enc/dec),
  // ALG_SET_IV (nonce) and ALG_SET_AEAD_ASSOCLEN (AAD length). Input and output
  // are both AAD-prefixed: send AAD||data, receive AAD||result, so we split the
  // AAD back off on the way out.
  namespace aead_detail {
    struct iovec  { void* base; unsigned long len; };
    struct msghdr {
      void* name; unsigned int namelen;
      iovec* iov; unsigned long iovlen;
      void* control; unsigned long controllen;
      unsigned int flags;
    };
    constexpr int ALG_SET_IV = 2, ALG_SET_OP = 3, ALG_SET_AEAD_ASSOCLEN = 4, ALG_SET_AEAD_AUTHSIZE = 5;
    constexpr unsigned int ALG_OP_DECRYPT = 0, ALG_OP_ENCRYPT = 1;
    inline void put32 (unsigned char* p, unsigned int v){ for(int i=0;i<4;i++) p[i]=(unsigned char)(v>>(8*i)); }
    inline void put64 (unsigned char* p, unsigned long v){ for(int i=0;i<8;i++) p[i]=(unsigned char)(v>>(8*i)); }
  }

  // encrypt: in = plaintext (in_len)        -> out = ciphertext||tag (in_len+16)
  // decrypt: in = ciphertext||tag (in_len)  -> out = plaintext (in_len-16);
  //          returns -errno (e.g. -EBADMSG) if the tag does not verify.
  // Returns bytes written to out, or -errno.
  inline long aes_gcm (bool encrypt,
                       const unsigned char* key, unsigned long key_len,    // 16 (AES-128) or 32
                       const unsigned char* iv,  unsigned long iv_len,     // 12
                       const unsigned char* aad, unsigned long aad_len,
                       const unsigned char* in,  unsigned long in_len,
                       unsigned char* out, unsigned long /*out_cap*/) {
    using namespace aead_detail;
    if (aad_len > 240 || iv_len > 16) return -22;   // -EINVAL: keep cmsg sizing bounded

    file_descriptor tfm (call (calls::socket, AF_ALG, SOCK_SEQPACKET, 0L));
    if (! tfm.ok ()) return tfm.get ();
    sockaddr_alg sa {};
    sa.salg_family = AF_ALG;
    cstr_copy (sa.salg_type, "aead");
    cstr_copy (sa.salg_name, "gcm(aes)");
    long r = call (calls::bind, tfm.get (), &sa, sizeof sa);                          if (failed(r)) return r;
    r = call (calls::setsockopt, tfm.get (), SOL_ALG, ALG_SET_KEY, key, key_len);     if (failed(r)) return r;
    r = call (calls::setsockopt, tfm.get (), SOL_ALG, ALG_SET_AEAD_AUTHSIZE, (void*)nullptr, 16L); if (failed(r)) return r;

    file_descriptor op (call (calls::accept, tfm.get (), 0L, 0L));
    if (! op.ok ()) return op.get ();

    // Control buffer: cmsghdr is {u64 len; int level; int type} = 16 bytes, then
    // data, each cmsg CMSG_ALIGN(8)-padded. msg_control must be 8-aligned.
    alignas (8) unsigned char cbuf[24 + 32 + 24] = {};
    unsigned long off = 0;
    auto hdr = [&] (unsigned long datalen, int type) -> unsigned char* {
      unsigned char* c = cbuf + off;
      put64 (c, 16 + datalen);
      put32 (c + 8,  (unsigned int) SOL_ALG);
      put32 (c + 12, (unsigned int) type);
      off += 16 + ((datalen + 7) & ~7UL);
      return c + 16;
    };
    put32 (hdr (4, ALG_SET_OP), encrypt ? ALG_OP_ENCRYPT : ALG_OP_DECRYPT);
    { unsigned char* d = hdr (4 + iv_len, ALG_SET_IV);            // struct af_alg_iv
      put32 (d, (unsigned int) iv_len);
      for (unsigned long i=0;i<iv_len;i++) d[4+i]=iv[i]; }
    put32 (hdr (4, ALG_SET_AEAD_ASSOCLEN), (unsigned int) aad_len);

    iovec siov[2] = { {(void*)aad, aad_len}, {(void*)in, in_len} };   // send AAD || in
    msghdr sm {}; sm.iov = aad_len ? siov : siov + 1; sm.iovlen = aad_len ? 2 : 1;
    sm.control = cbuf; sm.controllen = off;
    r = call (calls::sendmsg, op.get (), &sm, 0L);
    if (failed(r)) return r;

    unsigned char aad_scratch[256];
    long expect = encrypt ? (long) in_len + 16 : (long) in_len - 16;
    if (expect < 0) return -22;
    iovec riov[2] = { {aad_scratch, aad_len}, {out, (unsigned long) expect} };   // recv AAD || out
    msghdr rm {}; rm.iov = aad_len ? riov : riov + 1; rm.iovlen = aad_len ? 2 : 1;
    long got = call (calls::recvmsg, op.get (), &rm, 0L);
    if (failed(got)) return got;
    return got - (long) aad_len;
  }
}
