"""Generate original geometric radar icons using only Python's standard library."""
from pathlib import Path
import math
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]

def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)

def generate(size):
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            u, v = (x + .5) / size - .5, (y + .5) / size - .5
            d = math.hypot(u, v)
            color = (16, 29, 50)
            if any(abs(d-r) < .009 for r in (.15, .28, .41)) or (abs(u)<.006 or abs(v)<.006) and d<.41:
                color = (59, 106, 123)
            if abs(u + v) < .012 and u >= 0 and d < .41:
                color = (96, 230, 198)
            if math.hypot(u-.19, v+.19)<.026:
                color = (236, 194, 90)
            row.extend(color)
        rows.append(b"\x00" + row)
    data = b"\x89PNG\r\n\x1a\n"
    data += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
    data += chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
    data += chunk(b"IEND", b"")
    (ROOT / f"radar-icon-{size}.png").write_bytes(data)

if __name__ == "__main__":
    for size in (192, 512):
        generate(size)
