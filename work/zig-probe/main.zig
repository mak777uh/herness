const std = @import("std");

pub fn main(init: std.process.Init) !void {
    const io = init.io;
    const stdout = std.Io.File.stdout();
    var buf: [8192]u8 = undefined;
    var w = stdout.writer(io, &buf);
    try w.interface.print("zig ok, args={d}\n", .{init.minimal.args.vector.len});
    try w.interface.flush();
}
