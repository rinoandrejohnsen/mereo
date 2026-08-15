#include "parity.h++"
extern "C" void _start() {
    { Mark keep{104};
      volatile int n = 1;   // argc, not foldable
      int i = 0;
    loop:
      { Mark o{103};
        if (i == 1) { Mark c{102}; Mark e{105};  // the cold road
                      if (n < 9) goto merge;     // ~e ~c, then rejoin
                      Mark late{101}; }
        else        { Mark h{101}; }             // the likely road
      merge: ;
        ++i;
        if (i < n + 2) goto loop;
      }
    }
    sysexit(0);
}
