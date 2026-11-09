"""Интерфейс: панель быстрого доступа, показатели, инвентарь, крафт и служебные экраны."""
import math

import pygame

from survival import (ARMOR, ARMOR_KIND, ARMOR_SLOT_NAMES, ARMOR_SLOTS, BOOTS, CHESTPLATE, HELMET, armor_points,
                      CHEST_SIZE, AXE, BAKED_FRUIT, CHARM_KIND, COIN, COOKED_MEAT, COPPER_INGOT, DUSK, EMBER_INGOT, FIRST_ITEM,
                      FRUIT, HOTBAR_SIZE, INGOT, INVENTORY_SIZE, IRON_INGOT, RUBY, SILVER_INGOT, STAR, DRAGON_SCALE, FLUFF, MAX_AIR, MEAT, PICK, SHARD, SHOVEL, STICK, SWORD, THORN, TIER_COLORS,
                      TOOLS, can_craft, item_name)
from world import BLOCKS, FORGE, WORKBENCH

WHITE = (255, 255, 255)
SOFT_WHITE = (235, 235, 250)
PANEL = (28, 28, 54, 150)
SHADOW = (20, 20, 40, 170)
SLOT_STEP = 52
SLOT_SIZE = 48
ROW_H = 50
PANEL_W = 960
ICON = 38

WOOD = (150, 104, 74)
INGOTS = {INGOT: ((250, 168, 48), (255, 214, 130)), COPPER_INGOT: ((206, 118, 70), (240, 170, 124)),
          IRON_INGOT: ((168, 170, 182), (216, 218, 228)), SILVER_INGOT: ((208, 222, 240), (244, 250, 255)),
          EMBER_INGOT: ((236, 78, 38), (255, 160, 96))}
GEMS = {SHARD: ((150, 244, 236), (222, 255, 250)), RUBY: ((226, 40, 84), (255, 150, 170)),
        STAR: ((96, 226, 250), (226, 250, 255)), DRAGON_SCALE: ((48, 112, 214), (150, 204, 255))}


class Hud:
    def __init__(self, tiles):
        pygame.font.init()
        self.tiles = tiles
        self.font = pygame.font.SysFont("segoeui,arial", 17)
        self.small = pygame.font.SysFont("segoeui,arial", 14, bold=True)
        self.big = pygame.font.SysFont("segoeui,arial", 34, bold=True)
        self.icons = {}
        self.pips = {
            "hp": self._pip_pair("diamond", (244, 88, 112)),
            "food": self._pip_pair("circle", (250, 176, 72)),
            "air": self._pip_pair("circle", (120, 206, 244)),
            "armor": self._pip_pair("diamond", (186, 196, 214)),
        }

    # --- Значки --------------------------------------------------------------

    def icon(self, item):
        if item not in self.icons:
            self.icons[item] = self._block_icon(item) if item < FIRST_ITEM else self._item_icon(item)
        return self.icons[item]

    def _block_icon(self, block):
        b = BLOCKS[block]
        tile = self.tiles[b.side][::-1]
        surf = pygame.image.frombytes(tile.tobytes(), (tile.shape[1], tile.shape[0]), "RGBA")
        return pygame.transform.smoothscale(surf, (ICON, ICON))

    @staticmethod
    def _item_icon(item):
        s = pygame.Surface((114, 114), pygame.SRCALPHA)
        if item == STICK:
            pygame.draw.line(s, WOOD, (28, 92), (86, 22), 14)
        elif item in INGOTS:
            body, shine = INGOTS[item]
            pygame.draw.polygon(s, body, [(14, 76), (36, 38), (100, 38), (98, 76)])
            pygame.draw.polygon(s, shine, [(36, 38), (100, 38), (86, 54), (32, 54)])
        elif item in GEMS:
            body, shine = GEMS[item]
            pygame.draw.polygon(s, body, [(57, 8), (88, 54), (57, 106), (26, 54)])
            pygame.draw.polygon(s, shine, [(57, 8), (70, 54), (57, 106), (44, 54)])
        elif item in (FRUIT, BAKED_FRUIT):
            color = (236, 92, 112) if item == FRUIT else (178, 96, 56)
            pygame.draw.circle(s, color, (57, 66), 36)
            pygame.draw.circle(s, (255, 190, 190) if item == FRUIT else (222, 160, 110), (44, 52), 9)
            pygame.draw.ellipse(s, (106, 196, 160), (58, 12, 34, 20))
        elif item in (MEAT, COOKED_MEAT):
            color = (240, 150, 150) if item == MEAT else (170, 96, 66)
            pygame.draw.ellipse(s, color, (14, 28, 86, 60))
            pygame.draw.ellipse(s, (252, 226, 214), (58, 42, 26, 22))
        elif item == DUSK:
            for x, y, r in ((40, 74, 22), (72, 76, 18), (56, 48, 20)):
                pygame.draw.circle(s, (70, 56, 110), (x, y), r)
            pygame.draw.circle(s, (250, 176, 72), (58, 62), 5)
        elif item == THORN:
            pygame.draw.polygon(s, (126, 200, 120), [(100, 12), (42, 72), (22, 96), (56, 84)])
        elif item == FLUFF:
            for x, y, r in ((42, 70, 24), (72, 68, 26), (56, 44, 26)):
                pygame.draw.circle(s, (250, 240, 228), (x, y), r)
            pygame.draw.circle(s, (232, 212, 200), (58, 66), 9)
        elif item == COIN:
            pygame.draw.circle(s, (196, 124, 34), (57, 57), 44)
            pygame.draw.circle(s, (250, 176, 72), (57, 57), 36)
            pygame.draw.polygon(s, (255, 226, 150), [(57, 30), (78, 57), (57, 84), (36, 57)])
        elif TOOLS[item].kind == ARMOR_KIND:
            color = TIER_COLORS[TOOLS[item].tier]
            shade = tuple(int(v * 0.72) for v in color)
            slot = ARMOR[item].slot
            if slot == HELMET:
                pygame.draw.rect(s, color, (24, 22, 66, 34), border_top_left_radius=26, border_top_right_radius=26)
                pygame.draw.rect(s, shade, (24, 54, 16, 38))
                pygame.draw.rect(s, shade, (74, 54, 16, 38))
            elif slot == CHESTPLATE:
                pygame.draw.polygon(s, color, [(12, 22), (40, 14), (57, 26), (74, 14), (102, 22), (92, 50), (82, 44),
                                               (82, 102), (32, 102), (32, 44), (22, 50)])
                pygame.draw.line(s, shade, (57, 30), (57, 100), 5)
            elif slot == BOOTS:
                for x in (18, 62):
                    pygame.draw.polygon(s, color, [(x, 36), (x + 20, 36), (x + 20, 76), (x + 34, 82), (x + 34, 98), (x, 98)])
            else:
                pygame.draw.rect(s, shade, (28, 14, 58, 22))
                pygame.draw.polygon(s, color, [(28, 34), (54, 34), (50, 102), (30, 102)])
                pygame.draw.polygon(s, color, [(60, 34), (86, 34), (84, 102), (64, 102)])
        elif TOOLS[item].kind == CHARM_KIND:
            pygame.draw.circle(s, (250, 168, 48), (57, 62), 38, 10)
            pygame.draw.polygon(s, (120, 90, 190), [(57, 40), (76, 62), (57, 86), (38, 62)])
            pygame.draw.line(s, (235, 235, 250), (57, 6), (57, 24), 6)
        elif TOOLS[item].kind == SWORD:
            color = TIER_COLORS[TOOLS[item].tier]
            pygame.draw.polygon(s, color, [(100, 10), (88, 12), (34, 68), (46, 80), (102, 22)])
            pygame.draw.line(s, (90, 70, 60), (24, 58), (56, 90), 10)
            pygame.draw.line(s, WOOD, (38, 76), (18, 96), 12)
        else:
            tool = TOOLS[item]
            color = TIER_COLORS[tool.tier]
            pygame.draw.line(s, WOOD, (24, 96), (76, 36), 12)
            if tool.kind == PICK:
                pygame.draw.lines(s, color, False, [(30, 26), (66, 18), (98, 50)], 16)
            elif tool.kind == AXE:
                pygame.draw.polygon(s, color, [(58, 18), (100, 14), (104, 60), (78, 48)])
            elif tool.kind == SHOVEL:
                pygame.draw.circle(s, color, (84, 28), 22)
        return pygame.transform.smoothscale(s, (ICON, ICON))

    @staticmethod
    def _pip_pair(shape, color):
        def make(fill):
            s = pygame.Surface((16, 16), pygame.SRCALPHA)
            if shape == "diamond":
                pygame.draw.polygon(s, fill, [(8, 1), (15, 8), (8, 15), (1, 8)])
            else:
                pygame.draw.circle(s, fill, (8, 8), 7)
            return s
        return make(color), make((30, 30, 56, 190))

    def _draw_pips(self, surf, kind, x, y, value, right_align=False):
        """Десять значков; значение 0..20, один значок равен двум единицам."""
        full, empty = self.pips[kind]
        for i in range(10):
            px = x - 18 * i - 16 if right_align else x + 18 * i
            surf.blit(empty, (px, y))
            part = max(0, min(2, value - i * 2))
            if part:
                surf.blit(full, (px, y), (0, 0, 16 * part // 2, 16))

    def _text(self, surf, text, pos, font=None, color=WHITE, center=False):
        image = (font or self.font).render(text, True, color)
        rect = image.get_rect(center=pos) if center else image.get_rect(topleft=pos)
        surf.blit(image, rect)
        return rect

    def _stack(self, surf, rect, stack):
        icon = self.icon(stack.item)
        surf.blit(icon, icon.get_rect(center=rect.center))
        if stack.count > 1:
            label = str(stack.count)
            right = rect.right - 6
            bottom = rect.bottom - 3
            shade = self.small.render(label, True, (16, 16, 32))
            text = self.small.render(label, True, WHITE)
            r = text.get_rect(bottomright=(right, bottom))
            surf.blit(shade, r.move(1, 1))
            surf.blit(text, r)
        tool = TOOLS.get(stack.item)
        if tool and stack.durability < tool.durability:
            part = stack.durability / tool.durability
            bar = pygame.Rect(rect.x + 6, rect.bottom - 7, rect.w - 12, 3)
            pygame.draw.rect(surf, (20, 20, 40), bar)
            color = (120, 224, 140) if part > 0.4 else (244, 120, 90)
            pygame.draw.rect(surf, color, (bar.x, bar.y, max(1, int(bar.w * part)), 3))

    # --- Размещение ----------------------------------------------------------

    @staticmethod
    def layout(size):
        w, h = size
        ph = min(500, h - 30)
        panel = pygame.Rect((w - PANEL_W) // 2, (h - ph) // 2, PANEL_W, ph)
        gx, gy = panel.x + 24, panel.y + 66
        slots = []
        for i in range(INVENTORY_SIZE):
            if i < HOTBAR_SIZE:
                slots.append(pygame.Rect(gx + i * SLOT_STEP, gy + 3 * SLOT_STEP + 14, SLOT_SIZE, SLOT_SIZE))
            else:
                row, col = divmod(i - HOTBAR_SIZE, HOTBAR_SIZE)
                slots.append(pygame.Rect(gx + col * SLOT_STEP, gy + row * SLOT_STEP, SLOT_SIZE, SLOT_SIZE))
        lx = gx + HOTBAR_SIZE * SLOT_STEP + 24
        recipes = pygame.Rect(lx, gy, panel.right - lx - 24, panel.bottom - gy - 20)
        return panel, slots, recipes

    @staticmethod
    def visible_rows(size):
        return Hud.layout(size)[2].h // ROW_H

    @staticmethod
    def chest_slots(area):
        return [pygame.Rect(area.x + (i % 8) * SLOT_STEP, area.y + (i // 8) * SLOT_STEP, SLOT_SIZE, SLOT_SIZE)
                for i in range(CHEST_SIZE)]

    @staticmethod
    def armor_slots(panel):
        return [pygame.Rect(panel.x + 24 + i * SLOT_STEP, panel.bottom - 66, SLOT_SIZE, SLOT_SIZE)
                for i in range(ARMOR_SLOTS)]

    def hit_test(self, size, pos, scroll, count, chest=False):
        """Что под курсором: ('slot', i), ('armor', i), ('chest', i), ('recipe', i) или None. count — длина списка справа."""
        panel, slots, recipes = self.layout(size)
        for i, rect in enumerate(slots):
            if rect.collidepoint(pos):
                return "slot", i
        for i, rect in enumerate(self.armor_slots(panel)):
            if rect.collidepoint(pos):
                return "armor", i
        if chest:
            for i, rect in enumerate(self.chest_slots(recipes)):
                if rect.collidepoint(pos):
                    return "chest", i
            return None
        if recipes.collidepoint(pos):
            index = scroll + (pos[1] - recipes.y) // ROW_H
            if index < count:
                return "recipe", index
        return None

    # --- Экраны --------------------------------------------------------------

    def compose(self, size, g, lines, mouse):
        surf = pygame.Surface(size, pygame.SRCALPHA)
        self._play_layer(surf, size, g, lines)
        if g.screen in ("inventory", "trade", "chest"):
            self._inventory(surf, size, g, mouse)
        elif g.screen == "sleep":
            self._sleep(surf, size, g)
        elif g.screen == "dead":
            self._dead(surf, size)
        elif not g.captured:
            self._pause(surf, size, g)
        return surf

    def _play_layer(self, surf, size, g, lines):
        w, h = size
        cx, cy = w // 2, h // 2
        if g.screen is None:
            pygame.draw.circle(surf, SHADOW, (cx, cy), 6, 3)
            pygame.draw.circle(surf, WHITE + (235,), (cx, cy), 5, 1)

        step = 54
        bar_w = step * HOTBAR_SIZE + 14
        x0 = cx - bar_w // 2
        y0 = h - 76
        pygame.draw.rect(surf, PANEL, (x0, y0, bar_w, 66), border_radius=20)
        for i in range(HOTBAR_SIZE):
            r = pygame.Rect(x0 + 10 + i * step, y0 + 7, 48, 52)
            if i == g.selected:
                pygame.draw.rect(surf, (255, 255, 255, 70), r, border_radius=14)
                pygame.draw.rect(surf, WHITE + (235,), r, 2, border_radius=14)
            stack = g.inventory.slots[i]
            if stack:
                self._stack(surf, r, stack)

        top = y0
        if not g.creative:
            v = g.vitals
            self._draw_pips(surf, "hp", x0 + 8, y0 - 24, v.hp)
            self._draw_pips(surf, "food", x0 + bar_w - 8, y0 - 24, v.food, right_align=True)
            points = armor_points(g.armor)
            if points:
                self._draw_pips(surf, "armor", x0 + 8, y0 - 46, min(20, points))
            if v.air < MAX_AIR:
                self._draw_pips(surf, "air", x0 + bar_w - 8, y0 - 46, math.ceil(v.air * 2), right_align=True)
            top = y0 - (46 if points else 24)

        selected = g.inventory.slots[g.selected]
        if selected and g.screen is None:
            name = self.font.render(item_name(selected.item), True, WHITE)
            bg = pygame.Rect(0, 0, name.get_width() + 24, name.get_height() + 6)
            bg.center = (cx, top - 22)
            pygame.draw.rect(surf, PANEL, bg, border_radius=12)
            surf.blit(name, name.get_rect(center=bg.center))

        if g.toast_text and g.screen is None:
            text = self.font.render(g.toast_text, True, WHITE)
            bg = pygame.Rect(0, 0, text.get_width() + 28, text.get_height() + 10)
            bg.center = (cx, top - 62)
            pygame.draw.rect(surf, (70, 44, 84, 190), bg, border_radius=14)
            surf.blit(text, text.get_rect(center=bg.center))

        boss = g.boss
        if boss is not None:
            track = pygame.Rect(cx - 220, 22, 440, 14)
            pygame.draw.rect(surf, (20, 20, 44, 210), track.inflate(6, 6), border_radius=9)
            share = max(0.0, boss.hp / boss.kind.hp)
            pygame.draw.rect(surf, (72, 158, 255), (track.x, track.y, int(track.w * share), track.h), border_radius=6)
            self._text(surf, boss.kind.name, (cx, 54), self.small, center=True)

        for i, line in enumerate(lines):
            text = self.font.render(line, True, WHITE)
            bg = pygame.Surface((text.get_width() + 12, text.get_height() + 2), pygame.SRCALPHA)
            bg.fill((20, 20, 40, 110))
            surf.blit(bg, (8, 8 + i * 26))
            surf.blit(text, (14, 9 + i * 26))

    @staticmethod
    def _veil(surf, size, color):
        veil = pygame.Surface(size, pygame.SRCALPHA)
        veil.fill(color)
        surf.blit(veil, (0, 0))

    def _inventory(self, surf, size, g, mouse):
        self._veil(surf, size, (16, 14, 36, 120))
        panel, slots, recipes = self.layout(size)
        pygame.draw.rect(surf, (34, 32, 62, 244), panel, border_radius=22)
        self._text(surf, "Инвентарь", (panel.x + 24, panel.y + 20))
        trading = g.screen == "trade"
        in_chest = g.screen == "chest"
        title = f"Обмен: {g.trader.kind.name}" if trading else "Сундук" if in_chest else "Изготовление"
        self._text(surf, title, (recipes.x, panel.y + 20))

        items = g.menu_items()
        hover = self.hit_test(size, mouse, g.recipe_scroll, len(items), in_chest)
        for i, rect in enumerate(slots):
            lit = hover == ("slot", i)
            pygame.draw.rect(surf, (88, 86, 130, 255) if lit else (54, 52, 90, 255), rect, border_radius=10)
            if i == g.selected:
                pygame.draw.rect(surf, (235, 235, 250), rect, 2, border_radius=10)
            stack = g.inventory.slots[i]
            if stack:
                self._stack(surf, rect, stack)

        info_y = slots[0].bottom + 14
        source = {"chest": g.chest.slots if g.chest else None, "armor": g.armor.slots}.get(hover and hover[0], g.inventory.slots)
        if hover and hover[0] in ("slot", "chest", "armor") and source[hover[1]]:
            stack = source[hover[1]]
            text = item_name(stack.item)
            if stack.durability is not None:
                text += f"   ·   прочность {stack.durability}/{TOOLS[stack.item].durability}"
            self._text(surf, text, (panel.x + 24, info_y))
        near = [name for station, name in ((WORKBENCH, "верстак"), (FORGE, "горн")) if station in g.stations]
        note = "Рядом: " + ", ".join(near) if near else "Рядом нет верстака и горна"
        if trading:
            note = f"Янтарных монет: {g.inventory.count(COIN)}"
        self._text(surf, note, (panel.x + 24, info_y + 28), color=(190, 190, 220))
        self._text(surf, "ЛКМ — взять/положить, ПКМ — половину или по одному", (panel.x + 24, info_y + 54),
                   color=(150, 150, 186))

        self._text(surf, "Клик за пределами окна — выбросить предмет", (panel.x + 24, info_y + 78), color=(150, 150, 186))
        armor_rects = self.armor_slots(panel)
        for i, rect in enumerate(armor_rects):
            lit = hover == ("armor", i)
            pygame.draw.rect(surf, (96, 92, 128, 255) if lit else (66, 62, 96, 255), rect, border_radius=10)
            if g.armor.slots[i]:
                self._stack(surf, rect, g.armor.slots[i])
            else:
                self._text(surf, ARMOR_SLOT_NAMES[i], rect.center, self.small, (150, 150, 186), center=True)
        self._text(surf, f"Защита: {armor_points(g.armor)}", (armor_rects[-1].right + 16, armor_rects[-1].y + 12))
        if in_chest:
            for i, rect in enumerate(self.chest_slots(recipes)):
                lit = hover == ("chest", i)
                pygame.draw.rect(surf, (88, 86, 130, 255) if lit else (54, 52, 90, 255), rect, border_radius=10)
                if g.chest.slots[i]:
                    self._stack(surf, rect, g.chest.slots[i])
        else:
            self._recipes(surf, recipes, g, hover, items, trading)

        if g.held:
            rect = pygame.Rect(0, 0, SLOT_SIZE, SLOT_SIZE)
            rect.center = mouse
            self._stack(surf, rect, g.held)

    def _recipes(self, surf, area, g, hover, items, trading):
        rows = area.h // ROW_H
        names = {WORKBENCH: "верстак", FORGE: "горн", None: "руками"}
        for row, index in enumerate(range(g.recipe_scroll, min(g.recipe_scroll + rows, len(items)))):
            recipe = items[index]
            rect = pygame.Rect(area.x, area.y + row * ROW_H, area.w - 12, ROW_H - 4)
            ready = can_craft(recipe, g.inventory, g.stations)
            base = (70, 92, 104, 255) if ready else (46, 44, 76, 255)
            if hover == ("recipe", index):
                base = (96, 128, 138, 255) if ready else (60, 58, 92, 255)
            pygame.draw.rect(surf, base, rect, border_radius=10)
            icon = self.icon(recipe.item)
            surf.blit(icon, icon.get_rect(center=(rect.x + 26, rect.centery)))
            title = item_name(recipe.item) + (f" ×{recipe.count}" if recipe.count > 1 else "")
            color = WHITE if ready else (160, 160, 190)
            self._text(surf, title, (rect.x + 52, rect.y + 3), self.small, color)
            station_ok = recipe.station is None or recipe.station in g.stations
            caption = names[recipe.station]
            if trading:
                caption = "продать жителю" if recipe.item == COIN else "купить у жителя"
            self._text(surf, caption, (rect.x + 52, rect.y + 24), self.small,
                       (168, 210, 190) if station_ok else (236, 130, 120))

            x = rect.right - 8
            for item, n in reversed(recipe.needs):
                have = g.inventory.count(item) >= n
                label = self.small.render(str(n), True, WHITE if have else (240, 130, 120))
                x -= label.get_width()
                surf.blit(label, label.get_rect(midleft=(x, rect.centery)))
                x -= 28
                mini = pygame.transform.smoothscale(self.icon(item), (26, 26))
                surf.blit(mini, mini.get_rect(midleft=(x, rect.centery)))
                x -= 8

        if len(items) > rows:
            track = pygame.Rect(area.right - 6, area.y, 5, rows * ROW_H - 4)
            pygame.draw.rect(surf, (54, 52, 90), track, border_radius=3)
            h = max(24, track.h * rows // len(items))
            y = track.y + (track.h - h) * g.recipe_scroll // (len(items) - rows)
            pygame.draw.rect(surf, (170, 170, 210), (track.x, y, 5, h), border_radius=3)

    def _sleep(self, surf, size, g):
        darkness = min(1.0, g.sleep_time / 1.5)
        self._veil(surf, size, (6, 6, 22, int(235 * darkness)))
        cx, cy = size[0] // 2, size[1] // 2
        self._text(surf, "Сон...", (cx, cy - 20), self.big, center=True)
        hint = "Ждём, пока уснут все игроки   ·   Esc — встать" if g.net else "Esc — встать"
        self._text(surf, hint, (cx, cy + 34), color=SOFT_WHITE, center=True)

    def _dead(self, surf, size):
        self._veil(surf, size, (70, 12, 34, 190))
        cx, cy = size[0] // 2, size[1] // 2
        self._text(surf, "Вы погибли", (cx, cy - 60), self.big, center=True)
        self._text(surf, "Половина вещей потеряна, инструменты остались", (cx, cy), color=SOFT_WHITE, center=True)
        self._text(surf, "Клик — возродиться", (cx, cy + 40), color=SOFT_WHITE, center=True)

    def _pause(self, surf, size, g):
        self._veil(surf, size, (16, 14, 36, 165))
        cx, cy = size[0] // 2, size[1] // 2
        self._text(surf, "Пауза", (cx, cy - 190), self.big, center=True)
        last = "F — полёт   ·   " if g.creative else ""
        help_lines = [
            "Клик — продолжить   ·   Q — сохранить и выйти" + ("   ·   в сетевой игре мир не останавливается" if g.net else ""),
            "WASD — ходьба   ·   Пробел — прыжок   ·   Ctrl — бег   ·   Shift — красться",
            "ЛКМ — ударить, держать — добывать   ·   ПКМ — поставить, съесть, верстак и горн, обмен с жителем",
            "E — инвентарь и крафт   ·   1-9 или колесо — выбор слота   ·   СКМ — выбрать такой же блок",
            "Q — выбросить предмет   ·   Ctrl+Q — всю стопку   ·   ПКМ по кровати — спать, по сундуку — открыть",
            "F5 — вид от третьего лица   ·   ПКМ с бронёй в руке — надеть",
            last + "+ / − — дальность   ·   T — ускорить время   ·   M — звук   ·   F2 — снимок экрана",
        ]
        for i, line in enumerate(help_lines):
            self._text(surf, line, (cx, cy - 130 + i * 32), color=SOFT_WHITE, center=True)
