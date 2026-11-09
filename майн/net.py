"""Сетевая игра по TCP: один игрок держит мир (хост), остальные подключаются к нему."""
import json
import math
import queue
import socket
import struct
import threading

from drops import Drop
from mobs import KINDS, VILLAGERS, Mob, Target, ThornShot
from survival import ARMOR, ARMOR_SLOTS, CHEST_SIZE, NAMES, Stack, item_limit
from world import BASE, BLOCKS, HEIGHT

PORT = 47800
VERSION = 5
MAX_PLAYERS = 8
SEND_PERIOD = 1.0 / 15.0
MAX_FROM_SERVER = 64 * 1024 * 1024
MAX_FROM_CLIENT = 1024 * 1024
MAX_HIT = 28
BACKLOG = 32
SNAP_DISTANCE = 6.0
HELLO_TIMEOUT = 10.0


class NetError(Exception):
    """Понятная игроку причина, по которой не удалось подключиться."""


class Link:
    """Сообщения JSON поверх TCP: чтение и отправка идут в отдельных потоках."""

    def __init__(self, sock, limit):
        self.sock = sock
        self.limit = limit
        self.inbox = queue.Queue()
        self.outbox = queue.Queue()
        self.alive = True
        sock.settimeout(None)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.reader = threading.Thread(target=self._read_loop, daemon=True)
        self.writer = threading.Thread(target=self._write_loop, daemon=True)
        self.reader.start()
        self.writer.start()

    def _read_exact(self, count):
        data = bytearray()
        while len(data) < count:
            part = self.sock.recv(min(count - len(data), 65536))
            if not part:
                raise ConnectionError
            data.extend(part)
        return bytes(data)

    def _read_loop(self):
        try:
            while True:
                size = struct.unpack(">I", self._read_exact(4))[0]
                if size > self.limit:
                    break
                self.inbox.put(json.loads(self._read_exact(size).decode("utf-8")))
        except (OSError, ConnectionError, ValueError):
            pass
        self.alive = False
        self.inbox.put(None)

    def _write_loop(self):
        try:
            while True:
                frame = self.outbox.get()
                if frame is None:
                    break
                self.sock.sendall(frame)
        except OSError:
            self.alive = False

    def send(self, message, droppable=False):
        """droppable — можно пропустить, если получатель не успевает."""
        if self.alive and not (droppable and self.outbox.qsize() > BACKLOG):
            data = json.dumps(message, separators=(",", ":")).encode("utf-8")
            self.outbox.put(struct.pack(">I", len(data)) + data)

    def drain(self):
        messages = []
        while not self.inbox.empty():
            messages.append(self.inbox.get_nowait())
        return messages

    def close(self):
        self.outbox.put(None)
        self.writer.join(2.0)
        self.alive = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()


def lan_address():
    """Адрес компьютера в локальной сети. Пакеты при этом не отправляются."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def parse_address(text):
    """'192.168.1.5' или '192.168.1.5:47800' -> (адрес, порт)."""
    text = text.strip()
    if not text:
        raise NetError("Введите адрес сервера")
    host, separator, port = text.rpartition(":")
    if not separator:
        return text, PORT
    if not host or not port.isdigit() or not 0 < int(port) < 65536:
        raise NetError("Неверный порт в адресе")
    return host, int(port)


def join(address, port, name):
    """Подключается к серверу. Возвращает (Link, приветствие) или бросает NetError."""
    try:
        sock = socket.create_connection((address, port), timeout=6.0)
    except OSError as error:
        raise NetError(f"Не удалось подключиться к {address}:{port}") from error
    link = Link(sock, MAX_FROM_SERVER)
    link.send({"t": "hello", "v": VERSION, "name": name})
    try:
        reply = link.inbox.get(timeout=HELLO_TIMEOUT)
    except queue.Empty as error:
        link.close()
        raise NetError("Сервер не ответил") from error
    if reply is None:
        link.close()
        raise NetError("Сервер разорвал соединение")
    if reply.get("t") != "welcome":
        link.close()
        raise NetError(reply.get("why", "Сервер отказал в подключении"))
    return link, reply


def _glide(current, goal, dt):
    """Плавно подводит позицию к последней полученной. Возвращает пройденный путь."""
    gap = math.dist(current, goal)
    if gap > SNAP_DISTANCE:
        current[:] = goal
        return 0.0
    k = min(1.0, dt * 12.0)
    for i in range(3):
        current[i] += (goal[i] - current[i]) * k
    return gap * k


def _turned(yaw, goal, dt):
    return yaw + ((goal - yaw + math.pi) % math.tau - math.pi) * min(1.0, dt * 12.0)


class Peer:
    """Другой игрок: pos — последняя известная точка, shown — сглаженная для отрисовки."""

    def __init__(self, peer_id, name, pos):
        self.id = peer_id
        self.name = name
        self.pos = list(pos)
        self.shown = list(pos)
        self.yaw = 0.0
        self.goal_yaw = 0.0
        self.swing = 0.0
        self.phase = 0.0
        self.alive = True
        self.link = None
        self.trading = None
        self.sleeping = False
        self.armor = []
        self.held = None

    def advance(self, dt):
        self.phase += _glide(self.shown, self.pos, dt) * 5.0
        self.yaw = _turned(self.yaw, self.goal_yaw, dt)

    def apply(self, pos, yaw, swing):
        self.pos = list(pos)
        self.goal_yaw = yaw
        self.swing = swing


def _number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValueError
    return float(value)


class HostSession:
    """Мир и существа считаются здесь, клиенты получают снимки."""

    is_host = True

    def __init__(self, game, name, port=PORT):
        self.game = game
        self.name = name
        self.port = port
        self.peers_by_id = {}
        self.ids = 1
        self.waiting = []
        self.fresh = queue.Queue()
        self.timer = 0.0
        self.chest_users = {}  # клетка сундука -> id игрока (0 — хост)
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(("", port))
        self.listener.listen(MAX_PLAYERS)
        self.address = f"{lan_address()}:{port}"
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self):
        while True:
            try:
                sock, _ = self.listener.accept()
            except OSError:
                return
            self.fresh.put(Link(sock, MAX_FROM_CLIENT))

    def peers(self):
        return list(self.peers_by_id.values())

    def status(self):
        return f"Сервер {self.address}   ·   игроков: {len(self.peers_by_id) + 1}"

    def targets(self):
        prey = not self.game.creative
        return [Target(p, self._hurt_callback(p), prey) for p in self.peers() if p.alive]

    def _hurt_callback(self, peer):
        def hurt(amount, source):
            peer.link.send({"t": "hurt", "a": amount, "s": list(source)})
        return hurt

    def _broadcast(self, message, exclude=None, droppable=False):
        for peer in self.peers():
            if peer is not exclude:
                peer.link.send(message, droppable)

    # --- Подключение и выход --------------------------------------------------

    def _admit(self):
        while not self.fresh.empty():
            self.waiting.append(self.fresh.get_nowait())
        for link in list(self.waiting):
            for message in link.drain():
                self.waiting.remove(link)
                if message is None:
                    link.close()
                else:
                    self._greet(link, message)
                break

    def _greet(self, link, hello):
        why = None
        name = hello.get("name")
        taken = {p.name for p in self.peers()} | {self.name}
        if hello.get("t") != "hello" or hello.get("v") != VERSION:
            why = "Разные версии игры"
        elif not isinstance(name, str) or not name.strip() or len(name) > 16:
            why = "Недопустимое имя игрока"
        elif name in taken:
            why = "Игрок с таким именем уже на сервере"
        elif len(self.peers_by_id) + 1 >= MAX_PLAYERS:
            why = "На сервере нет свободных мест"
        if why:
            link.send({"t": "refused", "why": why})
            link.close()
            return

        game = self.game
        peer_id = self.ids
        self.ids += 1
        state = game.guests.get(name)
        if state and state.get("realm", "surface") != game.realm:
            # Сохранённая точка относится к другому измерению.
            state = {k: v for k, v in state.items() if k not in ("pos", "realm")}
        link.send({"t": "welcome", "id": peer_id, "seed": game.world.seed, "creative": game.creative,
                   "day": game.day_time, "spawn": list(game.spawn), "edits": game.world.edits_json(), "state": state,
                   "realm": game.realm})
        start = state["pos"] if state and state.get("pos") else game.spawn
        peer = Peer(peer_id, name, start)
        peer.link = link
        self.peers_by_id[peer_id] = peer
        game.toast(f"{name} присоединяется к игре")
        self._broadcast({"t": "toast", "x": f"{name} присоединяется к игре"}, exclude=peer)

    def _leave(self, peer):
        del self.peers_by_id[peer.id]
        if peer.trading:
            peer.trading.trading = False
        self.chest_users = {c: u for c, u in self.chest_users.items() if u != peer.id}
        peer.link.close()
        self.game.toast(f"{peer.name} выходит из игры")
        self._broadcast({"t": "toast", "x": f"{peer.name} выходит из игры"})

    # --- Сообщения клиентов ---------------------------------------------------

    def _handle(self, peer, m):
        kind = m["t"]
        if kind == "pos":
            pos = [_number(v) for v in m["p"][:3]]
            if len(pos) == 3:
                peer.apply(pos, _number(m["y"]), max(0.0, min(1.0, _number(m["w"]))))
                peer.alive = bool(m["a"])
                peer.armor = [a for a in m["r"][:ARMOR_SLOTS] if a in ARMOR]
                held = m["i"]
                peer.held = held if isinstance(held, int) and (held < len(BLOCKS) or held in NAMES) else None
        elif kind == "b":
            x, y, z, block = (int(v) for v in m["b"])
            if 0 <= y < HEIGHT and 0 <= block < len(BLOCKS) and block != BASE:
                self.game.apply_remote_block(x, y, z, block)
                self._broadcast({"t": "b", "b": [x, y, z, block]}, exclude=peer)
        elif kind == "hit":
            mob = self._mob(m["id"])
            if mob is not None:
                damage = max(1, min(MAX_HIT, int(m["d"])))
                drops = self.game.mobs.hit(mob, damage, peer.pos)
                if drops:
                    peer.link.send({"t": "give", "i": drops})
        elif kind == "trade":
            mob = self._mob(m["id"])
            if mob is not None and mob.home is not None:
                mob.trading = bool(m["on"])
                peer.trading = mob if mob.trading else None
        elif kind == "state" and isinstance(m["d"], dict):
            self.game.guests[peer.name] = m["d"]
        elif kind == "gate" and m["r"] in ("surface", "hell", "edge"):
            self.game.travel(m["r"])
        elif kind == "drop":
            item, count, durability = m["s"]
            if (item < len(BLOCKS) or item in NAMES) and 1 <= count <= item_limit(item):
                pos = [_number(v) for v in m["p"][:3]]
                vel = [_number(v) for v in m["v"][:3]]
                self.game.world.dropped.append(Drop(self.game.world, item, count, durability, pos, vel))
        elif kind == "chest_open":
            cell = tuple(int(v) for v in m["c"])
            if self.claim_chest(cell, peer.id):
                peer.link.send({"t": "chest", "c": list(cell), "s": self.game.chest_data(cell)})
            else:
                peer.link.send({"t": "chest", "c": list(cell), "busy": True})
        elif kind == "chest_set":
            cell = tuple(int(v) for v in m["c"])
            if self.chest_users.get(cell) == peer.id and isinstance(m["s"], list) and len(m["s"]) <= CHEST_SIZE:
                self.game.world.chests[cell] = m["s"]
        elif kind == "chest_close":
            cell = tuple(int(v) for v in m["c"])
            if self.chest_users.get(cell) == peer.id:
                del self.chest_users[cell]
        elif kind == "sleep":
            peer.sleeping = bool(m["on"])

    def _mob(self, mob_id):
        return next((m for m in self.game.mobs.mobs if m.id == mob_id), None)

    # --- Каждый кадр ----------------------------------------------------------

    def update(self, dt):
        self._admit()
        for peer in self.peers():
            for message in peer.link.drain():
                if message is None:
                    self._leave(peer)
                    break
                try:
                    self._handle(peer, message)
                except (KeyError, TypeError, ValueError, IndexError):
                    pass  # испорченное сообщение не должно ронять сервер
            peer.advance(dt)
        self.timer -= dt
        if self.timer <= 0.0 and self.peers_by_id:
            self.timer = SEND_PERIOD
            self._broadcast(self._snapshot(), droppable=True)

    def _snapshot(self):
        game = self.game
        p = game.player
        armor, held = game.gear()
        players = [[0, self.name, *(round(v, 3) for v in p.pos), round(p.yaw, 3), round(game.swing, 2), armor, held]]
        for peer in self.peers():
            players.append([peer.id, peer.name, *(round(v, 3) for v in peer.pos),
                            round(peer.goal_yaw, 3), round(peer.swing, 2), peer.armor, peer.held])
        mobs = [[m.id, KINDS.index(m.kind), round(m.pos[0], 3), round(m.pos[1], 3), round(m.pos[2], 3),
                 round(m.yaw, 3), round(m.hp, 1), round(m.swing, 2), round(m.flash, 2), round(m.bar, 1),
                 int(m.exposed), int(m.flee > 0.0)] for m in game.mobs.mobs]
        shots = [[round(s.pos[0], 2), round(s.pos[1], 2), round(s.pos[2], 2), round(s.vel[0], 1), round(s.vel[2], 1), int(s.frost)]
                 for s in game.mobs.shots]
        items = [[d.id, d.item, d.count, round(d.pos[0], 2), round(d.pos[1], 2), round(d.pos[2], 2), round(d.age, 1)]
                 for d in game.world.dropped]
        return {"t": "s", "day": round(game.day_time, 5), "p": players, "m": mobs, "h": shots, "d": items}

    def block_changed(self, x, y, z, block):
        self._broadcast({"t": "b", "b": [x, y, z, block]})

    def claim_chest(self, cell, user):
        """Сундук открыт только у одного игрока, иначе вещи могли бы раздвоиться."""
        if self.chest_users.get(cell, user) != user:
            return False
        self.chest_users[cell] = user
        return True

    def release_chest(self, cell):
        self.chest_users.pop(cell, None)

    def pick_up(self, peer, stack):
        peer.link.send({"t": "pick", "s": list(stack)})

    def all_asleep(self):
        return all(p.sleeping or not p.alive for p in self.peers())

    def wake_all(self):
        for peer in self.peers():
            peer.sleeping = False
        self._broadcast({"t": "wake"})

    def realm_changed(self, name, landing):
        """Измерение общее на всех: игроки перемещаются вместе."""
        self._broadcast({"t": "realm", "r": name, "edits": self.game.world.edits_json(), "p": list(landing)})
        for peer in self.peers():
            peer.pos = list(landing)
            peer.shown = list(landing)
            peer.trading = None

    def send_events(self, events):
        if events and self.peers_by_id:
            self._broadcast({"t": "ev", "e": [[n, list(p)] for n, p in events]}, droppable=True)

    def on_save(self, data):
        pass

    def close(self):
        self._broadcast({"t": "bye"})
        for peer in self.peers():
            peer.link.close()
        self.peers_by_id.clear()
        self.listener.close()
        for link in self.waiting:
            link.close()


class ClientSession:
    """Показывает мир хоста и отправляет ему действия своего игрока."""

    is_host = False

    def __init__(self, game, link, my_id, name):
        self.game = game
        self.link = link
        self.my_id = my_id
        self.name = name
        self.others = {}
        self.known = {}
        self.known_drops = {}
        self.timer = 0.0

    def peers(self):
        return list(self.others.values())

    def status(self):
        names = ", ".join(sorted(p.name for p in self.others.values())) or "никого"
        return f"В сети: {names}"

    def update(self, dt):
        for message in self.link.drain():
            if message is None:
                self._lost("Соединение с сервером потеряно")
                return
            self._handle(message)

        for mob in self.game.mobs.mobs:
            mob.phase += _glide(mob.pos, mob.goal, dt) * 5.0
            mob.yaw = _turned(mob.yaw, mob.goal_yaw, dt)
        for peer in self.others.values():
            peer.advance(dt)
        for drop in self.game.world.dropped:
            _glide(drop.pos, drop.goal, dt)

        self.timer -= dt
        if self.timer <= 0.0:
            self.timer = SEND_PERIOD
            game = self.game
            p = game.player
            armor, held = game.gear()
            self.link.send({"t": "pos", "p": [round(v, 3) for v in p.pos], "y": round(p.yaw, 3), "w": round(game.swing, 2),
                            "a": game.screen != "dead", "r": armor, "i": held}, droppable=True)

    def _lost(self, text):
        # Важна первая причина: после «сервер закрыт» соединение всё равно оборвётся.
        if self.game.running:
            self.game.exit_message = text
            self.game.running = False

    def _handle(self, m):
        game = self.game
        kind = m["t"]
        if kind == "s":
            self._snapshot(m)
        elif kind == "b":
            game.apply_remote_block(*m["b"])
        elif kind == "ev":
            game.mobs.events.extend((name, tuple(pos)) for name, pos in m["e"])
        elif kind == "hurt":
            game.hurt_player(m["a"], m["s"])
        elif kind == "give":
            for item, count in m["i"]:
                if game.inventory.add(item, count):
                    game.toast("Инвентарь полон")
        elif kind == "toast":
            game.toast(m["x"])
        elif kind == "chest":
            game.chest_reply(tuple(m["c"]), m.get("s"), m.get("busy", False))
        elif kind == "pick":
            game.pick_up_stack(Stack(*m["s"]))
        elif kind == "wake":
            game.get_up(notify=False)
        elif kind == "realm":
            self.known = {}
            self.known_drops = {}
            game.arrive(m["r"], m["edits"], m["p"])
        elif kind == "bye":
            self._lost("Сервер закрыт")

    def _snapshot(self, m):
        game = self.game
        game.day_time = m["day"]

        seen = set()
        for peer_id, name, x, y, z, yaw, swing, armor, held in m["p"]:
            if peer_id == self.my_id:
                continue
            seen.add(peer_id)
            if peer_id not in self.others:
                self.others[peer_id] = Peer(peer_id, name, (x, y, z))
            self.others[peer_id].apply((x, y, z), yaw, swing)
            self.others[peer_id].armor = armor
            self.others[peer_id].held = held
        for peer_id in set(self.others) - seen:
            del self.others[peer_id]

        fresh = {}
        for row in m["m"]:
            mob_id, kind, x, y, z, yaw, hp, swing, flash, bar, exposed, flee = row
            mob = self.known.get(mob_id)
            if mob is None:
                mob = Mob(game.world, KINDS[kind], x, y, z)
                mob.id = mob_id
                mob.yaw = yaw
                mob.home = True if KINDS[kind] in VILLAGERS else None
            mob.goal = [x, y, z]
            mob.goal_yaw = yaw
            mob.hp, mob.swing, mob.flash, mob.bar = hp, swing, flash, bar
            mob.exposed = bool(exposed)
            mob.flee = 1.0 if flee else 0.0
            fresh[mob_id] = mob
        self.known = fresh
        game.mobs.mobs = list(fresh.values())
        fresh_drops = {}
        for drop_id, item, count, x, y, z, age in m["d"]:
            drop = self.known_drops.get(drop_id)
            if drop is None:
                drop = Drop(game.world, item, count, None, (x, y, z))
            drop.goal = [x, y, z]
            drop.age = age
            fresh_drops[drop_id] = drop
        self.known_drops = fresh_drops
        game.world.dropped = list(fresh_drops.values())
        game.mobs.shots = [ThornShot((x, y, z), (vx, 0.0, vz), frost=bool(frost)) for x, y, z, vx, vz, frost in m["h"]]

    def hit(self, mob, damage):
        self.link.send({"t": "hit", "id": mob.id, "d": damage})

    def trade(self, mob, on):
        self.link.send({"t": "trade", "id": mob.id, "on": on})

    def travel(self, name):
        self.link.send({"t": "gate", "r": name})

    def drop(self, stack, pos, vel):
        self.link.send({"t": "drop", "s": list(stack.key()), "p": list(pos), "v": list(vel)})

    def chest_open(self, cell):
        self.link.send({"t": "chest_open", "c": list(cell)})

    def chest_set(self, cell, slots):
        self.link.send({"t": "chest_set", "c": list(cell), "s": slots})

    def chest_close(self, cell):
        self.link.send({"t": "chest_close", "c": list(cell)})

    def sleep(self, on):
        self.link.send({"t": "sleep", "on": on})

    def block_changed(self, x, y, z, block):
        self.link.send({"t": "b", "b": [x, y, z, block]})

    def send_events(self, events):
        pass

    def on_save(self, data):
        keys = ("pos", "yaw", "pitch", "inventory", "vitals", "realm", "armor")
        self.link.send({"t": "state", "d": {k: data[k] for k in keys if k in data}})

    def close(self):
        self.link.close()
