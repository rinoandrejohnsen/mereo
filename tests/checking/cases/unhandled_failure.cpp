// C++ at its strongest here: `[[nodiscard]]` is the annotation that exists for
// this, and ignoring it is a WARNING. The program still compiles.
[[nodiscard]] static long read_or_fail() { return -1; }
int main() {
    read_or_fail();                             // MISTAKE
    return 0;
}
