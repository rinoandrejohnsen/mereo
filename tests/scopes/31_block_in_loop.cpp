#include "parity.h++"
extern "C" void _start() {
    { Mark keep{104};
      int n = 0;
    loop:
      { Mark o{103};
        { Mark t{101}; }        // the block's dedent
        ++n;
      }                          // the loop's per-pass release
      if (n < 2) goto loop;
    }
    sysexit(0);
}
