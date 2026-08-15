#include "parity.h++"
extern "C" void _start() {
    { Mark keep{104};
      volatile int n = 1;   // argc, not foldable
      int i = 0;
    loop:
      { Mark o{103};
        if (n == 1) { Mark c{102};
                      goto done; }      // ~c then ~o, past the loop
        { Mark h{101}; }
        ++i;
        if (i < 3) goto loop;
      }
    done: ;
    }
    sysexit(0);
}
