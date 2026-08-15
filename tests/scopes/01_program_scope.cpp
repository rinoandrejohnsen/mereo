// Program scope: acquire a, b, c -> destroy c, b, a (LIFO).
#include "parity.h++"

extern "C" void _start() {
    { Mark a{101}, b{102}, c{103}; }
    sysexit(0);
}
