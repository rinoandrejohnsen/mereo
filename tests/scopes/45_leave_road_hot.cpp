#include "parity.h++"
extern "C" void _start() {
    { Mark keep{104};
      volatile int n = 1;   // argc, not foldable
      int i = 0;
    loop:
      { Mark o{103};
        if (n == 9) { Mark c{102}; }            // the cold road
        else        { Mark h{101};              // the likely road
                      if (n < 9) goto merge;    // ~h, then rejoin
                      Mark skipped{102}; }
      merge: ;
        ++i;
        if (i < 3) goto loop;
      }
    }
    sysexit(0);
}
