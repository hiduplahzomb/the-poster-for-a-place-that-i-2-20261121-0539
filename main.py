#!/usr/bin/env python3
"""SOLMARA — a travel poster for a place that isn't there.

Generates a 1024x1024 travel poster (PNG) for Solmara, a twin-sunset
archipelago where the sun sets twice: two suns sink over a glass-calm bay,
a dark cliff-city glows on the headland, and the name is set big in the
sky. Pure Python standard library only — no network, no fonts, no
third-party packages — so it runs in the make.fun sandbox. Deterministic:
the same bytes every run. Writes /output/entry.png.
"""

import math
import os
import struct
import zlib

W = 1024
H = 1024
OUT = "/output/entry.png"
HORIZON = 690

# ---------------------------------------------------------------- palette
# Sky gradient stops: (fraction of horizon, RGB), top -> horizon.
SKY = [
    (0.00, (24, 14, 58)),
    (0.28, (74, 30, 96)),
    (0.50, (158, 62, 110)),
    (0.68, (226, 110, 96)),
    (0.84, (255, 168, 104)),
    (1.00, (255, 208, 128)),
]
# Sea gradient stops: (fraction of sea band, RGB), horizon -> bottom.
SEA = [
    (0.00, (255, 196, 122)),
    (0.22, (196, 110, 108)),
    (0.55, (96, 58, 108)),
    (1.00, (28, 22, 66)),
]

SUN_BIG = (560, 575, 96)      # x, y, radius — the gold sun
SUN_SMALL = (395, 495, 52)    # x, y, radius — the rose sun
GOLD_CORE = (255, 244, 204)
GOLD_MID = (255, 206, 122)
GOLD_EDGE = (255, 158, 96)
ROSE_CORE = (255, 224, 212)
ROSE_EDGE = (255, 150, 138)

RIDGE_LEFT = (56, 30, 84)
RIDGE_RIGHT = (42, 24, 72)
RIM = (255, 172, 118)
CITY = (36, 20, 64)
WINDOW = (255, 210, 122)
BIRD = (40, 20, 66)
NAME_CREAM = (255, 246, 220)
NAME_SHADOW = (52, 18, 72)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(c1, c2, t):
    return (int(lerp(c1[0], c2[0], t)),
            int(lerp(c1[1], c2[1], t)),
            int(lerp(c1[2], c2[2], t)))


def gradient(stops, t):
    """Interpolate a multi-stop gradient at t in [0, 1]."""
    if t <= stops[0][0]:
        return stops[0][1]
    for i in range(1, len(stops)):
        if t <= stops[i][0]:
            p0, c0 = stops[i - 1]
            p1, c1 = stops[i]
            return lerp_color(c0, c1, (t - p0) / (p1 - p0))
    return stops[-1][1]


def blend(dst, src, a):
    """Blend src RGB over dst RGB with alpha a in [0, 1]."""
    return (int(dst[0] + (src[0] - dst[0]) * a),
            int(dst[1] + (src[1] - dst[1]) * a),
            int(dst[2] + (src[2] - dst[2]) * a))


def ridge_top(x):
    """Top edge y of the land silhouette at column x, or None (open sea).
    Two headlands frame the bay: each rises from the horizon at the
    water's edge and tapers back down into the sea, so the shore slopes
    instead of standing as a wall."""
    if x < 400:
        t = 1.0 - x / 400.0
        top = 690 - 46 * t ** 1.5 - 6 * math.sin(x * 0.031 + 2.1)
        if x > 340:  # plunge into the sea near the channel
            top += 450 * ((x - 340) / 60.0) ** 2
        return int(top)
    if x < 700:
        return None
    t = (x - 700) / 324.0
    top = 690 - 46 * t ** 1.5 - 6 * math.sin(x * 0.027 + 1.0)
    if x < 760:  # plunge into the sea near the channel
        top += 450 * ((760 - x) / 60.0) ** 2
    return int(top)


# Cliff-city towers on the headland: (x, width, height, dome?).
TOWERS = [
    (780, 22, 66, False), (806, 22, 92, True), (832, 26, 58, False),
    (862, 20, 108, True), (886, 24, 74, False), (914, 22, 96, True),
    (940, 24, 62, False), (968, 20, 84, True), (992, 24, 56, False),
]
# Lit windows: (tower index, dx, dy) in pixels from the tower's top-left.
WINDOWS = [
    (0, 8, 12), (0, 14, 30), (1, 8, 16), (1, 8, 40), (2, 10, 14),
    (2, 16, 34), (3, 7, 20), (3, 7, 52), (4, 9, 18), (4, 15, 44),
    (5, 8, 24), (5, 8, 56), (6, 12, 16), (6, 18, 36), (7, 8, 18),
    (7, 8, 46), (8, 9, 14), (8, 18, 32),
]
# Birds: (x, y, wingspan).
BIRDS = [
    (180, 330, 26), (240, 300, 20), (300, 345, 30), (700, 300, 24),
    (760, 340, 18), (830, 285, 26), (130, 420, 18),
]

# Display letterforms for SOLMARA, 7 wide x 9 tall, '#' = filled.
GLYPHS = {
    "S": [
        ".#####.",
        "#.....#",
        "#......",
        "#......",
        ".#####.",
        "......#",
        "......#",
        "#.....#",
        ".#####.",
    ],
    "O": [
        "..###..",
        ".#...#.",
        "#.....#",
        "#.....#",
        "#.....#",
        "#.....#",
        "#.....#",
        ".#...#.",
        "..###..",
    ],
    "L": [
        "#......",
        "#......",
        "#......",
        "#......",
        "#......",
        "#......",
        "#......",
        "#......",
        "#######",
    ],
    "M": [
        "#.....#",
        "##...##",
        "#.#.#.#",
        "#.#.#.#",
        "#..#..#",
        "#.....#",
        "#.....#",
        "#.....#",
        "#.....#",
    ],
    "A": [
        "...#...",
        "..#.#..",
        ".#...#.",
        "#.....#",
        "#.....#",
        "#######",
        "#.....#",
        "#.....#",
        "#.....#",
    ],
    "R": [
        "######.",
        "#.....#",
        "#.....#",
        "######.",
        "#..#...",
        "#...#..",
        "#....#.",
        "#.....#",
        "#.....#",
    ],
}
NAME = "SOLMARA"
CELL = 15          # pixels per grid cell
GAP = 20           # pixels between letters
NAME_Y = 128       # top of the name


def sparkle(x, y):
    """Deterministic glitter value in [0, 1) for a sea pixel."""
    n = (x * 374761393 + y * 668265263) ^ ((x * y) * 974634 + 1442695041)
    n = (n ^ (n >> 13)) * 1274126177
    return ((n ^ (n >> 16)) & 0xFFFF) / 65536.0


def render():
    """Return the poster as a list of 1024 rows, each a bytearray of RGB."""
    rows = []
    # Precompute per-column ridge tops and city masks.
    tops = [ridge_top(x) for x in range(W)]
    city_top = {}
    for (tx, tw, th, _dome) in TOWERS:
        base = tops[tx + tw // 2] or HORIZON
        for x in range(tx, tx + tw):
            city_top[x] = base - th
    dome_top = {}
    for (tx, tw, th, dome) in TOWERS:
        if not dome:
            continue
        base = tops[tx + tw // 2] or HORIZON
        cx = tx + tw // 2
        r = tw // 2
        for x in range(tx, tx + tw):
            dx = x - cx
            dy = int(math.sqrt(max(0, r * r - dx * dx)))
            dome_top[x] = base - th - dy

    for y in range(H):
        if y < HORIZON:
            base = gradient(SKY, y / HORIZON)
        else:
            base = gradient(SEA, (y - HORIZON) / (H - HORIZON))
        # Start from a flat row of the base colour.
        row = bytearray(bytes(base) * W)
        for x in range(W):
            i = x * 3
            r, g, b = row[i], row[i + 1], row[i + 2]
            if y < HORIZON:
                # --- sun glow (additive-ish blend toward warm light) ---
                for (sx, sy, sr, tint, reach, strength) in (
                        (SUN_BIG[0], SUN_BIG[1], SUN_BIG[2], GOLD_MID, 300, 0.55),
                        (SUN_SMALL[0], SUN_SMALL[1], SUN_SMALL[2], ROSE_CORE, 190, 0.45)):
                    dx = x - sx
                    dy = y - sy
                    d2 = dx * dx + dy * dy
                    if d2 < reach * reach:
                        d = math.sqrt(d2)
                        fall = (1.0 - d / reach) ** 2 * strength
                        r, g, b = blend((r, g, b), tint, fall)
                # --- sun discs ---
                for (sx, sy, sr, core, mid, edge) in (
                        (SUN_BIG[0], SUN_BIG[1], SUN_BIG[2], GOLD_CORE, GOLD_MID, GOLD_EDGE),
                        (SUN_SMALL[0], SUN_SMALL[1], SUN_SMALL[2], ROSE_CORE, ROSE_CORE, ROSE_EDGE)):
                    dx = x - sx
                    dy = y - sy
                    d2 = dx * dx + dy * dy
                    if d2 <= sr * sr:
                        d = math.sqrt(d2) / sr
                        if d < 0.55:
                            r, g, b = lerp_color(core, mid, d / 0.55)
                        else:
                            r, g, b = lerp_color(mid, edge, (d - 0.55) / 0.45)
            else:
                # --- sea: sun glitter, in two columns under the suns ---
                depth = (y - HORIZON) / (H - HORIZON)
                width = 70 + depth * 260
                glit = 0.0
                for (sx, _sy, _sr) in (SUN_BIG, SUN_SMALL):
                    dx = abs(x - sx)
                    if dx < width:
                        s = sparkle(x, y)
                        if s > 0.72:
                            glit = max(glit, (s - 0.72) / 0.28
                                       * (1.0 - dx / width) * (1.0 - depth * 0.55))
                if glit > 0:
                    r, g, b = blend((r, g, b), (255, 226, 150), min(1.0, glit * 1.15))
            # --- land silhouette + warm rim light ---
            top = tops[x]
            if top is not None and y >= top:
                colour = RIDGE_LEFT if x < 400 else RIDGE_RIGHT
                if y < top + 3:
                    r, g, b = blend(colour, RIM, 0.75)
                else:
                    r, g, b = colour
            # --- cliff-city towers (dark, rising above the ridge) ---
            ct = city_top.get(x)
            if ct is not None and ct <= y < (tops[x] or HORIZON):
                r, g, b = CITY
            dt = dome_top.get(x)
            if dt is not None and dt <= y < (city_top.get(x, HORIZON)):
                r, g, b = CITY
            row[i], row[i + 1], row[i + 2] = r, g, b
        rows.append(row)

    # --- lit windows ---
    for (ti, dx, dy) in WINDOWS:
        tx, tw, th, _dome = TOWERS[ti]
        base = tops[tx + tw // 2] or HORIZON
        wx, wy = tx + dx, base - th + dy
        for yy in range(wy, wy + 4):
            for xx in range(wx, wx + 3):
                if 0 <= xx < W and 0 <= yy < H:
                    i = xx * 3
                    rows[yy][i:i + 3] = bytes(WINDOW)

    # --- birds: two short rising strokes each ---
    for (bx, by, span) in BIRDS:
        half = span // 2
        for t in range(0, half + 1):
            lift = int(3.0 * (1.0 - (t / half) ** 2))
            for (xx, yy) in ((bx - t, by - lift), (bx + t, by - lift)):
                for dy in (0, 1):
                    if 0 <= xx < W and 0 <= yy + dy < H:
                        i = xx * 3
                        rows[yy + dy][i:i + 3] = bytes(BIRD)

    # --- twin-sun motif above the name ---
    mx, my = W // 2, 78
    for (cx, cy, rr, col) in ((mx - 26, my, 17, GOLD_MID),
                              (mx + 24, my - 6, 12, ROSE_CORE)):
        for yy in range(cy - rr, cy + rr + 1):
            for xx in range(cx - rr, cx + rr + 1):
                if (xx - cx) ** 2 + (yy - cy) ** 2 <= rr * rr:
                    if 0 <= xx < W and 0 <= yy < H:
                        i = xx * 3
                        rows[yy][i:i + 3] = bytes(col)

    # --- the name, big in the sky (shadow pass, then cream) ---
    name_w = len(NAME) * 7 * CELL + (len(NAME) - 1) * GAP
    x0 = (W - name_w) // 2
    for (ox, oy, colour, alpha) in ((5, 6, NAME_SHADOW, 0.55),
                                    (0, 0, NAME_CREAM, 1.0)):
        for li, ch in enumerate(NAME):
            gx = x0 + li * (7 * CELL + GAP) + ox
            gy = NAME_Y + oy
            for gr, line in enumerate(GLYPHS[ch]):
                for gc, cell in enumerate(line):
                    if cell != "#":
                        continue
                    for yy in range(gy + gr * CELL, gy + (gr + 1) * CELL):
                        if not (0 <= yy < H):
                            continue
                        for xx in range(gx + gc * CELL, gx + (gc + 1) * CELL):
                            if not (0 <= xx < W):
                                continue
                            i = xx * 3
                            if alpha >= 1.0:
                                rows[yy][i:i + 3] = bytes(colour)
                            else:
                                dst = (rows[yy][i], rows[yy][i + 1], rows[yy][i + 2])
                                rows[yy][i:i + 3] = bytes(blend(dst, colour, alpha))

    # --- thin rule under the name ---
    rule_y = NAME_Y + 9 * CELL + 22
    for yy in range(rule_y, rule_y + 3):
        for xx in range(x0 + 60, x0 + name_w - 60):
            i = xx * 3
            dst = (rows[yy][i], rows[yy][i + 1], rows[yy][i + 2])
            rows[yy][i:i + 3] = bytes(blend(dst, NAME_CREAM, 0.6))

    # --- gentle vignette ---
    for y in range(H):
        ny = (y - H / 2) / (H / 2)
        for x in range(W):
            nx = (x - W / 2) / (W / 2)
            d2 = nx * nx + ny * ny
            if d2 > 0.55:
                f = 1.0 - 0.16 * min(1.0, (d2 - 0.55) / 0.45)
                i = x * 3
                rows[y][i] = int(rows[y][i] * f)
                rows[y][i + 1] = int(rows[y][i + 1] * f)
                rows[y][i + 2] = int(rows[y][i + 2] * f)
    return rows


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _filter_score(buf):
    """Sum of absolute values of bytes read as signed (PNG heuristic)."""
    return sum(v if v < 128 else 256 - v for v in buf)


def write_png(path, rows):
    """Encode rows (bytearray RGB) as a PNG with per-row filter choice."""
    raw = bytearray()
    prev = bytearray(W * 3)
    for row in rows:
        cands = []
        # Filter 0: None.
        cands.append((0, bytes(row)))
        # Filter 1: Sub.
        sub = bytearray(W * 3)
        for i in range(W * 3):
            left = row[i - 3] if i >= 3 else 0
            sub[i] = (row[i] - left) & 0xFF
        cands.append((1, bytes(sub)))
        # Filter 2: Up.
        up = bytearray(W * 3)
        for i in range(W * 3):
            up[i] = (row[i] - prev[i]) & 0xFF
        cands.append((2, bytes(up)))
        best = min(cands, key=lambda c: _filter_score(c[1]))
        raw.append(best[0])
        raw.extend(best[1])
        prev = row
    comp = zlib.compress(bytes(raw), 9)

    def chunk(kind, data):
        c = struct.pack(">I", len(data)) + kind + data
        return c + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", comp) + chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(png)
    return len(png)


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    rows = render()
    n = write_png(OUT, rows)
    print("wrote %s (%d bytes, %dx%d)" % (OUT, n, W, H))


if __name__ == "__main__":
    main()
