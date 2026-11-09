"""Существа: модели из прямоугольных частей, поведение, появление и бой."""
import itertools
import math
import random
import time
from collections import namedtuple

import numpy as np

from player import HALF, TALL, Body, is_solid, ray_box
from survival import ARMOR, BOOTS, CHESTPLATE, HELMET, LEGGINGS, COOKED_MEAT, DRAGON_SCALE, DUSK, FLUFF as FLUFF_ITEM, FOOD, STAR, FRUIT, MEAT, THORN, TIER_COLORS, TOOLS, AXE, PICK, SHOVEL, SWORD, is_block
from world import AIR, DOOR_BLOCK, DOOR_STATE, GLOW, HEIGHT, LAVA, OPAQUE, PANEL_BOX, SNOW, TURF, WATER

ATTACK_REACH = 3.6
SIGHT = 26.0
DESPAWN = 70.0
SPAWN_PERIOD = 1.0
SPAWN_TRIES = 4
SPAWN_NEAR, SPAWN_FAR = 18.0, 40.0
MAX_PASSIVE = 10
MAX_HOSTILE = 14
RESIDENT_RANGE = 56.0
ARRIVE = 0.4
WAYPOINT_PATIENCE = 8.0
PUFF_HOP = 5.2
DOOR_REACH = 1.7
DOOR_LEAVE = 1.6
DRAGON_CIRCLE = 11.0
DRAGON_SWOOP = 5.0
DRAGON_REST = 8.0
DRAGON_ORBIT = 34.0
DRAGON_RANGE = 64.0
DRAGON_CONTACT = 4.2
DRAGON_PERCH_OFFSET = 9.0
DRAGON_BOLT_SPEED = 24.0
DRAGON_BOLT_DAMAGE = 4
LAMP_LEVEL = 0.68
SAFE_LIGHT_RADIUS = 6
MOB_GRAVITY = 28.0
MOB_JUMP = 8.2
MAX_STEP = 0.033
THORN_SPEED = 16.0
THORN_GRAVITY = 12.0
THORN_DAMAGE = 3
SHOOT_RANGE = 16.0
THINK_REFRESH = 0.4


def _c(r, g, b):
    return (r / 255.0, g / 255.0, b / 255.0)


# Часть модели: смещение центра, размер, цвет, группа движения, светится ли.
# Группы: 0 — неподвижна, 1 и 2 — ноги в противофазе, 3 — руки.
Part = namedtuple("Part", "off size color group glow")


def _p(off, size, color, group=0, glow=False):
    return Part(off, size, color, group, glow)


CREAM, MOSS, ROSE = _c(222, 214, 186), _c(106, 196, 160), _c(236, 124, 138)
BARK, AMBER_GLOW, DARK = _c(116, 80, 110), _c(250, 176, 72), _c(30, 26, 44)
GRAZER_PARTS = [
    _p((0, 0.55, 0), (0.8, 0.55, 1.0), CREAM),
    _p((0, 0.87, 0.05), (0.7, 0.12, 0.85), MOSS),
    _p((0.16, 0.98, 0.2), (0.13, 0.1, 0.13), ROSE),
    _p((-0.18, 0.98, -0.12), (0.11, 0.09, 0.11), ROSE),
    _p((0, 0.76, -0.64), (0.46, 0.42, 0.42), _c(204, 196, 168)),
    _p((0.13, 1.04, -0.64), (0.06, 0.2, 0.06), BARK),
    _p((-0.13, 1.04, -0.64), (0.06, 0.2, 0.06), BARK),
    _p((0.13, 1.17, -0.64), (0.1, 0.1, 0.1), AMBER_GLOW, 0, True),
    _p((-0.13, 1.17, -0.64), (0.1, 0.1, 0.1), AMBER_GLOW, 0, True),
    _p((0.13, 0.8, -0.86), (0.08, 0.09, 0.02), DARK),
    _p((-0.13, 0.8, -0.86), (0.08, 0.09, 0.02), DARK),
    _p((0.25, 0.16, 0.32), (0.17, 0.32, 0.17), _c(186, 176, 150), 1),
    _p((-0.25, 0.16, 0.32), (0.17, 0.32, 0.17), _c(186, 176, 150), 2),
    _p((0.25, 0.16, -0.32), (0.17, 0.32, 0.17), _c(186, 176, 150), 2),
    _p((-0.25, 0.16, -0.32), (0.17, 0.32, 0.17), _c(186, 176, 150), 1),
]

PLUM, DEEP, BONE = _c(84, 58, 116), _c(52, 38, 84), _c(232, 222, 202)
SHADE_PARTS = [
    _p((0.2, 0.3, 0), (0.25, 0.6, 0.27), DEEP, 1),
    _p((-0.2, 0.3, 0), (0.25, 0.6, 0.27), DEEP, 2),
    _p((0, 0.98, 0), (0.84, 0.8, 0.56), PLUM),
    _p((0, 1.36, 0.05), (1.02, 0.2, 0.66), DEEP),
    _p((0, 1.6, -0.12), (0.56, 0.5, 0.5), BONE),
    _p((0.14, 1.65, -0.38), (0.12, 0.1, 0.02), AMBER_GLOW, 0, True),
    _p((-0.14, 1.65, -0.38), (0.12, 0.1, 0.02), AMBER_GLOW, 0, True),
    _p((0, 1.46, -0.38), (0.3, 0.05, 0.02), DARK),
    _p((0.56, 0.94, -0.02), (0.2, 0.76, 0.22), PLUM, 3),
    _p((-0.56, 0.94, -0.02), (0.2, 0.76, 0.22), PLUM, 3),
]

BRAMBLE, SPINE = _c(74, 112, 92), _c(176, 216, 150)
BRISTLER_PARTS = [
    _p((0.3, 0.1, 0.3), (0.16, 0.26, 0.16), DEEP, 1),
    _p((-0.3, 0.1, 0.3), (0.16, 0.26, 0.16), DEEP, 2),
    _p((0.3, 0.1, -0.3), (0.16, 0.26, 0.16), DEEP, 2),
    _p((-0.3, 0.1, -0.3), (0.16, 0.26, 0.16), DEEP, 1),
    _p((0, 0.56, 0), (0.9, 0.7, 0.9), BRAMBLE),
    _p((0, 0.6, -0.46), (0.34, 0.14, 0.02), _c(244, 90, 170), 0, True),
    _p((0, 1.04, 0), (0.09, 0.3, 0.09), SPINE),
    _p((0.27, 1.0, 0.27), (0.08, 0.24, 0.08), SPINE),
    _p((-0.27, 1.0, 0.27), (0.08, 0.24, 0.08), SPINE),
    _p((0.27, 1.0, -0.27), (0.08, 0.24, 0.08), SPINE),
    _p((-0.27, 1.0, -0.27), (0.08, 0.24, 0.08), SPINE),
    _p((0.56, 0.62, 0.14), (0.24, 0.08, 0.08), SPINE),
    _p((-0.56, 0.62, 0.14), (0.24, 0.08, 0.08), SPINE),
    _p((0.56, 0.5, -0.2), (0.24, 0.08, 0.08), SPINE),
    _p((-0.56, 0.5, -0.2), (0.24, 0.08, 0.08), SPINE),
    _p((0.16, 0.66, 0.56), (0.08, 0.08, 0.24), SPINE),
    _p((-0.16, 0.5, 0.56), (0.08, 0.08, 0.24), SPINE),
]

PEACH, FLUFF, EAR = _c(244, 196, 160), _c(252, 226, 200), _c(232, 150, 140)
PUFF_PARTS = [
    _p((0, 0.38, 0), (0.62, 0.56, 0.68), PEACH),
    _p((0, 0.68, 0.04), (0.5, 0.1, 0.56), FLUFF),
    _p((0, 0.42, -0.34), (0.42, 0.34, 0.04), FLUFF),
    _p((0.15, 0.82, -0.08), (0.12, 0.34, 0.08), EAR),
    _p((-0.15, 0.82, -0.08), (0.12, 0.34, 0.08), EAR),
    _p((0.14, 0.5, -0.36), (0.08, 0.09, 0.02), DARK),
    _p((-0.14, 0.5, -0.36), (0.08, 0.09, 0.02), DARK),
    _p((0.22, 0.38, -0.34), (0.1, 0.07, 0.02), ROSE),
    _p((-0.22, 0.38, -0.34), (0.1, 0.07, 0.02), ROSE),
    _p((0, 0.46, 0.38), (0.2, 0.2, 0.12), FLUFF),
    _p((0.18, 0.08, -0.16), (0.16, 0.16, 0.2), EAR, 1),
    _p((-0.18, 0.08, -0.16), (0.16, 0.16, 0.2), EAR, 2),
    _p((0.18, 0.08, 0.18), (0.16, 0.16, 0.2), EAR, 2),
    _p((-0.18, 0.08, 0.18), (0.16, 0.16, 0.2), EAR, 1),
]


def _villager_parts(robe, trim):
    skin, straw = _c(226, 186, 156), _c(232, 200, 120)
    return [
        _p((0.13, 0.22, 0), (0.18, 0.44, 0.2), _c(92, 70, 60), 1),
        _p((-0.13, 0.22, 0), (0.18, 0.44, 0.2), _c(92, 70, 60), 2),
        _p((0, 0.76, 0), (0.56, 0.68, 0.42), robe),
        _p((0, 0.56, -0.22), (0.3, 0.26, 0.03), trim),
        _p((0, 0.99, -0.22), (0.56, 0.08, 0.03), trim),
        _p((0.35, 0.8, 0), (0.14, 0.56, 0.16), robe, 3),
        _p((-0.35, 0.8, 0), (0.14, 0.56, 0.16), robe, 3),
        _p((0, 1.32, 0), (0.42, 0.42, 0.42), skin),
        _p((0.1, 1.36, -0.22), (0.07, 0.08, 0.02), DARK),
        _p((-0.1, 1.36, -0.22), (0.07, 0.08, 0.02), DARK),
        _p((0, 1.24, -0.22), (0.14, 0.03, 0.02), _c(150, 92, 86)),
        _p((0, 1.56, 0), (0.92, 0.05, 0.92), straw),
        _p((0, 1.64, 0), (0.46, 0.12, 0.46), straw),
        _p((0, 1.72, 0), (0.24, 0.08, 0.24), _c(204, 170, 96)),
    ]


Kind = namedtuple("Kind", "name hp half tall speed hostile ranged damage reach cooldown drops parts voice")
PUFF = Kind("Пухляк", 5, 0.32, 0.8, 2.4, False, False, 0, 0, 0, [(FRUIT, 0, 1), (FLUFF_ITEM, 1, 2)], PUFF_PARTS, "puffer")
VILLAGERS = [
    Kind(job, 14, 0.28, 1.72, 1.6, False, False, 0, 0, 0, [], _villager_parts(robe, trim), "villager")
    for job, robe, trim in (("Рудокоп", _c(92, 134, 176), _c(232, 222, 190)),
                            ("Кузнец", _c(190, 104, 96), _c(250, 214, 150)),
                            ("Фермер", _c(112, 156, 110), _c(238, 226, 170)),
                            ("Травник", _c(150, 112, 176), _c(236, 216, 226)))
]

# Цель для существ: body — тело с полем pos, hit — вызов при уроне, prey — можно ли на неё нападать.
Target = namedtuple("Target", "body hit prey")
_mob_ids = itertools.count(1)


def _traveller_parts(color):
    skin, hood = _c(226, 190, 164), tuple(v * 0.72 for v in color)
    return [
        _p((0.13, 0.32, 0), (0.2, 0.64, 0.22), _c(66, 62, 88), 1),
        _p((-0.13, 0.32, 0), (0.2, 0.64, 0.22), _c(66, 62, 88), 2),
        _p((0, 0.98, 0), (0.56, 0.68, 0.32), color),
        _p((0.37, 0.98, 0), (0.16, 0.66, 0.2), color, 3),
        _p((-0.37, 0.98, 0), (0.16, 0.66, 0.2), color, 3),
        _p((0, 1.54, 0), (0.44, 0.44, 0.44), skin),
        _p((0.1, 1.58, -0.23), (0.07, 0.08, 0.02), DARK),
        _p((-0.1, 1.58, -0.23), (0.07, 0.08, 0.02), DARK),
        _p((0, 1.78, 0.03), (0.5, 0.14, 0.5), hood),
        _p((0, 1.58, 0.25), (0.5, 0.42, 0.08), hood),
    ]


PEER_MODELS = [_traveller_parts(_c(*rgb)) for rgb in
               ((236, 120, 92), (84, 168, 214), (244, 196, 84), (146, 110, 210), (98, 190, 130))]


def _limb(x_off, z_off, pivot_y, center_y, size, theta):
    """Смещение части, вращающейся вместе с конечностью вокруг её верхней точки.

    Шейдер вращает каждую часть вокруг её собственного верха, здесь это учитывается."""
    c, s = math.cos(theta), math.sin(theta)
    reach = pivot_y - center_y
    half = size[1] * 0.5
    return (x_off, pivot_y - reach * c - half * (1.0 - c), z_off - reach * s + half * s)


def peer_parts(peer, light, block_colors):
    """Модель игрока с бронёй и предметом в руке; shown — сглаженная позиция."""
    stride = math.sin(peer.phase) * 0.7
    arm = -1.7 * peer.swing + stride * 0.3
    swings = (0.0, stride, -stride, arm)
    x, y, z = peer.shown
    yaw = peer.yaw
    out = [(x, y, z, *p.off, *p.size, yaw, swings[p.group], *p.color, light, 0.0)
           for p in PEER_MODELS[peer.id % len(PEER_MODELS)]]

    def box(off, size, color, theta=0.0):
        out.append((x, y, z, *off, *size, yaw, theta, *color, light, 0.0))

    for item in peer.armor:
        if item is None or item not in ARMOR:
            continue
        slot = ARMOR[item].slot
        tone = tuple(v / 255.0 for v in TIER_COLORS[TOOLS[item].tier])
        dark = tuple(v * 0.72 for v in tone)
        if slot == HELMET:  # лицо остаётся открытым
            box((0, 1.84, 0.02), (0.56, 0.14, 0.6), tone)
            box((0, 1.62, 0.3), (0.56, 0.44, 0.06), dark)
            box((0.27, 1.62, 0.02), (0.06, 0.44, 0.56), dark)
            box((-0.27, 1.62, 0.02), (0.06, 0.44, 0.56), dark)
        elif slot == CHESTPLATE:
            box((0, 0.98, 0), (0.64, 0.74, 0.4), tone)
            for side in (0.37, -0.37):
                size = (0.24, 0.4, 0.28)
                box(_limb(side, 0.0, 1.31, 1.13, size, arm), size, dark, arm)
        elif slot == LEGGINGS:
            box((0, 0.67, 0), (0.6, 0.18, 0.38), dark)
            for side, theta in ((0.13, stride), (-0.13, -stride)):
                size = (0.26, 0.5, 0.28)
                box(_limb(side, 0.0, 0.64, 0.4, size, theta), size, tone, theta)
        elif slot == BOOTS:
            for side, theta in ((0.13, stride), (-0.13, -stride)):
                size = (0.27, 0.24, 0.32)
                box(_limb(side, -0.02, 0.64, 0.12, size, theta), size, tone, theta)

    held = peer.held
    if held is not None:
        tool = TOOLS.get(held)
        if is_block(held) and held < len(block_colors):
            size = (0.22, 0.22, 0.22)
            box(_limb(0.37, -0.1, 1.31, 0.58, size, arm), size, block_colors[held], arm)
        else:
            color = tuple(v / 255.0 for v in TIER_COLORS[tool.tier]) if tool else ITEM_COLORS.get(held, AMBER_GLOW)
            size = (0.07, 0.07, 0.62)
            box(_limb(0.37, -0.28, 1.31, 0.62, size, arm), size, color, arm)
    return out
GRAZER = Kind("Луговик", 8, 0.45, 1.05, 1.6, False, False, 0, 0, 0, [(MEAT, 1, 2), (FLUFF_ITEM, 0, 2)], GRAZER_PARTS, "grazer")
SHADE = Kind("Тенник", 16, 0.42, 1.85, 3.4, True, False, 4, 1.8, 1.0, [(DUSK, 0, 2)], SHADE_PARTS, "shade")
BRISTLER = Kind("Колючник", 12, 0.45, 1.15, 2.2, True, True, 0, 0, 2.2, [(THORN, 0, 2)], BRISTLER_PARTS, "bristler")

SCORCH, COAL, FLAME = _c(70, 46, 52), _c(40, 30, 38), _c(255, 128, 44)
EMBERLING_PARTS = [
    _p((0.22, 0.34, 0), (0.28, 0.68, 0.3), COAL, 1),
    _p((-0.22, 0.34, 0), (0.28, 0.68, 0.3), COAL, 2),
    _p((0, 1.08, 0), (0.96, 0.84, 0.62), SCORCH),
    _p((0.2, 1.12, -0.32), (0.1, 0.5, 0.02), FLAME, 0, True),
    _p((-0.14, 1.0, -0.32), (0.08, 0.4, 0.02), FLAME, 0, True),
    _p((0.62, 1.06, 0), (0.26, 0.82, 0.28), SCORCH, 3),
    _p((-0.62, 1.06, 0), (0.26, 0.82, 0.28), SCORCH, 3),
    _p((0, 1.72, -0.06), (0.52, 0.42, 0.46), COAL),
    _p((0.13, 1.76, -0.3), (0.12, 0.09, 0.02), FLAME, 0, True),
    _p((-0.13, 1.76, -0.3), (0.12, 0.09, 0.02), FLAME, 0, True),
    _p((0.3, 2.0, -0.06), (0.1, 0.34, 0.1), _c(220, 200, 170)),
    _p((-0.3, 2.0, -0.06), (0.1, 0.34, 0.1), _c(220, 200, 170)),
]
LILAC, INDIGO, GLINT = _c(186, 172, 234), _c(96, 76, 168), _c(120, 244, 255)
VOIDLING_PARTS = [
    _p((0, 0.86, 0), (0.86, 0.72, 0.86), LILAC),
    _p((0, 0.86, 0), (1.2, 0.12, 1.2), INDIGO),
    _p((0, 0.9, -0.44), (0.3, 0.3, 0.02), GLINT, 0, True),
    _p((0, 1.32, 0), (0.42, 0.2, 0.42), INDIGO),
    _p((0.3, 0.28, 0.2), (0.12, 0.54, 0.12), INDIGO, 1),
    _p((-0.3, 0.28, 0.2), (0.12, 0.54, 0.12), INDIGO, 2),
    _p((0, 0.28, -0.3), (0.12, 0.54, 0.12), INDIGO, 1),
]
EMBERLING = Kind("Жаровик", 26, 0.46, 2.0, 3.7, True, False, 5, 1.9, 1.4, [(DUSK, 0, 2)], EMBERLING_PARTS, "shade")
VOIDLING = Kind("Пустотник", 20, 0.46, 1.45, 2.6, True, True, 0, 0, 1.8, [(DUSK, 1, 3)], VOIDLING_PARTS, "bristler")
DRAGON = Kind("Лазурный дракон", 320, 2.7, 3.4, 15.0, True, False, 8, 0, 2.2,
              [(STAR, 6, 8), (DRAGON_SCALE, 6, 8)], [], "dragon")
KINDS = [GRAZER, PUFF, SHADE, BRISTLER, *VILLAGERS, EMBERLING, VOIDLING, DRAGON]

AZURE, AZURE_DEEP, BELLY = _c(58, 128, 222), _c(30, 72, 160), _c(190, 226, 250)
MEMBRANE, FROST_WHITE, EYE_GOLD = _c(44, 92, 188), _c(222, 244, 255), _c(255, 208, 90)
FROST_BOLT = _c(150, 226, 255)


def _dragon_parts(mob):
    """Модель дракона; крылья и хвост двигаются прямо здесь, поэтому части создаются каждый кадр."""
    x, y, z = mob.pos
    t = time.perf_counter()
    perched = mob.bar > 0.0  # у дракона это поле означает «сидит на земле»
    flap = math.sin(t * (1.6 if perched else 5.5)) * (0.1 if perched else 1.0)
    parts = []

    def box(off, size, color, glow=False):
        parts.append((x, y, z, *off, *size, mob.yaw, 0.0, *color, -1.0 if glow else 1.0, mob.flash))

    box((0, 2.1, 0), (2.1, 1.7, 4.3), AZURE)
    box((0, 1.25, 0), (1.7, 0.3, 3.9), BELLY)
    for i in range(6):
        box((0, 3.1, -2.0 + i * 0.8), (0.16, 0.5, 0.46), FROST_WHITE)
    for i in range(4):
        box((0, 2.5 + i * 0.42, -2.7 - i * 0.82), (1.15 - i * 0.1, 1.05 - i * 0.08, 1.05), AZURE)
    box((0, 4.3, -6.2), (1.15, 0.9, 1.5), AZURE)
    box((0, 3.95, -7.3), (0.8, 0.45, 1.0), AZURE_DEEP)
    box((0.42, 4.5, -6.75), (0.16, 0.16, 0.04), EYE_GOLD, True)
    box((-0.42, 4.5, -6.75), (0.16, 0.16, 0.04), EYE_GOLD, True)
    box((0.34, 5.0, -5.7), (0.16, 0.8, 0.16), FROST_WHITE)
    box((-0.34, 5.0, -5.7), (0.16, 0.8, 0.16), FROST_WHITE)
    for i in range(8):
        sway = math.sin(t * 2.2 + i * 0.6) * i * 0.16
        box((sway, 2.1 - i * 0.07, 2.7 + i * 0.95), (1.05 - i * 0.1, 0.95 - i * 0.09, 1.1), AZURE)
    box((math.sin(t * 2.2 + 4.8) * 1.3, 1.6, 10.3), (1.0, 0.14, 1.2), FROST_WHITE)
    for sx, sz in ((1.0, -1.4), (-1.0, -1.4), (1.0, 1.4), (-1.0, 1.4)):
        box((sx, 0.6, sz), (0.55, 1.25, 0.65), AZURE_DEEP)
    for side in (1, -1):
        for i in range(5):
            lift = flap * (i + 1) * 0.42
            box((side * (1.75 + i * 1.55), 2.8 + lift, 0.1 + i * 0.12), (1.6, 0.12, 3.7 - i * 0.55), MEMBRANE)
            box((side * (1.75 + i * 1.55), 2.92 + lift, -1.6 + i * 0.3), (1.6, 0.2, 0.24), AZURE_DEEP)
    return parts


class Mob(Body):
    def __init__(self, world, kind, x, y, z):
        super().__init__(world, x, y, z, kind.half, kind.tall)
        self.id = next(_mob_ids)
        self.kind = kind
        self.hp = kind.hp
        self.yaw = random.uniform(0.0, math.tau)
        self.wish = (0.0, 0.0)
        self.think = 0.0
        self.refresh = 0.0
        self.exposed = True
        self.sees = False
        self.phase = 0.0
        self.flash = 0.0
        self.bar = 0.0
        self.cool = kind.cooldown
        self.swing = 0.0
        self.stun = 0.0
        self.flee = 0.0
        self.voice_in = random.uniform(2.0, 12.0)
        self.home = None
        self.key = None
        self.plan = []
        self.plan_time = 0.0
        self.resting = False
        self.trading = False
        self.opened_door = False


class ThornShot:
    def __init__(self, pos, vel, damage=THORN_DAMAGE, gravity=THORN_GRAVITY, frost=False):
        self.pos = list(pos)
        self.vel = list(vel)
        self.life = 5.0
        self.damage = damage
        self.gravity = gravity
        self.frost = frost


class Mobs:
    def __init__(self, world):
        self.world = world
        self.mobs = []
        self.shots = []
        self.spawn_timer = 0.0
        self.events = []  # звуки за кадр: (имя, точка)
        self.door_moves = []  # клетки, которые изменили жители: (x, y, z, блок)
        self.sun = 1.0
        self.residents = set()
        self.killed = set()

    def _drop(self, mob):
        self.mobs.remove(mob)
        self.residents.discard(mob.key)

    # --- Освещённость и видимость --------------------------------------------

    def sky_exposed(self, x, y, z):
        c = self.world.chunks.get((x >> 4, z >> 4))
        if c is None or y >= HEIGHT:
            return True
        return not OPAQUE[c[x & 15, max(y, 0):, z & 15]].any()

    def light_at(self, pos):
        x, y, z = (math.floor(v) for v in pos)
        return 1.0 if self.sky_exposed(x, y, z) else 0.32

    def _near_lamp(self, x, y, z):
        get = self.world.get
        r = SAFE_LIGHT_RADIUS
        for dx in range(-r, r + 1):
            for dy in range(-3, 4):
                for dz in range(-r, r + 1):
                    if get(x + dx, y + dy, z + dz) == GLOW:
                        return True
        return False

    def line_clear(self, a, b):
        """Нет ли непрозрачных блоков между двумя точками."""
        d = math.dist(a, b)
        steps = max(1, int(d * 2))
        get = self.world.get
        for i in range(1, steps):
            t = i / steps
            block = get(math.floor(a[0] + (b[0] - a[0]) * t), math.floor(a[1] + (b[1] - a[1]) * t),
                        math.floor(a[2] + (b[2] - a[2]) * t))
            if block is None or OPAQUE[block] or (block in DOOR_STATE and not DOOR_STATE[block][2]):
                return False
        return True

    # --- Появление -----------------------------------------------------------

    def _try_spawn(self, player, sun):
        angle = random.uniform(0.0, math.tau)
        distance = random.uniform(SPAWN_NEAR, SPAWN_FAR)
        x = math.floor(player.pos[0] + math.cos(angle) * distance)
        z = math.floor(player.pos[2] + math.sin(angle) * distance)
        chunk = self.world.chunks.get((x >> 4, z >> 4))
        if chunk is None:
            return None
        column = chunk[x & 15, :, z & 15]
        if self.world.hostile_names:
            return self._spawn_in_realm(column, x, z, player.pos[1])
        solid = np.nonzero(OPAQUE[column])[0]
        if len(solid) == 0:
            return None
        surface = int(solid[-1]) + 1
        if surface + 2 >= HEIGHT or column[surface] != AIR:
            return None

        passive = sum(1 for m in self.mobs if not m.kind.hostile and m.home is None)
        hostile = sum(1 for m in self.mobs if m.kind.hostile)
        ground = column[surface - 1]
        if sun > 0.05:
            # Днём появляются только мирные существа.
            if passive < MAX_PASSIVE and ground in (TURF, SNOW) and random.random() < 0.5:
                return self._add(PUFF if ground == SNOW or random.random() < 0.45 else GRAZER, x, surface, z)
            return None
        if sun >= -0.03 or hostile >= MAX_HOSTILE:
            return None

        y = surface
        if random.random() < 0.3:
            y = self._cave_floor(column, surface, player.pos[1])
            if y is None:
                return None
        if self._near_lamp(x, y, z):
            return None
        return self._add(SHADE if random.random() < 0.65 else BRISTLER, x, y, z)

    def _spawn_in_realm(self, column, x, z, near_y):
        """В особых измерениях враги появляются всегда, на твёрдом полу рядом с высотой игрока."""
        if sum(1 for m in self.mobs if m.kind.hostile) >= MAX_HOSTILE:
            return None
        floors = np.nonzero(OPAQUE[column[:-2]] & (column[:-2] != LAVA)
                            & (column[1:-1] == AIR) & (column[2:] == AIR))[0] + 1
        if len(floors) == 0:
            return None
        y = int(floors[np.abs(floors - near_y).argmin()])
        if abs(y - near_y) > 18:
            return None
        names = self.world.hostile_names
        return self._add(next(k for k in KINDS if k.name == random.choice(names)), x, y, z)

    @staticmethod
    def _cave_floor(column, surface, near_y):
        """Высота пола пещеры в столбце, ближайшая к игроку."""
        floors = np.nonzero(OPAQUE[column[:-2]] & (column[1:-1] == AIR) & (column[2:] == AIR))[0] + 1
        floors = floors[floors < surface - 2]
        if len(floors) == 0:
            return None
        y = int(floors[np.abs(floors - near_y).argmin()])
        return y if abs(y - near_y) <= 18 else None

    def _add(self, kind, x, y, z):
        mob = Mob(self.world, kind, x + 0.5, float(y), z + 0.5)
        if mob._collides(*mob.pos):
            return None
        mob.exposed = self.sky_exposed(x, y, z)
        self.mobs.append(mob)
        return mob

    def _populate(self, player, sun):
        """Селит по одному жителю в каждый дом рядом с игроком."""
        px, pz = player.pos[0], player.pos[2]
        reach = RESIDENT_RANGE
        for village in self.world.villages.near(px - reach, pz - reach, px + reach, pz + reach):
            for index, house in enumerate(village.houses):
                key = (village.key, index)
                door = house.door
                if key in self.residents or key in self.killed or math.hypot(door[0] - px, door[1] - pz) > reach:
                    continue
                spot = house.inside if sun < 0.0 else door
                if self.world.get(math.floor(spot[0]), house.floor, math.floor(spot[1])) is None:
                    continue
                kind = VILLAGERS[hash(key) % len(VILLAGERS)]
                mob = Mob(self.world, kind, spot[0], float(house.floor), spot[1])
                mob.home = house
                mob.key = key
                mob.resting = sun < 0.0
                mob.exposed = self.sky_exposed(math.floor(spot[0]), house.floor, math.floor(spot[1]))
                self.mobs.append(mob)
                self.residents.add(key)

    # --- Бой -----------------------------------------------------------------

    def aimed(self, origin, direction, cell):
        """Ближайшее существо под прицелом, если его не заслоняет блок."""
        limit = ATTACK_REACH
        if cell:
            t = ray_box(origin, direction, cell, [v + 1 for v in cell])
            if t is not None:
                limit = min(limit, t)
        best, best_t = None, math.inf
        for mob in self.mobs:
            x, y, z = mob.pos
            pad = mob.half + 0.08
            t = ray_box(origin, direction, (x - pad, y, z - pad), (x + pad, y + mob.tall, z + pad))
            if t is not None and t <= limit and t < best_t:
                best, best_t = mob, t
        return best

    @staticmethod
    def _push(mob, source, strength):
        dx, dz = mob.pos[0] - source[0], mob.pos[2] - source[2]
        length = math.hypot(dx, dz) or 1.0
        mob.vel[0] = dx / length * strength
        mob.vel[2] = dz / length * strength
        mob.vel[1] = 5.0
        mob.stun = 0.3

    def hit(self, mob, damage, source):
        """Удар по существу. Возвращает выпавшие предметы, если оно погибло."""
        mob.hp -= damage
        mob.flash = 1.0
        if mob.kind is not DRAGON:
            mob.bar = 4.0
            self._push(mob, source, 7.0)
        if not mob.kind.hostile:
            mob.flee = 5.0
            mob.think = 0.0
        if mob.hp > 0:
            self.events.append((f"{mob.kind.voice}_hurt", tuple(mob.pos)))
            return []
        self.events.append((f"{mob.kind.voice}_die", tuple(mob.pos)))
        self._drop(mob)
        if mob.key:
            self.killed.add(mob.key)
        if mob.kind is DRAGON:
            self.world.boss_done = True
        drops = []
        for item, low, high in mob.kind.drops:
            count = random.randint(low, high)
            if count:
                drops.append((item, count))
        return drops

    # --- Поведение -----------------------------------------------------------

    def update(self, dt, player, day_time, on_hit, aggressive=True, others=()):
        """player — свой игрок (None, если он погиб), others — цели других игроков."""
        dt = min(dt, MAX_STEP)
        targets = list(others)
        if player is not None:
            targets.insert(0, Target(player, on_hit, aggressive))
        if dt <= 0.0 or not targets:
            return
        sun = math.sin(day_time * math.tau)
        self.sun = sun
        self.spawn_timer -= dt
        if self.spawn_timer <= 0.0:
            self.spawn_timer = SPAWN_PERIOD
            for target in targets:
                self._populate(target.body, sun)
            for _ in range(SPAWN_TRIES):
                self._try_spawn(random.choice(targets).body, sun)

        self._summon_boss(targets)
        for mob in list(self.mobs):
            focus = self._focus(mob, targets)
            if mob.kind is DRAGON:
                self._dragon(mob, focus, dt)
            elif self._alive_after_upkeep(mob, focus.body, sun, dt):
                self._act(mob, focus.body, dt, focus.hit, focus.prey)
                self._move(mob, dt)
        self._separate([t.body for t in targets])
        self._fly_shots(dt, targets)

    # --- Лазурный дракон ------------------------------------------------------

    def _summon_boss(self, targets):
        """Босс появляется, как только игроки прибывают в его измерение."""
        if not self.world.has_boss or self.world.boss_done or any(m.kind is DRAGON for m in self.mobs):
            return
        x, y, z = targets[0].body.pos
        mob = Mob(self.world, DRAGON, x + 32.0, min(y + 26.0, HEIGHT - 8.0), z)
        mob.state = "circle"
        mob.timer = DRAGON_CIRCLE
        mob.angle = 0.0
        mob.nest = [x, y + 26.0, z]
        mob.perch = None
        mob.bolts = 0
        mob.voice_in = 6.0
        mob.cool = 3.0
        self.mobs.append(mob)
        self.events.append(("dragon_idle", tuple(mob.pos)))

    def _ground_near(self, x, z):
        """Точка на вершине острова рядом с (x, z) или None, если там пустота."""
        for angle in (0.0, 1.57, 3.14, 4.71):
            px = math.floor(x + math.cos(angle) * DRAGON_PERCH_OFFSET)
            pz = math.floor(z + math.sin(angle) * DRAGON_PERCH_OFFSET)
            chunk = self.world.chunks.get((px >> 4, pz >> 4))
            if chunk is None:
                continue
            solid = np.nonzero(OPAQUE[chunk[px & 15, :, pz & 15]])[0]
            if len(solid):
                return [px + 0.5, float(solid[-1]) + 1.0, pz + 0.5]
        return None

    @staticmethod
    def _fly(mob, goal, speed, dt):
        """Полёт к точке сквозь воздух; возвращает оставшееся расстояние."""
        delta = [goal[i] - mob.pos[i] for i in range(3)]
        distance = math.sqrt(sum(v * v for v in delta))
        k = min(1.0, 4.0 * dt)
        for i in range(3):
            wanted = delta[i] / max(distance, 0.001) * min(speed, distance / max(dt, 0.001))
            mob.vel[i] += (wanted - mob.vel[i]) * k
            mob.pos[i] += mob.vel[i] * dt
        if math.hypot(mob.vel[0], mob.vel[2]) > 0.5:
            target = math.atan2(mob.vel[0], -mob.vel[2])
            mob.yaw += ((target - mob.yaw + math.pi) % math.tau - math.pi) * min(1.0, 5.0 * dt)
        return distance

    def _frost_bolt(self, mob, body, turn=0.0):
        """Ледяной заряд изо рта; turn поворачивает его в сторону."""
        start = (mob.pos[0] + math.sin(mob.yaw) * 7.0, mob.pos[1] + 3.8, mob.pos[2] - math.cos(mob.yaw) * 7.0)
        aim = [body.pos[0] - start[0], body.pos[1] + 1.2 - start[1], body.pos[2] - start[2]]
        c, s = math.cos(turn), math.sin(turn)
        aim[0], aim[2] = aim[0] * c - aim[2] * s, aim[0] * s + aim[2] * c
        length = math.sqrt(sum(v * v for v in aim)) or 1.0
        self.shots.append(ThornShot(start, [v / length * DRAGON_BOLT_SPEED for v in aim], DRAGON_BOLT_DAMAGE, 0.0, True))
        self.events.append(("frost_shot", start))

    def _dragon(self, mob, focus, dt):
        mob.flash = max(0.0, mob.flash - dt * 5.0)
        mob.cool -= dt
        mob.timer -= dt
        mob.voice_in -= dt
        if mob.voice_in <= 0.0:
            mob.voice_in = random.uniform(7.0, 14.0)
            self.events.append(("dragon_idle", tuple(mob.pos)))
        body = focus.body
        angry = mob.hp < mob.kind.hp * 0.5
        reload = mob.kind.cooldown * (0.6 if angry else 1.0)
        mob.bar = 0.0

        if mob.state == "circle":
            mob.angle += dt * 0.42
            goal = [mob.nest[0] + math.cos(mob.angle) * DRAGON_ORBIT, mob.nest[1],
                    mob.nest[2] + math.sin(mob.angle) * DRAGON_ORBIT]
            self._fly(mob, goal, mob.kind.speed, dt)
            if focus.prey and mob.cool <= 0.0 and math.dist(mob.pos, body.pos) < DRAGON_RANGE:
                mob.cool = reload
                self._frost_bolt(mob, body)
            if mob.timer <= 0.0:
                mob.state = "swoop"
                mob.timer = DRAGON_SWOOP

        elif mob.state == "swoop":
            distance = self._fly(mob, [body.pos[0], body.pos[1], body.pos[2]], mob.kind.speed * 1.5, dt)
            flat = math.hypot(mob.pos[0] - body.pos[0], mob.pos[2] - body.pos[2])
            struck = focus.prey and flat < DRAGON_CONTACT and abs(mob.pos[1] - body.pos[1]) < 4.5
            if struck:
                focus.hit(mob.kind.damage, tuple(mob.pos))
                self.events.append(("dragon_hurt", tuple(mob.pos)))
            if struck or distance < 2.5 or mob.timer <= 0.0:
                mob.perch = self._ground_near(body.pos[0], body.pos[2])
                mob.state = "land" if mob.perch else "circle"
                mob.timer = DRAGON_CIRCLE

        elif mob.state == "land":
            if self._fly(mob, mob.perch, mob.kind.speed * 0.8, dt) < 0.8:
                mob.pos = list(mob.perch)
                mob.vel = [0.0, 0.0, 0.0]
                mob.state = "rest"
                mob.timer = DRAGON_REST
                mob.cool = 1.5

        else:  # rest: дракон сидит на земле, и его можно достать мечом
            mob.bar = 1.0
            turn = (math.atan2(body.pos[0] - mob.pos[0], -(body.pos[2] - mob.pos[2])) - mob.yaw + math.pi) % math.tau - math.pi
            mob.yaw += turn * min(1.0, 2.5 * dt)
            if focus.prey and mob.cool <= 0.0:
                mob.cool = reload * 1.4
                for side in (-0.28, 0.0, 0.28):
                    self._frost_bolt(mob, body, side)
            if mob.timer <= 0.0:
                mob.state = "circle"
                mob.timer = DRAGON_CIRCLE
                mob.nest = [body.pos[0], min(body.pos[1] + 26.0, HEIGHT - 8.0), body.pos[2]]
                self.events.append(("dragon_idle", tuple(mob.pos)))

    @staticmethod
    def _focus(mob, targets):
        """Ближайшая цель; враждебные выбирают только тех, на кого можно напасть."""
        pool = [t for t in targets if t.prey] if mob.kind.hostile else targets
        return min(pool or targets, key=lambda t: math.dist(t.body.pos, mob.pos))

    def _alive_after_upkeep(self, mob, player, sun, dt):
        x, y, z = mob.pos
        ix, iy, iz = math.floor(x), math.floor(y), math.floor(z)
        if math.dist(mob.pos, player.pos) > DESPAWN or self.world.get(ix, iy, iz) is None:
            self._drop(mob)
            return False
        mob.flash = max(0.0, mob.flash - dt * 5.0)
        mob.bar = max(0.0, mob.bar - dt)
        mob.swing = max(0.0, mob.swing - dt * 4.0)
        mob.stun = max(0.0, mob.stun - dt)
        mob.flee = max(0.0, mob.flee - dt)
        mob.cool = max(0.0, mob.cool - dt)
        mob.voice_in -= dt
        if mob.voice_in <= 0.0:
            mob.voice_in = random.uniform(6.0, 16.0)
            self.events.append((f"{mob.kind.voice}_idle", tuple(mob.pos)))
        mob.refresh -= dt
        if mob.refresh <= 0.0:
            mob.refresh = THINK_REFRESH
            mob.exposed = self.sky_exposed(ix, iy + 1, iz)
            head = (x, y + mob.tall * 0.8, z)
            eye = (player.pos[0], player.pos[1] + 1.5, player.pos[2])
            mob.sees = math.dist(head, eye) <= SIGHT and self.line_clear(head, eye)
        if mob.kind.hostile and mob.exposed and sun > 0.1:
            # Враждебные существа тают на солнце и ничего не оставляют.
            mob.hp -= 4.0 * dt
            mob.flash = max(mob.flash, 0.4)
            if mob.hp <= 0:
                self._drop(mob)
                return False
        return True

    def _wander(self, mob, dt):
        mob.think -= dt
        if mob.think <= 0.0:
            mob.think = random.uniform(1.5, 5.0)
            if random.random() < 0.45:
                mob.wish = (0.0, 0.0)
            else:
                angle = random.uniform(0.0, math.tau)
                mob.wish = (math.cos(angle) * 0.7, math.sin(angle) * 0.7)

    def _use_door(self, mob):
        """Житель открывает свою дверь, когда идёт сквозь неё, и закрывает её за собой."""
        home = mob.home
        if home.gate is None:
            return
        gx, gz = home.gate
        block = self.world.get(gx, home.floor, gz)
        if block not in DOOR_STATE:
            return  # дверь сломали или заменили
        cx, cz = gx + 0.5, gz + 0.5
        near = math.hypot(mob.pos[0] - cx, mob.pos[2] - cz)
        opened = DOOR_STATE[block][2]
        out_x, out_z = home.door[0] - home.inside[0], home.door[1] - home.inside[1]

        def outside(x, z):
            return (x - cx) * out_x + (z - cz) * out_z > 0.0

        crossing = bool(mob.plan) and outside(*mob.plan[0]) != outside(mob.pos[0], mob.pos[2])
        if not opened and crossing and near < DOOR_REACH:
            mob.opened_door = True
        elif not (opened and mob.opened_door and near > DOOR_LEAVE and not crossing):
            return
        else:
            mob.opened_door = False
        material, side, is_open = DOOR_STATE[block]
        swapped = DOOR_BLOCK[(material, side, not is_open)]
        for y in (home.floor, home.floor + 1):
            self.world.set(gx, y, gz, swapped)
            self.door_moves.append((gx, y, gz, swapped))

    def _live_in_village(self, mob, dt):
        """Распорядок жителя: днём гуляет по своей тропе, ночью сидит дома."""
        self._use_door(mob)
        home = mob.home
        night = self.sun < 0.0
        at_home = math.hypot(mob.pos[0] - home.inside[0], mob.pos[2] - home.inside[1]) < 1.2
        if night != mob.resting:
            mob.resting = night
            mob.plan = [home.door, home.inside] if night else [home.door]
            mob.plan_time = 0.0
        elif night and not at_home and not mob.plan:
            mob.plan = [home.door, home.inside]

        if mob.plan:
            tx, tz = mob.plan[0]
            dx, dz = tx - mob.pos[0], tz - mob.pos[2]
            distance = math.hypot(dx, dz)
            mob.plan_time += dt
            if distance < ARRIVE or mob.plan_time > WAYPOINT_PATIENCE:
                mob.plan.pop(0)
                mob.plan_time = 0.0
                mob.wish = (0.0, 0.0)
            else:
                mob.wish = (dx / distance, dz / distance)
            return

        mob.wish = (0.0, 0.0)
        if night:
            return
        mob.think -= dt
        if mob.think <= 0.0:
            mob.think = random.uniform(2.0, 6.0)
            if random.random() < 0.6:
                x, z = random.choice(home.strip)
                mob.plan = [(x + random.uniform(-0.7, 0.7), z + random.uniform(-0.7, 0.7))]
                mob.plan_time = 0.0

    def _edge_ahead(self, mob):
        """Спереди обрыв или вода (для мирных существ)."""
        x = math.floor(mob.pos[0] + mob.wish[0] * 1.2)
        y = math.floor(mob.pos[1])
        z = math.floor(mob.pos[2] + mob.wish[1] * 1.2)
        get = self.world.get
        if get(x, y - 1, z) == WATER:
            return True
        return not is_solid(get(x, y - 1, z)) and not is_solid(get(x, y - 2, z))

    def _act(self, mob, player, dt, on_hit, aggressive):
        kind = mob.kind
        dx, dz = player.pos[0] - mob.pos[0], player.pos[2] - mob.pos[2]
        flat = math.hypot(dx, dz) or 0.001
        to_player = (dx / flat, dz / flat)

        if not kind.hostile:
            if mob.flee > 0.0:
                mob.wish = (-to_player[0] * 2.0, -to_player[1] * 2.0)
                mob.plan.clear()
            elif mob.trading:
                mob.wish = (0.0, 0.0)
            elif mob.home is not None:
                self._live_in_village(mob, dt)
            else:
                self._wander(mob, dt)
                if mob.on_ground and mob.wish != (0.0, 0.0) and self._edge_ahead(mob):
                    mob.wish = (0.0, 0.0)
                    mob.think = 1.0
        elif not aggressive or not mob.sees and flat > 10.0:
            self._wander(mob, dt)
        elif kind.ranged:
            self._act_ranged(mob, player, flat, to_player, on_hit, aggressive)
        else:
            mob.wish = (0.0, 0.0) if flat < 1.2 else to_player
            vertical = abs(player.pos[1] - mob.pos[1])
            if flat < kind.reach and vertical < 1.9 and mob.sees and mob.cool <= 0.0:
                mob.cool = kind.cooldown
                mob.swing = 1.0
                self.events.append(("shade_attack", tuple(mob.pos)))
                on_hit(kind.damage, mob.pos)

        if mob.wish != (0.0, 0.0):
            target = math.atan2(mob.wish[0], -mob.wish[1])
        elif (kind.hostile and aggressive and mob.sees) or mob.trading:
            target = math.atan2(dx, -dz)
        else:
            return
        turn = (target - mob.yaw + math.pi) % math.tau - math.pi
        mob.yaw += turn * min(1.0, 10.0 * dt)

    def _act_ranged(self, mob, player, flat, to_player, on_hit, aggressive):
        if flat < 6.0:
            mob.wish = (-to_player[0], -to_player[1])
        elif flat > 11.0 or not mob.sees:
            mob.wish = to_player
        else:
            mob.wish = (0.0, 0.0)
        if aggressive and mob.sees and flat <= SHOOT_RANGE and mob.cool <= 0.0:
            mob.cool = mob.kind.cooldown
            mob.swing = 1.0
            start = (mob.pos[0], mob.pos[1] + 0.75, mob.pos[2])
            eye = (player.pos[0], player.pos[1] + 1.3, player.pos[2])
            distance = math.dist(start, eye)
            flight = distance / THORN_SPEED
            vel = [(eye[i] - start[i]) / flight for i in range(3)]
            vel[1] += 0.5 * THORN_GRAVITY * flight
            self.shots.append(ThornShot(start, vel))
            self.events.append(("thorn_shot", start))

    def _move(self, mob, dt):
        x, y, z = mob.pos
        in_water = self.world.get(math.floor(x), math.floor(y + 0.5), math.floor(z)) in (WATER, LAVA)
        speed = mob.kind.speed * (0.5 if in_water else 1.0)
        rate = 2.0 if mob.stun > 0.0 else (10.0 if mob.on_ground else 3.0)
        wx, wz = (0.0, 0.0) if mob.stun > 0.0 else mob.wish
        blend = min(1.0, rate * dt)
        mob.vel[0] += (wx * speed - mob.vel[0]) * blend
        mob.vel[2] += (wz * speed - mob.vel[2]) * blend
        if in_water:
            mob.vel[1] += (2.0 - mob.vel[1]) * min(1.0, 6.0 * dt)
        else:
            mob.vel[1] = max(mob.vel[1] - MOB_GRAVITY * dt, -18.0)

        blocked_x = mob._move_axis(0, mob.vel[0] * dt)
        if blocked_x:
            mob.vel[0] = 0.0
        blocked_z = mob._move_axis(2, mob.vel[2] * dt)
        if blocked_z:
            mob.vel[2] = 0.0
        falling = mob.vel[1] < 0
        hit = mob._move_axis(1, mob.vel[1] * dt)
        mob.on_ground = hit and falling
        if hit:
            mob.vel[1] = 0.0
        if (blocked_x or blocked_z) and mob.on_ground and (wx or wz):
            mob.vel[1] = MOB_JUMP
        elif mob.kind is PUFF and mob.on_ground and (wx or wz):
            mob.vel[1] = PUFF_HOP
        mob.phase += math.hypot(mob.vel[0], mob.vel[2]) * dt * 5.0

    def _separate(self, bodies):
        mobs = [m for m in self.mobs if m.kind is not DRAGON]
        for i, a in enumerate(mobs):
            for b in mobs[i + 1:]:
                dx, dz = b.pos[0] - a.pos[0], b.pos[2] - a.pos[2]
                gap = a.half + b.half
                if abs(dx) < gap and abs(dz) < gap and abs(b.pos[1] - a.pos[1]) < 2.0:
                    length = math.hypot(dx, dz) or 0.001
                    push = (gap - length) * 0.08
                    if push > 0.0:
                        a._move_axis(0, -dx / length * push)
                        a._move_axis(2, -dz / length * push)
                        b._move_axis(0, dx / length * push)
                        b._move_axis(2, dz / length * push)
            for body in bodies:
                dx, dz = a.pos[0] - body.pos[0], a.pos[2] - body.pos[2]
                gap = a.half + HALF
                length = math.hypot(dx, dz) or 0.001
                if length < gap and abs(a.pos[1] - body.pos[1]) < 1.8:
                    a._move_axis(0, dx / length * (gap - length) * 0.3)
                    a._move_axis(2, dz / length * (gap - length) * 0.3)

    def _stops_shot(self, x, y, z):
        """Твёрдый блок или створка двери в этой точке."""
        block = self.world.get(math.floor(x), math.floor(y), math.floor(z))
        box = PANEL_BOX.get(block)
        if box is None:
            return is_solid(block)
        fx, fz = x - math.floor(x), z - math.floor(z)
        return box[0] <= fx <= box[3] and box[2] <= fz <= box[5]

    def _fly_shots(self, dt, targets):
        pad = HALF + 0.12
        for shot in list(self.shots):
            shot.vel[1] -= shot.gravity * dt
            for i in range(3):
                shot.pos[i] += shot.vel[i] * dt
            shot.life -= dt
            x, y, z = shot.pos
            struck = None
            for t in targets:
                px, py, pz = t.body.pos
                if abs(x - px) < pad and abs(z - pz) < pad and py - 0.1 < y < py + TALL + 0.1:
                    struck = t
                    break
            if struck is not None:
                self.shots.remove(shot)
                if struck.prey:
                    struck.hit(shot.damage, (x - shot.vel[0], y, z - shot.vel[2]))
            elif shot.life <= 0.0:
                self.shots.remove(shot)
            elif self._stops_shot(x, y, z):
                self.shots.remove(shot)
                self.events.append(("thorn_hit", tuple(shot.pos)))

    # --- Части для отрисовки -------------------------------------------------

    def parts(self, eye):
        out = []
        for mob in self.mobs:
            if mob.kind is DRAGON:
                out.extend(_dragon_parts(mob))
                continue
            x, y, z = mob.pos
            light = 1.0 if mob.exposed else 0.32
            # Под крышей дома жителя освещает лампа, а не небо.
            lamp_lit = mob.home is not None and not mob.exposed
            stride = math.sin(mob.phase) * 0.7
            swings = (0.0, stride, -stride, -1.7 * mob.swing + stride * 0.3)
            for p in mob.kind.parts:
                color = tuple(v * LAMP_LEVEL for v in p.color) if lamp_lit else p.color
                out.append((x, y, z, *p.off, *p.size, mob.yaw, swings[p.group], *color,
                            -1.0 if p.glow or lamp_lit else light, mob.flash))
            if mob.bar > 0.0:
                self._health_bar(out, mob, eye)
        for shot in self.shots:
            yaw = math.atan2(shot.vel[0], -shot.vel[2])
            if shot.frost:
                out.append((*shot.pos, 0.0, 0.0, 0.0, 0.42, 0.42, 0.9, yaw, 0.0, *FROST_BOLT, -1.0, 0.0))
            else:
                out.append((*shot.pos, 0.0, 0.0, 0.0, 0.07, 0.07, 0.42, yaw, 0.0, *SPINE, -1.0, 0.0))
        return out

    @staticmethod
    def _health_bar(out, mob, eye):
        x, y, z = mob.pos
        yaw = math.atan2(eye[0] - x, -(eye[2] - z))
        top = mob.tall + 0.34
        share = max(0.0, mob.hp / mob.kind.hp)
        width = 0.86 * share
        out.append((x, y, z, 0.0, top, 0.0, 0.94, 0.11, 0.02, yaw, 0.0, 0.1, 0.09, 0.18, -1.0, 0.0))
        # Локальная ось X смотрит от левого края полоски к правому.
        out.append((x, y, z, (width - 0.86) * -0.5, top, -0.02, width, 0.07, 0.02, yaw, 0.0,
                    0.96, 0.32, 0.4, -1.0, 0.0))


# --- Предмет в руке ----------------------------------------------------------

WOOD_COLOR = _c(150, 104, 74)
SKIN_COLOR = _c(214, 176, 150)
ITEM_COLORS = {MEAT: _c(240, 150, 150), COOKED_MEAT: _c(170, 96, 66), DUSK: _c(70, 56, 110), THORN: SPINE}


def _hand_part(base, along, size, yaw, theta, color, light):
    """Часть на оси предмета: along — расстояние вдоль неё. Шейдер вращает часть вокруг её верха."""
    c, s = math.cos(theta), math.sin(theta)
    half = size[1] * 0.5
    off = (0.0, along * c - half * (1.0 - c), along * s + half * s)
    return (*base, *off, *size, yaw, theta, *color, light, 0.0)


def hand_parts(stack, eye, look, yaw, pitch, swing, light, block_colors):
    """Предмет в правой руке; swing — фаза взмаха 0..1."""
    right = (math.cos(yaw), 0.0, math.sin(yaw))
    up = (-right[2] * look[1], right[2] * look[0] - right[0] * look[2], right[0] * look[1])
    forward = 0.74 + 0.16 * swing
    side = 0.44 - 0.1 * swing
    down = 0.4 + 0.06 * swing
    base = tuple(eye[i] + look[i] * forward + right[i] * side - up[i] * down for i in range(3))
    theta = pitch - 0.45 - swing * 1.1

    tool = TOOLS.get(stack.item) if stack else None
    if stack is None:
        return [_hand_part(base, 0.0, (0.11, 0.42, 0.11), yaw, theta, SKIN_COLOR, light)]
    if tool is None:
        if is_block(stack.item):
            return [_hand_part(base, 0.0, (0.17, 0.17, 0.17), yaw, theta, block_colors[stack.item], light)]
        color = ITEM_COLORS.get(stack.item, ROSE if stack.item in FOOD else AMBER_GLOW)
        return [_hand_part(base, 0.0, (0.13, 0.13, 0.13), yaw, theta, color, light)]

    metal = tuple(v / 255.0 for v in TIER_COLORS[tool.tier])
    if tool.kind == SWORD:
        return [
            _hand_part(base, -0.1, (0.035, 0.16, 0.035), yaw, theta, WOOD_COLOR, light),
            _hand_part(base, -0.02, (0.13, 0.03, 0.04), yaw, theta, _c(110, 92, 84), light),
            _hand_part(base, 0.2, (0.05, 0.42, 0.018), yaw, theta, metal, light),
        ]
    head = {PICK: (0.26, 0.05, 0.06), AXE: (0.16, 0.13, 0.04), SHOVEL: (0.11, 0.15, 0.03)}.get(tool.kind)
    if head is None:
        return [_hand_part(base, 0.0, (0.14, 0.14, 0.04), yaw, theta, metal, light)]
    return [
        _hand_part(base, 0.0, (0.04, 0.38, 0.04), yaw, theta, WOOD_COLOR, light),
        _hand_part(base, 0.19, head, yaw, theta, metal, light),
    ]
