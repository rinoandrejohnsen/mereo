// The same two-step acquisition. If `lseek` throws, the destructor does NOT
// run -- the object was never fully constructed -- so the descriptor leaks.
// Nothing here is diagnosed; the fix is a member whose own destructor closes
// it, which is a discipline rather than a rule.
extern "C" long open(const char *, int, ...);
extern "C" long lseek(int, long, int);
extern "C" long close(int);

struct Holder {
    int descriptor;
    explicit Holder(const char *path) {         // MISTAKE
        descriptor = static_cast<int>(open(path, 0));
        if (descriptor < 0) throw 1;
        if (lseek(descriptor, 0, 0) < 0) throw 2;   // leaks `descriptor`
    }
    ~Holder() { close(descriptor); }
};

int main() {
    Holder h{"/dev/null"};
    return h.descriptor >= 0 ? 0 : 1;
}
