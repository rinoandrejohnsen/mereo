// Legal C++: a function has a frame, so it can call itself.
static void down(long n) { down(n); }           // MISTAKE
int main() { down(0); }
