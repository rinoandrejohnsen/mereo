#include "parity.h++"
extern "C" void _start() {
    { Mark w{100};
      { Mark tmp{101}; }             // fault-order: ~tmp then ~w
    }
    sysexit(1);
}
