// The same mistake, with the requirement WRITTEN as a concept.
#include <concepts>
template <class T> concept Readable = requires(T t) { t.read(); };
struct File { void read() {} };
template <Readable T> void inner(T t) { t.read(); }
template <Readable T> void outer(T t) { inner(t); }
int main() {
    long n = 0;
    outer(n);                                   // MISTAKE
}
