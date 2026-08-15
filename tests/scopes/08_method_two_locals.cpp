#include "parity.h++"
static void run() { Mark p{101}, q{102}; }      // ~q, ~p at return
extern "C" void _start() {
    { Mark w{100}; run(); }
    sysexit(0);
}
