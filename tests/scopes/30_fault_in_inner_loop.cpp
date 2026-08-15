#include "parity.h++"
// the mereo twin's loops are do-while, so the goto shape mirrors them exactly
extern "C" void _start() {
    { Mark keep{104};
      volatile int limit = 1;   // argc, not foldable
      int i = 0, j = 0, n = 0;
    outer:
      { Mark o{103};
        j = 0;
      inner:
        { Mark t{101};
          ++n;
          if (!(n < limit + 2)) goto fault;   // ~t then ~o then ~keep
          ++j;
          if (j < 2) goto inner;
        }
      }
      ++i;
      if (i < 3) goto outer;
    fault: ;
    }
    sysexit(1);
}
