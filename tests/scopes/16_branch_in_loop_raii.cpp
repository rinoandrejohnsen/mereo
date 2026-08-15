#include "parity.h++"
extern "C" void _start() {
    { Mark keep{104};
      volatile int m = 1;   // not foldable, as in the mereo twin
      for (int i = 0; i < 3; ++i) {
        if (m == 0) { Mark c{102}; } else { Mark h{101}; }
      }
    }
    sysexit(0);
}
