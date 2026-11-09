"""Процедурные текстуры блоков в собственном мягком пастельном стиле."""
import numpy as np

SIZE = 32
_yy, _xx = np.meshgrid(np.arange(SIZE, dtype=float), np.arange(SIZE, dtype=float), indexing="ij")


def _soft(rng, cells):
    """Плавный шум 0..1, бесшовный по краям тайла."""
    grid = rng.random((cells, cells))
    fx = _xx / SIZE * cells
    fy = _yy / SIZE * cells
    ix = fx.astype(int)
    iy = fy.astype(int)
    u = fx - ix
    v = fy - iy
    u = u * u * (3 - 2 * u)
    v = v * v * (3 - 2 * v)
    a = grid[iy % cells, ix % cells] * (1 - u) + grid[iy % cells, (ix + 1) % cells] * u
    b = grid[(iy + 1) % cells, ix % cells] * (1 - u) + grid[(iy + 1) % cells, (ix + 1) % cells] * u
    return a * (1 - v) + b * v


def _bevel(strength=0.14, width=3.0):
    """Мягкая фаска: края тайла чуть темнее."""
    d = np.minimum.reduce([_xx, SIZE - 1 - _xx, _yy, SIZE - 1 - _yy])
    return 1.0 - strength * (1.0 - np.clip(d / width, 0, 1)) ** 2


def _paint(color, rng, mottling=0.14, bevel=0.14):
    n = _soft(rng, 3) * 0.55 + _soft(rng, 8) * 0.45 - 0.5
    shade = (1.0 + n * mottling * 2.0) * _bevel(bevel)
    return np.array(color, dtype=float)[None, None, :] * shade[..., None]


def _band(base, band, rng):
    """Боковая грань с цветной полосой сверху (строка 0 — низ тайла)."""
    edge = SIZE - 10 + np.sin(_xx * 0.55 + rng.random() * 6) * 1.6 + np.sin(_xx * 1.3) * 0.8
    t = np.clip(_yy - edge + 0.5, 0, 1)[..., None]
    return base * (1 - t) + band * t


def _rgba(rgb, alpha=1.0):
    a = np.broadcast_to(np.asarray(alpha, dtype=float) * 255.0, (SIZE, SIZE))
    return np.dstack([np.clip(rgb, 0, 255), a]).astype(np.uint8)


def _rock(rng):
    strata = np.sin((_xx + _yy * 2.0 + _soft(rng, 4) * 14.0) / 4.5)[..., None] * 9.0
    return _paint((124, 132, 156), rng, 0.1) + strata


def _gems(base, rng, color, count=6):
    img = base.copy()
    for _ in range(count):
        cx, cy = rng.uniform(5, SIZE - 5, 2)
        r = rng.uniform(2.2, 3.8)
        d = np.hypot(_xx - cx, _yy - cy) / r
        t = np.clip(1.4 - d * 1.4, 0, 1)[..., None]
        shine = np.clip(1.0 - np.hypot(_xx - cx + 0.8, _yy - cy - 0.8) / (r * 0.5), 0, 1)[..., None]
        img = img * (1 - t) + np.array(color, dtype=float)[None, None, :] * t + shine * 70
    return img


def build_tiles(seed=7321):
    """Массив (слои, 32, 32, 4); порядок совпадает с константами T_* из world.py."""
    rng = np.random.default_rng(seed)
    soil = _paint((150, 108, 104), rng)
    turf = _paint((106, 196, 160), rng, 0.16)
    snow = _paint((236, 242, 252), rng, 0.04, 0.08)

    trunk = _paint((116, 80, 110), rng, 0.08)
    trunk += (np.sin(_xx * 1.15 + _soft(rng, 3) * 5.0) * 13.0)[..., None]
    rings = np.hypot(_xx - 15.5, _yy - 15.5)
    trunk_top = _paint((206, 164, 150), rng, 0.05) + (np.sin(rings * 1.5) * 13.0)[..., None]

    petals = (np.sin(_xx * 0.8) * np.sin(_yy * 0.8))[..., None] * 15.0
    crown = _paint((236, 124, 138), rng, 0.2, 0.08) + petals
    frost_crown = _paint((146, 196, 232), rng, 0.2, 0.08) + petals

    ripples = np.sin((_xx + _soft(rng, 3) * 18.0) * 0.5) * np.sin((_yy + _soft(rng, 3) * 18.0) * 0.5)
    water = _paint((58, 158, 176), rng, 0.08, 0.0) + (ripples * 11.0)[..., None]

    planks = _paint((226, 176, 112), rng, 0.08, 0.1)
    planks += (np.sin(_yy * 1.8 + _soft(rng, 4) * 6.0) * 6.0)[..., None]
    planks[(np.round(_xx).astype(int) % 11) == 0] *= 0.68

    brick = _paint((204, 106, 84), rng, 0.12, 0.0)
    mortar = np.zeros((SIZE, SIZE), dtype=bool)
    mortar[(_yy.astype(int) % 16) <= 1] = True
    row = _yy.astype(int) // 16
    mortar[((_xx.astype(int) + row * 8) % 16) <= 1] = True
    brick[mortar] = (232, 216, 200)
    brick *= _bevel(0.12)[..., None]

    rim = np.minimum.reduce([_xx, SIZE - 1 - _xx, _yy, SIZE - 1 - _yy]) < 2
    sheen = np.abs((_xx - _yy) % 26 - 13) < 2
    glass_rgb = np.full((SIZE, SIZE, 3), (205, 232, 240), dtype=float)
    glass_alpha = np.where(rim, 0.95, np.where(sheen, 0.34, 0.14))

    amber = _gems(_rock(rng), rng, (250, 168, 48))

    d = np.hypot(_xx - 15.5, _yy - 15.5)
    facets = (np.abs(np.sin(np.arctan2(_yy - 15.5, _xx - 15.5) * 3.0)) * 34.0)[..., None]
    glow = np.array((150, 244, 236), dtype=float)[None, None, :] * (1.15 - (d / 26.0)[..., None]) + facets

    base = _paint((58, 54, 92), rng, 0.34, 0.1)

    bench_top = planks.copy()
    bench_top[(np.abs(_xx - 15.5) < 10.5) & (np.abs(_yy - 15.5) < 10.5)] = (120, 84, 62)
    bench_top[(np.abs(_xx - 15.5) < 9) & (np.abs(_yy - 15.5) < 9)] = (242, 214, 168)
    bench_top[(np.abs(_xx - 15.5) < 1) | (np.abs(_yy - 15.5) < 1)] = (120, 84, 62)

    bench_side = planks * 0.82
    bench_side[_yy >= 24] = (120, 84, 62)
    bench_side[(_yy >= 26) & (_yy < 30)] = (226, 176, 112)
    bench_side[(_xx >= 4) & (_xx < 8) & (_yy < 24)] = (120, 84, 62)
    bench_side[(_xx >= 24) & (_xx < 28) & (_yy < 24)] = (120, 84, 62)

    forge_side = _paint((84, 84, 112), rng, 0.2, 0.16)
    arch = (np.abs(_xx - 15.5) < 9) & (_yy < 13 + np.sqrt(np.maximum(81 - (_xx - 15.5) ** 2, 0)) * 0.55)
    forge_side[arch] = (46, 38, 58)
    fire = np.clip(1.0 - np.hypot((_xx - 15.5) / 7.0, (_yy - 4.0) / 6.5), 0, 1)[..., None]
    forge_side = forge_side * (1 - fire) + np.array((255, 158, 60), dtype=float)[None, None, :] * fire * 1.2

    forge_top = _paint((84, 84, 112), rng, 0.2, 0.16)
    ember = np.clip(1.25 - np.hypot(_xx - 15.5, _yy - 15.5) / 8.0, 0, 1)[..., None]
    forge_top = forge_top * (1 - ember) + (np.array((255, 136, 52), dtype=float)[None, None, :]
                                           + _soft(rng, 6)[..., None] * 60.0) * ember

    path = _paint((188, 152, 114), rng, 0.2, 0.07)
    path = _gems(path, rng, (150, 124, 104), 9)

    copper = _gems(_rock(rng), rng, (214, 124, 72))
    iron = _gems(_rock(rng), rng, (214, 196, 178))
    silver = _gems(_rock(rng), rng, (226, 236, 250), 5)
    ruby = _gems(_rock(rng), rng, (232, 44, 84), 4)

    def door_tile(color, frame):
        """Дверь с филёнками и ручкой."""
        rgb = _paint(color, rng, 0.08, 0.05)
        rim = np.minimum.reduce([_xx, SIZE - 1 - _xx, _yy, SIZE - 1 - _yy]) < 3
        rgb[rim] = frame
        for y0, y1 in ((5, 13), (18, 26)):
            rgb[(_xx >= 7) & (_xx < 24) & (_yy >= y0) & (_yy < y1)] *= 0.72
        rgb[np.hypot(_xx - 25.0, _yy - 15.5) < 1.8] = (246, 214, 130)
        return rgb

    wood_door = door_tile((192, 136, 84), (124, 84, 58))
    metal_door = door_tile((166, 174, 192), (104, 110, 128))

    ash = _paint((98, 62, 70), rng, 0.3, 0.12)
    ash += (np.sin((_xx - _yy + _soft(rng, 3) * 20.0) * 0.7) * 8.0)[..., None]
    ember = _gems(ash, rng, (255, 112, 34))
    lava_flow = _soft(rng, 3) * 0.6 + _soft(rng, 7) * 0.4
    lava = np.stack([np.full_like(lava_flow, 255.0), 96.0 + lava_flow * 150.0, 22.0 + lava_flow * 40.0], axis=-1)
    pale = _paint((196, 190, 228), rng, 0.12, 0.12)
    star = _gems(pale, rng, (96, 240, 255), 5)

    def gate_tile(core, rim):
        d = np.hypot(_xx - 15.5, _yy - 15.5)
        swirl = np.sin(d * 0.9 + np.arctan2(_yy - 15.5, _xx - 15.5) * 3.0)
        rgb = np.array(core, dtype=float)[None, None, :] * (0.75 + 0.3 * swirl[..., None])
        edge = np.minimum.reduce([_xx, SIZE - 1 - _xx, _yy, SIZE - 1 - _yy]) < 3
        rgb[edge] = rim
        return rgb

    hell_gate = gate_tile((238, 56, 44), (52, 30, 44))
    edge_gate = gate_tile((130, 96, 250), (232, 226, 250))

    chest_top = _paint((168, 112, 62), rng, 0.1, 0.16)
    chest_top[(np.round(_xx).astype(int) % 11) == 0] *= 0.7
    chest_top[np.abs(_yy - 15.5) < 2] = (214, 176, 96)
    chest_side = _paint((158, 104, 58), rng, 0.1, 0.16)
    chest_side[(np.round(_yy).astype(int) % 8) == 0] *= 0.72
    chest_side[np.abs(_yy - 21.0) < 1.5] = (214, 176, 96)
    chest_side[(np.abs(_xx - 15.5) < 3.5) & (np.abs(_yy - 18.0) < 4.5)] = (236, 204, 124)
    chest_side[(np.abs(_xx - 15.5) < 1.2) & (np.abs(_yy - 17.5) < 2.0)] = (70, 52, 44)

    blanket = _paint((204, 72, 96), rng, 0.08, 0.1)
    bed_foot = blanket + (np.sin(_xx * 0.8) * np.sin(_yy * 0.8) * 9.0)[..., None]
    bed_head = _paint((226, 232, 244), rng, 0.04, 0.05)
    pillow = (np.abs(_xx - 15.5) < 11) & (np.abs(_yy - 15.5) < 8)
    bed_head[pillow] = (250, 250, 255)
    bed_head[~pillow] = (120, 150, 200)
    bed_side = _paint((154, 106, 70), rng, 0.08, 0.06)
    bed_side[_yy > 18] = (204, 72, 96)

    tiles = [
        _rgba(turf),
        _rgba(_band(soil, turf, rng)),
        _rgba(soil),
        _rgba(_rock(rng)),
        _rgba(_paint((238, 208, 164), rng, 0.08)),
        _rgba(snow),
        _rgba(_band(soil, snow, rng)),
        _rgba(trunk),
        _rgba(trunk_top),
        _rgba(crown),
        _rgba(frost_crown),
        _rgba(water, 0.74),
        _rgba(planks),
        _rgba(brick),
        _rgba(glass_rgb, glass_alpha),
        _rgba(amber),
        _rgba(glow),
        _rgba(base),
        _rgba(bench_top),
        _rgba(bench_side),
        _rgba(forge_top),
        _rgba(forge_side),
        _rgba(path),
        _rgba(copper),
        _rgba(iron),
        _rgba(silver),
        _rgba(ruby),
        _rgba(wood_door),
        _rgba(metal_door),
        _rgba(ash),
        _rgba(ember),
        _rgba(lava),
        _rgba(pale),
        _rgba(star),
        _rgba(hell_gate),
        _rgba(edge_gate),
        _rgba(chest_top),
        _rgba(chest_side),
        _rgba(bed_head),
        _rgba(bed_foot),
        _rgba(bed_side),
    ]
    return np.stack(tiles)
