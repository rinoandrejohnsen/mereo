// A faithful C++ jsondemo: every helper always_inline, freestanding, no libc.
// Mirrors json.mereo's flat scan -- locate key, step over ':', read the value.
#define AI __attribute__((always_inline)) inline

AI long sys3 (long n, long a, long b, long c) {
  long r; __asm__ volatile ("syscall" : "=a"(r)
      : "a"(n), "D"(a), "S"(b), "d"(c) : "rcx","r11","memory"); return r;
}
AI long wr (long fd, const void* p, long n) { return sys3(1, fd, (long)p, n); }
[[noreturn]] AI void ex (long s) { sys3(60, s, 0, 0); __builtin_unreachable(); }


// --- the error apparatus mereo generates and C++ does not -------------------
// Per fallible step: a diagnostic naming program/step/operation, the failing
// value in decimal, an -EPIPE/-EINTR discrimination for graceful shutdown, and
// a distinct exit status. This is the part you must remember to write.
AI void write_value (long e) {          // mereo's _write_value, verbatim shape
  char d[8]; long n = e < 0; long i;
  if (n) e = -e;
  d[1] = (char)('0' + e / 10000 % 10);
  d[2] = (char)('0' + e / 1000  % 10);
  d[3] = (char)('0' + e / 100   % 10);
  d[4] = (char)('0' + e / 10    % 10);
  d[5] = (char)('0' + e         % 10);
  d[6] = '\n';
  i = 5 - (e >= 10) - (e >= 100) - (e >= 1000) - (e >= 10000);
  d[i - 1] = '-'; i -= n;
  sys3(1, 2, (long)d + i, 7 - i);
}
AI void fault (const char* msg, long len, long value, long stage) {
  if (value == -32) ex(0);              // -EPIPE: graceful shutdown
  sys3(1, 2, (long)msg, len);
  write_value(value);
  ex(stage);
}

// find: offset of the first BYTE in data[0..len), or len if absent
AI long findb (const unsigned char* d, long len, unsigned char b) {
  long i = 0; while (i < len && d[i] != b) ++i; return i;
}
// search: offset of needle in data[0..len), or len if absent
AI long search (const unsigned char* d, long len, const unsigned char* nd, long nl) {
  long i = 0;
  while (i < len) {
    long k = findb(d + i, len - i, nd[0]); i += k;
    if (i >= len) return len;
    long j = 0; while (j < nl && i + j < len && d[i+j] == nd[j]) ++j;
    if (j == nl) return i;
    ++i;
  }
  return len;
}
struct json {
  const unsigned char* content; long length;
  AI void text (const char* key, long keylen, long& start, long& vlen) const {
    long keyat = search(content, length, (const unsigned char*)key, keylen);
    if (keyat >= length) fault("jsondemo: 1: text: ", 19, keyat, 1);
    long off = keyat + keylen;
    off += findb(content + off, length - off, ':') + 1;
    off += findb(content + off, length - off, '"') + 1;
    start = off;
    vlen  = findb(content + start, length - start, '"');
  }
  AI void number (const char* key, long keylen, long& value) const {
    long keyat = search(content, length, (const unsigned char*)key, keylen);
    if (keyat >= length) fault("jsondemo: 4: number: ", 21, keyat, 4);
    long off = keyat + keylen;
    off += findb(content + off, length - off, ':') + 1;
    long v = 0, neg = 0, i = off;
    if (content[i] == '-') { neg = 1; ++i; }
    while (i < length && content[i] >= '0' && content[i] <= '9') { v = v*10 + (content[i]-'0'); ++i; }
    value = neg ? -v : v;
  }
};
AI long format (long v, unsigned char* out) {          // decimal digits -> length
  unsigned char tmp[24]; long n = 0;
  if (v == 0) tmp[n++] = '0';
  long a = v < 0 ? -v : v;
  while (a) { tmp[n++] = (unsigned char)('0' + a % 10); a /= 10; }
  if (v < 0) tmp[n++] = '-';
  for (long i = 0; i < n; ++i) out[i] = tmp[n-1-i];
  return n;
}
static const unsigned char raw[] = "{\"name\":\"mereo\",\"port\":443,\"secure\":true}";

extern "C" __attribute__((force_align_arg_pointer, externally_visible)) void _start () {
  json doc { raw, 41 };
  long start = 0, vlen = 0, portnum = 0;
  unsigned char digits[8];
  doc.text("name", 4, start, vlen);
  { long r = wr(1, raw + start, vlen);
    if (r != vlen) fault("jsondemo: 2: write terminal: ", 28, r, 2); }
  { long r = wr(1, "\n", 1);
    if (r != 1) fault("jsondemo: 3: write terminal: ", 28, r, 3); }
  doc.number("port", 4, portnum);
  long dlen = format(portnum, digits);
  { long r = wr(1, digits, dlen);
    if (r != dlen) fault("jsondemo: 5: write terminal: ", 28, r, 5); }
  { long r = wr(1, "\n", 1);
    if (r != 1) fault("jsondemo: 6: write terminal: ", 28, r, 6); }
  ex(0);
}
