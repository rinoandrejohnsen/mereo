// The same mistake. `anytype` is unconstrained, which is the point of the row.
const File = struct {
    fn read(_: File) void {}
};
fn inner(t: anytype) void { t.read(); }
fn outer(t: anytype) void { inner(t); }
pub fn main() void {
    const n: i64 = 0;
    outer(n);                                   // MISTAKE
}
