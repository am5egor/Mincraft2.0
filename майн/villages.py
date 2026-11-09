"""Деревни: планировка домов, площади и троп. Результат зависит только от зерна мира."""
import math
import random
from collections import namedtuple

import numpy as np

from world import (AIR, BRICK, CHEST, CHUNK, DOOR_BLOCK, FORGE, GLASS, GLOW, HEIGHT, PATH, PLANKS, ROCK, SAND, SEA, SNOW, SOIL, TRUNK,
                   WATER, WORKBENCH)

CELL = 176
CHANCE = 0.6
EDGE = 56
RADIUS = 34
WALL_HEIGHT = 3
PLAZA = 6
MAX_SLOPE = 3
MIN_HOUSES = 3

# door — клетка у входа, inside — центр дома, strip — точки прогулок, floor — высота пола,
# gate — клетка с самой дверью (x, z).
House = namedtuple("House", "door inside strip floor gate chest", defaults=(None, None))
Village = namedtuple("Village", "key x z cells houses chests")


def _sign(v):
    return (v > 0) - (v < 0)


class Villages:
    def __init__(self, world):
        self.world = world
        self.cache = {}

    def at(self, gx, gz):
        key = (gx, gz)
        if key not in self.cache:
            self.cache[key] = self._plan(gx, gz)
        return self.cache[key]

    def near(self, x0, z0, x1, z1):
        """Деревни, зона которых пересекает прямоугольник."""
        found = []
        for gx in range(math.floor((x0 - RADIUS) / CELL), math.floor((x1 + RADIUS) / CELL) + 1):
            for gz in range(math.floor((z0 - RADIUS) / CELL), math.floor((z1 + RADIUS) / CELL) + 1):
                v = self.at(gx, gz)
                if v and x0 - RADIUS <= v.x <= x1 + RADIUS and z0 - RADIUS <= v.z <= z1 + RADIUS:
                    found.append(v)
        return found

    def covers(self, xs, zs, villages):
        """Какие точки лежат внутри деревень (там не растут деревья)."""
        inside = np.zeros(len(xs), dtype=bool)
        for v in villages:
            inside |= (xs - v.x) ** 2 + (zs - v.z) ** 2 <= RADIUS * RADIUS
        return inside

    def stamp(self, arr, ox, oz, villages):
        for v in villages:
            c = v.cells
            ok = (c[:, 0] >= ox) & (c[:, 0] < ox + CHUNK) & (c[:, 2] >= oz) & (c[:, 2] < oz + CHUNK)
            part = c[ok]
            # При повторах координат NumPy оставляет последнее значение: дома перекрывают тропы.
            arr[part[:, 0] - ox, part[:, 1], part[:, 2] - oz] = part[:, 3]

    # --- Планировка ----------------------------------------------------------

    def _surface(self, xs, zs):
        return self.world.surface(np.array(xs, dtype=np.int64), np.array(zs, dtype=np.int64))

    def _plan(self, gx, gz):
        rng = random.Random(f"{self.world.seed}:{gx}:{gz}")
        if rng.random() > CHANCE:
            return None
        cx = gx * CELL + rng.randint(EDGE, CELL - EDGE)
        cz = gz * CELL + rng.randint(EDGE, CELL - EDGE)

        span = np.arange(-PLAZA, PLAZA + 1)
        X, Z = np.meshgrid(cx + span, cz + span, indexing="ij")
        ground, temp = self._surface(X, Z)
        hc = int(ground[PLAZA, PLAZA])
        if not SEA + 3 <= hc <= SEA + 28 or ground.max() - ground.min() > 4:
            return None
        warmth = float(temp[PLAZA, PLAZA])
        wall, roof = PLANKS, BRICK
        if warmth > 0.16:
            wall, roof = SAND, PLANKS
        elif warmth < -0.16:
            roof = SNOW

        cells = []

        def add(x, y, z, block):
            if 1 <= y < HEIGHT:
                cells.append((x, y, z, block))

        houses = []
        count = rng.randint(5, 7)
        ring = rng.randint(16, 20)
        base = rng.uniform(0.0, math.tau)
        for i in range(count):
            angle = base + i * math.tau / count + rng.uniform(-0.15, 0.15)
            house = self._house(add, rng, cx, cz, angle, ring, wall, roof)
            if house:
                houses.append(house)
        if len(houses) < MIN_HOUSES:
            return None

        roads = []
        add_late = cells[:]
        cells.clear()
        for h in houses:
            roads.append(self._path(add, h, cx, cz))
        self._plaza(add, cx, cz, hc)
        cells.extend(add_late)

        finished = [h._replace(strip=road) for h, road in zip(houses, roads)]
        return Village((gx, gz), cx, cz, np.array(cells, dtype=np.int32), finished, frozenset(h.chest for h in finished))

    def _path(self, add, house, cx, cz):
        """Тропа от входа к площади. Возвращает точки для прогулок жителей."""
        x0, z0 = house.strip
        dx, dz = cx + 0.5 - x0, cz + 0.5 - z0
        length = math.hypot(dx, dz)
        steps = max(1, int(length * 2))
        columns, walk = [], []
        for i in range(steps + 1):
            t = i / steps
            if (1.0 - t) * length < PLAZA + 1.0:
                break
            x, z = x0 + dx * t, z0 + dz * t
            ix, iz = math.floor(x), math.floor(z)
            columns.append((ix, iz))
            columns.append((ix + _sign(abs(dz) >= abs(dx)), iz + _sign(abs(dx) > abs(dz))))
            walk.append((x, z))
        columns = sorted(set(columns))
        xs, zs = zip(*columns)
        ground, _ = self._surface(xs, zs)
        for (x, z), y in zip(columns, ground.tolist()):
            if y > SEA:
                add(x, y, z, PATH)
        return tuple(walk)

    @staticmethod
    def _plaza(add, cx, cz, hc):
        for dx in range(-PLAZA, PLAZA + 1):
            for dz in range(-PLAZA, PLAZA + 1):
                if dx * dx + dz * dz > PLAZA * PLAZA + 4:
                    continue
                x, z = cx + dx, cz + dz
                for y in range(hc - 5, hc):
                    add(x, y, z, SOIL)
                add(x, hc, z, PATH)
                for y in range(hc + 1, hc + 7):
                    add(x, y, z, AIR)
        # Колодец: кольцо камня и вода внутри.
        for dx in range(-2, 3):
            for dz in range(-2, 3):
                x, z = cx + dx, cz + dz
                if max(abs(dx), abs(dz)) == 2:
                    add(x, hc, z, ROCK)
                    add(x, hc + 1, z, ROCK)
                else:
                    add(x, hc - 1, z, ROCK)
                    add(x, hc, z, WATER)
        # Фонари отгоняют ночных существ от площади.
        for dx, dz in ((PLAZA - 1, 0), (1 - PLAZA, 0), (0, PLAZA - 1), (0, 1 - PLAZA)):
            add(cx + dx, hc + 1, cz + dz, TRUNK)
            add(cx + dx, hc + 2, cz + dz, TRUNK)
            add(cx + dx, hc + 3, cz + dz, GLOW)

    def _house(self, add, rng, vx, vz, angle, ring, wall, roof):
        cx = vx + round(math.cos(angle) * ring)
        cz = vz + round(math.sin(angle) * ring)
        to_x, to_z = vx - cx, vz - cz
        if abs(to_x) > abs(to_z):
            fx, fz = _sign(to_x), 0
        else:
            fx, fz = 0, _sign(to_z)

        width, depth = rng.choice((2, 3)), rng.choice((2, 3))
        hx, hz = (depth, width) if fx else (width, depth)

        X, Z = np.meshgrid(np.arange(cx - hx - 1, cx + hx + 2), np.arange(cz - hz - 1, cz + hz + 2), indexing="ij")
        ground, _ = self._surface(X, Z)
        low, high = int(ground.min()), int(ground.max())
        if high - low > MAX_SLOPE or low <= SEA:
            return None
        floor = int(np.median(ground)) + 1

        for x in range(cx - hx - 1, cx + hx + 2):
            for z in range(cz - hz - 1, cz + hz + 2):
                for y in range(floor, floor + WALL_HEIGHT + 7):
                    add(x, y, z, AIR)

        for x in range(cx - hx, cx + hx + 1):
            for z in range(cz - hz, cz + hz + 1):
                for y in range(low - 2, floor - 1):
                    add(x, y, z, ROCK)
                add(x, floor - 1, z, PLANKS)
                edge_x, edge_z = abs(x - cx) == hx, abs(z - cz) == hz
                if edge_x or edge_z:
                    for y in range(floor, floor + WALL_HEIGHT):
                        add(x, y, z, TRUNK if edge_x and edge_z else wall)

        door_x, door_z = cx + fx * hx, cz + fz * hz
        for x, z in ((cx + hx, cz), (cx - hx, cz), (cx, cz + hz), (cx, cz - hz)):
            if (x, z) != (door_x, door_z):
                add(x, floor + 1, z, GLASS)
        # Закрытая створка стоит на внешнем краю дверного проёма.
        side = {(0, -1): 0, (1, 0): 1, (0, 1): 2, (-1, 0): 3}[(fx, fz)]
        door_block = DOOR_BLOCK[(0, side, False)]
        add(door_x, floor, door_z, door_block)
        add(door_x, floor + 1, door_z, door_block)

        # Крыша: кольца сходятся к коньку, нижний слой служит потолком.
        ax, az = hx + 1, hz + 1
        y = floor + WALL_HEIGHT
        layer = 0
        while ax >= 0 and az >= 0:
            for x in range(cx - ax, cx + ax + 1):
                for z in range(cz - az, cz + az + 1):
                    if layer == 0 or abs(x - cx) == ax or abs(z - cz) == az:
                        add(x, y, z, roof)
            ax -= 1
            az -= 1
            y += 1
            layer += 1

        add(cx, floor + WALL_HEIGHT - 1, cz, GLOW)
        chest_side = 1
        furniture = rng.random()
        if furniture < 0.6:
            side = rng.choice((-1, 1))
            if fx:
                spot = (cx - fx * (hx - 1), cz + side * (hz - 1))
            else:
                spot = (cx + side * (hx - 1), cz - fz * (hz - 1))
            add(spot[0], floor, spot[1], WORKBENCH if furniture < 0.4 else FORGE)
            chest_side = -side
        if fx:
            chest = (cx - fx * (hx - 1), floor, cz + chest_side * (hz - 1))
        else:
            chest = (cx + chest_side * (hx - 1), floor, cz - fz * (hz - 1))
        add(*chest, CHEST)

        for step in (1, 2):
            x, z = door_x + fx * step, door_z + fz * step
            for y in range(floor - 4, floor - 1):
                add(x, y, z, ROCK)
            add(x, floor - 1, z, PATH)
            for y in range(floor, floor + 4):
                add(x, y, z, AIR)

        door = (door_x + fx + 0.5, door_z + fz + 0.5)
        return House(door, (cx + 0.5, cz + 0.5), door, floor, (door_x, door_z), chest)
