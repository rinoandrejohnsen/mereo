// Zig's strongest feature, and it wins this row outright: a failure is an error
// union in the type, and discarding one is an error rather than a warning.
fn readOrFail() !i64 {
    return error.Bad;
}
pub fn main() void {
    readOrFail();                               // MISTAKE
}
