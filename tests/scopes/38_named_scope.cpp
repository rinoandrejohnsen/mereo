#include "parity.h++"
extern "C" void _start() {
    { Mark keep{103};
      volatile int n = 1;   // argc, not foldable
      { Mark t{101};
        if (n == 1) goto done;      // ~t on the way out
        Mark u{102};
      }                              // ~u then ~t on the fall-through
    done: ;
    }
    sysexit(0);
}
