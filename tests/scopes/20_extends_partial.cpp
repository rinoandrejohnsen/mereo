// C++ ground truth for PARTIAL construction. The top layer's acquire failed, so
// that layer was never constructed -- and C++ destroys only the subobjects that
// were. Modelled (as in 03_fault_tower) by the scope that actually came to
// exist: B and its base A -> 102, 101, and never 103.
#include "parity.h++"
struct A { ~A() { sysclose(101); } };
struct B : A { ~B() { sysclose(102); } };
struct C : B { ~C() { sysclose(103); } };
extern "C" void _start() {
    { B b; }
    sysexit(1);
}
