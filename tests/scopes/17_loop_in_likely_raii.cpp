#include "parity.h++"
extern "C" void _start() {
    { Mark keep{104};
      volatile int n = 1;   // not foldable, as in the mereo twin
      if (n == 0) { Mark c{102}; }
      else { for (int k = 0; k < 3; ++k) { Mark t{101}; } }
    }
    sysexit(0);
}
