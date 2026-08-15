#include "parity.h++"
static void run() { Mark tmp{101}; }        // tmp released at function return
extern "C" void _start() {
    { Mark w{100}; run(); run(); }
    sysexit(0);
}
