// The same shape: an out-parameter is a pointer, and there is nothing to point
// a literal at.
fn give(value: *i64) void { value.* = 7; }
pub fn main() void {
    give(5);                                    // MISTAKE
}
