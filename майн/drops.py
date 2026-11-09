"""Выброшенные предметы: падают, лежат в мире и подбираются игроками."""
import itertools
import math

from mobs import ITEM_COLORS
from player import Body
from survival import TIER_COLORS, TOOLS, is_block

DROP_LIFE = 300.0
PICKUP_DELAY = 1.5
PICKUP_RADIUS = 1.5
_GRAVITY = 18.0
_ids = itertools.count(1)
_DEFAULT_COLOR = (0.98, 0.69, 0.28)


class Drop(Body):
    def __init__(self, world, item, count, durability, pos, vel=(0.0, 0.0, 0.0)):
        super().__init__(world, *pos, 0.13, 0.26)
        self.id = next(_ids)
        self.item = item
        self.count = count
        self.durability = durability
        self.vel = list(vel)
        self.age = 0.0
        self.delay = PICKUP_DELAY

    def step(self, dt):
        dt = min(dt, 0.05)
        self.age += dt
        self.delay -= dt
        self.vel[1] = max(self.vel[1] - _GRAVITY * dt, -20.0)
        if self.on_ground:
            self.vel[0] *= max(0.0, 1.0 - 8.0 * dt)
            self.vel[2] *= max(0.0, 1.0 - 8.0 * dt)
        for axis in (0, 2):
            if self._move_axis(axis, self.vel[axis] * dt):
                self.vel[axis] = 0.0
        falling = self.vel[1] < 0.0
        hit = self._move_axis(1, self.vel[1] * dt)
        self.on_ground = hit and falling
        if hit:
            self.vel[1] = 0.0


def drop_parts(drop, light, block_colors):
    """Вращающийся значок предмета на земле."""
    x, y, z = drop.pos
    block = is_block(drop.item)
    tool = TOOLS.get(drop.item)
    if block:
        color = block_colors[drop.item]
    elif tool:
        color = tuple(v / 255.0 for v in TIER_COLORS[tool.tier])
    else:
        color = ITEM_COLORS.get(drop.item, _DEFAULT_COLOR)
    size = 0.26 if block else 0.18
    bob = 0.14 + math.sin(drop.age * 3.0) * 0.05
    return [(x, y, z, 0.0, bob, 0.0, size, size, size, drop.age * 1.8, 0.0, *color, light, 0.0)]
