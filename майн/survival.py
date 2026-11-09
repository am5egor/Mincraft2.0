"""Выживание: предметы, инструменты, инвентарь, рецепты и показатели игрока."""
import copy
import random
from collections import namedtuple

from world import (AMBER, ASH, BED, BED_STATE, BLOCKS, BRICK, CHEST, COPPER_ORE, CROWN, DOOR, DOOR_BLOCK, DOOR_STATE, EDGE_GATE, EMBER_ORE, FORGE,
                   FROST_CROWN, GLASS, GLOW, HELL_GATE, IRON_DOOR, IRON_ORE, PALE, PATH, PLANKS, ROCK,
                   RUBY_ORE, SAND, SILVER_ORE, SNOW, SOIL, STAR_ORE, TRUNK, TURF, WORKBENCH)

MAX_STACK = 64
FIRST_ITEM = 100
INVENTORY_SIZE = 36
HOTBAR_SIZE = 9

STICK, INGOT, SHARD, FRUIT, BAKED_FRUIT, MEAT, COOKED_MEAT, DUSK, THORN, COIN = range(FIRST_ITEM, FIRST_ITEM + 10)

PICK, AXE, SHOVEL, SWORD, CHARM_KIND = range(5)
Tool = namedtuple("Tool", "kind tier durability speed")
TIERS = [(60, 2.2), (140, 4.0), (500, 7.5)]
TIER_MATERIALS = [PLANKS, ROCK, INGOT]
TIER_COLORS = [(206, 160, 104), (150, 158, 184), (250, 168, 48), (126, 200, 120), (232, 44, 84), (110, 232, 250), (64, 150, 255), (196, 200, 212)]
TOOL_NAMES = {
    PICK: ("Деревянная кирка", "Каменная кирка", "Янтарная кирка"),
    AXE: ("Деревянный топор", "Каменный топор", "Янтарный топор"),
    SHOVEL: ("Деревянная лопата", "Каменная лопата", "Янтарная лопата"),
    SWORD: ("Деревянный меч", "Каменный меч", "Янтарный меч"),
}
TOOLS = {}
NAMES = {STICK: "Палка", INGOT: "Янтарный слиток", SHARD: "Осколок кристалла",
         FRUIT: "Плод", BAKED_FRUIT: "Печёный плод", MEAT: "Мякоть", COOKED_MEAT: "Жареная мякоть",
         DUSK: "Тёмная пыль", THORN: "Шип", COIN: "Янтарная монета"}
FIRST_TOOL = FIRST_ITEM + 10
for kind in (PICK, AXE, SHOVEL, SWORD):
    for tier, (durability, speed) in enumerate(TIERS):
        item = FIRST_TOOL + kind * 3 + tier
        TOOLS[item] = Tool(kind, tier, durability, speed)
        NAMES[item] = TOOL_NAMES[kind][tier]

THORN_SWORD = FIRST_TOOL + 12
CHARM = FIRST_TOOL + 13
TOOLS[THORN_SWORD] = Tool(SWORD, 3, 900, 1.0)
TOOLS[CHARM] = Tool(CHARM_KIND, 0, 250, 1.0)
NAMES[THORN_SWORD] = "Тернистый меч"
NAMES[CHARM] = "Оберег"


# Уровни из новых материалов: 3 уже занят тернистым мечом.
FIRST_EXTRA_TOOL = FIRST_TOOL + 14
RUBY_TIER, STAR_TIER, IRON_TIER = 4, 5, 7
EXTRA_TIERS = {RUBY_TIER: (1200, 10.0, "Рубиновая", "Рубиновый"), STAR_TIER: (3000, 14.0, "Звёздная", "Звёздный"),
               IRON_TIER: (250, 5.5, "Железная", "Железный")}
# Номера уровней не совпадают с силой: железо появилось позже, а добывает как камень.
TIER_RANK = {IRON_TIER: 1}
COPPER_INGOT, IRON_INGOT, SILVER_INGOT, RUBY, EMBER_INGOT, STAR = range(FIRST_EXTRA_TOOL + 8, FIRST_EXTRA_TOOL + 14)
DRAGON_SCALE, AZURE_SWORD = FIRST_EXTRA_TOOL + 14, FIRST_EXTRA_TOOL + 15
FLUFF = FIRST_EXTRA_TOOL + 16
AZURE_TIER = 6
FIRST_IRON_TOOL = FIRST_EXTRA_TOOL + 17
FIRST_ARMOR = FIRST_EXTRA_TOOL + 21
NAMES.update({COPPER_INGOT: "Медный слиток", IRON_INGOT: "Железный слиток", SILVER_INGOT: "Серебряный слиток",
              RUBY: "Рубин", EMBER_INGOT: "Жаровый слиток", STAR: "Звёздный камень",
              DRAGON_SCALE: "Драконья чешуя", AZURE_SWORD: "Лазурный меч", FLUFF: "Пух"})


def tool_id(kind, tier):
    if tier < 3:
        return FIRST_TOOL + kind * 3 + tier
    if tier == IRON_TIER:
        return FIRST_IRON_TOOL + kind
    return FIRST_EXTRA_TOOL + kind * 2 + (tier - RUBY_TIER)


for tier, (durability, speed, feminine, masculine) in EXTRA_TIERS.items():
    for kind, adjective, noun in ((PICK, feminine, "кирка"), (AXE, masculine, "топор"),
                                  (SHOVEL, feminine, "лопата"), (SWORD, masculine, "меч")):
        item = tool_id(kind, tier)
        TOOLS[item] = Tool(kind, tier, durability, speed)
        NAMES[item] = f"{adjective} {noun}"

TOOLS[AZURE_SWORD] = Tool(SWORD, AZURE_TIER, 5000, 1.0)

# Броня: четыре слота, износ хранится как у инструментов.
ARMOR_KIND = 5
HELMET, CHESTPLATE, LEGGINGS, BOOTS = range(4)
ARMOR_SLOTS = 4
ARMOR_SLOT_NAMES = ("Шлем", "Тело", "Ноги", "Сапоги")
ARMOR_POINT = 0.032  # доля урона, которую гасит одно очко защиты
ArmorPiece = namedtuple("ArmorPiece", "slot points")
ARMOR = {}
ARMOR_ITEM = {}
_ARMOR_TYPES = ((IRON_TIER, "Железн", 240, (2, 5, 4, 1)), (RUBY_TIER, "Рубинов", 640, (3, 7, 5, 3)))
for _index, (_tier, _stem, _durability, _points) in enumerate(_ARMOR_TYPES):
    for _slot, _noun in enumerate(("ый шлем", "ый нагрудник", "ые поножи", "ые сапоги")):
        _item = FIRST_ARMOR + _index * 4 + _slot
        TOOLS[_item] = Tool(ARMOR_KIND, _tier, _durability, 1.0)
        NAMES[_item] = _stem + _noun
        ARMOR[_item] = ArmorPiece(_slot, _points[_slot])
        ARMOR_ITEM[(_tier, _slot)] = _item
ARMOR_COST = (4, 7, 6, 3)


def armor_points(armor):
    return sum(ARMOR[s.item].points for s in armor.slots if s)

FOOD = {FRUIT: 3, BAKED_FRUIT: 7, MEAT: 3, COOKED_MEAT: 8}
SWORD_DAMAGE = (4, 6, 9, 13, 15, 20, 28, 7)
AXE_DAMAGE = (3, 4, 6, 6, 8, 11, 11, 5)
CHARM_FACTOR = 0.6


def attack_damage(stack):
    tool = TOOLS.get(stack.item) if stack else None
    if tool is None or tool.kind in (CHARM_KIND, ARMOR_KIND):
        return 1
    if tool.kind == SWORD:
        return SWORD_DAMAGE[tool.tier]
    if tool.kind == AXE:
        return AXE_DAMAGE[tool.tier]
    return 2


def item_name(item):
    return BLOCKS[item].name if item < FIRST_ITEM else NAMES[item]


def item_limit(item):
    return 1 if item in TOOLS else MAX_STACK


def is_block(item):
    return item < FIRST_ITEM


# --- Добыча ----------------------------------------------------------------

# Блок: (прочность в секундах голыми руками, подходящий инструмент, минимальный уровень).
# Уровень -1 — добывается чем угодно.
MINING = {
    TURF: (0.7, SHOVEL, -1),
    SOIL: (0.6, SHOVEL, -1),
    PATH: (0.7, SHOVEL, -1),
    SAND: (0.6, SHOVEL, -1),
    SNOW: (0.3, SHOVEL, -1),
    ROCK: (2.4, PICK, 0),
    BRICK: (2.6, PICK, 0),
    FORGE: (3.4, PICK, 0),
    AMBER: (3.2, PICK, 1),
    GLOW: (2.0, PICK, 1),
    TRUNK: (2.2, AXE, -1),
    PLANKS: (2.2, AXE, -1),
    WORKBENCH: (2.4, AXE, -1),
    CROWN: (0.25, None, -1),
    FROST_CROWN: (0.25, None, -1),
    GLASS: (0.4, None, -1),
    COPPER_ORE: (2.8, PICK, 0),
    IRON_ORE: (3.2, PICK, 1),
    SILVER_ORE: (3.6, PICK, 2),
    RUBY_ORE: (4.0, PICK, 2),
    ASH: (1.6, PICK, 0),
    EMBER_ORE: (4.2, PICK, 2),
    PALE: (2.8, PICK, 1),
    STAR_ORE: (5.0, PICK, RUBY_TIER),
    HELL_GATE: (4.0, PICK, 1),
    EDGE_GATE: (4.0, PICK, 1),
}
# Какой предмет получается из каждого положения двери и какой блок её сменяет.
DOOR_ITEM = {block: (DOOR, IRON_DOOR)[state[0]] for block, state in DOOR_STATE.items()}
DOOR_SWAP = {block: DOOR_BLOCK[(state[0], state[1], not state[2])] for block, state in DOOR_STATE.items()}
MINING[CHEST] = (2.0, AXE, -1)
for _bed_block in BED_STATE:
    MINING[_bed_block] = (0.8, AXE, -1)
for _door_block, _door_state in DOOR_STATE.items():
    MINING[_door_block] = (1.8, AXE, -1) if _door_state[0] == 0 else (3.6, PICK, 1)
GATES = {HELL_GATE: "hell", EDGE_GATE: "edge"}
GATE_OF_REALM = {realm: gate for gate, realm in GATES.items()}
WRONG_TOOL_PENALTY = 3.5


def mining_time(block, stack):
    """Время добычи выбранным предметом и получит ли игрок добычу."""
    hardness, kind, min_tier = MINING[block]
    tool = TOOLS.get(stack.item) if stack else None
    right = tool is not None and tool.kind == kind
    speed = tool.speed if right else 1.0
    harvest = min_tier < 0 or (right and TIER_RANK.get(tool.tier, tool.tier) >= min_tier)
    seconds = hardness / speed
    return (seconds if harvest else seconds * WRONG_TOOL_PENALTY), harvest


def required_tool(block):
    """Подсказка, чем добывать блок."""
    _, kind, min_tier = MINING[block]
    if min_tier >= RUBY_TIER:
        return "Нужна рубиновая кирка или лучше"
    if min_tier == 2:
        return "Нужна янтарная кирка или лучше"
    if min_tier == 1:
        return "Нужна кирка из камня или лучше"
    return "Нужна кирка" if kind == PICK else ""


def block_drops(block, rng=random):
    """Что выпадает из блока при правильной добыче: список (предмет, количество)."""
    if block in (TURF, PATH):
        return [(SOIL, 1)]
    if block in DOOR_ITEM:
        return [(DOOR_ITEM[block], 1)]
    if block in BED_STATE:
        return [(BED, 1)]
    if block == GLOW:
        return [(SHARD, 2)]
    if block == RUBY_ORE:
        return [(RUBY, 1)]
    if block == STAR_ORE:
        return [(STAR, 1)]
    if block == GLASS:
        return []
    if block in (CROWN, FROST_CROWN):
        roll = rng.random()
        if roll < 0.22:
            return [(FRUIT, 1)]
        if roll < 0.36:
            return [(STICK, 1)]
        return []
    return [(block, 1)]


# --- Инвентарь -------------------------------------------------------------

class Stack:
    __slots__ = ("item", "count", "durability")

    def __init__(self, item, count=1, durability=None):
        self.item = item
        self.count = count
        if durability is None and item in TOOLS:
            durability = TOOLS[item].durability
        self.durability = durability

    def key(self):
        return self.item, self.count, self.durability


class Inventory:
    def __init__(self, size=INVENTORY_SIZE):
        self.slots = [None] * size

    def take(self, stack):
        """Кладёт стопку с сохранением износа. Возвращает количество, которое не поместилось."""
        if stack.item in TOOLS:
            if None not in self.slots:
                return stack.count
            self.slots[self.slots.index(None)] = Stack(stack.item, stack.count, stack.durability)
            return 0
        return self.add(stack.item, stack.count)

    def add(self, item, count=1):
        """Кладёт предметы и возвращает количество, которое не поместилось."""
        limit = item_limit(item)
        for stack in self.slots:
            if count and stack and stack.item == item and stack.count < limit:
                moved = min(count, limit - stack.count)
                stack.count += moved
                count -= moved
        for i, stack in enumerate(self.slots):
            if count and stack is None:
                moved = min(count, limit)
                self.slots[i] = Stack(item, moved)
                count -= moved
        return count

    def put(self, stack):
        """Возвращает стопку в инвентарь, сохраняя износ инструмента."""
        if stack.item not in TOOLS:
            self.add(stack.item, stack.count)
        elif None in self.slots:
            self.slots[self.slots.index(None)] = stack

    def count(self, item):
        return sum(s.count for s in self.slots if s and s.item == item)

    def remove(self, item, count):
        """Списывает с самых маленьких стопок, чтобы быстрее освобождать слоты."""
        matching = [i for i, s in enumerate(self.slots) if s and s.item == item]
        for i in sorted(matching, key=lambda k: self.slots[k].count):
            stack = self.slots[i]
            moved = min(count, stack.count)
            stack.count -= moved
            count -= moved
            if stack.count == 0:
                self.slots[i] = None

    def use_one(self, index):
        stack = self.slots[index]
        stack.count -= 1
        if stack.count == 0:
            self.slots[index] = None

    def wear(self, index):
        """Износ инструмента в слоте. True, если инструмент сломался."""
        stack = self.slots[index]
        if stack is None or stack.durability is None:
            return False
        stack.durability -= 1
        if stack.durability <= 0:
            self.slots[index] = None
            return True
        return False

    def lose_half(self):
        """Потери при смерти: половина каждой стопки; инструменты остаются."""
        for i, stack in enumerate(self.slots):
            if stack and stack.item not in TOOLS:
                stack.count //= 2
                if stack.count == 0:
                    self.slots[i] = None

    def snapshot(self):
        return tuple(s.key() if s else None for s in self.slots)

    def to_json(self):
        return [list(s.key()) if s else None for s in self.slots]

    def load_json(self, data):
        for i, entry in enumerate(data[:len(self.slots)]):
            self.slots[i] = Stack(*entry) if entry else None


# --- Рецепты ---------------------------------------------------------------

Recipe = namedtuple("Recipe", "item count needs station")

RECIPES = [
    Recipe(PLANKS, 4, [(TRUNK, 1)], None),
    Recipe(STICK, 4, [(PLANKS, 2)], None),
    Recipe(WORKBENCH, 1, [(PLANKS, 4)], None),
]
for tier, material in enumerate(TIER_MATERIALS):
    RECIPES += [
        Recipe(tool_id(PICK, tier), 1, [(material, 3), (STICK, 2)], WORKBENCH),
        Recipe(tool_id(AXE, tier), 1, [(material, 3), (STICK, 2)], WORKBENCH),
        Recipe(tool_id(SHOVEL, tier), 1, [(material, 1), (STICK, 2)], WORKBENCH),
        Recipe(tool_id(SWORD, tier), 1, [(material, 2), (STICK, 1)], WORKBENCH),
    ]
for tier, material in ((IRON_TIER, IRON_INGOT), (RUBY_TIER, RUBY), (STAR_TIER, STAR)):
    RECIPES += [
        Recipe(tool_id(PICK, tier), 1, [(material, 3), (STICK, 2)], WORKBENCH),
        Recipe(tool_id(AXE, tier), 1, [(material, 3), (STICK, 2)], WORKBENCH),
        Recipe(tool_id(SHOVEL, tier), 1, [(material, 1), (STICK, 2)], WORKBENCH),
        Recipe(tool_id(SWORD, tier), 1, [(material, 2), (STICK, 1)], WORKBENCH),
    ]
RECIPES += [
    Recipe(DOOR, 1, [(PLANKS, 6)], WORKBENCH),
    Recipe(IRON_DOOR, 1, [(IRON_INGOT, 6)], WORKBENCH),
    Recipe(COPPER_INGOT, 1, [(COPPER_ORE, 1)], FORGE),
    Recipe(IRON_INGOT, 1, [(IRON_ORE, 1)], FORGE),
    Recipe(SILVER_INGOT, 1, [(SILVER_ORE, 1)], FORGE),
    Recipe(EMBER_INGOT, 1, [(EMBER_ORE, 1)], FORGE),
    Recipe(GLOW, 1, [(COPPER_INGOT, 2), (SHARD, 1)], WORKBENCH),
    Recipe(HELL_GATE, 1, [(IRON_INGOT, 6), (RUBY, 2)], WORKBENCH),
    Recipe(EDGE_GATE, 1, [(EMBER_INGOT, 6), (SILVER_INGOT, 4)], WORKBENCH),
    Recipe(AZURE_SWORD, 1, [(DRAGON_SCALE, 6), (STAR, 2), (STICK, 1)], WORKBENCH),
    Recipe(CHEST, 1, [(PLANKS, 8)], WORKBENCH),
    Recipe(BED, 1, [(PLANKS, 3), (FLUFF, 3)], WORKBENCH),
    *[Recipe(ARMOR_ITEM[(armor_tier, slot)], 1, [(armor_material, cost)], WORKBENCH)
      for armor_tier, armor_material in ((IRON_TIER, IRON_INGOT), (RUBY_TIER, RUBY))
      for slot, cost in enumerate(ARMOR_COST)],
    Recipe(THORN_SWORD, 1, [(INGOT, 2), (THORN, 4), (STICK, 1)], WORKBENCH),
    Recipe(CHARM, 1, [(DUSK, 6), (INGOT, 2)], WORKBENCH),
    Recipe(COOKED_MEAT, 1, [(MEAT, 1)], FORGE),
    Recipe(FORGE, 1, [(ROCK, 8)], WORKBENCH),
    Recipe(GLOW, 1, [(SHARD, 4)], WORKBENCH),
    Recipe(INGOT, 1, [(AMBER, 1)], FORGE),
    Recipe(GLASS, 1, [(SAND, 1)], FORGE),
    Recipe(BRICK, 2, [(SOIL, 2), (SAND, 1)], FORGE),
    Recipe(BAKED_FRUIT, 1, [(FRUIT, 1)], FORGE),
]
STATIONS = (WORKBENCH, FORGE)

CHEST_SIZE = 24
# Добыча деревенских сундуков: (предмет, минимум, максимум, вес).
LOOT = (
    (FRUIT, 1, 4, 10), (BAKED_FRUIT, 1, 3, 7), (COOKED_MEAT, 1, 3, 7), (STICK, 2, 6, 9), (PLANKS, 4, 12, 9),
    (TRUNK, 2, 6, 7), (ROCK, 4, 12, 7), (GLASS, 1, 4, 3), (FLUFF, 1, 3, 5), (COIN, 1, 5, 8), (COPPER_INGOT, 1, 3, 5),
    (IRON_INGOT, 1, 2, 4), (INGOT, 1, 2, 3), (SHARD, 1, 2, 3), (SILVER_INGOT, 1, 1, 1), (RUBY, 1, 1, 1),
    (tool_id(PICK, 1), 1, 1, 2), (tool_id(SWORD, 1), 1, 1, 2), (tool_id(AXE, 0), 1, 1, 2), (DOOR, 1, 1, 2),
)


def loot_for(cell, seed):
    """Случайное, но постоянное для мира содержимое сундука."""
    rng = random.Random(f"{seed}:{cell[0]}:{cell[1]}:{cell[2]}")
    slots = [None] * CHEST_SIZE
    picked = rng.choices(LOOT, weights=[entry[3] for entry in LOOT], k=rng.randint(3, 7))
    for spot, (item, low, high, _) in zip(rng.sample(range(CHEST_SIZE), len(picked)), picked):
        slots[spot] = list(Stack(item, rng.randint(low, high)).key())
    return slots


def _sell(item, count, coins):
    """Житель покупает у игрока."""
    return Recipe(COIN, coins, [(item, count)], None)


def _buy(item, count, coins):
    """Житель продаёт игроку."""
    return Recipe(item, count, [(COIN, coins)], None)


# Сделки каждой профессии. Продажа всегда выгоднее для жителя, чем покупка.
TRADES = {
    "Рудокоп": [
        _sell(ROCK, 16, 1),
        _sell(AMBER, 3, 2),
        _sell(SHARD, 2, 1),
        _sell(COPPER_ORE, 8, 1),
        _sell(IRON_ORE, 6, 1),
        _buy(TRUNK, 4, 1),
        _buy(tool_id(PICK, 1), 1, 3),
        _buy(GLOW, 1, 4),
    ],
    "Кузнец": [
        _sell(INGOT, 2, 3),
        _sell(BRICK, 8, 1),
        _sell(COPPER_INGOT, 4, 1),
        _sell(IRON_INGOT, 3, 2),
        _sell(SILVER_INGOT, 2, 3),
        _sell(RUBY, 1, 4),
        _buy(INGOT, 1, 2),
        _buy(tool_id(SWORD, 1), 1, 2),
        _buy(tool_id(PICK, 2), 1, 5),
        _buy(tool_id(SWORD, 2), 1, 6),
    ],
    "Фермер": [
        _sell(FRUIT, 4, 1),
        _sell(MEAT, 3, 1),
        _sell(SOIL, 32, 1),
        _buy(FRUIT, 3, 2),
        _buy(BAKED_FRUIT, 2, 1),
        _buy(COOKED_MEAT, 2, 1),
    ],
    "Травник": [
        _sell(DUSK, 2, 1),
        _sell(THORN, 2, 1),
        _buy(DUSK, 1, 1),
        _buy(THORN, 1, 1),
        _buy(GLASS, 4, 3),
        _buy(CHARM, 1, 8),
    ],
}


def has_ingredients(recipe, inventory):
    return all(inventory.count(item) >= n for item, n in recipe.needs)


def can_craft(recipe, inventory, stations):
    return (recipe.station is None or recipe.station in stations) and has_ingredients(recipe, inventory)


def craft(recipe, inventory, stations):
    """Изготавливает предмет. Инвентарь меняется только при успехе."""
    if not can_craft(recipe, inventory, stations):
        return False
    trial = copy.deepcopy(inventory)
    for item, n in recipe.needs:
        trial.remove(item, n)
    if trial.add(recipe.item, recipe.count):
        return False
    inventory.slots = trial.slots
    return True


# --- Показатели ------------------------------------------------------------

MAX_HP = 20
MAX_FOOD = 20
MAX_AIR = 10.0
SPRINT_MIN_FOOD = 5
SAFE_FALL = 3.2
REGEN_SECONDS = 2.5
REGEN_FOOD_COST = 0.5  # сколько сытости стоит одна единица здоровья


class Vitals:
    def __init__(self):
        self.hp = MAX_HP
        self.food = MAX_FOOD
        self.air = MAX_AIR
        self.tiredness = 0.0
        self.regen = 0.0
        self.choke = 0.0
        self.hurt = 0.0

    def damage(self, amount):
        if amount > 0:
            self.hp = max(0, self.hp - amount)
            self.hurt = 1.0

    def fall(self, impact, gravity):
        """Урон от удара о землю по скорости падения."""
        self.damage(int(impact * impact / (2.0 * gravity) - SAFE_FALL))

    def eat(self, item):
        self.food = min(MAX_FOOD, self.food + FOOD[item])

    def tire(self, amount):
        self.tiredness += amount
        while self.tiredness >= 1.0:
            self.tiredness -= 1.0
            self.food = max(0, self.food - 1)

    def update(self, dt, underwater):
        self.hurt = max(0.0, self.hurt - dt * 2.0)

        if underwater:
            self.air -= dt
            if self.air <= 0.0:
                self.air = 0.0
                self.choke += dt
                if self.choke >= 1.0:
                    self.choke -= 1.0
                    self.damage(2)
        else:
            self.air = min(MAX_AIR, self.air + dt * 4.0)
            self.choke = 0.0

        # Сытость расходуется только здесь: еда превращается в здоровье.
        if self.food > 0 and 0 < self.hp < MAX_HP:
            self.regen += dt
            if self.regen >= REGEN_SECONDS:
                self.regen = 0.0
                self.hp += 1
                self.tire(REGEN_FOOD_COST)
        else:
            self.regen = 0.0

    def to_json(self):
        return {"hp": self.hp, "food": self.food, "air": self.air, "tiredness": self.tiredness}

    def load_json(self, data):
        self.hp = data["hp"]
        self.food = data["food"]
        self.air = data["air"]
        self.tiredness = data["tiredness"]
