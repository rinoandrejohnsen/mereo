#include "parity.h++"
extern "C" void _start() {
    { Mark a{101}, b{102}; }        // early leave -> ~b, ~a
    sysexit(1);
}
