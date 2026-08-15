// C++ ground truth for a 3-deep ownership stack: base subobjects are destroyed
// after the derived one, so the layers come apart in reverse -- 103, 102, 101.
#include "parity.h++"
struct A { ~A() { sysclose(101); } };
struct B : A { ~B() { sysclose(102); } };
struct C : B { ~C() { sysclose(103); } };
extern "C" void _start() {
    { C c; }
    sysexit(0);
}
