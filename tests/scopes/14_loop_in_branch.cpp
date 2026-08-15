#include "parity.h++"
extern "C" void _start() {
    { Mark keep{103};
      volatile int n = 1;   // not foldable, as in the mereo twin
      if (n == 1) { for (int i = 0; i < 3; ++i) { Mark tmp{101}; } }  // 101 x3
    }                                                                 // keep 103
    sysexit(0);
}
