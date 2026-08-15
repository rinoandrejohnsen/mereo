#include "parity.h++"
extern "C" void _start() {
    { Mark keep{103};
      volatile int n = 1;   // argc, not foldable
      if (n == 9) { Mark c{102}; }
      Mark after{101};
    }
    sysexit(0);
}
