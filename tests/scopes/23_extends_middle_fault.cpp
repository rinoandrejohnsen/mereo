// C++ ground truth for a MIDDLE base failing to acquire. A was constructed, B's
// acquire failed, and C was never reached -- C++ destroys only the subobjects
// that came to exist. Modelled (as in 03_fault_tower) by that scope: just A.
#include "parity.h++"
struct A { ~A() { sysclose(101); } };
struct B { ~B() { sysclose(102); } };
struct C { ~C() { sysclose(103); } };
struct T : A, B, C { };
extern "C" void _start() {
    { A a; }
    sysexit(1);
}
