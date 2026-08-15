// tls.h++ : the TLS 1.3 protocol layer, built on crypto.h++ primitives.
//
// Increment 4 -- the key schedule (RFC 8446 S7.1). Given the X25519 shared secret
// and the running transcript hashes, derive every secret/key/IV the handshake and
// record layers need. Pure HKDF on already-verified primitives; checked against
// the RFC 8448 worked example.
//
// Learning implementation -- see crypto.h++.
# pragma once

# include "crypto.h++"

namespace linux::tls {

  // Derive-Secret(Secret, Label, Messages)
  //   = HKDF-Expand-Label(Secret, Label, Transcript-Hash(Messages), Hash.length)
  inline void derive_secret (const unsigned char secret[32], const char* label,
                             const unsigned char transcript_hash[32], unsigned char out[32]) {
    crypto::hkdf_expand_label (secret, label, transcript_hash, 32, out, 32);
  }

  // Per-record traffic key / nonce, and the Finished MAC key, from a traffic
  // secret (RFC 8446 S7.3): all HKDF-Expand-Label with an empty context.
  inline void traffic_key (const unsigned char secret[32], unsigned char key[16]) {
    crypto::hkdf_expand_label (secret, "key", nullptr, 0, key, 16);   // AES-128
  }
  inline void traffic_iv (const unsigned char secret[32], unsigned char iv[12]) {
    crypto::hkdf_expand_label (secret, "iv", nullptr, 0, iv, 12);
  }
  inline void finished_key (const unsigned char secret[32], unsigned char out[32]) {
    crypto::hkdf_expand_label (secret, "finished", nullptr, 0, out, 32);
  }

  // The full schedule (no-PSK). Filled in three steps as the handshake advances.
  struct key_schedule {
    unsigned char early[32], handshake[32], master[32];
    unsigned char c_hs[32], s_hs[32];   // client/server handshake traffic secrets
    unsigned char c_ap[32], s_ap[32];   // client/server application traffic secrets

    // Step 1 (before any message): Early-Secret = HKDF-Extract(0, 0).
    void init () {
      unsigned char zeros[32] = {};
      crypto::hkdf_extract (nullptr, 0, zeros, 32, early);
    }

    // Step 2 (after ServerHello): mix in the ECDHE shared secret to get the
    // Handshake-Secret, then the two handshake traffic secrets from the
    // ClientHello..ServerHello transcript hash.
    void set_handshake (const unsigned char ecdhe[32], const unsigned char th_ch_sh[32]) {
      unsigned char empty[32], derived[32];
      crypto::sha256 ("", 0, empty);
      derive_secret (early, "derived", empty, derived);
      crypto::hkdf_extract (derived, 32, ecdhe, 32, handshake);
      derive_secret (handshake, "c hs traffic", th_ch_sh, c_hs);
      derive_secret (handshake, "s hs traffic", th_ch_sh, s_hs);
    }

    // Step 3 (after server Finished): Master-Secret, then the application traffic
    // secrets from the ClientHello..server-Finished transcript hash.
    void set_application (const unsigned char th_ch_sf[32]) {
      unsigned char empty[32], derived[32], zeros[32] = {};
      crypto::sha256 ("", 0, empty);
      derive_secret (handshake, "derived", empty, derived);
      crypto::hkdf_extract (derived, 32, zeros, 32, master);
      derive_secret (master, "c ap traffic", th_ch_sf, c_ap);
      derive_secret (master, "s ap traffic", th_ch_sf, s_ap);
    }
  };

  // -- wire format: writer / reader, records, ClientHello, ServerHello ----------
  // TLS structures are length-prefixed; we reserve a length with mark*(), write
  // the content, then back-patch with patch*(). Writes past `cap` are counted but
  // dropped, so len > cap signals overflow.
  struct writer {
    unsigned char* buf; unsigned long cap; unsigned long len = 0;
    void byte (unsigned v)               { if (len < cap) buf[len] = (unsigned char) v; ++len; }
    void u16  (unsigned v)               { byte(v>>8); byte(v); }
    void u24  (unsigned long v)          { byte(v>>16); byte(v>>8); byte(v); }
    void raw  (const void* p, unsigned long n){ for(unsigned long i=0;i<n;i++) byte(((const unsigned char*)p)[i]); }
    unsigned long mark16 () { unsigned long at=len; u16(0);  return at; }
    unsigned long mark24 () { unsigned long at=len; u24(0);  return at; }
    void patch16 (unsigned long at){ unsigned long n=len-at-2; if(at+1<cap){ buf[at]=(unsigned char)(n>>8); buf[at+1]=(unsigned char)n; } }
    void patch24 (unsigned long at){ unsigned long n=len-at-3; if(at+2<cap){ buf[at]=(unsigned char)(n>>16); buf[at+1]=(unsigned char)(n>>8); buf[at+2]=(unsigned char)n; } }
  };

  struct reader {
    const unsigned char* p; unsigned long n; unsigned long pos = 0; bool err = false;
    unsigned byte (){ if(pos>=n){err=true;return 0;} return p[pos++]; }
    unsigned u16 (){ unsigned a=byte(),b=byte(); return (a<<8)|b; }
    unsigned long u24 (){ unsigned long a=byte(),b=byte(),c=byte(); return (a<<16)|(b<<8)|c; }
    const unsigned char* take (unsigned long k){ if(pos+k>n){err=true;return nullptr;} const unsigned char* r=p+pos; pos+=k; return r; }
    void skip (unsigned long k){ if(pos+k>n){ err=true; return; } pos+=k; }
  };

  // Serialize a ClientHello *handshake message* (msg_type|len|body) -- this is
  // what feeds the transcript. Wrap it in record() to put it on the wire.
  inline void client_hello_message (writer& w, const unsigned char random[32],
                                    const unsigned char session_id[32],
                                    const unsigned char pubkey[32], const char* host) {
    w.byte (1);                                   // ClientHello
    unsigned long hs = w.mark24 ();
      w.u16 (0x0303);                             // legacy_version
      w.raw (random, 32);
      w.byte (32); w.raw (session_id, 32);        // legacy_session_id (compat)
      w.u16 (2); w.u16 (0x1301);                  // cipher_suites: TLS_AES_128_GCM_SHA256
      w.byte (1); w.byte (0);                     // compression: null
      unsigned long ex = w.mark16 ();
        w.u16 (0x002b); { unsigned long e=w.mark16(); w.byte(2); w.u16(0x0304); w.patch16(e); }   // supported_versions: TLS 1.3
        w.u16 (0x000a); { unsigned long e=w.mark16(); w.u16(2); w.u16(0x001d); w.patch16(e); }    // supported_groups: x25519
        w.u16 (0x000d); { unsigned long e=w.mark16(); w.u16(4); w.u16(0x0403); w.u16(0x0804); w.patch16(e); } // sig algs
        w.u16 (0x0033); { unsigned long e=w.mark16();                                              // key_share
            unsigned long ks=w.mark16(); w.u16(0x001d); w.u16(32); w.raw(pubkey,32); w.patch16(ks); w.patch16(e); }
        w.u16 (0x0000); { unsigned long e=w.mark16();                                              // server_name (SNI)
            unsigned long list=w.mark16(); w.byte(0); unsigned long nm=w.mark16();
            unsigned long hl=0; while(host[hl]) ++hl; w.raw(host,hl);
            w.patch16(nm); w.patch16(list); w.patch16(e); }
        w.u16 (0x0010); { unsigned long e=w.mark16();                                              // ALPN: http/1.1
            unsigned long list=w.mark16(); w.byte(8); w.raw("http/1.1",8); w.patch16(list); w.patch16(e); }
      w.patch16 (ex);
    w.patch24 (hs);
  }

  // Wrap a fragment in a TLSPlaintext record (type: 22 handshake, 23 app data).
  inline void record (writer& w, unsigned type, const unsigned char* frag, unsigned long n) {
    w.byte (type); w.u16 (0x0303);
    unsigned long L = w.mark16 (); w.raw (frag, n); w.patch16 (L);
  }

  struct server_hello {
    bool ok = false;
    unsigned cipher_suite = 0;
    unsigned char key_share[32] = {};   // server's x25519 public key
  };

  // Parse a ServerHello *handshake message* (msg_type 2 + length + body).
  inline server_hello parse_server_hello (const unsigned char* msg, unsigned long n) {
    server_hello sh;
    reader r { msg, n };
    if (r.byte() != 2) return sh;          // ServerHello
    r.u24();                               // length
    r.u16();                               // legacy_version
    r.skip (32);                           // random
    unsigned sid = r.byte(); r.skip (sid); // session_id echo
    sh.cipher_suite = r.u16();
    r.byte();                              // legacy_compression_method
    unsigned ext_len = r.u16();
    unsigned long end = r.pos + ext_len;
    while (r.pos < end && ! r.err) {
      unsigned et = r.u16(); unsigned el = r.u16();
      unsigned long next = r.pos + el;
      if (next > n) { r.err = true; break; }
      if (et == 0x0033) {                  // key_share: group | key<2>
        unsigned grp = r.u16(); unsigned kl = r.u16();
        if (grp == 0x001d && kl == 32) { const unsigned char* k = r.take(32); if (k) for(int i=0;i<32;i++) sh.key_share[i]=k[i]; }
      }
      r.pos = next;                        // advance to next extension
    }
    sh.ok = ! r.err;
    return sh;
  }

  // -- record protection (RFC 8446 S5.2/5.3) -----------------------------------
  // Per-record nonce: the 12-byte static IV XOR the record sequence number,
  // right-aligned and big-endian.
  inline void record_nonce (const unsigned char iv[12], unsigned long long seq, unsigned char nonce[12]) {
    for (int i=0;i<12;i++) nonce[i] = iv[i];
    for (int i=0;i<8;i++)  nonce[11-i] ^= (unsigned char) (seq >> (8*i));
  }

  // Seal: `pt` is inner_content||inner_type. Writes header||ciphertext||tag into
  // `out`; AAD is that 5-byte header. Returns record length or -errno.
  inline long seal_record (const unsigned char key[16], const unsigned char iv[12], unsigned long long seq,
                           const unsigned char* pt, unsigned long pt_len, unsigned char* out, unsigned long cap) {
    unsigned long ct_len = pt_len + 16;
    out[0]=23; out[1]=0x03; out[2]=0x03; out[3]=(unsigned char)(ct_len>>8); out[4]=(unsigned char)ct_len;
    unsigned char nonce[12]; record_nonce (iv, seq, nonce);
    long n = crypto::aes_gcm (true, key,16, nonce,12, out,5, pt,pt_len, out+5, cap-5);
    return failed(n) ? n : 5 + n;
  }

  // Open: `rec` = full received record (header||ct||tag). Writes
  // inner_content||inner_type into `out`; returns inner length, or -errno
  // (including AEAD authentication failure). The header is the AAD.
  inline long open_record (const unsigned char key[16], const unsigned char iv[12], unsigned long long seq,
                           const unsigned char* rec, unsigned long rec_len, unsigned char* out, unsigned long cap) {
    if (rec_len < 5 + 16) return -22;
    unsigned char nonce[12]; record_nonce (iv, seq, nonce);
    return crypto::aes_gcm (false, key,16, nonce,12, rec,5, rec+5, rec_len-5, out, cap);
  }

  // The inner content type is the last non-zero byte (TLS 1.3 zero-pads after it).
  // Returns the content length (the type byte and padding stripped); *type set.
  inline unsigned long inner_content (unsigned char* p, unsigned long n, unsigned* type) {
    while (n > 0 && p[n-1] == 0) --n;
    if (n == 0) { *type = 0; return 0; }
    *type = p[n-1];
    return n - 1;
  }

  // -- transcript hash ----------------------------------------------------------
  // Running concatenation of handshake messages (no record headers); SHA-256 on
  // demand gives Transcript-Hash at any point.
  struct transcript {
    unsigned char data[16384];
    unsigned long len = 0;
    void add (const unsigned char* p, unsigned long n){ for(unsigned long i=0;i<n;i++) if(len<sizeof data) data[len++]=p[i]; }
    void hash (unsigned char out[32]) const { crypto::sha256 (data, len, out); }
  };

  // Finished verify_data = HMAC(finished_key(secret), Transcript-Hash) (S4.4.4).
  inline void finished_mac (const unsigned char traffic_secret[32],
                            const unsigned char transcript_hash[32], unsigned char out[32]) {
    unsigned char fk[32]; finished_key (traffic_secret, fk);
    crypto::hmac_sha256 (fk, 32, transcript_hash, 32, out);
  }

  // KTLS key material: struct tls12_crypto_info_aes_gcm_128 (from <linux/tls.h>).
  // The 12-byte TLS 1.3 static IV is split as salt(4)||iv(8); rec_seq is the
  // starting record sequence number (0 for a fresh epoch).
  struct ktls_aes_gcm_128 {
    unsigned short version, cipher_type;        // TLS_1_3_VERSION (0x0304), TLS_CIPHER_AES_GCM_128 (51)
    unsigned char iv[8], key[16], salt[4], rec_seq[8];
  };

  // -- client : drive a full TLS 1.3 handshake + app records over a socket fd ---
  //
  // WARNING: this does NOT validate the server certificate (deferred to a later
  // increment). It verifies the server Finished -- proving the peer completed the
  // ECDHE -- but with no cert check there is no authentication: an active MITM is
  // not detected. Use only against trusted endpoints / for learning.
  struct client {
    long fd = -1;
    key_schedule ks;
    transcript tr;
    unsigned char priv[32], pub[32];
    unsigned char chk[16], chiv[12], shk[16], shiv[12];   // handshake traffic keys
    unsigned char cak[16], caiv[12], sak[16], saiv[12];   // application traffic keys
    unsigned long long cseq = 0, sseq = 0;
    bool ktls = false;                 // true once the kernel TLS record layer is active
    long ktls_err = 0;                 // -errno of the failing KTLS setsockopt (debug)

    bool read_n (unsigned char* p, unsigned long n) {
      for (unsigned long got=0; got<n; ) { long r = call(calls::read, fd, p+got, n-got); if (r<=0) return false; got += (unsigned long)r; }
      return true;
    }
    bool write_n (const unsigned char* p, unsigned long n) {
      for (unsigned long s=0; s<n; ) { long r = call(calls::write, fd, p+s, n-s); if (r<=0) return false; s += (unsigned long)r; }
      return true;
    }
    long read_record (unsigned char* rec, unsigned long cap) {       // -> full record length
      if (! read_n (rec, 5)) return -1;
      unsigned long blen = ((unsigned long)rec[3]<<8) | rec[4];
      if (5+blen > cap) return -1;
      if (! read_n (rec+5, blen)) return -1;
      return (long)(5+blen);
    }

    // Hand the application keys to the kernel's TLS ULP. Afterwards the kernel
    // performs all record AES-GCM / framing / sequencing, and write_app/read_app
    // become plain write()/recvmsg(). Returns 0 if KTLS is active, <0 otherwise.
    int setup_ktls () {
      long r = call (calls::setsockopt, fd, 6 /*SOL_TCP*/, 31 /*TCP_ULP*/, "tls", 4L);
      if (failed (r)) { ktls_err = r; return -1; }
      ktls_aes_gcm_128 info {};
      info.version = 0x0304; info.cipher_type = 51;               // TLS 1.3, AES-128-GCM
      for (int i=0;i<4;i++)  info.salt[i] = caiv[i];              // TX: client app keys
      for (int i=0;i<8;i++)  info.iv[i]   = caiv[4+i];
      for (int i=0;i<16;i++) info.key[i]  = cak[i];
      r = call (calls::setsockopt, fd, 282 /*SOL_TLS*/, 1 /*TLS_TX*/, &info, (long) sizeof info);
      if (failed (r)) { ktls_err = r; return -2; }
      for (int i=0;i<4;i++)  info.salt[i] = saiv[i];              // RX: server app keys
      for (int i=0;i<8;i++)  info.iv[i]   = saiv[4+i];
      for (int i=0;i<16;i++) info.key[i]  = sak[i];
      r = call (calls::setsockopt, fd, 282, 2 /*TLS_RX*/, &info, (long) sizeof info);
      if (failed (r)) { ktls_err = r; return -3; }
      return 0;
    }

    // Returns 0 on success (server Finished verified), negative on error.
    int handshake (const char* host, const unsigned char client_random[32],
                   const unsigned char session_id[32], const unsigned char ephemeral_priv[32]) {
      for (int i=0;i<32;i++) priv[i]=ephemeral_priv[i];
      crypto::x25519_base (pub, priv);
      ks.init ();                          // Early-Secret = HKDF-Extract(0,0)

      unsigned char ch[512]; writer cw { ch, sizeof ch };
      client_hello_message (cw, client_random, session_id, pub, host);
      tr.add (ch, cw.len);
      unsigned char rec[20000]; writer rw { rec, sizeof rec };
      record (rw, 22, ch, cw.len);
      if (! write_n (rec, rw.len)) return -1;

      long rl;
      do { rl = read_record (rec, sizeof rec); if (rl<0) return -2; } while (rec[0]==20);  // skip CCS
      if (rec[0] != 22) return -3;                                   // expect ServerHello
      server_hello sh = parse_server_hello (rec+5, rl-5);
      if (! sh.ok || sh.cipher_suite != 0x1301) return -4;
      tr.add (rec+5, rl-5);

      unsigned char shared[32], th[32];
      crypto::x25519 (shared, priv, sh.key_share);
      tr.hash (th);
      ks.set_handshake (shared, th);
      traffic_key (ks.s_hs, shk); traffic_iv (ks.s_hs, shiv);
      traffic_key (ks.c_hs, chk); traffic_iv (ks.c_hs, chiv);
      sseq = 0; cseq = 0;

      // read + decrypt the server flight, processing handshake messages to Finished
      unsigned char hs[16384]; unsigned long hl=0, hp=0;
      for (bool done=false; ! done; ) {
        rl = read_record (rec, sizeof rec);
        if (rl < 0) return -5;
        if (rec[0] == 20) continue;                  // CCS, not counted
        if (rec[0] != 23) return -6;                 // expect encrypted
        unsigned char pt[20000];
        long pn = open_record (shk, shiv, sseq++, rec, rl, pt, sizeof pt);
        if (pn < 0) return -7;
        unsigned itype; unsigned long clen = inner_content (pt, pn, &itype);
        if (itype == 21) return -8;                  // alert
        if (itype != 22) continue;
        for (unsigned long i=0;i<clen && hl<sizeof hs;i++) hs[hl++]=pt[i];
        while (hp + 4 <= hl) {
          unsigned long mlen = ((unsigned long)hs[hp+1]<<16)|((unsigned long)hs[hp+2]<<8)|hs[hp+3];
          if (hp + 4 + mlen > hl) break;             // message incomplete; read more
          unsigned char* msg = hs + hp; unsigned long msgn = 4 + mlen;
          if (hs[hp] == 20) {                         // server Finished
            unsigned char thh[32], exp[32]; tr.hash (thh); finished_mac (ks.s_hs, thh, exp);
            for (int i=0;i<32;i++) if (msg[4+i]!=exp[i]) return -9;   // MISMATCH
            tr.add (msg, msgn); done = true; hp += msgn; break;
          }
          tr.add (msg, msgn); hp += msgn;            // EE / Certificate / CertVerify (NOT validated)
        }
      }

      unsigned char thsf[32]; tr.hash (thsf);         // transcript CH..server Finished
      ks.set_application (thsf);
      traffic_key (ks.c_ap, cak); traffic_iv (ks.c_ap, caiv);
      traffic_key (ks.s_ap, sak); traffic_iv (ks.s_ap, saiv);

      // client Finished, encrypted under the client handshake keys
      unsigned char cvd[32]; finished_mac (ks.c_hs, thsf, cvd);
      unsigned char fin[40]; writer fw { fin, sizeof fin };
      fw.byte (20); { unsigned long h=fw.mark24(); fw.raw(cvd,32); fw.patch24(h); }
      unsigned char finp[64]; for (unsigned long i=0;i<fw.len;i++) finp[i]=fin[i]; finp[fw.len]=22;
      unsigned char finrec[96]; long frl = seal_record (chk, chiv, cseq++, finp, fw.len+1, finrec, sizeof finrec);
      if (frl < 0 || ! write_n (finrec, frl)) return -10;

      cseq = 0; sseq = 0;                              // application epoch
      ktls = (setup_ktls () == 0);                     // offload the record layer to the kernel
      return 0;
    }

    long write_app (const unsigned char* p, unsigned long n) {
      if (ktls) return write_n (p, n) ? (long) n : -1;     // KTLS: kernel frames + encrypts
      if (n > 16384) n = 16384;
      unsigned char pt[16385]; for (unsigned long i=0;i<n;i++) pt[i]=p[i]; pt[n]=23;   // inner type app_data
      unsigned char rec[16500]; long rl = seal_record (cak, caiv, cseq++, pt, n+1, rec, sizeof rec);
      if (rl < 0) return rl;
      return write_n (rec, rl) ? (long) n : -1;
    }

    // KTLS read path: the kernel decrypts; recvmsg delivers plaintext plus the
    // record type via a control message. Skips post-handshake records.
    long read_ktls (unsigned char* out, unsigned long cap) {
      for (;;) {
        crypto::aead_detail::iovec io { out, cap };  // carries the record type via cmsg
        crypto::aead_detail::msghdr m {}; m.iov = &io; m.iovlen = 1;
        alignas(8) unsigned char cbuf[64]; m.control = cbuf; m.controllen = sizeof cbuf;
        long n = call (calls::recvmsg, fd, &m, 0);
        if (n <= 0) return n;                        // 0 = orderly close, <0 = error
        unsigned rectype = 23;                       // default: application_data
        for (unsigned long off=0; off+16 <= m.controllen; ) {
          unsigned long clen=0; for(int i=0;i<8;i++) clen |= (unsigned long)cbuf[off+i]<<(8*i);
          int level = cbuf[off+8]|(cbuf[off+9]<<8)|(cbuf[off+10]<<16)|(cbuf[off+11]<<24);
          int ctype = cbuf[off+12]|(cbuf[off+13]<<8)|(cbuf[off+14]<<16)|(cbuf[off+15]<<24);
          if (level==282 /*SOL_TLS*/ && ctype==2 /*TLS_GET_RECORD_TYPE*/ && clen>=17) rectype = cbuf[off+16];
          if (clen < 16) break;
          off += (clen + 7) & ~7UL;
        }
        if (rectype == 23) return n;                 // application_data
        if (rectype == 21) return 0;                 // alert / close_notify
        // rectype == 22 (NewSessionTicket) etc. -> ignore, read the next record
      }
    }

    // One application record's worth of data; skips post-handshake handshake
    // records (NewSessionTicket). 0 = clean close, <0 = error.
    long read_app (unsigned char* out, unsigned long cap) {
      if (ktls) return read_ktls (out, cap);          // kernel does the record layer
      for (;;) {
        unsigned char rec[20000]; long rl = read_record (rec, sizeof rec);
        if (rl < 0) return -1;
        if (rec[0] == 20) continue;
        unsigned char pt[20000]; long pn = open_record (sak, saiv, sseq++, rec, rl, pt, sizeof pt);
        if (pn < 0) return -2;
        unsigned itype; unsigned long clen = inner_content (pt, pn, &itype);
        if (itype == 22) continue;                    // NewSessionTicket -> ignore
        if (itype == 21) return 0;                    // alert / close_notify
        if (itype == 23) { unsigned long k = clen<cap?clen:cap; for (unsigned long i=0;i<k;i++) out[i]=pt[i]; return (long)k; }
      }
    }
  };
}
