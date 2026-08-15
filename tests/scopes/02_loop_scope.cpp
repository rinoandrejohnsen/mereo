#include "parity.h++"
extern "C" void _start() {
    { Mark keep{103};
      for (int n = 0; n < 2; ++n) { Mark tmp{101}; }
    }
    sysexit(0);
}
