"""Кубозем: воксельная песочница. Без параметров открывает меню; --seed или --creative запускают мир сразу."""
import argparse
import math
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor

import moderngl
import pygame

from drops import PICKUP_RADIUS, DROP_LIFE, Drop, drop_parts
from hud import Hud
from menu import Menu
from mesher import PAD, build_mesh
from mobs import DRAGON, Mobs, hand_parts, peer_parts
from net import Peer
from player import GRAVITY, UNBREAKABLE, Player
from realms import REALMS
from render import Renderer
from sounds import Audio, material_of
from survival import (ARMOR, ARMOR_POINT, ARMOR_SLOTS, armor_points, CHEST_SIZE, loot_for, CHARM, CHARM_FACTOR, DOOR_ITEM, DOOR_SWAP, FOOD, GATE_OF_REALM, GATES, HOTBAR_SIZE, MAX_FOOD, MINING, RECIPES, SPRINT_MIN_FOOD, STATIONS,
                      TRADES, Inventory, Stack, Vitals, attack_damage, block_drops, craft, is_block, item_limit, mining_time,
                      required_tool)
from textures import build_tiles
from world import (OPAQUE, AIR, BED, BED_BLOCK, BED_STATE, BLOCKS, BRICK, CHEST, CHUNK, SIDE_STEP, DOOR, DOOR_BLOCK, DOOR_STATE, GLASS, GLOW, IRON_DOOR, LAVA, PANEL_BOX,
                   PLANKS, ROCK, SAND, SOIL, TRUNK, TURF, WATER, World)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAVE_DIR = os.path.join(BASE_DIR, "save")
SAVE_PATH = os.path.join(SAVE_DIR, "world.json")
SHOTS_DIR = os.path.join(BASE_DIR, "screenshots")
DAY_LENGTH = 480.0
ACTION_DELAY = 0.22
ATTACK_DELAY = 0.42
KNOCKBACK = 7.0
STEP_LENGTH = 2.1
SWIM_LENGTH = 2.6
DIG_SOUND_DELAY = 0.24
LAND_SOUND_SPEED = 7.0
AUTOSAVE = 60.0
WORKERS = 3
MAX_JOBS = 6
UPLOADS_PER_FRAME = 3
MIN_RADIUS, MAX_RADIUS = 3, 16
STATION_REACH = 4
TRADE_REACH = 6.0
MENUS = ("inventory", "trade", "chest")
PEER_CHUNK_RADIUS = 5
VOID_Y = -14.0
LAVA_BURN_DELAY = 0.5
LAVA_DAMAGE = 3
GATE_SEARCH = 6
SLEEP_SECONDS = 2.5
MORNING = 0.02
ENEMY_NEAR_BED = 10.0
THROW_SPEED = 6.5
CAMERA_DISTANCE = 4.0
CAMERA_STEP = 0.2
CAMERA_MARGIN = 0.3
CREATIVE_HOTBAR = [TURF, SOIL, ROCK, SAND, PLANKS, BRICK, GLASS, TRUNK, GLOW]


def spiral(radius):
    cells = [(dx, dz) for dx in range(-radius, radius + 1) for dz in range(-radius, radius + 1)
             if dx * dx + dz * dz <= radius * radius + 1]
    cells.sort(key=lambda c: c[0] * c[0] + c[1] * c[1])
    return cells


class Shell:
    """Окно, графика и звук, общие для меню и игры."""

    def __init__(self):
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.init()
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
        pygame.display.gl_set_attribute(pygame.GL_DEPTH_SIZE, 24)
        pygame.display.set_mode((1280, 720), pygame.OPENGL | pygame.DOUBLEBUF | pygame.RESIZABLE, vsync=1)
        pygame.display.set_caption("Кубозем")
        self.ctx = moderngl.create_context(require=330)
        self.tiles = build_tiles()
        self.renderer = Renderer(self.ctx, self.tiles)
        self.hud = Hud(self.tiles)
        self.audio = Audio()
        self.quit = False


class Game:
    def __init__(self, seed=None, save_path=SAVE_PATH, radius=8, day_time=0.12, capture=True, creative=False,
                 shell=None, start=None):
        """start — мир, полученный от сервера: {"edits": ..., "player": ...}."""
        self.owns_shell = shell is None
        self.shell = shell or Shell()
        self.ctx = self.shell.ctx
        tiles = self.shell.tiles
        self.renderer = self.shell.renderer
        self.hud = self.shell.hud
        self.audio = self.shell.audio
        self.net = None
        self.exit_message = ""
        self.guests = {}
        self.stride = 0.0
        self.dig_sound = 0.0
        self.ambient_in = 6.0
        self.was_grounded = True
        self.was_in_water = False
        self.last_hp = 0
        self.block_colors = [tuple(tiles[b.side][..., :3].mean(axis=(0, 1)) / 255.0) for b in BLOCKS]

        self.root = World(seed, save_path)
        self.realms = {"surface": self.root}
        if start:
            self.root.saved_player = start["player"]
        self.realm = (self.root.saved_player or {}).get("realm", "surface")
        self.world = self._realm(self.realm)
        if start:
            self.world.load_edits(start["edits"])
        self.lava_burn = 0.0
        self.mobs = Mobs(self.world)
        self.attack_cool = 0.0
        self.swing = 0.0
        self.pool = ThreadPoolExecutor(WORKERS)
        self.gen_jobs = {}
        self.mesh_jobs = {}
        self.ready = []
        self.dirty = set()
        self.versions = {}

        self.radius = radius
        self.cells = spiral(radius + 1)
        self.last_chunk = None

        self.creative = creative
        self.inventory = Inventory()
        self.vitals = Vitals()
        self.held = None
        self.screen = None
        self.stations = set()
        self.recipe_scroll = 0
        self.trader = None
        self.chest = None
        self.chest_cell = None
        self.armor = Inventory(ARMOR_SLOTS)
        self.camera = 0  # 0 — от первого лица, 1 — со спины, 2 — спереди
        self.avatar = Peer(0, "", (0.0, 0.0, 0.0))
        self.sleep_time = 0.0
        self.mine_cell = None
        self.mine_progress = 0.0
        self.toast_text = ""
        self.toast_time = 0.0
        self.survival_state = {}

        self.day_time = day_time
        self.clock_time = 0.0
        self.selected = 0
        self.action_cool = 0.0
        self.autosave = AUTOSAVE
        self.fps = 0.0
        self.fps_frames = 0
        self.fps_time = 0.0
        self.hud_state = None
        self.visible = 0
        self.running = True

        self.player = self._create_player()
        if creative:
            for i, block in enumerate(CREATIVE_HOTBAR):
                self.inventory.slots[i] = Stack(block, item_limit(block))
        self.captured = False
        if capture:
            self.set_capture(True)
        if not creative and self.vitals.hp <= 0:
            self.respawn()

    def _create_player(self):
        saved = self.root.saved_player or {}
        self.spawns = dict(saved.get("realm_spawns", {}))
        if saved.get("spawn"):
            self.spawns["surface"] = saved["spawn"]
        if self.realm not in self.spawns:
            self.spawns[self.realm] = list(self.world.find_spawn())
        self.return_pos = saved.get("return_pos")
        x, y, z = saved.get("pos") or self.spawn
        self._ensure_chunks(x, z)
        player = Player(self.world, x, y, z)
        if not saved.get("pos"):
            player.place_at(x, y, z)
        if saved:
            player.yaw = saved.get("yaw", player.yaw)
            player.pitch = saved.get("pitch", player.pitch)
            player.flying = self.creative and saved.get("flying", False)
            self.guests = saved.get("guests", {})
            self.day_time = saved.get("day_time", self.day_time)
            self.survival_state = {k: saved[k] for k in ("inventory", "vitals", "armor") if k in saved}
        if not self.creative:
            if "inventory" in self.survival_state:
                self.inventory.load_json(self.survival_state["inventory"])
            if "vitals" in self.survival_state:
                self.vitals.load_json(self.survival_state["vitals"])
            if "armor" in self.survival_state:
                self.armor.load_json(self.survival_state["armor"])
            if not saved:
                self.toast("Держите ЛКМ на стволе дерева, E — инвентарь и крафт", 9.0)
        return player

    @property
    def spawn(self):
        """Точка возрождения в текущем измерении."""
        return self.spawns[self.realm]

    @property
    def boss(self):
        """Главный босс рядом, если он есть."""
        return next((m for m in self.mobs.mobs if m.kind is DRAGON), None)

    def _realm(self, name):
        """Мир измерения; особые создаются при первом посещении."""
        if name not in self.realms:
            world = REALMS[name](self.root.seed)
            world.load_edits(self.root.saved_realms.get(name, {}))
            world.load_chests(self.root.saved_realm_chests.get(name, {}))
            world.boss_done = bool((self.root.saved_player or {}).get("boss_done"))
            self.realms[name] = world
        return self.realms[name]

    def _switch_world(self, name):
        for future in list(self.gen_jobs) + list(self.mesh_jobs):
            future.result()
        self.gen_jobs.clear()
        self.mesh_jobs.clear()
        self.ready.clear()
        self.dirty.clear()
        self.versions.clear()
        self.renderer.clear()
        self.world.chunks.clear()
        if self.screen in MENUS:
            self.close_inventory()
        self._reset_mining()
        self.realm = name
        self.world = self._realm(name)
        self.player.world = self.world
        self.mobs = Mobs(self.world)
        self.last_chunk = None

    def travel(self, dest):
        """Перемещение через врата; в сетевой игре перемещаются все вместе."""
        if self.is_client:
            self.net.travel(dest)
            return
        p = self.player
        if self.realm == "surface":
            self.return_pos = list(p.pos)
        px, pz = p.pos[0], p.pos[2]
        self._switch_world(dest)
        if dest == "surface":
            landing = self.return_pos or self.spawns.setdefault("surface", list(self.root.find_spawn()))
        else:
            landing = list(self.world.find_landing(px, pz))
            self._ensure_chunks(landing[0], landing[2])
            self._place_return_gate(landing, dest)
            self.spawns[dest] = landing
        self._ensure_chunks(landing[0], landing[2])
        p.place_at(*landing)
        self.audio.play("portal")
        if self.net:
            self.net.realm_changed(dest, p.pos)

    def arrive(self, name, edits, landing):
        """Клиент: сервер перенёс всех в другое измерение."""
        self._switch_world(name)
        self.world.edits.clear()
        self.world.load_edits(edits)
        self.spawns[name] = list(landing)
        self._ensure_chunks(landing[0], landing[2])
        self.player.place_at(*landing)
        self.audio.play("portal")

    def _place_return_gate(self, landing, dest):
        """Ставит рядом с местом прибытия врата обратно, если поблизости их ещё нет."""
        get = self.world.get
        gate = GATE_OF_REALM[dest]
        lx, ly, lz = (math.floor(v) for v in landing)
        reach = range(-GATE_SEARCH, GATE_SEARCH + 1)
        if any(get(lx + dx, ly + dy, lz + dz) == gate for dx in reach for dy in reach for dz in reach):
            return
        for dx, dz in ((2, 0), (-2, 0), (0, 2), (0, -2), (2, 2), (-2, -2)):
            cell = (lx + dx, ly, lz + dz)
            below = get(cell[0], ly - 1, cell[2])
            if get(*cell) == AIR and below not in (None, AIR, LAVA, WATER):
                self.world.set(*cell, gate)
                return
        self.world.set(lx + 1, ly, lz, gate)  # неровное место: важнее, чтобы путь назад был

    def _ensure_chunks(self, x, z):
        cx, cz = math.floor(x) >> 4, math.floor(z) >> 4
        for dx in range(-1, 2):
            for dz in range(-1, 2):
                key = (cx + dx, cz + dz)
                if key not in self.world.chunks:
                    self.world.chunks[key] = self.world.generate(key)

    def set_capture(self, on):
        self.captured = on
        pygame.mouse.set_visible(not on)
        pygame.event.set_grab(on)
        pygame.mouse.get_rel()

    def toast(self, text, seconds=3.0):
        self.toast_text = text
        self.toast_time = seconds

    # --- Подгрузка чанков ---------------------------------------------------

    def _mesh_job(self, key, version):
        return key, version, build_mesh(self.world.padded(key, PAD))

    @property
    def is_client(self):
        return self.net is not None and not self.net.is_host

    def _peer_bodies(self):
        """Игроки по сети, вокруг которых хост должен держать загруженный мир."""
        return self.net.peers() if self.net and self.net.is_host else []

    def _collect_jobs(self):
        for future in [f for f in self.gen_jobs if f.done()]:
            key = self.gen_jobs.pop(future)
            if key not in self.world.chunks:
                arr = future.result()
                self.world.apply_edits_to(key, arr)  # правка могла прийти по сети, пока чанк строился
                self.world.chunks[key] = arr
        for future in [f for f in self.mesh_jobs if f.done()]:
            del self.mesh_jobs[future]
            self.ready.append(future.result())

    def _has_neighbours(self, key):
        chunks = self.world.chunks
        return all((key[0] + dx, key[1] + dz) in chunks for dx in (-1, 0, 1) for dz in (-1, 0, 1))

    def stream(self):
        self._collect_jobs()

        uploaded = 0
        while self.ready and uploaded < UPLOADS_PER_FRAME:
            key, version, (solid, clear) = self.ready.pop(0)
            if version != self.versions.get(key, 0):
                continue
            self.dirty.discard(key)
            self.renderer.upload(key, solid, clear)
            uploaded += 1

        pcx, pcz = math.floor(self.player.pos[0]) >> 4, math.floor(self.player.pos[2]) >> 4
        if (pcx, pcz) != self.last_chunk:
            self.last_chunk = (pcx, pcz)
            self._unload(pcx, pcz)

        jobs = len(self.gen_jobs) + len(self.mesh_jobs)
        if jobs >= MAX_JOBS:
            return
        generating = set(self.gen_jobs.values())
        meshing = {k for k, _, _ in self.ready} | set(self.mesh_jobs.values())
        chunks = self.world.chunks
        meshes = self.renderer.meshes
        limit = (self.radius + 1) ** 2
        for dx, dz in self.cells:
            key = (pcx + dx, pcz + dz)
            if key not in chunks:
                if key not in generating:
                    self.gen_jobs[self.pool.submit(self.world.generate, key)] = key
                    jobs += 1
            elif (key in self.dirty or key not in meshes) and key not in meshing:
                if dx * dx + dz * dz <= limit - 2 * self.radius and self._has_neighbours(key):
                    version = self.versions.get(key, 0)
                    self.mesh_jobs[self.pool.submit(self._mesh_job, key, version)] = key
                    jobs += 1
            if jobs >= MAX_JOBS:
                return

        for peer in self._peer_bodies():
            px, pz = math.floor(peer.pos[0]) >> 4, math.floor(peer.pos[2]) >> 4
            for dx, dz in spiral(PEER_CHUNK_RADIUS):
                key = (px + dx, pz + dz)
                if key not in chunks and key not in generating:
                    self.gen_jobs[self.pool.submit(self.world.generate, key)] = key
                    generating.add(key)
                    jobs += 1
                    if jobs >= MAX_JOBS:
                        return

    def _unload(self, pcx, pcz):
        keep_mesh = (self.radius + 2) ** 2
        keep_data = (self.radius + 4) ** 2
        peers = [(math.floor(p.pos[0]) >> 4, math.floor(p.pos[2]) >> 4) for p in self._peer_bodies()]

        def wanted(key):
            return ((key[0] - pcx) ** 2 + (key[1] - pcz) ** 2 <= keep_data
                    or any((key[0] - x) ** 2 + (key[1] - z) ** 2 <= (PEER_CHUNK_RADIUS + 3) ** 2 for x, z in peers))

        for key in [k for k in self.renderer.meshes
                    if (k[0] - pcx) ** 2 + (k[1] - pcz) ** 2 > keep_mesh]:
            self.renderer.drop(key)
        for key in [k for k in self.world.chunks if not wanted(k)]:
            del self.world.chunks[key]

    def _remesh_now(self, key):
        if key in self.world.chunks and self._has_neighbours(key):
            solid, clear = build_mesh(self.world.padded(key, PAD))
            self.renderer.upload(key, solid, clear)
            self.dirty.discard(key)

    def _changed(self, x, z):
        """После правки блока: обновить свой чанк и соседей, куда дотягивается свет."""
        cx, cz = x >> 4, z >> 4
        lx, lz = x & 15, z & 15
        now = {(cx, cz)}
        later = set()
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                if (dx, dz) == (0, 0):
                    continue
                gap_x = lx + 1 if dx < 0 else CHUNK - lx if dx > 0 else 0
                gap_z = lz + 1 if dz < 0 else CHUNK - lz if dz > 0 else 0
                gap = max(gap_x, gap_z)
                if gap == 1:
                    now.add((cx + dx, cz + dz))
                elif gap <= PAD:
                    later.add((cx + dx, cz + dz))
        for key in now | later:
            self.versions[key] = self.versions.get(key, 0) + 1
        for key in now:
            self._remesh_now(key)
        self.dirty |= {k for k in later if k in self.renderer.meshes}

    def _set_block(self, x, y, z, block):
        """Правка блока своим игроком; в сетевой игре о ней узнают остальные."""
        if not self.world.set(x, y, z, block):
            return False
        self._changed(x, z)
        if self.net:
            self.net.block_changed(x, y, z, block)
        return True

    def apply_remote_block(self, x, y, z, block):
        """Правка блока другим игроком."""
        old = self.world.get(x, y, z)
        if old == CHEST and block == AIR:
            self._spill_chest((x, y, z))
        self.world.apply_edit(x, y, z, block)
        self._changed(x, z)
        sound = block if block != AIR else old
        if sound not in (None, AIR, WATER):
            self.audio.play(f"break_{material_of(sound)}", (x + 0.5, y + 0.5, z + 0.5))

    def _door_run(self, x, y, z):
        """Все блоки двери, стоящие в одном столбце с указанным."""
        cells = [(x, y, z)]
        for step in (1, -1):
            yy = y + step
            while self.world.get(x, yy, z) in DOOR_ITEM:
                cells.append((x, yy, z))
                yy += step
        return cells

    def _clear_cell(self, cell):
        """Убирает блок; дверь убирается целиком."""
        block = self.world.get(*cell)
        if block in DOOR_ITEM:
            cells = self._door_run(*cell)
        elif block in BED_STATE:
            cells = self._bed_cells(cell)
        else:
            cells = [cell]
        if block == CHEST:
            self._spill_chest(cell)
        for c in cells:
            self._set_block(*c, AIR)
        return True

    def _bed_cells(self, cell):
        """Обе половины кровати."""
        is_head, facing = BED_STATE[self.world.get(*cell)]
        dx, dz = SIDE_STEP[facing]
        sign = -1 if is_head else 1
        other = (cell[0] + dx * sign, cell[1], cell[2] + dz * sign)
        return [cell, other] if self.world.get(*other) in BED_STATE else [cell]

    def _build_bed(self, foot):
        stack = self.inventory.slots[self.selected]
        facing = round(self.player.yaw / (math.tau / 4.0)) % 4
        dx, dz = SIDE_STEP[facing]
        head = (foot[0] + dx, foot[1], foot[2] + dz)
        get = self.world.get
        for x, y, z in (foot, head):
            below = get(x, y - 1, z)
            if get(x, y, z) not in (AIR, WATER) or below is None or not BLOCKS[below].solid or self.player.overlaps(x, y, z):
                self.toast("Здесь нет места для кровати")
                return False
        self._set_block(*foot, BED_BLOCK[(False, facing)])
        self._set_block(*head, BED_BLOCK[(True, facing)])
        self.audio.play("break_leaf", (foot[0] + 0.5, foot[1] + 0.5, foot[2] + 0.5), 0.6)
        if not self.creative:
            self.inventory.use_one(self.selected)
        return True

    # --- Сон ------------------------------------------------------------------

    def use_bed(self, cell):
        if self.world.fixed_time is not None:
            self.toast("В этом месте не уснуть")
            return False
        self.spawns[self.realm] = [cell[0] + 0.5, cell[1] + 0.6, cell[2] + 0.5]
        if math.sin(self.day_time * math.tau) >= -0.02:
            self.toast("Точка возрождения сохранена. Спать можно только ночью")
            return False
        p = self.player
        if any(m.kind.hostile and math.dist(m.pos, p.pos) < ENEMY_NEAR_BED for m in self.mobs.mobs):
            self.toast("Рядом враги, уснуть не получится")
            return False
        p.pos = list(self.spawns[self.realm])
        p.vel = [0.0, 0.0, 0.0]
        self.screen = "sleep"
        self.sleep_time = 0.0
        self._reset_mining()
        self.set_capture(False)
        if self.is_client:
            self.net.sleep(True)
        return True

    def get_up(self, notify=True):
        if self.screen != "sleep":
            return
        self.screen = None
        self.sleep_time = 0.0
        self.set_capture(True)
        if notify and self.is_client:
            self.net.sleep(False)

    def _update_sleep(self, dt):
        if self.screen != "sleep":
            return
        self.sleep_time += dt
        if self.is_client or self.sleep_time < SLEEP_SECONDS or (self.net and not self.net.all_asleep()):
            return
        self.day_time = MORNING
        self.get_up()
        if self.net:
            self.net.wake_all()

    # --- Сундуки --------------------------------------------------------------

    def chest_data(self, cell):
        """Содержимое сундука; деревенский наполняется при первом открытии."""
        world = self.world
        if cell not in world.chests:
            x, _, z = cell
            in_village = any(cell in v.chests for v in world.villages.near(x, z, x, z))
            world.chests[cell] = loot_for(cell, self.root.seed) if in_village else [None] * CHEST_SIZE
        return world.chests[cell]

    def open_chest(self, cell):
        if self.is_client:
            self.net.chest_open(cell)
            return
        if self.net and not self.net.claim_chest(cell, 0):
            self.toast("Сундук сейчас открыт другим игроком")
            return
        self.show_chest(cell, self.chest_data(cell))

    def chest_reply(self, cell, slots, busy):
        if busy:
            self.toast("Сундук сейчас открыт другим игроком")
        elif self.screen is None:
            self.show_chest(cell, slots)
        else:
            self.net.chest_close(cell)

    def show_chest(self, cell, slots):
        self.chest = Inventory(CHEST_SIZE)
        self.chest.load_json(slots)
        self.chest_cell = cell
        self.screen = "chest"
        self._reset_mining()
        self.audio.play("door", (cell[0] + 0.5, cell[1] + 0.5, cell[2] + 0.5))
        self.set_capture(False)

    def _commit_chest(self):
        if self.chest is None:
            return
        slots = self.chest.to_json()
        if self.is_client:
            self.net.chest_set(self.chest_cell, slots)
        else:
            self.world.chests[self.chest_cell] = slots

    def _end_chest(self):
        if self.chest is None:
            return
        self._commit_chest()
        if self.is_client:
            self.net.chest_close(self.chest_cell)
        elif self.net:
            self.net.release_chest(self.chest_cell)
        self.chest = None
        self.chest_cell = None

    def _spill_chest(self, cell):
        """Сломанный сундук: вещи высыпаются, а пустой не наполнится снова."""
        if self.is_client:
            return
        pos = (cell[0] + 0.5, cell[1] + 0.5, cell[2] + 0.5)
        for entry in self.chest_data(cell):
            if entry:
                vel = (random.uniform(-2.0, 2.0), random.uniform(2.0, 4.0), random.uniform(-2.0, 2.0))
                self.world.dropped.append(Drop(self.world, *entry, pos, vel))
        self.world.chests[cell] = [None] * CHEST_SIZE

    # --- Выброшенные предметы --------------------------------------------------

    def throw_stack(self, stack):
        p = self.player
        look = p.look
        start = (p.eye[0] + look[0] * 0.4, p.eye[1] - 0.3, p.eye[2] + look[2] * 0.4)
        vel = (look[0] * THROW_SPEED, look[1] * THROW_SPEED + 2.0, look[2] * THROW_SPEED)
        self.audio.play("throw")
        if self.is_client:
            self.net.drop(stack, start, vel)
        else:
            self.world.dropped.append(Drop(self.world, stack.item, stack.count, stack.durability, start, vel))

    def drop_selected(self, whole_stack):
        """Q — один предмет из выбранного слота, Ctrl+Q — всю стопку."""
        slots = self.inventory.slots
        stack = slots[self.selected]
        if stack is None:
            return
        if whole_stack or stack.count == 1:
            slots[self.selected] = None
            self.throw_stack(stack)
        else:
            stack.count -= 1
            self.throw_stack(Stack(stack.item, 1, stack.durability))

    def pick_up_stack(self, stack):
        """Кладёт подобранное в инвентарь; что не влезло, падает обратно."""
        left = self.inventory.take(stack)
        if left < stack.count:
            self.audio.play("pickup")
        if left:
            self.throw_stack(Stack(stack.item, left, stack.durability))

    def _update_drops(self, dt):
        if self.is_client:
            return
        world = self.world
        p = self.player
        peers = [peer for peer in self.net.peers() if peer.alive] if self.net else []
        for drop in list(world.dropped):
            drop.step(dt)
            if drop.age > DROP_LIFE or drop.pos[1] < VOID_Y:
                world.dropped.remove(drop)
            elif drop.delay <= 0.0:
                chest_height = (p.pos[0], p.pos[1] + 0.8, p.pos[2])
                if self.screen != "dead" and math.dist(chest_height, drop.pos) < PICKUP_RADIUS:
                    stack = Stack(drop.item, drop.count, drop.durability)
                    left = self.inventory.take(stack)
                    if left < drop.count:
                        self.audio.play("pickup")
                    if left:
                        drop.count = left
                    else:
                        world.dropped.remove(drop)
                    continue
                for peer in peers:
                    if math.dist((peer.pos[0], peer.pos[1] + 0.8, peer.pos[2]), drop.pos) < PICKUP_RADIUS:
                        self.net.pick_up(peer, (drop.item, drop.count, drop.durability))
                        world.dropped.remove(drop)
                        break

    def toggle_door(self, cell):
        cells = self._door_run(*cell)
        p = self.player
        # Створка поворачивается на петле: нельзя, чтобы она прошла сквозь игрока.
        if any(p.hits_box(*p.pos, c, PANEL_BOX[DOOR_SWAP[self.world.get(*c)]]) for c in cells):
            return False
        for c in cells:
            self._set_block(*c, DOOR_SWAP[self.world.get(*c)])
        self.audio.play("door", (cell[0] + 0.5, cell[1] + 0.5, cell[2] + 0.5))
        return True

    # --- Действия -----------------------------------------------------------

    def try_attack(self):
        """Удар по существу под прицелом. True, если оно есть, даже когда удар ещё не готов."""
        p = self.player
        mob = self.mobs.aimed(p.eye, p.look, p.target()[0])
        if mob is None:
            return False
        if self.attack_cool <= 0.0:
            self.attack_cool = ATTACK_DELAY
            self.swing = 1.0
            stack = self.inventory.slots[self.selected]
            self.audio.play("swing")
            self.audio.play("hit", tuple(mob.pos))
            if self.is_client:
                self.net.hit(mob, attack_damage(stack))  # добыча придёт от сервера
            else:
                for item, count in self.mobs.hit(mob, attack_damage(stack), p.pos):
                    if self.inventory.add(item, count):
                        self.toast("Инвентарь полон")
            if not self.creative and self.inventory.wear(self.selected):
                self.toast("Инструмент сломался")
                self.audio.play("snap")
        return True

    def _absorb(self, amount):
        """Броня гасит часть урона и изнашивается от каждого удара."""
        points = armor_points(self.armor)
        if not points:
            return amount
        for i in range(ARMOR_SLOTS):
            if self.armor.wear(i):
                self.toast("Часть брони сломалась")
                self.audio.play("snap")
        return max(1, round(amount * (1.0 - points * ARMOR_POINT)))

    def equip_selected(self):
        """Надевает броню из руки; надетая раньше возвращается в этот слот."""
        stack = self.inventory.slots[self.selected]
        slot = ARMOR[stack.item].slot
        self.inventory.slots[self.selected], self.armor.slots[slot] = self.armor.slots[slot], stack
        self.audio.play("click")
        return True

    def gear(self):
        """Что видно на персонаже другим игрокам: номера брони и предмет в руке."""
        held = self.inventory.slots[self.selected]
        return [s.item for s in self.armor.slots if s], held.item if held else None

    def hurt_player(self, amount, source):
        """Удар существа или шипа; оберег забирает часть урона."""
        if self.screen == "dead":
            return
        for i, stack in enumerate(self.inventory.slots):
            if stack and stack.item == CHARM:
                amount = max(1, round(amount * CHARM_FACTOR))
                if self.inventory.wear(i):
                    self.toast("Оберег рассыпался")
                break
        amount = self._absorb(amount)
        self.vitals.damage(amount)
        self.get_up()  # удар будит
        p = self.player
        dx, dz = p.pos[0] - source[0], p.pos[2] - source[2]
        length = math.hypot(dx, dz) or 1.0
        p.vel[0] = dx / length * KNOCKBACK
        p.vel[2] = dz / length * KNOCKBACK
        p.vel[1] = 5.0

    def dig(self):
        """Мгновенное разрушение (творческий режим)."""
        cell, _ = self.player.target()
        if cell is None or self.world.get(*cell) in UNBREAKABLE:
            return False
        return self._clear_cell(cell)

    def _reset_mining(self):
        self.mine_cell = None
        self.mine_progress = 0.0

    def mine_step(self, dt, held):
        """Один шаг добычи, пока удерживается кнопка."""
        cell = self.player.target()[0] if held else None
        block = self.world.get(*cell) if cell else None
        if block not in MINING:
            self._reset_mining()
            return
        if cell != self.mine_cell:
            self.mine_cell = cell
            self.mine_progress = 0.0
        seconds, _ = mining_time(block, self.inventory.slots[self.selected])
        self.mine_progress += dt / seconds
        self.dig_sound -= dt
        if self.dig_sound <= 0.0:
            self.dig_sound = DIG_SOUND_DELAY
            self.audio.play(f"dig_{material_of(block)}", (cell[0] + 0.5, cell[1] + 0.5, cell[2] + 0.5))
        if self.mine_progress >= 1.0:
            self._reset_mining()
            self.finish_mining(cell, block)

    def finish_mining(self, cell, block):
        inv = self.inventory
        _, harvest = mining_time(block, inv.slots[self.selected])
        self._clear_cell(cell)
        self.audio.play(f"break_{material_of(block)}", (cell[0] + 0.5, cell[1] + 0.5, cell[2] + 0.5))
        if harvest:
            for item, count in block_drops(block):
                if inv.add(item, count):
                    self.toast("Инвентарь полон")
        else:
            self.toast(required_tool(block) or "Этим блок не добыть")
        if inv.wear(self.selected):
            self.toast("Инструмент сломался")
            self.audio.play("snap")

    def build(self):
        stack = self.inventory.slots[self.selected]
        if stack is None or not is_block(stack.item):
            return False
        cell, free = self.player.target()
        if cell is None or free is None or self.player.overlaps(*free):
            return False
        if stack.item == BED:
            return self._build_bed(free)
        is_door = stack.item in (DOOR, IRON_DOOR)
        above = (free[0], free[1] + 1, free[2])
        if is_door and (self.world.get(*above) not in (AIR, WATER) or self.player.overlaps(*above)):
            return False
        placed = stack.item
        if is_door:
            # Закрытая створка встаёт у края, ближнего к игроку.
            look = round(self.player.yaw / (math.tau / 4.0)) % 4
            placed = DOOR_BLOCK[(DOOR_STATE[stack.item][0], (look + 2) % 4, False)]
        if not self._set_block(*free, placed):
            return False
        if is_door:
            self._set_block(*above, placed)
        self.audio.play(f"break_{material_of(stack.item)}", (free[0] + 0.5, free[1] + 0.5, free[2] + 0.5), 0.6)
        if not self.creative:
            self.inventory.use_one(self.selected)
        return True

    def use(self, repeat=False):
        """Правая кнопка: житель, станция, еда или постройка."""
        cell, _ = self.player.target()
        if not repeat:
            mob = self.mobs.aimed(self.player.eye, self.player.look, cell)
            if mob is not None and mob.home is not None:
                self.open_trade(mob)
                return True
        block = self.world.get(*cell) if cell else None
        if not repeat and block in DOOR_ITEM:
            return self.toggle_door(cell)
        if not repeat and block == CHEST:
            self.open_chest(cell)
            return True
        if not repeat and block in BED_STATE:
            self.use_bed(cell)
            return True
        if not repeat and block in GATES:
            self.travel("surface" if GATES[block] == self.realm else GATES[block])
            return True
        if not repeat and cell and self.world.get(*cell) in STATIONS:
            self.open_inventory()
            return True
        stack = self.inventory.slots[self.selected]
        if not repeat and stack and stack.item in ARMOR:
            return self.equip_selected()
        if stack and stack.item in FOOD and not self.creative:
            if repeat or self.vitals.food >= MAX_FOOD:
                return False
            self.vitals.eat(stack.item)
            self.inventory.use_one(self.selected)
            self.audio.play("eat")
            return True
        return self.build()

    def pick(self):
        cell, _ = self.player.target()
        if cell is None:
            return
        block = self.world.get(*cell)
        if block in UNBREAKABLE:
            return
        block = DOOR_ITEM.get(block, block)
        for i, stack in enumerate(self.inventory.slots[:HOTBAR_SIZE]):
            if stack and stack.item == block:
                self.selected = i
                return
        if self.creative:
            self.inventory.slots[self.selected] = Stack(block, item_limit(block))

    def nearby_stations(self):
        ex, ey, ez = (math.floor(c) for c in self.player.eye)
        reach = range(-STATION_REACH, STATION_REACH + 1)
        found = set()
        for dx in reach:
            for dy in reach:
                for dz in reach:
                    block = self.world.get(ex + dx, ey + dy, ez + dz)
                    if block in STATIONS:
                        found.add(block)
        return found

    def open_inventory(self):
        self.stations = self.nearby_stations()
        self.screen = "inventory"
        self._reset_mining()
        self.audio.play("ui_open")
        self.set_capture(False)

    def open_trade(self, mob):
        if mob.flee > 0.0:
            self.toast("Житель напуган и не хочет меняться")
            return
        self.trader = mob
        mob.trading = True
        if self.is_client:
            self.net.trade(mob, True)
        self.recipe_scroll = 0
        self.screen = "trade"
        self._reset_mining()
        self.audio.play("ui_open")
        self.audio.play("villager_idle", tuple(mob.pos))
        self.set_capture(False)

    def menu_items(self):
        """Список справа в открытом окне: рецепты или сделки жителя."""
        if self.screen == "chest":
            return []
        return TRADES[self.trader.kind.name] if self.trader else RECIPES

    def _end_trade(self):
        if self.trader:
            self.trader.trading = False
            if self.is_client:
                self.net.trade(self.trader, False)
            self.trader = None
            self.recipe_scroll = 0

    def _return_held(self):
        if self.held:
            self.inventory.put(self.held)
            self.held = None

    def close_inventory(self):
        self._return_held()
        self._end_trade()
        self._end_chest()
        self.screen = None
        self.audio.play("ui_close")
        self.set_capture(True)

    def _inventory_click(self, button, pos):
        items = self.menu_items()
        size = pygame.display.get_window_size()
        hit = self.hud.hit_test(size, pos, self.recipe_scroll, len(items), self.screen == "chest")
        if hit is None:
            if self.held and not self.hud.layout(size)[0].collidepoint(pos):
                self._throw_held(button)
            return
        kind, index = hit
        if kind == "recipe":
            # Пока предмет в руке, крафт запрещён: результат мог бы занять его место.
            if button == 1 and self.held is None:
                made = craft(items[index], self.inventory, self.stations)
                success = "trade" if self.trader else "craft"
                self.audio.play(success if made else "deny")
            return

        self.audio.play("click")
        slots = {"chest": self.chest.slots if self.chest else None, "armor": self.armor.slots}.get(kind, self.inventory.slots)
        stack = slots[index]
        held = self.held
        if kind == "armor" and held and (held.item not in ARMOR or ARMOR[held.item].slot != index):
            self.audio.play("deny")
            return
        same = held and stack and held.item == stack.item
        limit = item_limit(stack.item) if stack else 0
        if button == 1:
            if same and limit > 1:
                moved = min(held.count, limit - stack.count)
                stack.count += moved
                held.count -= moved
                self.held = held if held.count else None
            else:
                slots[index], self.held = held, stack
        elif button == 3:
            if held is None and stack:
                half = (stack.count + 1) // 2
                self.held = Stack(stack.item, half, stack.durability)
                stack.count -= half
                if stack.count == 0:
                    slots[index] = None
            elif held and (stack is None or (same and stack.count < limit)):
                if stack is None:
                    slots[index] = Stack(held.item, 1, held.durability)
                else:
                    stack.count += 1
                held.count -= 1
                self.held = held if held.count else None
        self._commit_chest()

    def _throw_held(self, button):
        """Клик за пределами окна: ЛКМ — вся стопка в руке, ПКМ — один предмет."""
        held = self.held
        if button == 1:
            self.held = None
            self.throw_stack(held)
        elif button == 3:
            held.count -= 1
            self.throw_stack(Stack(held.item, 1, held.durability))
            self.held = held if held.count else None

    def _scroll_recipes(self, delta):
        rows = self.hud.visible_rows(pygame.display.get_window_size())
        self.recipe_scroll = max(0, min(max(0, len(self.menu_items()) - rows), self.recipe_scroll + delta))

    def die(self):
        self._return_held()
        self._end_trade()
        self._end_chest()
        self.inventory.lose_half()
        self._reset_mining()
        self.audio.play("death")
        self.screen = "dead"
        self.set_capture(False)

    def respawn(self):
        x, y, z = self.spawn
        self._ensure_chunks(x, z)
        self.player.place_at(x, y, z)
        self.vitals = Vitals()
        self.screen = None
        self.last_chunk = None
        self.mobs.mobs = [m for m in self.mobs.mobs if not m.kind.hostile]
        self.mobs.shots.clear()
        self.audio.play("respawn")
        self.set_capture(True)

    def change_radius(self, delta):
        self.radius = max(MIN_RADIUS, min(MAX_RADIUS, self.radius + delta))
        self.cells = spiral(self.radius + 1)
        self.last_chunk = None

    def save(self):
        p = self.player
        others = {name: list(point) for name, point in self.spawns.items() if name != "surface"}
        data = {"pos": list(p.pos), "yaw": p.yaw, "pitch": p.pitch, "flying": p.flying, "day_time": self.day_time,
                "spawn": self.spawns.get("surface"), "realm_spawns": others, "realm": self.realm,
                "return_pos": self.return_pos, "creative": self.creative, "guests": self.guests,
                "boss_done": self._realm("edge").boss_done}
        if self.creative:
            data.update(self.survival_state)
        else:
            data["inventory"] = self.inventory.to_json()
            data["vitals"] = self.vitals.to_json()
            data["armor"] = self.armor.to_json()
        if self.net:
            self.net.on_save(data)
        self.root.save(data, {name: w for name, w in self.realms.items() if name != "surface"})

    def screenshot(self, path=None):
        if path is None:
            os.makedirs(SHOTS_DIR, exist_ok=True)
            path = os.path.join(SHOTS_DIR, time.strftime("%Y%m%d-%H%M%S.png"))
        size = pygame.display.get_window_size()
        data = self.ctx.screen.read(viewport=(0, 0, size[0], size[1]), components=3)
        pygame.image.save(pygame.image.frombytes(data, size, "RGB", True), path)
        return path

    # --- Цикл ---------------------------------------------------------------

    def handle_events(self):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.running = False
                self.shell.quit = True
            elif e.type == pygame.KEYDOWN:
                self._key(e.key)
            elif e.type == pygame.WINDOWFOCUSLOST and self.captured:
                self.set_capture(False)
            elif e.type == pygame.MOUSEBUTTONDOWN:
                self._mouse(e.button, e.pos)
            elif e.type == pygame.MOUSEWHEEL:
                if self.screen in MENUS:
                    self._scroll_recipes(-e.y)
                elif self.captured:
                    self.selected = (self.selected - e.y) % HOTBAR_SIZE
                    self.audio.play("tick")

    def _key(self, key):
        if key == pygame.K_F2:
            self.screenshot()
        elif self.screen in MENUS:
            if key in (pygame.K_e, pygame.K_ESCAPE):
                self.close_inventory()
        elif self.screen == "dead":
            return
        elif self.screen == "sleep":
            if key == pygame.K_ESCAPE:
                self.get_up()
        elif key == pygame.K_ESCAPE:
            self.set_capture(not self.captured)
        elif not self.captured:
            if key == pygame.K_q:
                self.running = False
        elif key == pygame.K_e:
            self.open_inventory()
        elif key == pygame.K_F5:
            self.camera = (self.camera + 1) % 3
        elif key == pygame.K_q:
            self.drop_selected(bool(pygame.key.get_mods() & pygame.KMOD_CTRL))
        elif key == pygame.K_f and self.creative:
            self.player.flying = not self.player.flying
            self.player.vel[1] = 0.0
        elif pygame.K_1 <= key <= pygame.K_9:
            self.selected = key - pygame.K_1
            self.audio.play("tick")
        elif key == pygame.K_m:
            self.toast("Звук выключен" if self.audio.toggle_mute() else "Звук включён")
        elif key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
            self.change_radius(1)
        elif key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self.change_radius(-1)

    def _mouse(self, button, pos):
        if self.screen == "sleep":
            return
        if self.screen == "dead":
            if button == 1:
                self.respawn()
        elif self.screen in MENUS:
            self._inventory_click(button, pos)
        elif not self.captured:
            if button == 1:
                self.set_capture(True)
        elif button == 3:
            self.use()
            self.action_cool = ACTION_DELAY
        elif button == 1 and self.creative:
            if not self.try_attack():
                self.dig()
            self.action_cool = ACTION_DELAY
        elif button == 2:
            self.pick()

    def _head_in_water(self):
        x, y, z = self.player.eye
        return self.world.get(math.floor(x), math.floor(y + 0.13), math.floor(z)) == WATER

    def _footsteps(self, dt):
        p = self.player
        if p.in_water and not self.was_in_water and not p.flying:
            self.audio.play("splash")
        self.was_in_water = p.in_water

        x, y, z = p.pos
        below = self.world.get(math.floor(x), math.floor(y - 0.05), math.floor(z))
        if p.on_ground and not self.was_grounded and p.impact > LAND_SOUND_SPEED and not p.in_water:
            self.audio.play("land")
        self.was_grounded = p.on_ground
        if self.creative:
            p.impact = 0.0

        speed = math.hypot(p.vel[0], p.vel[2])
        if p.flying or speed < 0.5:
            return
        if p.in_water:
            self.stride += speed * dt
            if self.stride >= SWIM_LENGTH:
                self.stride = 0.0
                self.audio.play("swim")
        elif p.on_ground and below not in (None, AIR, WATER):
            self.stride += speed * dt
            if self.stride >= STEP_LENGTH:
                self.stride = 0.0
                self.audio.play(f"step_{material_of(below)}")

    def _apply_door_moves(self):
        """Жители открыли или закрыли двери: обновить геометрию и сообщить игрокам."""
        for x, y, z, block in self.mobs.door_moves:
            self._changed(x, z)
            if self.net:
                self.net.block_changed(x, y, z, block)
            self.audio.play("door", (x + 0.5, y + 0.5, z + 0.5), 0.5)
        self.mobs.door_moves.clear()

    def _play_events(self):
        if self.net:
            self.net.send_events(self.mobs.events)
        for name, pos in self.mobs.events:
            # Голос босса слышен на всю арену, он летает дальше обычной слышимости.
            self.audio.play(name, None if name.startswith("dragon_") else pos)
            if name == "dragon_die":
                self.toast("Лазурный дракон повержен!", 6.0)
        self.mobs.events.clear()

    def _ambience(self, dt):
        """Ветер на открытом воздухе и редкие звуки по обстановке."""
        ex, ey, ez = self.player.eye
        under = self._head_in_water()
        open_air = self.mobs.sky_exposed(math.floor(ex), math.floor(ey), math.floor(ez))
        self.audio.set_wind(0.0 if under or not open_air else 0.07 + min(0.12, max(0.0, ey - 45.0) * 0.003), dt)

        self.ambient_in -= dt
        if self.ambient_in > 0.0:
            return
        self.ambient_in = random.uniform(5.0, 16.0)
        angle = random.uniform(0.0, math.tau)
        around = (ex + math.cos(angle) * 10.0, ey + random.uniform(-2.0, 5.0), ez + math.sin(angle) * 10.0)
        sun = math.sin(self.day_time * math.tau)
        if under:
            self.audio.play("bubbles")
        elif self.world.fixed_time is not None:
            return  # в особых измерениях нет птиц, сверчков и капели
        elif not open_air:
            self.audio.play("drip", around)
        elif sun > 0.1:
            self.audio.play("bird", around)
        elif sun < -0.05:
            self.audio.play("cricket", around)

    def _watch_health(self):
        if self.vitals.hp < self.last_hp:
            self.audio.play("hurt")
        self.last_hp = self.vitals.hp

    def update(self, dt):
        if not self.captured and self.screen is None and not self.net:
            return  # пауза; в сетевой игре мир продолжает жить

        self.audio.listen(self.player.eye, self.player.yaw)
        speed = 30.0 if self.captured and not self.is_client and pygame.key.get_pressed()[pygame.K_t] else 1.0
        self.day_time = (self.day_time + dt * speed / DAY_LENGTH) % 1.0
        self.clock_time += dt
        self.toast_time -= dt
        if self.toast_time <= 0.0:
            self.toast_text = ""
        self.attack_cool -= dt
        self.swing = max(0.0, self.swing - dt * 4.0)
        if self.trader and (self.trader not in self.mobs.mobs
                            or math.dist(self.trader.pos, self.player.pos) > TRADE_REACH):
            self.close_inventory()

        forward = strafe = 0.0
        jump = down = sprint = mining = False
        if self.captured:
            dx, dy = pygame.mouse.get_rel()
            self.player.turn(dx, dy)
            keys = pygame.key.get_pressed()
            forward = float(keys[pygame.K_w]) - float(keys[pygame.K_s])
            strafe = float(keys[pygame.K_d]) - float(keys[pygame.K_a])
            jump = keys[pygame.K_SPACE]
            down = keys[pygame.K_LSHIFT]
            sprint = keys[pygame.K_LCTRL]

            self.action_cool -= dt
            buttons = pygame.mouse.get_pressed()
            attacking = buttons[0] and self.try_attack()
            mining = buttons[0] and not attacking
            if self.action_cool <= 0.0 and (buttons[2] or (self.creative and mining)):
                self.use(repeat=True) if buttons[2] else self.dig()
                self.action_cool = ACTION_DELAY

        sprinting = sprint and forward > 0 and (self.creative or self.vitals.food >= SPRINT_MIN_FOOD)
        self.player.update(dt, forward, strafe, jump, down, sprinting)
        self._footsteps(dt)
        self.avatar.phase += math.hypot(self.player.vel[0], self.player.vel[2]) * dt * 5.0
        if not self.creative:
            self.mine_step(dt, mining)
            if self.mine_cell is not None:
                self.swing = max(self.swing, abs(math.sin(self.clock_time * 9.0)) * 0.7)
            self.survive(dt)
        if self.player.pos[1] < VOID_Y and self.screen != "dead":
            if self.creative:
                self.player.place_at(*self.spawn)
            else:
                self.vitals.damage(self.vitals.hp)  # пустота под островами
        if not self.is_client:
            others = self.net.targets() if self.net else ()
            clock = self.day_time if self.world.fixed_time is None else self.world.fixed_time
            self.mobs.update(dt, None if self.screen == "dead" else self.player, clock, self.hurt_player,
                             aggressive=not self.creative, others=others)
        self._apply_door_moves()
        self._update_drops(dt)
        self._update_sleep(dt)
        if self.net:
            self.net.update(dt)
        self._play_events()
        self._ambience(dt)
        self._watch_health()

        self.autosave -= dt
        if self.autosave <= 0.0:
            self.autosave = AUTOSAVE
            self.save()

    def survive(self, dt):
        if self.screen == "dead":
            return
        vitals = self.vitals
        if self.player.impact > 0.0:
            vitals.fall(self.player.impact, GRAVITY)
            self.player.impact = 0.0
        x, y, z = self.player.pos
        self.lava_burn -= dt
        if self.world.get(math.floor(x), math.floor(y + 0.3), math.floor(z)) == LAVA and self.lava_burn <= 0.0:
            self.lava_burn = LAVA_BURN_DELAY
            vitals.damage(LAVA_DAMAGE)
        vitals.update(dt, self._head_in_water())
        if vitals.hp <= 0:
            self.die()

    def _view(self, eye, look):
        """Положение камеры и направление взгляда для текущего режима."""
        if self.camera == 0:
            return eye, look
        sign = -1.0 if self.camera == 1 else 1.0
        get = self.world.get
        distance = 0.0
        while distance < CAMERA_DISTANCE:
            probe = distance + CAMERA_STEP
            cell = [math.floor(eye[i] + look[i] * sign * probe) for i in range(3)]
            block = get(*cell)
            if block is None or OPAQUE[block]:
                break
            distance = probe
        distance = max(0.0, distance - CAMERA_MARGIN)
        camera = tuple(eye[i] + look[i] * sign * distance for i in range(3))
        return camera, look if self.camera == 1 else tuple(-v for v in look)

    def draw(self):
        size = pygame.display.get_window_size()
        p = self.player
        target, _ = p.target()
        eye, view = self._view(p.eye, p.look)
        fov = math.radians(84.0 if math.hypot(p.vel[0], p.vel[2]) > 5.6 else 76.0)
        progress = self.mine_progress if target == self.mine_cell else 0.0
        parts = self.mobs.parts(eye)
        if self.camera:
            a = self.avatar
            a.id, a.shown, a.yaw, a.swing = 1, p.pos, p.yaw, self.swing
            a.armor, a.held = self.gear()
            parts += peer_parts(a, self.mobs.light_at(p.eye), self.block_colors)
        elif self.screen is None:
            parts += hand_parts(self.inventory.slots[self.selected], eye, p.look, p.yaw, p.pitch, self.swing,
                                self.mobs.light_at(eye), self.block_colors)
        for drop in self.world.dropped:
            parts += drop_parts(drop, self.mobs.light_at(drop.pos), self.block_colors)
        if self.net:
            for peer in self.net.peers():
                parts += peer_parts(peer, self.mobs.light_at(peer.shown), self.block_colors)
        self.visible = self.renderer.draw(size, eye, view, self.radius, self.day_time, self.clock_time,
                                          target, self._head_in_water(), fov, progress, parts, self.world.look,
                                          PANEL_BOX.get(self.world.get(*target)) if target else None)

        mode = "творческий" if self.creative else "выживание"
        if self.world.title:
            mode += f"   ·   {self.world.title}"
        lines = [f"FPS {self.fps:.0f}   ·   чанков {self.visible}   ·   дальность {self.radius}",
                 f"X {p.pos[0]:.0f}  Y {p.pos[1]:.0f}  Z {p.pos[2]:.0f}   ·   {mode}"]
        if self.net:
            lines.append(self.net.status())
        v = self.vitals
        mouse = pygame.mouse.get_pos() if self.screen in MENUS else None
        boss_hp = math.ceil(self.boss.hp) if self.boss else None
        state = (size, boss_hp, self.armor.snapshot(), self.chest.snapshot() if self.chest else None, int(self.sleep_time * 8), self.inventory.snapshot(), self.held.key() if self.held else None, self.selected,
                 tuple(lines), self.captured, self.screen, v.hp, v.food, math.ceil(v.air * 2),
                 self.recipe_scroll, tuple(sorted(self.stations)), self.toast_text, mouse)
        if state != self.hud_state:
            self.hud_state = state
            self.renderer.upload_hud(self.hud.compose(size, self, lines, mouse))
        self.renderer.draw_hud(v.hurt)

    def frame(self, dt):
        self.handle_events()
        self.audio.set_paused(not self.captured and self.screen is None)
        self.update(dt)
        self.stream()
        self.draw()
        pygame.display.flip()

        self.fps_frames += 1
        self.fps_time += dt
        if self.fps_time >= 0.5:
            self.fps = self.fps_frames / self.fps_time
            self.fps_frames = 0
            self.fps_time = 0.0

    def run(self):
        clock = pygame.time.Clock()
        while self.running:
            self.frame(min(clock.tick(240) / 1000.0, 0.1))
        self.close()

    def close(self):
        self._return_held()
        self._end_trade()
        self._end_chest()
        self.save()
        if self.net:
            self.net.close()
        self.pool.shutdown(wait=True, cancel_futures=True)
        if self.owns_shell:
            pygame.quit()
        else:
            self.renderer.clear()
            self.audio.quiet()
            self.set_capture(False)


def main():
    parser = argparse.ArgumentParser(description="Кубозем — воксельная песочница")
    parser.add_argument("--seed", type=int, help="зерно нового мира (для существующего сохранения не действует)")
    parser.add_argument("--radius", type=int, default=8, help="дальность прорисовки в чанках")
    parser.add_argument("--creative", action="store_true", help="творческий режим: полёт и бесконечные блоки")
    args = parser.parse_args()
    radius = max(MIN_RADIUS, min(MAX_RADIUS, args.radius))
    if args.seed is not None or args.creative:
        Game(seed=args.seed, radius=radius, creative=args.creative).run()
        return
    shell = Shell()
    Menu(shell, Game, radius, SAVE_DIR).run()
    pygame.quit()


if __name__ == "__main__":
    main()
