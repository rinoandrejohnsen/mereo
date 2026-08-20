// The same shape, and caught the same way: the name is block-scoped.
const File = struct {
    fn read(_: File) void {}
};
pub fn main() void {
    { const source = File{}; _ = source; }
    source.read();                              // MISTAKE
}
