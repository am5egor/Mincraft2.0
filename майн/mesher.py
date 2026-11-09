"""Превращает блоки чанка в вершины: скрытые грани отбрасываются, свет и затенение считаются массивами."""
import numpy as np

from world import AIR, CHUNK, CUTOUT, EMIT, FACE_TILE, HEIGHT, OPAQUE, PANEL_SIDE, WATER

PAD = 8
LIGHT_STEPS = 8
LIGHT_FALLOFF = 2

# Нормаль и две касательные (u x v = n); v боковых граней направлена вверх.
DIRS = [
    ((1, 0, 0), (0, 0, -1), (0, 1, 0)),
    ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
    ((0, 1, 0), (0, 0, 1), (1, 0, 0)),
    ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
    ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
    ((0, 0, -1), (-1, 0, 0), (0, 1, 0)),
]
SIGNS = np.array([(-1, -1), (1, -1), (1, 1), (-1, 1)])
TABLES = []
for n, u, v in DIRS:
    n, u, v = np.array(n), np.array(u), np.array(v)
    su = SIGNS[:, 0, None] * u
    sv = SIGNS[:, 1, None] * v
    TABLES.append({
        "n": n,
        "corner": ((n + su + sv) + 1) // 2,
        "side1": n + su,
        "side2": n + sv,
        "diag": n + su + sv,
    })
ORDER = np.array([0, 1, 2, 0, 2, 3])
ORDER_FLIP = np.array([1, 2, 3, 1, 3, 0])


def _spread(light, blocked):
    """Растекание света: за шаг значение падает на LIGHT_FALLOFF."""
    for _ in range(LIGHT_STEPS):
        lower = light - LIGHT_FALLOFF
        out = light.copy()
        out[1:] = np.maximum(out[1:], lower[:-1])
        out[:-1] = np.maximum(out[:-1], lower[1:])
        out[:, 1:] = np.maximum(out[:, 1:], lower[:, :-1])
        out[:, :-1] = np.maximum(out[:, :-1], lower[:, 1:])
        out[:, :, 1:] = np.maximum(out[:, :, 1:], lower[:, :, :-1])
        out[:, :, :-1] = np.maximum(out[:, :, :-1], lower[:, :, 1:])
        out[blocked] = 0
        if np.array_equal(out, light):
            break
        light = out
    return light


def compute_light(b, opaque):
    """Солнечный свет и свет от блоков, значения 0..15."""
    filled = np.nonzero((b != AIR).any(axis=(0, 2)))[0]
    top = min(int(filled[-1]) + 3, b.shape[1])

    sky = np.full(b.shape, 15, dtype=np.int8)
    crop = opaque[:, :top, :]
    water = (b[:, :top, :] == WATER)
    covered = np.cumsum(crop[:, ::-1, :], axis=1)[:, ::-1, :] > 0
    depth = np.cumsum(water[:, ::-1, :], axis=1)[:, ::-1, :]
    column = np.clip(15 - depth * 2, 0, 15).astype(np.int8)
    column[covered] = 0
    sky[:, :top, :] = _spread(column, crop)

    glow = np.zeros(b.shape, dtype=np.int8)
    emit = EMIT[b]
    if emit.any():
        start = np.zeros(crop.shape, dtype=np.int8)
        start[emit[:, :top, :]] = 15
        glow[:, :top, :] = _spread(start, crop & ~emit[:, :top, :])
    return sky, glow


def _emit_faces(mask, b, d, opaque, sky, glow, panel=False):
    ix, iy, iz = np.nonzero(mask)
    count = len(ix)
    if count == 0:
        return None
    t = TABLES[d]
    cx, cy, cz = ix + PAD, iy + 1, iz + PAD
    block = b[cx, cy, cz]

    def cells(off):
        """Индексы соседних ячеек для четырёх углов каждой грани."""
        return cx[:, None] + off[:, 0], cy[:, None] + off[:, 1], cz[:, None] + off[:, 2]

    c1, c2, c3 = cells(t["side1"]), cells(t["side2"]), cells(t["diag"])
    n = t["n"]
    c0 = cx + n[0], cy + n[1], cz + n[2]
    s1, s2, s3 = opaque[c1], opaque[c2], opaque[c3]
    ao = np.where(s1 & s2, 0, 3 - s1.astype(np.int8) - s2.astype(np.int8) - s3.astype(np.int8))

    open1, open2, open3 = (~s1).astype(np.int16), (~s2).astype(np.int16), (~s3).astype(np.int16)
    weight = 1 + open1 + open2 + open3

    def smooth(light):
        total = light[c0][:, None] + light[c1] * open1 + light[c2] * open2 + light[c3] * open3
        return total * 16 // weight

    corner = t["corner"]
    is_water = block == WATER
    above = b[cx, cy + 1, cz] != WATER
    liquid = ((is_water & above)[:, None] & (corner[:, 1] == 1)[None, :]).astype(np.uint8)
    tex_u = (SIGNS[:, 0] + 1) // 2
    tex_v = (SIGNS[:, 1] + 1) // 2
    flags = (tex_u | tex_v << 1 | d << 2)[None, :] | (liquid << 5)

    v = np.empty((count, 4, 8), dtype=np.uint8)
    v[..., 0] = ix[:, None] + corner[:, 0]
    v[..., 1] = iy[:, None] + corner[:, 1]
    v[..., 2] = iz[:, None] + corner[:, 2]
    v[..., 3] = flags
    v[..., 4] = FACE_TILE[block, d][:, None]
    v[..., 5] = ao
    v[..., 6] = smooth(sky)
    v[..., 7] = smooth(glow)

    if panel:
        # Дальняя от края плоскость створки ставится на сам край и сдвигается шейдером на толщину.
        side = PANEL_SIDE[block][:, None]
        inset = np.zeros((count, 4), dtype=np.uint8)
        for wanted, axis, far, code in ((0, 2, 1, 3), (2, 2, 0, 4), (3, 0, 1, 1), (1, 0, 0, 2), (4, 1, 1, 5)):
            moved = (side == wanted) & (corner[None, :, axis] == far)
            v[..., axis][moved] += 1 if far == 0 else 255  # 255 — это -1 для байта
            inset[moved] = code
        v[..., 5] |= inset << 2

    flip = ao[:, 0] + ao[:, 2] < ao[:, 1] + ao[:, 3]
    order = np.where(flip[:, None], ORDER_FLIP, ORDER)
    return v[np.arange(count)[:, None], order]


def build_mesh(b):
    """b: блоки с полями PAD (см. World.padded). Возвращает байты непрозрачной и прозрачной геометрии."""
    opaque = OPAQUE[b]
    sky, glow = compute_light(b, opaque)
    x0, x1, y0, y1 = PAD, PAD + CHUNK, 1, HEIGHT + 1
    inner_block = b[x0:x1, y0:y1, x0:x1]
    inner_opaque = opaque[x0:x1, y0:y1, x0:x1]
    water = inner_block == WATER
    cutout = CUTOUT[inner_block]
    panels = PANEL_SIDE[inner_block] >= 0

    solid_parts, clear_parts = [], []
    for d, t in enumerate(TABLES):
        nx, ny, nz = t["n"]
        near_block = b[x0 + nx:x1 + nx, y0 + ny:y1 + ny, x0 + nz:x1 + nz]
        near_opaque = opaque[x0 + nx:x1 + nx, y0 + ny:y1 + ny, x0 + nz:x1 + nz]

        part = _emit_faces(inner_opaque & ~near_opaque, b, d, opaque, sky, glow)
        if part is not None:
            solid_parts.append(part)

        part = _emit_faces(panels, b, d, opaque, sky, glow, panel=True)
        if part is not None:
            solid_parts.append(part)

        clear_mask = (water & (near_block != WATER) & ~near_opaque) | (cutout & (near_block != inner_block) & ~near_opaque)
        part = _emit_faces(clear_mask, b, d, opaque, sky, glow)
        if part is not None:
            clear_parts.append(part)

    solid = np.concatenate(solid_parts).tobytes() if solid_parts else b""
    clear = np.concatenate(clear_parts).tobytes() if clear_parts else b""
    return solid, clear
