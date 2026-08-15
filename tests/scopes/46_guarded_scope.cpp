#include "parity.h++"
extern "C" void _start() {
    { Mark keep{103};
      volatile int n = 1;   // argc, not foldable
      if (n == 1) { Mark c{102};
                    Mark a{101}; }
    }
    sysexit(0);
}
