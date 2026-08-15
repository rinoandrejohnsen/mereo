#include "parity.h++"
// a template is spliced, so its scope is an ordinary block here
extern "C" void _start() {
    { Mark keep{103};
      volatile int n = 1;   // argc, not foldable
      int r = 0;
      { Mark t{101};
        r = 1;
        if (n == 1) goto done;      // ~t on the way out
        Mark u{102};
        r = 2;
      }                              // ~u then ~t on the fall-through
    done: ;
    }
    sysexit(0);
}
