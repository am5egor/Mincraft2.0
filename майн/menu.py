"""Главное меню: новые миры, загрузка сохранений и сетевая игра."""
import json
import math
import os
import time
import zlib
from collections import namedtuple

import pygame

from net import PORT, ClientSession, HostSession, NetError, join, parse_address

WHITE = (255, 255, 255)
SOFT = (222, 222, 242)
DIM = (168, 168, 204)
ERROR = (255, 170, 160)
PANEL = (28, 26, 54, 215)
COLUMN = 460
BUTTON_H = 50
GAP = 12
ROW_H = 58
FIELD_LIMIT = {"name": 32, "seed": 24, "player": 16, "address": 64}

Button = namedtuple("Button", "rect label action enabled")
Field = namedtuple("Field", "rect key caption")
SaveInfo = namedtuple("SaveInfo", "path name when creative broken")


def read_saves(folder):
    """Сохранения из папки, сначала недавние."""
    found = []
    if os.path.isdir(folder):
        for entry in os.listdir(folder):
            path = os.path.join(folder, entry)
            if not entry.endswith(".json") or not os.path.isfile(path):
                continue
            creative, broken = False, False
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                creative = bool((data.get("player") or {}).get("creative"))
                broken = "seed" not in data or "edits" not in data
            except (OSError, ValueError, AttributeError):
                broken = True
            found.append(SaveInfo(path, entry[:-5], os.path.getmtime(path), creative, broken))
    found.sort(key=lambda s: -s.when)
    return found


def safe_file_name(name):
    cleaned = "".join("_" if c in '<>:"/\\|?*' or ord(c) < 32 else c for c in name).strip(" .")
    return cleaned or "Мир"


def free_save_path(folder, name):
    """Путь для нового мира, который не затрёт существующий."""
    base = safe_file_name(name)
    path = os.path.join(folder, f"{base}.json")
    number = 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{base} ({number}).json")
        number += 1
    return path


def parse_seed(text):
    """Пусто — случайный мир; число используется как есть; текст превращается в число."""
    text = text.strip()
    if not text:
        return None
    try:
        return abs(int(text)) & 0xFFFFFF
    except ValueError:
        return zlib.crc32(text.encode("utf-8")) & 0xFFFFFF


class Menu:
    def __init__(self, shell, game_class, radius, folder):
        self.shell = shell
        self.game_class = game_class
        self.radius = radius
        self.folder = folder
        self.screen = "main"
        self.values = {"name": "Новый мир", "seed": "", "player": "Игрок", "address": ""}
        self.focus = None
        self.creative = False
        self.hosting = False
        self.message = ""
        self.saves = []
        self.selected = None
        self.scroll = 0
        self.state = None
        self.clock = 0.0

    # --- Переходы ------------------------------------------------------------

    def go(self, screen):
        self.screen = screen
        self.message = ""
        self.focus = None
        if screen == "load":
            self.saves = read_saves(self.folder)
            self.selected = None
            self.scroll = 0

    def _go_new(self, hosting):
        self.hosting = hosting
        self.go("new")
        self.focus = "name"

    def _go_load(self, hosting):
        self.hosting = hosting
        self.go("load")

    def _back_from_world_list(self):
        self.go("net" if self.hosting else "main")

    def quit(self):
        self.shell.quit = True

    # --- Запуск игры ---------------------------------------------------------

    def _player_name(self):
        return self.values["player"].strip()

    def _launch(self, path, seed, creative):
        name = self._player_name()
        if self.hosting and not name:
            self.message = "Введите имя игрока"
            return
        try:
            game = self.game_class(seed=seed, save_path=path, radius=self.radius, creative=creative, shell=self.shell)
        except (OSError, ValueError, KeyError) as error:
            self.message = f"Не удалось открыть мир: {error}"
            return
        if self.hosting:
            try:
                game.net = HostSession(game, name)
            except OSError:
                game.close()
                self.message = f"Порт {PORT} занят: сервер уже запущен?"
                return
        self._play(game)

    def _play(self, game):
        pygame.key.set_repeat()
        game.run()
        pygame.key.set_repeat(400, 35)
        self.state = None
        self.go("main")
        self.message = game.exit_message

    def create_world(self):
        name = self.values["name"].strip() or "Мир"
        self._launch(free_save_path(self.folder, name), parse_seed(self.values["seed"]), self.creative)

    def load_selected(self):
        info = self.saves[self.selected]
        self._launch(info.path, None, info.creative)

    def delete_selected(self):
        os.remove(self.saves[self.selected].path)
        self.go("load")

    def connect(self):
        name = self._player_name()
        if not name:
            self.message = "Введите имя игрока"
            return
        self.message = "Подключение..."
        self.state = None
        self.draw()
        try:
            host, port = parse_address(self.values["address"])
            link, hello = join(host, port, name)
        except NetError as error:
            self.message = str(error)
            return
        state = hello["state"] or {}
        player = {"realm_spawns": {hello["realm"]: hello["spawn"]}, "day_time": hello["day"], **state,
                  "realm": hello["realm"]}
        game = self.game_class(seed=hello["seed"], save_path=None, radius=self.radius, day_time=hello["day"],
                               creative=hello["creative"], shell=self.shell,
                               start={"edits": hello["edits"], "player": player})
        game.net = ClientSession(game, link, hello["id"], name)
        self._play(game)

    # --- Разметка ------------------------------------------------------------

    def _widgets(self, size):
        """Кнопки и поля текущего экрана."""
        w, h = size
        x = w // 2 - COLUMN // 2
        y = max(170, h // 2 - 130)
        buttons, fields = [], []

        def button(label, action, enabled=True):
            nonlocal y
            buttons.append(Button(pygame.Rect(x, y, COLUMN, BUTTON_H), label, action, enabled))
            y += BUTTON_H + GAP

        def field(key, caption):
            nonlocal y
            y += 22
            fields.append(Field(pygame.Rect(x, y, COLUMN, 44), key, caption))
            y += 44 + GAP

        if self.screen == "main":
            button("Новая игра", lambda: self._go_new(False))
            button("Загрузить игру", lambda: self._go_load(False))
            button("Сетевая игра", lambda: self.go("net"))
            button("Выход", self.quit)
        elif self.screen == "new":
            field("name", "Название мира")
            field("seed", "Зерно (можно оставить пустым)")
            mode = "Творческий" if self.creative else "Выживание"
            button(f"Режим: {mode}", self._toggle_mode)
            button("Открыть сервер" if self.hosting else "Создать мир", self.create_world)
            button("Назад", self._back_from_world_list)
        elif self.screen == "net":
            field("player", "Имя игрока")
            field("address", f"Адрес сервера (например 192.168.1.5, порт по умолчанию {PORT})")
            button("Подключиться", self.connect)
            button("Создать сервер в новом мире", lambda: self._go_new(True))
            button("Создать сервер в сохранённом мире", lambda: self._go_load(True))
            button("Назад", lambda: self.go("main"))
        elif self.screen == "load":
            bottom = h - 74
            gap = GAP
            width = (COLUMN + 240 - 2 * gap) // 3
            left = w // 2 - (COLUMN + 240) // 2
            chosen = self.selected is not None and not self.saves[self.selected].broken
            for i, (label, action, enabled) in enumerate((
                    ("Открыть сервер" if self.hosting else "Загрузить", self.load_selected, chosen),
                    ("Удалить", lambda: self.go("confirm"), self.selected is not None),
                    ("Назад", self._back_from_world_list, True))):
                rect = pygame.Rect(left + i * (width + gap), bottom, width, BUTTON_H)
                buttons.append(Button(rect, label, action, enabled))
        elif self.screen == "confirm":
            button("Удалить навсегда", self.delete_selected)
            button("Отмена", lambda: self.go("load"))
        return buttons, fields

    def _list_area(self, size):
        w, h = size
        return pygame.Rect(w // 2 - (COLUMN + 240) // 2, 150, COLUMN + 240, max(ROW_H, h - 150 - 92))

    def _toggle_mode(self):
        self.creative = not self.creative

    # --- Ввод ----------------------------------------------------------------

    def handle_events(self):
        size = pygame.display.get_window_size()
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.quit()
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                self._click(size, e.pos)
                if self.shell.quit:
                    return
            elif e.type == pygame.MOUSEWHEEL and self.screen == "load":
                self._scroll(size, -e.y)
            elif e.type == pygame.KEYDOWN:
                self._key(size, e)

    def _click(self, size, pos):
        buttons, fields = self._widgets(size)
        for b in buttons:
            if b.enabled and b.rect.collidepoint(pos):
                b.action()
                return
        self.focus = next((f.key for f in fields if f.rect.collidepoint(pos)), None)
        if self.screen == "load":
            area = self._list_area(size)
            if area.collidepoint(pos):
                index = self.scroll + (pos[1] - area.y) // ROW_H
                if index < len(self.saves):
                    self.selected = index

    def _scroll(self, size, delta):
        rows = self._list_area(size).h // ROW_H
        self.scroll = max(0, min(max(0, len(self.saves) - rows), self.scroll + delta))

    def _key(self, size, e):
        buttons, fields = self._widgets(size)
        if e.key == pygame.K_ESCAPE:
            back = {"new": self._back_from_world_list, "load": self._back_from_world_list,
                    "net": lambda: self.go("main"), "confirm": lambda: self.go("load")}.get(self.screen)
            if back:
                back()
        elif e.key == pygame.K_TAB and fields:
            keys = [f.key for f in fields]
            self.focus = keys[(keys.index(self.focus) + 1) % len(keys)] if self.focus in keys else keys[0]
        elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.screen in ("new", "net"):
            # Enter нажимает основную кнопку экрана.
            buttons[1 if self.screen == "new" else 0].action()
        elif self.focus:
            value = self.values[self.focus]
            if e.key == pygame.K_BACKSPACE:
                self.values[self.focus] = value[:-1]
            elif e.unicode and e.unicode.isprintable() and len(value) < FIELD_LIMIT[self.focus]:
                self.values[self.focus] = value + e.unicode

    # --- Отрисовка -----------------------------------------------------------

    def draw(self):
        size = pygame.display.get_window_size()
        shell = self.shell
        renderer = shell.renderer
        renderer.draw(size, (0.0, 70.0, 0.0), (0.58, 0.32, -0.75), 8, 0.2, self.clock, None, False, math.radians(76.0))
        mouse = pygame.mouse.get_pos()
        cursor = int(time.perf_counter() * 2.0) % 2 == 0
        state = (size, self.screen, tuple(self.values.values()), self.focus, self.creative, self.hosting,
                 self.message, self.selected, self.scroll, mouse, cursor, tuple(self.saves))
        if state != self.state:
            self.state = state
            renderer.upload_hud(self._compose(size, mouse, cursor))
        renderer.draw_hud()
        pygame.display.flip()

    def _titles(self):
        return {
            "main": ("Кубозем", ""),
            "new": ("Новый мир для сервера" if self.hosting else "Новый мир", ""),
            "load": ("Мир для сервера" if self.hosting else "Загрузить игру", ""),
            "net": ("Сетевая игра", ""),
            "confirm": ("Удалить мир?", ""),
        }[self.screen]

    def _compose(self, size, mouse, cursor):
        hud = self.shell.hud
        surf = pygame.Surface(size, pygame.SRCALPHA)
        w, h = size
        title, _ = self._titles()
        image = hud.big.render(title, True, WHITE)
        shade = hud.big.render(title, True, (34, 30, 70))
        rect = image.get_rect(center=(w // 2, 90))
        surf.blit(shade, rect.move(2, 3))
        surf.blit(image, rect)

        buttons, fields = self._widgets(size)
        if self.screen == "load":
            self._draw_list(surf, size, mouse)
        elif self.screen == "confirm":
            label = hud.font.render(f"«{self.saves[self.selected].name}» будет удалён без возможности вернуть",
                                    True, WHITE)
            surf.blit(label, label.get_rect(center=(w // 2, buttons[0].rect.y - 34)))

        for f in fields:
            caption = hud.small.render(f.caption, True, WHITE)
            surf.blit(caption, (f.rect.x + 2, f.rect.y - 22))
            focused = self.focus == f.key
            pygame.draw.rect(surf, PANEL, f.rect, border_radius=12)
            pygame.draw.rect(surf, WHITE if focused else (120, 120, 170), f.rect, 2, border_radius=12)
            text = self.values[f.key] + ("|" if focused and cursor else "")
            surf.blit(hud.font.render(text, True, WHITE), (f.rect.x + 14, f.rect.y + 10))

        for b in buttons:
            lit = b.enabled and b.rect.collidepoint(mouse)
            fill = (92, 128, 142, 235) if lit else (58, 64, 104, 225) if b.enabled else (40, 38, 64, 170)
            pygame.draw.rect(surf, fill, b.rect, border_radius=14)
            text = hud.font.render(b.label, True, WHITE if b.enabled else DIM)
            surf.blit(text, text.get_rect(center=b.rect.center))

        if self.message:
            text = hud.font.render(self.message, True, ERROR if self.message != "Подключение..." else SOFT)
            bg = pygame.Rect(0, 0, text.get_width() + 28, text.get_height() + 10)
            bg.center = (w // 2, h - 28)
            pygame.draw.rect(surf, PANEL, bg, border_radius=12)
            surf.blit(text, text.get_rect(center=bg.center))
        return surf

    def _draw_list(self, surf, size, mouse):
        hud = self.shell.hud
        area = self._list_area(size)
        pygame.draw.rect(surf, PANEL, area.inflate(16, 16), border_radius=18)
        if not self.saves:
            text = hud.font.render("Сохранений пока нет", True, SOFT)
            surf.blit(text, text.get_rect(center=area.center))
            return
        rows = area.h // ROW_H
        for row, index in enumerate(range(self.scroll, min(self.scroll + rows, len(self.saves)))):
            info = self.saves[index]
            rect = pygame.Rect(area.x, area.y + row * ROW_H, area.w, ROW_H - 6)
            selected = index == self.selected
            lit = rect.collidepoint(mouse)
            fill = (96, 128, 142, 240) if selected else (66, 66, 108, 235) if lit else (46, 44, 80, 235)
            pygame.draw.rect(surf, fill, rect, border_radius=12)
            surf.blit(hud.font.render(info.name, True, WHITE), (rect.x + 14, rect.y + 4))
            when = time.strftime("%d.%m.%Y %H:%M", time.localtime(info.when))
            mode = "файл повреждён" if info.broken else "творческий" if info.creative else "выживание"
            surf.blit(hud.small.render(f"{mode}   ·   {when}", True, SOFT), (rect.x + 14, rect.y + 29))

    def frame(self, dt):
        self.clock += dt
        self.handle_events()
        if not self.shell.quit:
            self.draw()

    def run(self):
        pygame.key.set_repeat(400, 35)
        clock = pygame.time.Clock()
        while not self.shell.quit:
            self.frame(min(clock.tick(60) / 1000.0, 0.1))
