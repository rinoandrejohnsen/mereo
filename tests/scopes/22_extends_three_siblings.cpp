// C++ ground truth for THREE independent bases. Bases are constructed in
// declaration order and destroyed in reverse, so the composite comes apart
// 103, 102, 101 -- the same as three members would.
#include "parity.h++"
struct A { ~A() { sysclose(101); } };
struct B { ~B() { sysclose(102); } };
struct C { ~C() { sysclose(103); } };
struct T : A, B, C { };
extern "C" void _start() {
    { T t; }
    sysexit(0);
}
