#include "parity.h++"
// mereo's `again` jumps to the loop's TOP, not to the bottom test -- one rule
// wherever it appears -- so the twin says it with a goto rather than
// `continue`, which in a do-while would run the trailing condition.
// Either way the destructors of the scopes left behind must run first.
extern "C" void _start() {
    { Mark keep{104};
      volatile int n = 1;   // not foldable, as in the mereo twin
      int i = 0;
    top:
      { Mark t{101};
        ++i;
        if (i == n) goto top;      // ~t runs on the way out of this scope
        Mark o{103};
      }                            // ~o then ~t
      if (i < 3) goto top;
    }                              // keep at exit
    sysexit(0);
}
