#include "parity.h++"
// `repeat outer` from inside `inner` is a continue of the OUTER loop -- C++ has
// no such statement, so the twin says it with a goto to the outer top. Either
// way the destructors of every scope left behind run first: ~t, then ~o.
extern "C" void _start() {
    { Mark keep{104};
      volatile int n = 1;   // not foldable, as in the mereo twin
      int i = 0, j = 0;
    outer:
      { Mark o{103};
        j = 0;
      inner:
        { Mark t{101};
          ++j;
          ++i;
          if (i == n) goto outer;      // ~t then ~o on the way out
          if (j < 2) goto inner;       // ~t
        }
      }                                // ~o
      if (i < 5) goto outer;
    }                                  // keep at exit
    sysexit(0);
}
