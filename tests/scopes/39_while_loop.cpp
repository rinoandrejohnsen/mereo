#include "parity.h++"
extern "C" void _start() {
    { Mark keep{103};
      volatile int i = 1;   // argc, not foldable
    scan:
      if (i >= 1) goto done;        // the top test -- zero passes
      { Mark t{101};
        ++i;
      }
      goto scan;
    done: ;
    }
    sysexit(0);
}
