#include "parity.h++"

static void reach() { Mark tmp{101}; }          // released when reach returns
static void work()  { reach(); Mark held{102}; }

extern "C" void _start() {
    work();                                     // close(101) then close(102)
    sysexit(0);
}
