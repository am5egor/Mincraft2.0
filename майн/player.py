"""Игрок и общая физика тел: движение, столкновения с блоками и луч выбора блока."""
import math

from world import AIR, BASE, BLOCKS, HEIGHT, LAVA, PANEL_BOX, WATER

HALF = 0.3
TALL = 1.8
EYE = 1.62
SKIN = 0.001
GRAVITY = 28.0
JUMP = 8.7
WALK = 4.4
SPRINT = 6.2
SNEAK = 1.6
FLY = 11.0
REACH = 6.0


def is_solid(block):
    return block is None or BLOCKS[block].solid


def ray_box(origin, direction, low, high):
    """Расстояние вдоль луча до коробки; 0, если начало внутри; None, если мимо."""
    near, far = 0.0, math.inf
    for i in range(3):
        if direction[i] == 0.0:
            if not low[i] <= origin[i] <= high[i]:
                return None
            continue
        a = (low[i] - origin[i]) / direction[i]
        b = (high[i] - origin[i]) / direction[i]
        if a > b:
            a, b = b, a
        near = max(near, a)
        far = min(far, b)
        if near > far:
            return None
    return near


class Body:
    """Прямоугольное тело, которое сталкивается с блоками. pos — точка под ногами."""

    def __init__(self, world, x, y, z, half, tall):
        self.world = world
        self.pos = [x, y, z]
        self.vel = [0.0, 0.0, 0.0]
        self.half = half
        self.tall = tall
        self.on_ground = False
        self.impact = 0.0

    def place_at(self, x, y, z):
        """Ставит тело в точку, поднимая его, пока оно застревает в блоках."""
        while y < HEIGHT - self.tall and self._collides(x, y, z):
            y += 1.0
        self.pos = [x, y, z]
        self.vel = [0.0, 0.0, 0.0]
        self.impact = 0.0

    def _collides(self, x, y, z):
        get = self.world.get
        half = self.half
        for ix in range(math.floor(x - half), math.floor(x + half) + 1):
            for iy in range(math.floor(y), math.floor(y + self.tall) + 1):
                for iz in range(math.floor(z - half), math.floor(z + half) + 1):
                    if is_solid(get(ix, iy, iz)):
                        return True
        return self._touches_panel(x, y, z)

    def _hits_solid(self, x, y, z):
        get = self.world.get
        half = self.half
        for ix in range(math.floor(x - half), math.floor(x + half) + 1):
            for iy in range(math.floor(y), math.floor(y + self.tall) + 1):
                for iz in range(math.floor(z - half), math.floor(z + half) + 1):
                    if is_solid(get(ix, iy, iz)):
                        return True
        return False

    def hits_box(self, x, y, z, cell, box):
        """Пересекает ли тело в точке (x, y, z) коробку box внутри клетки cell."""
        half = self.half
        return (x - half < cell[0] + box[3] and x + half > cell[0] + box[0]
                and y < cell[1] + box[4] and y + self.tall > cell[1] + box[1]
                and z - half < cell[2] + box[5] and z + half > cell[2] + box[2])

    def _touches_panel(self, x, y, z):
        get = self.world.get
        half = self.half
        for ix in range(math.floor(x - half), math.floor(x + half) + 1):
            for iy in range(math.floor(y), math.floor(y + self.tall) + 1):
                for iz in range(math.floor(z - half), math.floor(z + half) + 1):
                    box = PANEL_BOX.get(get(ix, iy, iz))
                    if box and self.hits_box(x, y, z, (ix, iy, iz), box):
                        return True
        return False

    def overlaps(self, x, y, z):
        """Пересекает ли тело ячейку блока (нужно при постройке)."""
        px, py, pz = self.pos
        half = self.half
        return (x < px + half and x + 1 > px - half and y < py + self.tall and y + 1 > py
                and z < pz + half and z + 1 > pz - half)

    def _move_axis(self, axis, delta):
        """Сдвиг по одной оси. Возвращает True, если упёрлись в блок."""
        if delta == 0.0:
            return False
        p = list(self.pos)
        p[axis] += delta
        if not self._collides(*p):
            self.pos = p
            return False
        if not self._hits_solid(*p):
            if self._touches_panel(*self.pos):  # створка закрылась на игроке: выйти можно
                self.pos = p
                return False
            return True  # у створки нет границы по сетке, поэтому просто останавливаемся
        low, high = (0.0, self.tall) if axis == 1 else (-self.half, self.half)
        if delta > 0:
            self.pos[axis] = math.floor(p[axis] + high) - high - SKIN
        else:
            self.pos[axis] = math.floor(p[axis] + low) + 1 - low + SKIN
        return True


class Player(Body):
    def __init__(self, world, x, y, z):
        super().__init__(world, x, y, z, HALF, TALL)
        self.yaw = 0.0
        self.pitch = -0.2
        self.flying = False
        self.in_water = False

    @property
    def eye(self):
        return (self.pos[0], self.pos[1] + EYE, self.pos[2])

    @property
    def look(self):
        cp = math.cos(self.pitch)
        return (math.sin(self.yaw) * cp, math.sin(self.pitch), -math.cos(self.yaw) * cp)

    def turn(self, dx, dy, sensitivity=0.0024):
        self.yaw = (self.yaw + dx * sensitivity) % math.tau
        self.pitch = max(-1.55, min(1.55, self.pitch - dy * sensitivity))

    def update(self, dt, forward, strafe, jump, down, sprint):
        """forward и strafe: -1..1; jump и down: удерживаемые клавиши."""
        # Большие шаги дробим, чтобы не проскакивать сквозь блоки.
        remaining = min(dt, 0.1)
        while remaining > 1e-5:
            step = min(remaining, 0.02)
            self._step(step, forward, strafe, jump, down, sprint)
            remaining -= step

    def _step(self, dt, forward, strafe, jump, down, sprint):
        x, y, z = self.pos
        self.in_water = self.world.get(math.floor(x), math.floor(y + 0.7), math.floor(z)) in (WATER, LAVA)

        sin, cos = math.sin(self.yaw), math.cos(self.yaw)
        wx = sin * forward + cos * strafe
        wz = -cos * forward + sin * strafe
        length = math.hypot(wx, wz)
        if length > 1:
            wx, wz = wx / length, wz / length

        if self.flying:
            speed = FLY * (2.2 if sprint else 1.0)
            rate = 10.0
            target_y = ((1 if jump else 0) - (1 if down else 0)) * speed
            self.vel[1] += (target_y - self.vel[1]) * min(1.0, rate * dt)
        else:
            speed = SNEAK if down and not self.in_water else (SPRINT if sprint else WALK)
            rate = 14.0 if self.on_ground else 4.0
            if self.in_water:
                speed *= 0.6
                rate = 8.0
                self.vel[1] = max(self.vel[1] - GRAVITY * 0.25 * dt, -3.5)
                if jump:
                    self.vel[1] = min(self.vel[1] + 30.0 * dt, 4.2)
                elif down:
                    self.vel[1] = max(self.vel[1] - 18.0 * dt, -4.2)
            else:
                self.vel[1] = max(self.vel[1] - GRAVITY * dt, -50.0)
                if jump and self.on_ground:
                    self.vel[1] = JUMP

        blend = min(1.0, rate * dt)
        self.vel[0] += (wx * speed - self.vel[0]) * blend
        self.vel[2] += (wz * speed - self.vel[2]) * blend

        if self._move_axis(0, self.vel[0] * dt):
            self.vel[0] = 0.0
        if self._move_axis(2, self.vel[2] * dt):
            self.vel[2] = 0.0
        falling = self.vel[1] < 0
        hit = self._move_axis(1, self.vel[1] * dt)
        self.on_ground = hit and falling
        if hit:
            if falling:
                self.impact = max(self.impact, -self.vel[1])
            self.vel[1] = 0.0

    def target(self):
        """Первый твёрдый блок на луче и пустая ячейка перед ним."""
        world = self.world
        origin = self.eye
        d = self.look
        cell = [math.floor(c) for c in origin]
        step = [1 if v > 0 else -1 for v in d]
        t_delta = [abs(1.0 / v) if v else math.inf for v in d]
        t_max = []
        for i in range(3):
            if d[i] > 0:
                t_max.append((cell[i] + 1 - origin[i]) / d[i])
            elif d[i] < 0:
                t_max.append((origin[i] - cell[i]) / -d[i])
            else:
                t_max.append(math.inf)

        previous = None
        t = 0.0
        while t <= REACH:
            block = world.get(*cell)
            if block is None:
                return None, None
            if block not in (AIR, WATER, LAVA):
                box = PANEL_BOX.get(block)
                # Луч проходит сквозь пустую часть клетки с дверью.
                if box is None or ray_box(origin, d, [cell[i] + box[i] for i in range(3)],
                                          [cell[i] + box[i + 3] for i in range(3)]) is not None:
                    return tuple(cell), previous
            previous = tuple(cell)
            axis = t_max.index(min(t_max))
            t = t_max[axis]
            t_max[axis] += t_delta[axis]
            cell[axis] += step[axis]
        return None, None


UNBREAKABLE = {BASE}
