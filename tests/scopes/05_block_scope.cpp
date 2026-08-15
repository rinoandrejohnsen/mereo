#include "parity.h++"
extern "C" void _start() {
    { Mark keep{103};
      { Mark tmp{101}; }                    // released at block close
    }
    sysexit(0);
}
