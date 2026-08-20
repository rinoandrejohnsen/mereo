// The same shape. C++ scopes the NAME to the block, so this is caught by
// lexical scoping rather than by anything about the destructor.
struct File { void read() {} };
int main() {
    { File source; (void)source; }
    source.read();                              // MISTAKE
}
