"""Отрисовка: шейдеры, небо, геометрия чанков, рамка выбора и интерфейс."""
import math

import moderngl
import numpy as np
import pygame

from mesher import SIGNS, TABLES
from world import CHUNK, HEIGHT

WORLD_VS = """
#version 330
in uvec4 in_a;
in uvec4 in_b;
uniform mat4 vp;
uniform vec3 chunk;
uniform float time;
out vec3 v_uv;
out float v_shade;
out vec2 v_light;
out vec3 v_pos;
const float FACE[6] = float[6](0.80, 0.80, 1.0, 0.52, 0.66, 0.66);
const float PANEL = 0.1875;
const float BED_TOP = 0.5625;
void main() {
    uint flags = in_a.w;
    vec3 p = vec3(in_a.xyz) + chunk;
    uint inset = in_b.y >> 2u;
    if (inset == 1u) p.x += PANEL;
    else if (inset == 2u) p.x -= PANEL;
    else if (inset == 3u) p.z += PANEL;
    else if (inset == 4u) p.z -= PANEL;
    else if (inset == 5u) p.y += BED_TOP;
    if ((flags & 32u) != 0u)
        p.y -= 0.13 + 0.035 * sin(time * 1.6 + p.x * 0.7 + p.z * 0.9);
    v_uv = vec3(float(flags & 1u), float((flags >> 1) & 1u), float(in_b.x));
    v_shade = FACE[(flags >> 2) & 7u] * mix(0.42, 1.0, float(in_b.y & 3u) / 3.0);
    v_light = vec2(in_b.z, in_b.w) / 240.0;
    v_pos = p;
    gl_Position = vp * vec4(p, 1.0);
}
"""

WORLD_FS = """
#version 330
in vec3 v_uv;
in float v_shade;
in vec2 v_light;
in vec3 v_pos;
out vec4 color;
uniform sampler2DArray tex;
uniform vec3 eye;
uniform vec3 fog_color;
uniform vec3 sun_color;
uniform vec2 fog_range;
uniform vec3 ambient;
void main() {
    vec4 c = texture(tex, v_uv);
    if (c.a < 0.05) discard;
    vec3 sky = sun_color * pow(v_light.x, 1.7);
    vec3 lamp = vec3(1.0, 0.86, 0.68) * pow(v_light.y, 1.5);
    vec3 light = max(max(sky, lamp), ambient);
    vec3 rgb = c.rgb * light * v_shade;
    float d = length(v_pos - eye);
    float fog = smoothstep(fog_range.x, fog_range.y, d);
    color = vec4(mix(rgb, fog_color, fog), c.a);
}
"""

SKY_VS = """
#version 330
out vec2 v_ndc;
void main() {
    vec2 p = vec2(float((gl_VertexID & 1) * 4 - 1), float((gl_VertexID & 2) * 2 - 1));
    v_ndc = p;
    gl_Position = vec4(p, 0.9999, 1.0);
}
"""

SKY_FS = """
#version 330
in vec2 v_ndc;
out vec4 color;
uniform mat4 inv_vp;
uniform vec3 eye;
uniform vec3 sun_dir;
uniform vec3 horizon;
uniform vec3 zenith;
uniform float night;
uniform float time;
uniform float celestial;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y);
}
float fbm(vec2 p) {
    float v = 0.0, a = 0.5;
    for (int i = 0; i < 5; i++) { v += a * noise(p); p = p * 2.05 + 11.3; a *= 0.5; }
    return v;
}
void main() {
    vec4 far_p = inv_vp * vec4(v_ndc, 1.0, 1.0);
    vec3 rd = normalize(far_p.xyz / far_p.w - eye);
    vec3 c = mix(horizon, zenith, pow(clamp(rd.y, 0.0, 1.0), 0.55));
    if (rd.y > 0.0) {
        vec2 cell = floor(rd.xz / (rd.y + 0.35) * 170.0);
        float star = step(0.9975, hash(cell)) * (0.5 + 0.5 * sin(time * 2.0 + hash(cell + 3.0) * 40.0));
        c += star * night * smoothstep(0.02, 0.25, rd.y);
    }
    float s = dot(rd, sun_dir);
    c += celestial * vec3(1.0, 0.86, 0.66) * (smoothstep(0.9988, 0.9994, s) * 2.0 + pow(max(s, 0.0), 180.0) * 0.5);
    float m = dot(rd, -sun_dir);
    c += celestial * vec3(0.82, 0.86, 1.0) * smoothstep(0.9990, 0.9994, m) * night;
    if (rd.y > 0.015 && celestial > 0.5) {
        vec2 q = rd.xz / (rd.y + 0.14) * 1.5 + vec2(time * 0.012, time * 0.004);
        float cover = smoothstep(0.50, 0.76, fbm(q)) * smoothstep(0.015, 0.22, rd.y);
        vec3 cloud = mix(horizon * 0.9 + 0.1, vec3(1.0), 1.0 - night) * mix(1.0, 0.16, night);
        c = mix(c, cloud, cover * 0.86);
    }
    color = vec4(c, 1.0);
}
"""

BOX_VS = """
#version 330
in vec3 in_pos;
in vec2 in_uv;
uniform mat4 vp;
uniform vec3 cell;
uniform vec3 low;
uniform vec3 span;
out vec2 v_uv;
void main() {
    v_uv = in_uv;
    gl_Position = vp * vec4(cell + low + (in_pos - 0.5) * span * 1.006 + span * 0.5, 1.0);
}
"""

BOX_FS = """
#version 330
in vec2 v_uv;
out vec4 color;
uniform float progress;
void main() {
    vec2 e = min(v_uv, 1.0 - v_uv);
    float edge = 1.0 - smoothstep(0.012, 0.045, min(e.x, e.y));
    float reach = max(abs(v_uv.x - 0.5), abs(v_uv.y - 0.5)) * 2.0;
    float crack = step(reach, progress) * step(0.001, progress) * (1.0 - edge);
    float stripes = 0.42 + 0.16 * sin((v_uv.x + v_uv.y * 1.7) * 46.0);
    vec3 rgb = mix(vec3(1.0), vec3(0.08, 0.07, 0.15), crack);
    color = vec4(rgb, max(0.06 + edge * 0.8, crack * stripes));
}
"""

PART_VS = """
#version 330
in vec3 in_pos;
in float in_shade;
in vec3 i_base;
in vec3 i_off;
in vec3 i_size;
in float i_yaw;
in float i_swing;
in vec3 i_color;
in float i_light;
in float i_flash;
uniform mat4 vp;
out vec3 v_color;
out float v_light;
out float v_flash;
out vec3 v_pos;
void main() {
    vec3 p = in_pos * i_size;
    p.y -= i_size.y * 0.5;
    float cs = cos(i_swing), sn = sin(i_swing);
    p = vec3(p.x, p.y * cs - p.z * sn, p.y * sn + p.z * cs);
    p.y += i_size.y * 0.5;
    p += i_off;
    float cy = cos(i_yaw), sy = sin(i_yaw);
    vec3 w = vec3(p.x * cy - p.z * sy, p.y, p.x * sy + p.z * cy) + i_base;
    v_color = i_color * in_shade * mix(0.86, 1.08, in_pos.y + 0.5);
    v_light = i_light;
    v_flash = i_flash;
    v_pos = w;
    gl_Position = vp * vec4(w, 1.0);
}
"""

PART_FS = """
#version 330
in vec3 v_color;
in float v_light;
in float v_flash;
in vec3 v_pos;
out vec4 color;
uniform vec3 eye;
uniform vec3 fog_color;
uniform vec3 sun_color;
uniform vec2 fog_range;
uniform vec3 ambient;
void main() {
    vec3 rgb = v_light < 0.0 ? v_color : v_color * max(sun_color * v_light, ambient);
    rgb = mix(rgb, vec3(0.95, 0.15, 0.18), v_flash * 0.75);
    float fog = smoothstep(fog_range.x, fog_range.y, length(v_pos - eye));
    color = vec4(mix(rgb, fog_color, fog), 1.0);
}
"""

MAX_PARTS = 4096
PART_FLOATS = 16

HUD_VS = """
#version 330
out vec2 v_uv;
void main() {
    vec2 p = vec2(float((gl_VertexID & 1) * 4 - 1), float((gl_VertexID & 2) * 2 - 1));
    v_uv = p * 0.5 + 0.5;
    gl_Position = vec4(p, 0.0, 1.0);
}
"""

HUD_FS = """
#version 330
in vec2 v_uv;
out vec4 color;
uniform sampler2D tex;
uniform float hurt;
void main() {
    vec4 t = texture(tex, v_uv);
    float veil = hurt * (0.16 + 0.75 * dot(v_uv - 0.5, v_uv - 0.5));
    float a = t.a + veil * (1.0 - t.a);
    vec3 rgb = (t.rgb * t.a + vec3(0.85, 0.08, 0.14) * veil * (1.0 - t.a)) / max(a, 0.001);
    color = vec4(rgb, a);
}
"""


def perspective(fovy, aspect, near, far):
    f = 1.0 / math.tan(fovy / 2.0)
    m = np.zeros((4, 4))
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = 2.0 * far * near / (near - far)
    m[3, 2] = -1.0
    return m


def view_matrix(eye, forward):
    eye = np.array(eye)
    f = np.array(forward)
    r = np.cross(f, (0.0, 1.0, 0.0))
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    m = np.eye(4)
    m[0, :3] = r
    m[1, :3] = u
    m[2, :3] = -f
    m[:3, 3] = (-r.dot(eye), -u.dot(eye), f.dot(eye))
    return m


def _gl(m):
    return m.T.astype("f4").tobytes()


def _mix(a, b, t):
    return tuple(x * (1.0 - t) + y * t for x, y in zip(a, b))


def _clamp01(x):
    return max(0.0, min(1.0, x))


def _smooth(a, b, x):
    t = _clamp01((x - a) / (b - a))
    return t * t * (3.0 - 2.0 * t)


class Renderer:
    def __init__(self, ctx, tiles):
        self.ctx = ctx
        self.tiles = tiles
        ctx.enable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

        self.world_prog = ctx.program(vertex_shader=WORLD_VS, fragment_shader=WORLD_FS)
        self.sky_prog = ctx.program(vertex_shader=SKY_VS, fragment_shader=SKY_FS)
        self.box_prog = ctx.program(vertex_shader=BOX_VS, fragment_shader=BOX_FS)
        self.hud_prog = ctx.program(vertex_shader=HUD_VS, fragment_shader=HUD_FS)

        layers, h, w = tiles.shape[:3]
        self.texture = ctx.texture_array((w, h, layers), 4, tiles.tobytes())
        self.texture.build_mipmaps()
        self.texture.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
        self.texture.anisotropy = 8.0
        self.world_prog["tex"].value = 0
        self.hud_prog["tex"].value = 0

        self.sky_vao = ctx.vertex_array(self.sky_prog, [])
        self.hud_vao = ctx.vertex_array(self.hud_prog, [])
        self.box_vao = self._make_box()
        self.part_prog = ctx.program(vertex_shader=PART_VS, fragment_shader=PART_FS)
        self.part_buffer = ctx.buffer(reserve=MAX_PARTS * PART_FLOATS * 4, dynamic=True)
        self.part_vao = self._make_parts()
        self.meshes = {}
        self.hud_texture = None
        self.hud_size = None
        self.vp = np.eye(4)

    def _make_box(self):
        data = []
        for t in TABLES:
            for k in (0, 1, 2, 0, 2, 3):
                data.extend(t["corner"][k].tolist())
                data.extend(((SIGNS[k, 0] + 1) / 2, (SIGNS[k, 1] + 1) / 2))
        vbo = self.ctx.buffer(np.array(data, dtype="f4").tobytes())
        return self.ctx.vertex_array(self.box_prog, [(vbo, "3f 2f", "in_pos", "in_uv")])

    def _make_parts(self):
        shades = (0.82, 0.82, 1.0, 0.55, 0.7, 0.7)
        data = []
        for t, shade in zip(TABLES, shades):
            for k in (0, 1, 2, 0, 2, 3):
                data.extend((t["corner"][k] - 0.5).tolist())
                data.append(shade)
        vbo = self.ctx.buffer(np.array(data, dtype="f4").tobytes())
        return self.ctx.vertex_array(self.part_prog, [
            (vbo, "3f 1f", "in_pos", "in_shade"),
            (self.part_buffer, "3f 3f 3f 1f 1f 3f 1f 1f /i", "i_base", "i_off", "i_size", "i_yaw", "i_swing",
             "i_color", "i_light", "i_flash"),
        ])

    # --- Геометрия чанков ---------------------------------------------------

    def upload(self, key, solid, clear):
        self.drop(key)
        record = []
        for data in (solid, clear):
            if data:
                vbo = self.ctx.buffer(data)
                vao = self.ctx.vertex_array(self.world_prog, [(vbo, "4u1 4u1", "in_a", "in_b")])
                record.append((vbo, vao))
            else:
                record.append(None)
        self.meshes[key] = record

    def drop(self, key):
        record = self.meshes.pop(key, None)
        if record:
            for part in record:
                if part:
                    part[1].release()
                    part[0].release()

    def clear(self):
        for key in list(self.meshes):
            self.drop(key)

    def _visible(self, vp):
        keys = list(self.meshes)
        if not keys:
            return []
        xz = np.array(keys, dtype=float) * CHUNK
        lo = np.column_stack([xz[:, 0], np.zeros(len(keys)), xz[:, 1]])
        hi = lo + (CHUNK, HEIGHT, CHUNK)
        ok = np.ones(len(keys), dtype=bool)
        for axis in range(3):
            for sign in (1, -1):
                plane = vp[3] + sign * vp[axis]
                n = plane[:3]
                far = np.where(n > 0, hi, lo)
                ok &= far.dot(n) + plane[3] >= 0
        return [keys[i] for i in np.nonzero(ok)[0]]

    # --- Кадр ---------------------------------------------------------------

    def draw(self, size, eye, look, radius, day_time, clock, target, underwater, fov, mine_progress=0.0, parts=(),
             realm_look=None, target_box=None):
        ctx = self.ctx
        ctx.viewport = (0, 0, size[0], size[1])
        ctx.screen.depth_mask = True
        ctx.clear(depth=1.0)

        far = (radius + 2) * CHUNK * 1.5
        proj = perspective(fov, size[0] / max(size[1], 1), 0.07, far)
        vp = proj @ view_matrix(eye, look)
        self.vp = vp

        angle = day_time * math.tau
        sun = np.array((math.cos(angle), math.sin(angle), 0.28))
        sun /= np.linalg.norm(sun)
        day = _smooth(-0.14, 0.2, float(sun[1]))
        dusk = max(0.0, 1.0 - abs(float(sun[1])) * 3.4) ** 2
        night = 1.0 - day

        zenith = _mix((0.035, 0.04, 0.13), (0.32, 0.50, 0.90), day)
        horizon = _mix((0.09, 0.09, 0.20), (0.84, 0.80, 0.92), day)
        horizon = _mix(horizon, (1.0, 0.58, 0.46), dusk * 0.72)
        sun_color = _mix((0.15, 0.18, 0.31), (1.0, 0.98, 0.93), day)
        sun_color = _mix(sun_color, (1.0, 0.72, 0.56), dusk * 0.5)

        fog_end = radius * CHUNK - 6.0
        ambient = (0.06, 0.065, 0.1)
        celestial = 1.0
        if realm_look:
            zenith, horizon, sun_color = realm_look["zenith"], realm_look["horizon"], realm_look["sun"]
            ambient = realm_look["ambient"]
            night = realm_look["stars"]
            celestial = 0.0
            fog_end *= realm_look["fog"]
        fog_range = (fog_end * 0.55, fog_end)
        if underwater:
            horizon = zenith = (0.09, 0.32 + 0.1 * day, 0.42 + 0.1 * day)
            fog_range = (1.0, 26.0)

        ctx.disable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
        p = self.sky_prog
        p["inv_vp"].write(_gl(np.linalg.inv(vp)))
        p["eye"].value = tuple(eye)
        p["sun_dir"].value = tuple(float(v) for v in sun)
        p["horizon"].value = horizon
        p["zenith"].value = zenith
        p["night"].value = night
        p["time"].value = clock
        p["celestial"].value = celestial
        self.sky_vao.render(moderngl.TRIANGLES, vertices=3)
        ctx.enable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)

        p = self.world_prog
        p["vp"].write(_gl(vp))
        p["eye"].value = tuple(eye)
        p["fog_color"].value = horizon
        p["fog_range"].value = fog_range
        p["sun_color"].value = sun_color
        p["ambient"].value = ambient
        p["time"].value = clock
        self.texture.use(0)

        visible = self._visible(vp)
        chunk = p["chunk"]
        for key in visible:
            part = self.meshes[key][0]
            if part:
                chunk.value = (key[0] * CHUNK, 0.0, key[1] * CHUNK)
                part[1].render(moderngl.TRIANGLES)

        if parts:
            count = min(len(parts), MAX_PARTS)
            self.part_buffer.write(np.array(parts[:count], dtype="f4").tobytes())
            q = self.part_prog
            q["vp"].write(_gl(vp))
            q["eye"].value = tuple(eye)
            q["fog_color"].value = horizon
            q["fog_range"].value = fog_range
            q["sun_color"].value = sun_color
            q["ambient"].value = ambient
            self.part_vao.render(moderngl.TRIANGLES, instances=count)

        # Вода и стекло — от дальних чанков к ближним, без записи глубины.
        ctx.enable(moderngl.BLEND)
        ctx.disable(moderngl.CULL_FACE)
        ctx.screen.depth_mask = False
        cx, cz = eye[0] / CHUNK - 0.5, eye[2] / CHUNK - 0.5
        for key in sorted(visible, key=lambda k: -((k[0] - cx) ** 2 + (k[1] - cz) ** 2)):
            part = self.meshes[key][1]
            if part:
                chunk.value = (key[0] * CHUNK, 0.0, key[1] * CHUNK)
                part[1].render(moderngl.TRIANGLES)

        if target:
            self.box_prog["vp"].write(_gl(vp))
            self.box_prog["cell"].value = tuple(float(v) for v in target)
            x0, y0, z0, x1, y1, z1 = target_box or (0.0, 0.0, 0.0, 1.0, 1.0, 1.0)
            self.box_prog["low"].value = (x0, y0, z0)
            self.box_prog["span"].value = (x1 - x0, y1 - y0, z1 - z0)
            self.box_prog["progress"].value = mine_progress
            self.box_vao.render(moderngl.TRIANGLES)
        ctx.screen.depth_mask = True
        return len(visible)

    # --- Интерфейс ----------------------------------------------------------

    def upload_hud(self, surf):
        size = surf.get_size()
        data = pygame.image.tobytes(surf, "RGBA", True)
        if self.hud_size != size:
            if self.hud_texture:
                self.hud_texture.release()
            self.hud_texture = self.ctx.texture(size, 4, data)
            self.hud_texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
            self.hud_size = size
        else:
            self.hud_texture.write(data)

    def draw_hud(self, hurt=0.0):
        ctx = self.ctx
        ctx.disable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
        ctx.enable(moderngl.BLEND)
        self.hud_texture.use(0)
        self.hud_prog["hurt"].value = hurt
        self.hud_vao.render(moderngl.TRIANGLES, vertices=3)
        ctx.disable(moderngl.BLEND)
        ctx.enable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
