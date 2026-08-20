// The same shape. A non-const reference cannot bind to a literal, so this is
// caught by the type system rather than by a constraint.
void give(long &value) { value = 7; }
int main() {
    give(5);                                    // MISTAKE
}
