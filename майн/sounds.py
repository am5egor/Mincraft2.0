"""Звук: все эффекты синтезируются при запуске, файлов не требуется."""
import math
import random

import numpy as np
import pygame

from world import (AMBER, ASH, BASE, BED_STATE, BRICK, CHEST, COPPER_ORE, CROWN, DOOR_STATE, EDGE_GATE, EMBER_ORE, FORGE,
                   FROST_CROWN, GLASS, GLOW, HELL_GATE, IRON_ORE, PALE, PLANKS, ROCK,
                   RUBY_ORE, SAND, SILVER_ORE, SNOW, STAR_ORE, TRUNK, WORKBENCH)

MAX_DISTANCE = 32.0
CHANNELS = 32
WIND_LENGTH = 8.0
WIND_CHANNEL = 0

MATERIALS = {
    ROCK: "stone", BRICK: "stone", AMBER: "stone", FORGE: "stone", BASE: "stone",
    COPPER_ORE: "stone", IRON_ORE: "stone", SILVER_ORE: "stone", RUBY_ORE: "stone", ASH: "stone", EMBER_ORE: "stone",
    PALE: "stone", STAR_ORE: "stone",
    HELL_GATE: "glass", EDGE_GATE: "glass",
    TRUNK: "wood", PLANKS: "wood", WORKBENCH: "wood",
    CROWN: "leaf", FROST_CROWN: "leaf",
    SAND: "sand", SNOW: "snow",
    GLASS: "glass", GLOW: "glass",
}


MATERIALS.update({block: ("wood", "stone")[state[0]] for block, state in DOOR_STATE.items()})
MATERIALS.update({block: "leaf" for block in BED_STATE})
MATERIALS[CHEST] = "wood"


def material_of(block):
    return MATERIALS.get(block, "earth")


# Материал: полоса шума (Гц), затухание (с), частота тона (Гц), доля тона.
MATERIAL_SOUND = {
    "earth": (120, 1400, 0.050, 110, 0.35),
    "stone": (500, 5000, 0.025, 420, 0.25),
    "wood": (200, 2200, 0.035, 300, 0.60),
    "leaf": (1800, 9000, 0.060, 0, 0.0),
    "sand": (1500, 8000, 0.090, 0, 0.0),
    "snow": (900, 5000, 0.080, 0, 0.0),
    "glass": (2500, 11000, 0.030, 2400, 0.70),
}


class Synth:
    """Строительные блоки звуков для заданной частоты дискретизации."""

    def __init__(self, rate, seed=4177):
        self.rate = rate
        self.rng = np.random.default_rng(seed)

    def times(self, seconds):
        return np.arange(int(seconds * self.rate)) / self.rate

    def noise(self, seconds, low, high):
        """Шум в полосе частот. Он периодичен по длине, поэтому годится для петель."""
        n = max(16, int(seconds * self.rate))
        spectrum = np.fft.rfft(self.rng.standard_normal(n))
        freq = np.fft.rfftfreq(n, 1.0 / self.rate)
        spectrum[(freq < low) | (freq > high)] = 0.0
        out = np.fft.irfft(spectrum, n)
        return out / (np.abs(out).max() + 1e-9)

    def sweep(self, seconds, start, end=None, saw=False, wobble=0.0, wobble_hz=0.0):
        """Тон с плавной сменой частоты; wobble — глубина дрожания в долях частоты."""
        t = self.times(seconds)
        end = start if end is None else end
        freq = start * (end / start) ** (t / max(seconds, 1e-6))
        if wobble:
            freq = freq * (1.0 + wobble * np.sin(math.tau * wobble_hz * t))
        phase = np.cumsum(freq) / self.rate
        if saw:
            return 2.0 * (phase % 1.0) - 1.0
        return np.sin(math.tau * phase)

    def decay(self, seconds, tau):
        return np.exp(-self.times(seconds) / tau)

    def swell(self, seconds, attack=0.03):
        """Огибающая: быстрый подъём, затем спад к нулю."""
        t = self.times(seconds)
        rise = np.clip(t / attack, 0.0, 1.0)
        return rise * np.clip(1.0 - t / seconds, 0.0, 1.0) ** 1.4

    def place(self, seconds, *events):
        """Сводит звуки: (момент начала в секундах, массив)."""
        out = np.zeros(int(seconds * self.rate))
        for start, wave in events:
            i = int(start * self.rate)
            part = wave[:max(0, len(out) - i)]
            out[i:i + len(part)] += part
        return out

    def bell(self, seconds, freq, tau=0.14):
        return self.sweep(seconds, freq) * self.decay(seconds, tau)

    def finish(self, wave, gain):
        """Нормировка и короткие фейды, чтобы не было щелчков на краях."""
        wave = wave / (np.abs(wave).max() + 1e-9) * gain
        fade_in = min(len(wave) // 4, int(0.002 * self.rate))
        fade_out = min(len(wave) // 4, int(0.006 * self.rate))
        wave[:fade_in] *= np.linspace(0.0, 1.0, fade_in)
        wave[-fade_out:] *= np.linspace(1.0, 0.0, fade_out)
        return wave

    # --- Материалы -----------------------------------------------------------

    def impact(self, material, seconds, tau_scale, thump):
        low, high, tau, tone_hz, tone_mix = MATERIAL_SOUND[material]
        tau *= tau_scale
        wave = self.noise(seconds, low, high) * self.decay(seconds, tau) * (1.0 - tone_mix)
        if tone_hz:
            hz = tone_hz * self.rng.uniform(0.88, 1.12)
            wave = wave + self.sweep(seconds, hz, hz * 0.8) * self.decay(seconds, tau * 1.3) * tone_mix
        if thump:
            wave = wave + self.sweep(seconds, 130, 60) * self.decay(seconds, 0.07) * thump
        return wave

    # --- Один вариант каждого звука ------------------------------------------

    def eat(self):
        bites = [(i * 0.1, self.noise(0.07, 700, 6000) * self.decay(0.07, 0.02)) for i in range(3)]
        return self.place(0.34, *bites)

    def craft(self):
        return self.place(0.5, (0.0, self.impact("wood", 0.1, 1.0, 0.0)),
                          (0.06, self.bell(0.4, 660)), (0.15, self.bell(0.33, 990)))

    def deny(self):
        return self.sweep(0.14, 170, 130, saw=True) * self.decay(0.14, 0.06)

    def ui(self, start, end):
        return self.sweep(0.09, start, end) * self.decay(0.09, 0.035)

    def click(self, hz=1500):
        return self.sweep(0.03, hz) * self.decay(0.03, 0.007)

    def snap(self):
        return self.noise(0.2, 1200, 9000) * self.decay(0.2, 0.025) + self.sweep(0.2, 700, 180) * self.decay(0.2, 0.06)

    def splash(self, seconds=0.5):
        return self.noise(seconds, 300, 5000) * self.swell(seconds, 0.02)

    def land(self):
        return self.sweep(0.22, 110, 45) * self.decay(0.22, 0.07) + self.noise(0.22, 120, 900) * self.decay(0.22, 0.03) * 0.6

    def hurt(self):
        voice = self.sweep(0.22, self.rng.uniform(250, 300), 140, saw=True, wobble=0.04, wobble_hz=32)
        return (voice * 0.8 + self.noise(0.22, 400, 2400) * 0.4) * self.swell(0.22, 0.01)

    def melody(self, notes, gap, tail=0.5):
        seconds = gap * len(notes) + tail
        return self.place(seconds, *[(i * gap, self.bell(tail, hz, 0.2)) for i, hz in enumerate(notes)])

    def swing(self):
        return self.noise(0.2, 800, 3500) * self.swell(0.2, 0.08)

    def hit(self):
        return self.sweep(0.13, 170, 70) * self.decay(0.13, 0.05) + self.noise(0.13, 900, 5000) * self.decay(0.13, 0.012) * 0.8

    def voice(self, seconds, start, end, saw=True, wobble=0.0, wobble_hz=0.0, breath=0.0):
        wave = self.sweep(seconds, start, end, saw=saw, wobble=wobble, wobble_hz=wobble_hz)
        if breath:
            wave = wave + self.noise(seconds, 300, 3000) * breath
        return wave * self.swell(seconds, 0.03)

    def rattle(self, seconds, rate_hz, low=1500, high=7000):
        count = int(seconds * rate_hz)
        clicks = [(i / rate_hz, self.noise(0.018, low, high) * self.decay(0.018, 0.005) * (1.0 - i / (count + 2)))
                  for i in range(count)]
        return self.place(seconds, *clicks)

    def bird(self):
        chirps = int(self.rng.integers(2, 5))
        base = self.rng.uniform(2300, 3400)
        events = []
        for i in range(chirps):
            top = base * self.rng.uniform(1.2, 1.6)
            events.append((i * 0.14, self.sweep(0.09, base, top) * self.swell(0.09, 0.015)))
        return self.place(0.14 * chirps + 0.12, *events)

    def cricket(self):
        t = self.times(0.6)
        pulses = (np.sin(math.tau * 31.0 * t) > 0.0).astype(float)
        return self.sweep(0.6, 4400) * pulses * self.swell(0.6, 0.05)

    def drip(self):
        hit = self.sweep(0.08, 800, 1500) * self.decay(0.08, 0.018)
        return self.place(0.6, (0.0, hit), (0.17, hit * 0.3), (0.34, hit * 0.1))

    def bubbles(self):
        events = []
        for i in range(6):
            low = self.rng.uniform(280, 520)
            events.append((i * 0.06 + self.rng.uniform(0, 0.03),
                           self.sweep(0.07, low, low * 1.9) * self.decay(0.07, 0.025)))
        return self.place(0.5, *events)

    def wind(self):
        """Бесшовная петля ветра."""
        t = self.times(WIND_LENGTH)
        wave = self.noise(WIND_LENGTH, 80, 700)
        slow = 0.65 + 0.2 * np.sin(math.tau * t / WIND_LENGTH) + 0.15 * np.sin(math.tau * 3.0 * t / WIND_LENGTH + 1.0)
        return wave * slow

    # --- Каталог -------------------------------------------------------------

    def catalog(self):
        """Имя звука: (генератор варианта, число вариантов, громкость)."""
        table = {
            "eat": (self.eat, 3, 0.55),
            "craft": (self.craft, 2, 0.5),
            "deny": (self.deny, 1, 0.35),
            "pickup": (lambda: self.sweep(0.1, 620, 1250) * self.decay(0.1, 0.04), 2, 0.3),
            "throw": (lambda: self.noise(0.12, 900, 4000) * self.swell(0.12, 0.03), 2, 0.25),
            "dragon_idle": (lambda: self.voice(1.2, 92, 60, wobble=0.14, wobble_hz=31, breath=0.7), 3, 0.75),
            "dragon_hurt": (lambda: self.voice(0.32, 170, 95, wobble=0.16, wobble_hz=44, breath=0.7), 3, 0.65),
            "dragon_die": (lambda: self.voice(1.4, 130, 34, wobble=0.18, wobble_hz=23, breath=0.8), 1, 0.85),
            "frost_shot": (lambda: self.noise(0.3, 1800, 9000) * self.swell(0.3, 0.02)
                           + self.sweep(0.3, 1500, 420) * self.decay(0.3, 0.12) * 0.6, 3, 0.45),
            "door": (lambda: self.impact("wood", 0.22, 1.5, 0.3) + self.sweep(0.22, 210, 130, saw=True)
                     * self.swell(0.22, 0.02) * 0.25, 3, 0.5),
            "portal": (lambda: self.sweep(1.1, 150, 1300, wobble=0.04, wobble_hz=9) * self.swell(1.1, 0.25)
                       + self.noise(1.1, 400, 5000) * self.swell(1.1, 0.5) * 0.35, 1, 0.55),
            "trade": (lambda: self.place(0.34, (0.0, self.bell(0.24, 1320, 0.06)),
                                         (0.08, self.bell(0.24, 1760, 0.06))), 2, 0.4),
            "ui_open": (lambda: self.ui(420, 760), 1, 0.28),
            "ui_close": (lambda: self.ui(760, 420), 1, 0.28),
            "click": (self.click, 2, 0.3),
            "tick": (lambda: self.click(2300), 1, 0.2),
            "snap": (self.snap, 2, 0.7),
            "splash": (self.splash, 3, 0.55),
            "swim": (lambda: self.splash(0.25), 3, 0.22),
            "land": (self.land, 2, 0.6),
            "hurt": (self.hurt, 3, 0.7),
            "death": (lambda: self.melody((392, 311, 233, 175), 0.2, 0.7), 1, 0.65),
            "respawn": (lambda: self.melody((392, 523, 659), 0.11, 0.55), 1, 0.5),
            "swing": (self.swing, 3, 0.3),
            "hit": (self.hit, 3, 0.65),
            "grazer_idle": (lambda: self.voice(0.42, 330, 290, wobble=0.05, wobble_hz=17), 3, 0.42),
            "grazer_hurt": (lambda: self.voice(0.2, 540, 390, wobble=0.07, wobble_hz=24), 2, 0.5),
            "grazer_die": (lambda: self.voice(0.5, 410, 140, wobble=0.06, wobble_hz=16), 1, 0.55),
            "shade_idle": (lambda: self.voice(0.7, 86, 70, wobble=0.1, wobble_hz=23, breath=0.45), 3, 0.5),
            "shade_attack": (lambda: self.voice(0.26, 90, 190, wobble=0.1, wobble_hz=38, breath=0.6), 2, 0.6),
            "shade_hurt": (lambda: self.voice(0.2, 150, 90, wobble=0.14, wobble_hz=41, breath=0.7), 2, 0.55),
            "shade_die": (lambda: self.voice(0.75, 125, 42, wobble=0.12, wobble_hz=19, breath=0.5), 1, 0.65),
            "bristler_idle": (lambda: self.rattle(0.42, 24), 3, 0.5),
            "bristler_hurt": (lambda: self.rattle(0.2, 44, 2500, 9000), 2, 0.45),
            "bristler_die": (lambda: self.rattle(0.6, 18, 800, 5000), 1, 0.55),
            "puffer_idle": (lambda: self.voice(0.13, 1100, 1550, saw=False), 3, 0.3),
            "puffer_hurt": (lambda: self.voice(0.14, 1700, 950, saw=False), 2, 0.4),
            "puffer_die": (lambda: self.voice(0.32, 1300, 380, saw=False, wobble=0.05, wobble_hz=22), 1, 0.45),
            "villager_idle": (lambda: self.place(0.42, (0.0, self.voice(0.17, 205, 170, wobble=0.03, wobble_hz=7)),
                                                 (0.2, self.voice(0.2, 165, 215, wobble=0.03, wobble_hz=7))), 4, 0.32),
            "villager_hurt": (lambda: self.voice(0.2, 310, 190, wobble=0.05, wobble_hz=28), 2, 0.5),
            "villager_die": (lambda: self.voice(0.55, 240, 95, wobble=0.04, wobble_hz=14), 1, 0.55),
            "thorn_shot": (lambda: self.noise(0.14, 1000, 7000) * self.decay(0.14, 0.03)
                           + self.sweep(0.14, 900, 280) * self.decay(0.14, 0.05), 2, 0.45),
            "thorn_hit": (lambda: self.click(3100), 2, 0.3),
            "bird": (self.bird, 5, 0.2),
            "cricket": (self.cricket, 2, 0.13),
            "drip": (self.drip, 3, 0.3),
            "bubbles": (self.bubbles, 3, 0.25),
        }
        for material in MATERIAL_SOUND:
            def maker(mat, seconds, tau_scale, thump):
                return lambda: self.impact(mat, seconds, tau_scale, thump)
            table[f"dig_{material}"] = (maker(material, 0.13, 1.0, 0.0), 4, 0.4)
            table[f"break_{material}"] = (maker(material, 0.3, 2.5, 0.5), 3, 0.7)
            table[f"step_{material}"] = (maker(material, 0.1, 0.7, 0.15), 4, 0.24)
        return table


class Audio:
    def __init__(self):
        self.enabled = pygame.mixer.get_init() is not None
        self.muted = False
        self.paused = False
        self.bank = {}
        self.ear = (0.0, 0.0, 0.0)
        self.right = (1.0, 0.0, 0.0)
        self.wind_level = 0.0
        if not self.enabled:
            return
        pygame.mixer.set_num_channels(CHANNELS)
        pygame.mixer.set_reserved(1)
        self.rate, _, self.mixer_channels = pygame.mixer.get_init()
        synth = Synth(self.rate)
        for name, (make, variants, gain) in synth.catalog().items():
            self.bank[name] = [self._sound(synth.finish(make(), gain)) for _ in range(variants)]
        wind = synth.wind()
        self.wind_channel = pygame.mixer.Channel(WIND_CHANNEL)
        self.wind_channel.play(self._sound(wind / (np.abs(wind).max() + 1e-9)), loops=-1)
        self.wind_channel.set_volume(0.0)

    def _sound(self, wave):
        samples = np.round(wave * 32000.0).astype(np.int16)
        if self.mixer_channels == 2:
            samples = np.column_stack((samples, samples))
        return pygame.mixer.Sound(buffer=samples.tobytes())

    def listen(self, ear, yaw):
        self.ear = ear
        self.right = (math.cos(yaw), 0.0, math.sin(yaw))

    def gains(self, pos, volume):
        """Громкость левого и правого канала для источника в точке pos."""
        if pos is None:
            return volume, volume
        dx, dy, dz = (pos[i] - self.ear[i] for i in range(3))
        distance = math.sqrt(dx * dx + dy * dy + dz * dz)
        if distance >= MAX_DISTANCE:
            return 0.0, 0.0
        level = volume * (1.0 - distance / MAX_DISTANCE) ** 1.5
        pan = (dx * self.right[0] + dz * self.right[2]) / max(distance, 1.0)
        return level * (1.0 - max(0.0, pan) * 0.7), level * (1.0 - max(0.0, -pan) * 0.7)

    def play(self, name, pos=None, volume=1.0):
        """Проигрывает случайный вариант. pos=None — звук не зависит от положения."""
        if not self.enabled or self.muted:
            return
        left, right = self.gains(pos, volume)
        if left <= 0.0 and right <= 0.0:
            return
        channel = random.choice(self.bank[name]).play()
        if channel is not None:
            channel.set_volume(left, right)

    def set_wind(self, target, dt):
        if not self.enabled:
            return
        self.wind_level += (target - self.wind_level) * min(1.0, dt * 1.5)
        level = 0.0 if self.muted else self.wind_level
        self.wind_channel.set_volume(level)

    def quiet(self):
        """Тишина при выходе в меню."""
        if not self.enabled:
            return
        pygame.mixer.unpause()
        self.paused = False
        for i in range(CHANNELS):
            if i != WIND_CHANNEL:
                pygame.mixer.Channel(i).stop()
        self.wind_level = 0.0
        self.wind_channel.set_volume(0.0)

    def toggle_mute(self):
        self.muted = not self.muted
        if self.enabled and self.muted:
            for i in range(CHANNELS):
                if i != WIND_CHANNEL:
                    pygame.mixer.Channel(i).stop()
            self.wind_channel.set_volume(0.0)
        return self.muted

    def set_paused(self, paused):
        if self.enabled and paused != self.paused:
            self.paused = paused
            if paused:
                pygame.mixer.pause()
            else:
                pygame.mixer.unpause()
