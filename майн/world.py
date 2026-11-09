"""Мир: типы блоков, генерация ландшафта, хранение чанков и правок игрока."""
import json
import os
from collections import namedtuple

import numpy as np

CHUNK = 16
HEIGHT = 112
SEA = 38

# Номера слоёв текстурного массива (рисуются в textures.py).
(T_TURF, T_TURF_SIDE, T_SOIL, T_ROCK, T_SAND, T_SNOW, T_SNOW_SIDE, T_TRUNK, T_TRUNK_TOP,
 T_CROWN, T_FROST_CROWN, T_WATER, T_PLANKS, T_BRICK, T_GLASS, T_AMBER, T_GLOW, T_BASE,
 T_BENCH_TOP, T_BENCH_SIDE, T_FORGE_TOP, T_FORGE_SIDE, T_PATH,
 T_COPPER, T_IRON, T_SILVER, T_RUBY, T_DOOR, T_IRON_DOOR,
 T_ASH, T_EMBER, T_LAVA, T_PALE, T_STAR, T_HELL_GATE, T_EDGE_GATE,
 T_CHEST_TOP, T_CHEST_SIDE, T_BED_HEAD, T_BED_FOOT, T_BED_SIDE) = range(41)

Block = namedtuple("Block", "name top side bottom opaque solid emit")


def _b(name, top, side=None, bottom=None, opaque=True, solid=True, emit=False):
    side = top if side is None else side
    bottom = top if bottom is None else bottom
    return Block(name, top, side, bottom, opaque, solid, emit)


BLOCKS = [
    _b("Воздух", 0, opaque=False, solid=False),
    _b("Дёрн", T_TURF, T_TURF_SIDE, T_SOIL),
    _b("Земля", T_SOIL),
    _b("Камень", T_ROCK),
    _b("Песок", T_SAND),
    _b("Снег", T_SNOW, T_SNOW_SIDE, T_SOIL),
    _b("Ствол", T_TRUNK_TOP, T_TRUNK, T_TRUNK_TOP),
    _b("Крона", T_CROWN),
    _b("Морозная крона", T_FROST_CROWN),
    _b("Вода", T_WATER, opaque=False, solid=False),
    _b("Доски", T_PLANKS),
    _b("Кирпич", T_BRICK),
    _b("Стекло", T_GLASS, opaque=False),
    _b("Янтарная руда", T_AMBER),
    _b("Светокристалл", T_GLOW, emit=True),
    _b("Основание", T_BASE),
    _b("Верстак", T_BENCH_TOP, T_BENCH_SIDE, T_PLANKS),
    _b("Горн", T_FORGE_TOP, T_FORGE_SIDE, T_FORGE_TOP),
    _b("Тропа", T_PATH, T_SOIL, T_SOIL),
    _b("Медная руда", T_COPPER),
    _b("Железная руда", T_IRON),
    _b("Серебряная руда", T_SILVER),
    _b("Рубиновая руда", T_RUBY),
    _b("Дверь", T_DOOR, opaque=False, solid=False),
    _b("Открытая дверь", T_DOOR, opaque=False, solid=False),
    _b("Железная дверь", T_IRON_DOOR, opaque=False, solid=False),
    _b("Открытая железная дверь", T_IRON_DOOR, opaque=False, solid=False),
    _b("Пепельник", T_ASH),
    _b("Жаровая руда", T_EMBER),
    _b("Лава", T_LAVA, solid=False, emit=True),
    _b("Бледняк", T_PALE),
    _b("Звёздная руда", T_STAR),
    _b("Адские врата", T_HELL_GATE, emit=True),
    _b("Врата Края", T_EDGE_GATE, emit=True),
]
(AIR, TURF, SOIL, ROCK, SAND, SNOW, TRUNK, CROWN, FROST_CROWN, WATER,
 PLANKS, BRICK, GLASS, AMBER, GLOW, BASE, WORKBENCH, FORGE, PATH,
 COPPER_ORE, IRON_ORE, SILVER_ORE, RUBY_ORE, DOOR, DOOR_OPEN, IRON_DOOR, IRON_DOOR_OPEN,
 ASH, EMBER_ORE, LAVA, PALE, STAR_ORE, HELL_GATE, EDGE_GATE) = range(len(BLOCKS))

# Дверь — тонкая створка у одного края клетки. Стороны идут по кругу: 0 — север (-Z), 1 — восток (+X),
# 2 — юг (+Z), 3 — запад (-X); открываясь, створка переходит к следующей стороне.
PANEL_THICKNESS = 3.0 / 16.0
DOOR_STATE = {}  # блок -> (материал, сторона закрытой двери, открыта ли)
DOOR_BLOCK = {}  # обратная таблица
for _material, (_closed, _opened, _name, _tile) in enumerate(((DOOR, DOOR_OPEN, "Дверь", T_DOOR),
                                                              (IRON_DOOR, IRON_DOOR_OPEN, "Железная дверь", T_IRON_DOOR))):
    for _side in range(4):
        for _is_open in (False, True):
            if _side == 0:  # номера первых двух уже есть в старых сохранениях
                _block = _opened if _is_open else _closed
            else:
                _block = len(BLOCKS)
                BLOCKS.append(_b(("Открытая " + _name.lower()) if _is_open else _name, _tile, opaque=False, solid=False))
            DOOR_STATE[_block] = (_material, _side, _is_open)
            DOOR_BLOCK[(_material, _side, _is_open)] = _block

CHEST = len(BLOCKS)
BLOCKS.append(_b("Сундук", T_CHEST_TOP, T_CHEST_SIDE, T_PLANKS))

# Кровать занимает две клетки: изножье и изголовье в сторону facing (номера сторон как у двери).
SIDE_STEP = ((0, -1), (1, 0), (0, 1), (-1, 0))
BED_SIDE = 4  # в таблице створок: низкий блок на всю клетку
BED_STATE = {}  # блок -> (изголовье ли, направление)
BED_BLOCK = {}
for _facing in range(4):
    for _is_head in (False, True):
        _block = len(BLOCKS)
        BLOCKS.append(_b("Кровать", T_BED_HEAD if _is_head else T_BED_FOOT, T_BED_SIDE, T_PLANKS, opaque=False, solid=False))
        BED_STATE[_block] = (_is_head, _facing)
        BED_BLOCK[(_is_head, _facing)] = _block
BED = BED_BLOCK[(False, 0)]  # этим номером кровать лежит в инвентаре


BED_HEIGHT = 9.0 / 16.0


def _panel_box(side):
    """Коробка створки внутри клетки: (x0, y0, z0, x1, y1, z1)."""
    t = PANEL_THICKNESS
    return ((0.0, 0.0, 0.0, 1.0, 1.0, t), (1.0 - t, 0.0, 0.0, 1.0, 1.0, 1.0),
            (0.0, 0.0, 1.0 - t, 1.0, 1.0, 1.0), (0.0, 0.0, 0.0, t, 1.0, 1.0),
            (0.0, 0.0, 0.0, 1.0, BED_HEIGHT, 1.0))[side]


PANEL_SIDE = np.full(len(BLOCKS), -1, dtype=np.int8)
PANEL_BOX = {}
for _block, (_material, _side, _is_open) in DOOR_STATE.items():
    PANEL_SIDE[_block] = (_side + 1) % 4 if _is_open else _side
    PANEL_BOX[_block] = _panel_box(int(PANEL_SIDE[_block]))
for _block in BED_STATE:
    PANEL_SIDE[_block] = BED_SIDE
    PANEL_BOX[_block] = _panel_box(BED_SIDE)

OPAQUE = np.array([b.opaque for b in BLOCKS], dtype=bool)
# Прозрачные блоки с вырезами: рисуются вместе с водой, но в отдельные грани.
CUTOUT = ~OPAQUE
CUTOUT[[AIR, WATER]] = False
CUTOUT[PANEL_SIDE >= 0] = False  # створки строятся отдельно
EMIT = np.array([b.emit for b in BLOCKS], dtype=bool)
# Порядок граней: +X, -X, +Y, -Y, +Z, -Z.
FACE_TILE = np.array([[b.side, b.side, b.top, b.bottom, b.side, b.side] for b in BLOCKS], dtype=np.uint8)


# --- Шум -------------------------------------------------------------------

def _hash(ix, iz, seed, iy=None):
    h = ix * 374761393 + iz * 668265263 + seed * 2147483647
    if iy is not None:
        h = h + iy * 1440662683
    h &= 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h ^= h >> 16
    return h / 4294967295.0


def _fade(t):
    return t * t * t * (t * (t * 6 - 15) + 10)


def perlin2(x, z, seed):
    ix = np.floor(x).astype(np.int64)
    iz = np.floor(z).astype(np.int64)
    fx = x - ix
    fz = z - iz

    def corner(i, j, dx, dz):
        a = _hash(i, j, seed) * 6.2831853
        return np.cos(a) * dx + np.sin(a) * dz

    u = _fade(fx)
    v = _fade(fz)
    a = corner(ix, iz, fx, fz) * (1 - u) + corner(ix + 1, iz, fx - 1, fz) * u
    b = corner(ix, iz + 1, fx, fz - 1) * (1 - u) + corner(ix + 1, iz + 1, fx - 1, fz - 1) * u
    return (a * (1 - v) + b * v) * 1.41


def fbm2(x, z, octaves, seed):
    total = 0.0
    amp = 1.0
    norm = 0.0
    for i in range(octaves):
        total = total + perlin2(x, z, seed + i * 17) * amp
        norm += amp
        amp *= 0.5
        x = x * 2.03
        z = z * 2.03
    return total / norm


def value3(x, y, z, seed):
    ix = np.floor(x).astype(np.int64)
    iy = np.floor(y).astype(np.int64)
    iz = np.floor(z).astype(np.int64)
    u = _fade(x - ix)
    v = _fade(y - iy)
    w = _fade(z - iz)

    def lat(dx, dy, dz):
        return _hash(ix + dx, iz + dz, seed, iy + dy)

    c00 = lat(0, 0, 0) * (1 - u) + lat(1, 0, 0) * u
    c10 = lat(0, 1, 0) * (1 - u) + lat(1, 1, 0) * u
    c01 = lat(0, 0, 1) * (1 - u) + lat(1, 0, 1) * u
    c11 = lat(0, 1, 1) * (1 - u) + lat(1, 1, 1) * u
    return ((c00 * (1 - v) + c10 * v) * (1 - w) + (c01 * (1 - v) + c11 * v) * w)


def _smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# --- Форма деревьев --------------------------------------------------------

def _sphere(radius):
    r = int(np.ceil(radius))
    g = np.mgrid[-r:r + 1, -r:r + 1, -r:r + 1].reshape(3, -1).T
    return g[(g * g).sum(axis=1) <= radius * radius + 0.3]


def _cone(radius, height):
    cells = []
    for y in range(height):
        rad = radius * (1 - y / height) + 0.4
        r = int(np.ceil(rad))
        for dx in range(-r, r + 1):
            for dz in range(-r, r + 1):
                if dx * dx + dz * dz <= rad * rad:
                    cells.append((dx, y, dz))
    return np.array(cells)


CROWN_SHAPES = [_sphere(2.2), _sphere(2.7), _sphere(3.2)]
FROST_SHAPES = [_cone(3.0, 6), _cone(3.5, 8)]
TREE_MARGIN = 4
TREE_CELL = 8


class World:
    realm = "surface"
    title = ""
    look = None         # оформление неба и света, см. realms.py
    fixed_time = None   # время суток, если в измерении оно не меняется
    hostile_names = ()  # какие враги появляются в особом измерении
    has_boss = False    # живёт ли здесь главный босс
    boss_done = False   # побеждён ли он навсегда

    def __init__(self, seed=None, save_path=None):
        self.save_path = save_path
        self.edits = {}
        self.chunks = {}
        self.saved_player = None
        self.saved_realms = {}
        self.saved_realm_chests = {}
        self.chests = {}    # содержимое открытых сундуков: (x, y, z) -> список стопок
        self.dropped = []   # лежащие предметы (при выходе из игры не сохраняются)
        loaded = self._load()
        if not loaded:
            self.seed = int(seed) if seed is not None else int.from_bytes(os.urandom(3), "little")
        # Импорт здесь: модуль villages сам использует константы этого файла.
        from villages import Villages
        self.villages = Villages(self)

    # --- Сохранение ---------------------------------------------------------

    def _load(self):
        if not self.save_path or not os.path.exists(self.save_path):
            return False
        with open(self.save_path, encoding="utf-8") as f:
            data = json.load(f)
        self.seed = data["seed"]
        self.saved_player = data.get("player")
        self.load_edits(data["edits"])
        self.saved_realms = data.get("realms", {})
        self.saved_realm_chests = data.get("realm_chests", {})
        self.load_chests(data.get("chests", {}))
        return True

    def load_edits(self, data):
        for key, cells in data.items():
            cx, cz = map(int, key.split(","))
            self.edits[(cx, cz)] = {int(i): int(b) for i, b in cells.items()}

    def load_chests(self, data):
        for key, slots in data.items():
            self.chests[tuple(int(v) for v in key.split(","))] = slots

    def chests_json(self):
        return {f"{x},{y},{z}": slots for (x, y, z), slots in self.chests.items()}

    def edits_json(self):
        return {f"{cx},{cz}": {str(i): b for i, b in cells.items()} for (cx, cz), cells in self.edits.items()}

    def save(self, player=None, realms=None):
        """realms — другие открытые измерения: {имя: World}."""
        if not self.save_path:
            return
        data = {
            "seed": self.seed,
            "player": player,
            "edits": self.edits_json(),
            "realms": {**self.saved_realms, **{name: w.edits_json() for name, w in (realms or {}).items()}},
            "chests": self.chests_json(),
            "realm_chests": {**self.saved_realm_chests, **{name: w.chests_json() for name, w in (realms or {}).items()}},
        }
        os.makedirs(os.path.dirname(self.save_path), exist_ok=True)
        tmp = self.save_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, self.save_path)

    # --- Доступ к блокам ----------------------------------------------------

    def get(self, x, y, z):
        """Номер блока; None, если чанк ещё не загружен."""
        if y < 0:
            return BASE
        if y >= HEIGHT:
            return AIR
        c = self.chunks.get((x >> 4, z >> 4))
        return None if c is None else int(c[x & 15, y, z & 15])

    def set(self, x, y, z, block):
        key = (x >> 4, z >> 4)
        c = self.chunks.get(key)
        if c is None or not 0 <= y < HEIGHT:
            return False
        c[x & 15, y, z & 15] = block
        self.edits.setdefault(key, {})[(x & 15) + (z & 15) * 16 + y * 256] = block
        return True

    def apply_edit(self, x, y, z, block):
        """Правка из сети: запоминается, даже если чанк сейчас не загружен."""
        if not self.set(x, y, z, block) and 0 <= y < HEIGHT:
            self.edits.setdefault((x >> 4, z >> 4), {})[(x & 15) + (z & 15) * 16 + y * 256] = block

    def apply_edits_to(self, key, arr):
        # Копия нужна: правка из сети может прийти, пока чанк строится в другом потоке.
        for index, block in list(self.edits.get(key, {}).items()):
            arr[index & 15, index >> 8, (index >> 4) & 15] = block

    def padded(self, key, pad):
        """Копия чанка с полями шириной pad из соседних чанков и по 1 слою снизу и сверху."""
        cx, cz = key
        size = CHUNK + 2 * pad
        out = np.zeros((size, HEIGHT + 2, size), dtype=np.uint8)
        out[:, 0, :] = BASE
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                src = self.chunks[(cx + dx, cz + dz)]
                x0 = max(0, pad + dx * CHUNK)
                x1 = min(size, pad + (dx + 1) * CHUNK)
                z0 = max(0, pad + dz * CHUNK)
                z1 = min(size, pad + (dz + 1) * CHUNK)
                sx = x0 - (pad + dx * CHUNK)
                sz = z0 - (pad + dz * CHUNK)
                out[x0:x1, 1:HEIGHT + 1, z0:z1] = src[sx:sx + x1 - x0, :, sz:sz + z1 - z0]
        return out

    # --- Генерация ----------------------------------------------------------

    def surface(self, x, z):
        """Высота поверхности и «температура» для массивов координат."""
        s = self.seed
        x = np.asarray(x, dtype=np.float64)
        z = np.asarray(z, dtype=np.float64)
        cont = fbm2(x / 420.0, z / 420.0, 4, s + 1)
        hills = fbm2(x / 110.0, z / 110.0, 4, s + 101)
        ridge = 1.0 - np.abs(perlin2(x / 170.0, z / 170.0, s + 201)) * 2.0
        peaks = _smooth(0.1, 0.42, cont) * np.clip(ridge, 0, 1) ** 2
        h = SEA + 6 + cont * 38 + hills * 14 + peaks * 34
        h = np.clip(np.floor(h), 3, HEIGHT - 16).astype(np.int64)
        temp = fbm2(x / 600.0, z / 600.0, 3, s + 301)
        return h, temp

    def generate(self, key):
        cx, cz = key
        ox, oz = cx * CHUNK, cz * CHUNK
        X, Z = np.meshgrid(ox + np.arange(CHUNK), oz + np.arange(CHUNK), indexing="ij")
        h, temp = self.surface(X, Z)

        top = np.full(h.shape, TURF, dtype=np.uint8)
        fill = np.full(h.shape, SOIL, dtype=np.uint8)
        desert = temp > 0.16
        frost = temp < -0.16
        top[desert] = SAND
        fill[desert] = SAND
        top[frost] = SNOW
        beach = h <= SEA + 1
        top[beach] = SAND
        fill[beach] = SAND
        crag = h > SEA + 34
        top[crag] = ROCK
        fill[crag] = ROCK
        top[h > SEA + 44] = SNOW

        Y = np.arange(HEIGHT)[None, :, None]
        hh = h[:, None, :]
        arr = np.where(Y < hh - 3, ROCK,
                       np.where(Y < hh, fill[:, None, :],
                                np.where(Y == hh, top[:, None, :],
                                         np.where(Y <= SEA, WATER, AIR)))).astype(np.uint8)

        self._carve(arr, X, Z, h)
        arr[:, 0, :] = BASE
        villages = self.villages.near(ox, oz, ox + CHUNK, oz + CHUNK)
        self._plant_trees(arr, ox, oz, villages)
        self.villages.stamp(arr, ox, oz, villages)

        self.apply_edits_to(key, arr)
        return arr

    def _carve(self, arr, X, Z, h):
        """Пещеры и залежи."""
        s = self.seed
        top = int(h.max()) + 1
        ys = np.arange(top)[None, :, None]
        x = X[:, None, :].astype(np.float64)
        z = Z[:, None, :].astype(np.float64)
        y = np.broadcast_to(ys, (CHUNK, top, CHUNK)).astype(np.float64)
        x = np.broadcast_to(x, y.shape)
        z = np.broadcast_to(z, y.shape)
        view = arr[:, :top, :]

        ore = value3(x / 5.0, y / 5.0, z / 5.0, s + 500)
        view[(view == ROCK) & (ore > 0.84) & (ys < 58)] = AMBER
        glow = value3(x / 6.5, y / 6.5, z / 6.5, s + 600)
        view[(view == ROCK) & (glow > 0.88) & (ys < 34)] = GLOW
        # Чем глубже, тем ценнее: (сдвиг шума, масштаб, порог, глубже какого уровня, блок).
        for shift, scale, threshold, below, block in ((1000, 4.5, 0.87, 72, COPPER_ORE), (1100, 4.5, 0.88, 52, IRON_ORE),
                                                      (1200, 4.0, 0.89, 30, SILVER_ORE), (1300, 3.5, 0.91, 18, RUBY_ORE)):
            noise = value3(x / scale, y / scale, z / scale, s + shift)
            view[(view == ROCK) & (noise > threshold) & (ys < below)] = block

        a = value3(x / 26.0, y / 17.0, z / 26.0, s + 700)
        b = value3(x / 26.0, y / 17.0, z / 26.0, s + 800)
        hh = h[:, None, :]
        tunnel = (np.abs(a - 0.5) < 0.05) & (np.abs(b - 0.5) < 0.05)
        allowed = (ys > 2) & (((hh > SEA + 1) & (ys <= hh)) | (ys < hh - 8))
        view[tunnel & allowed] = AIR

    def _plant_trees(self, arr, ox, oz, villages):
        s = self.seed
        gx0 = (ox - TREE_MARGIN) // TREE_CELL
        gx1 = (ox + CHUNK + TREE_MARGIN) // TREE_CELL
        gz0 = (oz - TREE_MARGIN) // TREE_CELL
        gz1 = (oz + CHUNK + TREE_MARGIN) // TREE_CELL
        gx, gz = np.meshgrid(np.arange(gx0, gx1 + 1, dtype=np.int64),
                             np.arange(gz0, gz1 + 1, dtype=np.int64), indexing="ij")
        gx = gx.ravel()
        gz = gz.ravel()
        tx = gx * TREE_CELL + (_hash(gx, gz, s + 900) * TREE_CELL).astype(np.int64)
        tz = gz * TREE_CELL + (_hash(gx, gz, s + 901) * TREE_CELL).astype(np.int64)
        h, temp = self.surface(tx, tz)
        forest = fbm2(tx / 90.0, tz / 90.0, 2, s + 902)
        chance = _hash(gx, gz, s + 903)
        kind = _hash(gx, gz, s + 904)
        keep = (h > SEA + 1) & (h <= SEA + 32) & (temp <= 0.16) & (chance < 0.25 + forest * 1.4)
        keep &= ~self.villages.covers(tx, tz, villages)

        for i in np.nonzero(keep)[0]:
            base = int(h[i]) + 1
            trunk_h = 5 + int(kind[i] * 3)
            if temp[i] < -0.16:
                shape = FROST_SHAPES[int(kind[i] * 2)]
                crown = FROST_CROWN
                centre = base + 2
            else:
                shape = CROWN_SHAPES[int(kind[i] * 3)]
                crown = CROWN
                centre = base + trunk_h
            self._stamp(arr, shape + (int(tx[i]) - ox, centre, int(tz[i]) - oz), crown)
            lx = int(tx[i]) - ox
            lz = int(tz[i]) - oz
            if 0 <= lx < CHUNK and 0 <= lz < CHUNK:
                top = base + trunk_h + (3 if crown == FROST_CROWN else 0)
                arr[lx, base:top, lz] = TRUNK

    @staticmethod
    def _stamp(arr, cells, block):
        ok = ((cells[:, 0] >= 0) & (cells[:, 0] < CHUNK) & (cells[:, 2] >= 0) & (cells[:, 2] < CHUNK)
              & (cells[:, 1] >= 0) & (cells[:, 1] < HEIGHT))
        c = cells[ok]
        air = arr[c[:, 0], c[:, 1], c[:, 2]] == AIR
        c = c[air]
        arr[c[:, 0], c[:, 1], c[:, 2]] = block

    def find_spawn(self):
        """Ближайшая к центру суша: координаты ног игрока."""
        for r in range(0, 4000, 16):
            xs = np.arange(-r, r + 1, 16, dtype=np.int64)
            X, Z = np.meshgrid(xs, xs, indexing="ij")
            h, _ = self.surface(X, Z)
            land = (h > SEA + 2) & (h < SEA + 30)
            if land.any():
                i, j = np.argwhere(land)[0]
                return int(X[i, j]) + 0.5, int(h[i, j]) + 1.0, int(Z[i, j]) + 0.5
        return 0.5, HEIGHT - 2.0, 0.5
