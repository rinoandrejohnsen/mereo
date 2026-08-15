// C++ ground truth for SIBLING ownership: a class with two independent bases.
// The bases are constructed in declaration order and destroyed in reverse, so
// the composite comes apart 102 then 101 -- the same as two members would.
#include "parity.h++"
struct A { ~A() { sysclose(101); } };
struct B { ~B() { sysclose(102); } };
struct P : A, B { };
extern "C" void _start() {
    { P p; }
    sysexit(0);
}
