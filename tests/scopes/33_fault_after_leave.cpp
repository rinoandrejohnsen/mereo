#include "parity.h++"
extern "C" void _start() {
    { Mark keep{104};
      volatile int limit = 1;   // argc, not foldable
      int i = 0;
    loop:
      { Mark t{101};
        if (i < limit) goto done;   // ~t on the way out
        ++i;
        if (i < 3) goto loop;
      }                              // ~t on the fall-out too
    done:
      if (i != 99) goto fault;
    fault: ;
    }                                // ~keep
    sysexit(1);
}
