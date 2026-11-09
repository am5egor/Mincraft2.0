"""Особые измерения: Ад с лавовым морем и Край из парящих островов."""
import numpy as np

from world import (AIR, ASH, BASE, CHUNK, EMBER_ORE, GLOW, HEIGHT, LAVA, PALE, STAR_ORE, World, _hash, _smooth, fbm2,
                   value3)

HELL_LAVA = 26
EDGE_LEVEL = 52
EDGE_GAP = 130.0


class NoVillages:
    """В особых измерениях деревень нет."""

    @staticmethod
    def near(*_):
        return []


def _spiral_search(shape, x, z):
    """Ближайшая подходящая точка рядом с (x, z): shape(X, Z) -> (годится, высота ног)."""
    cx, cz = int(np.floor(x)), int(np.floor(z))
    for r in range(0, 2400, 6):
        span = np.arange(-r, r + 1, 6, dtype=np.int64)
        X, Z = np.meshgrid(cx + span, cz + span, indexing="ij")
        ok, feet = shape(X, Z)
        if ok.any():
            distance = (X - cx) ** 2 + (Z - cz) ** 2
            distance = np.where(ok, distance, np.iinfo(np.int64).max)
            i, j = np.unravel_index(distance.argmin(), distance.shape)
            return float(X[i, j]) + 0.5, float(feet[i, j]), float(Z[i, j]) + 0.5
    return x, HEIGHT - 4.0, z


class HellWorld(World):
    realm = "hell"
    title = "Ад"
    fixed_time = 0.75
    hostile_names = ("Жаровик",)
    look = {"zenith": (0.16, 0.05, 0.05), "horizon": (0.3, 0.09, 0.06), "sun": (0.9, 0.55, 0.42),
            "ambient": (0.34, 0.2, 0.17), "stars": 0.0, "fog": 0.6}

    def __init__(self, seed):
        super().__init__(seed, None)
        self.villages = NoVillages()

    def _shape(self, X, Z):
        s = self.seed
        x, z = X.astype(np.float64), Z.astype(np.float64)
        floor = 34 + fbm2(x / 70.0, z / 70.0, 4, s + 2000) * 26 + fbm2(x / 18.0, z / 18.0, 2, s + 2010) * 6
        ceiling = 92 + fbm2(x / 60.0, z / 60.0, 3, s + 2020) * 14 - np.abs(fbm2(x / 9.0, z / 9.0, 2, s + 2030)) * 22
        pillar = fbm2(x / 26.0, z / 26.0, 2, s + 2040) > 0.42
        return np.floor(floor).astype(np.int64), np.floor(ceiling).astype(np.int64), pillar

    def generate(self, key):
        cx, cz = key
        X, Z = np.meshgrid(cx * CHUNK + np.arange(CHUNK), cz * CHUNK + np.arange(CHUNK), indexing="ij")
        floor, ceiling, pillar = self._shape(X, Z)
        Y = np.arange(HEIGHT)[None, :, None]
        low, high = floor[:, None, :], ceiling[:, None, :]
        solid = (Y <= low) | (Y >= high) | pillar[:, None, :]
        arr = np.where(solid, ASH, np.where(Y <= HELL_LAVA, LAVA, AIR)).astype(np.uint8)

        s = self.seed
        grid = np.broadcast_to(Y, arr.shape).astype(np.float64)
        x = np.broadcast_to(X[:, None, :], arr.shape).astype(np.float64)
        z = np.broadcast_to(Z[:, None, :], arr.shape).astype(np.float64)
        ore = value3(x / 4.5, grid / 4.5, z / 4.5, s + 2100)
        arr[(arr == ASH) & (ore > 0.85)] = EMBER_ORE
        crystal = value3(x / 6.0, grid / 6.0, z / 6.0, s + 2110)
        arr[(arr == ASH) & (crystal > 0.9)] = GLOW

        arr[:, 0, :] = BASE
        arr[:, HEIGHT - 1, :] = BASE
        self.apply_edits_to(key, arr)
        return arr

    def _landing(self, X, Z):
        floor, ceiling, pillar = self._shape(X, Z)
        return (floor > HELL_LAVA + 1) & (ceiling - floor > 6) & ~pillar, floor + 1

    def find_landing(self, x, z):
        return _spiral_search(self._landing, x, z)

    def find_spawn(self):
        return self.find_landing(0.5, 0.5)


class EdgeWorld(World):
    realm = "edge"
    title = "Край"
    fixed_time = 0.75
    hostile_names = ("Пустотник",)
    has_boss = True
    look = {"zenith": (0.03, 0.02, 0.1), "horizon": (0.13, 0.08, 0.26), "sun": (0.78, 0.72, 0.95),
            "ambient": (0.16, 0.13, 0.25), "stars": 1.0, "fog": 1.0}

    def __init__(self, seed):
        super().__init__(seed, None)
        self.villages = NoVillages()

    def get(self, x, y, z):
        return AIR if y < 0 else super().get(x, y, z)  # под островами только пустота

    def _shape(self, X, Z):
        """Верх и низ островов; там, где острова нет, верх равен -1."""
        s = self.seed
        x, z = X.astype(np.float64), Z.astype(np.float64)
        r = np.hypot(x, z)
        main = 1.0 - r / 90.0 + fbm2(x / 40.0, z / 40.0, 3, s + 3000) * 0.35
        outer = (fbm2(x / 150.0, z / 150.0, 3, s + 3010) - 0.2) * 3.2 * _smooth(EDGE_GAP, EDGE_GAP + 30.0, r)
        t = np.clip(np.maximum(main, outer), 0.0, 1.0)
        top = np.floor(EDGE_LEVEL + t * 8 + fbm2(x / 30.0, z / 30.0, 2, s + 3020) * 3).astype(np.int64)
        bottom = top - np.floor(3 + t * 30 + np.abs(fbm2(x / 12.0, z / 12.0, 2, s + 3030)) * 8).astype(np.int64)
        return np.where(t > 0.0, top, -1), bottom, t

    def generate(self, key):
        cx, cz = key
        X, Z = np.meshgrid(cx * CHUNK + np.arange(CHUNK), cz * CHUNK + np.arange(CHUNK), indexing="ij")
        top, bottom, t = self._shape(X, Z)
        Y = np.arange(HEIGHT)[None, :, None]
        hh = top[:, None, :]
        solid = (hh >= 0) & (Y <= hh) & (Y >= bottom[:, None, :])
        arr = np.where(solid, PALE, AIR).astype(np.uint8)

        s = self.seed
        grid = np.broadcast_to(Y, arr.shape).astype(np.float64)
        x = np.broadcast_to(X[:, None, :], arr.shape).astype(np.float64)
        z = np.broadcast_to(Z[:, None, :], arr.shape).astype(np.float64)
        ore = value3(x / 4.0, grid / 4.0, z / 4.0, s + 3100)
        arr[(arr == PALE) & (ore > 0.84) & (Y < hh - 2)] = STAR_ORE

        # Кристальные шпили стоят на одном столбце и не пересекают границы чанков.
        chance = _hash(X.astype(np.int64), Z.astype(np.int64), s + 3200)
        rise = (_hash(X.astype(np.int64), Z.astype(np.int64), s + 3201) * 9).astype(np.int64) + 5
        for i, j in np.argwhere((chance < 0.006) & (t > 0.3)):
            y0 = int(top[i, j]) + 1
            y1 = y0 + int(rise[i, j])
            arr[i, y0:y1, j] = PALE
            arr[i, y1, j] = GLOW

        self.apply_edits_to(key, arr)
        return arr

    def _landing(self, X, Z):
        top, _, t = self._shape(X, Z)
        return (top >= 0) & (t > 0.12), top + 1

    def find_landing(self, x, z):
        return _spiral_search(self._landing, x, z)

    def find_spawn(self):
        return self.find_landing(0.5, 0.5)


REALMS = {"hell": HellWorld, "edge": EdgeWorld}
