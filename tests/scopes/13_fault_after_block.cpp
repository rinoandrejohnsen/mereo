#include "parity.h++"
extern "C" void _start() {
    { Mark keep{103};
      { Mark tmp{101}; }             // 101 at dedent
      Mark later{102};               // fault-order: ~later then ~keep
    }
    sysexit(1);
}
