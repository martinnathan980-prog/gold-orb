#!/usr/bin/env python3
"""Carte du vol animée façon écran de siège, pour la vidéo Océane Airlines.

Rend une étape (ville de départ -> ville d'arrivée) en MP4 1920x1080, 30 i/s,
prête à glisser dans iMovie.

Dépendances : pip install numpy imageio-ffmpeg (ffmpeg fourni par le paquet).
Les polices et le fond de carte sont téléchargés au premier lancement.
"""
import json
import math
import os
import subprocess
import urllib.request

from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

ASSETS = {
    "countries-50m.json": "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-50m.json",
    "BarlowCondensed-SemiBold.ttf": "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/barlowcondensed/BarlowCondensed-SemiBold.ttf",
    "BarlowCondensed-Bold.ttf": "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/barlowcondensed/BarlowCondensed-Bold.ttf",
    "IBMPlexMono-SemiBold.ttf": "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/ibmplexmono/IBMPlexMono-SemiBold.ttf",
    "IBMPlexMono-Medium.ttf": "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/ibmplexmono/IBMPlexMono-Medium.ttf",
}
for name, url in ASSETS.items():
    if not os.path.exists(name):
        urllib.request.urlretrieve(url, name)

W, H = 1920, 1080
SS = 2  # suréchantillonnage pour lisser les traits
FPS = 30

OCEAN = (7, 27, 51)
LAND = (31, 43, 55)
COAST = (86, 128, 170)
BORDER = (60, 76, 92)
GRID = (15, 40, 68)
AMBER = (245, 176, 35)
WHITE = (238, 243, 248)
MUTED = (138, 162, 188)
PANEL = (4, 12, 20)

F_COND = "BarlowCondensed-SemiBold.ttf"
F_COND_B = "BarlowCondensed-Bold.ttf"
F_MONO = "IBMPlexMono-SemiBold.ttf"
F_MONO_M = "IBMPlexMono-Medium.ttf"


def font(path, size):
    return ImageFont.truetype(path, size)


# ---------- Géographie (TopoJSON world-atlas) ----------

def load_topo(path):
    topo = json.load(open(path))
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)
    return topo, arcs


def ring_points(ring, arcs):
    pts = []
    for i in ring:
        a = arcs[i] if i >= 0 else arcs[~i][::-1]
        pts.extend(a[1:] if pts else a)
    return pts


def polygons_and_borders(topo, arcs):
    polys = []
    use = {}
    for g in topo["objects"]["countries"]["geometries"]:
        if g["type"] == "Polygon":
            groups = [g["arcs"]]
        elif g["type"] == "MultiPolygon":
            groups = g["arcs"]
        else:
            continue
        for poly in groups:
            for k, ring in enumerate(poly):
                polys.append((k == 0, ring_points(ring, arcs)))
                for i in ring:
                    j = i if i >= 0 else ~i
                    use[j] = use.get(j, 0) + 1
    borders = [arcs[j] for j, n in use.items() if n >= 2]
    coasts = [arcs[j] for j, n in use.items() if n == 1]
    return polys, borders, coasts


# ---------- Projection ----------

class View:
    def __init__(self, lon0, lat0, k):
        self.lon0, self.lat0, self.k = lon0, lat0, k
        self.c = math.cos(math.radians(lat0))

    def xy(self, lon, lat, s=1):
        x = W / 2 + (lon - self.lon0) * self.c * self.k
        y = H * 0.44 - (lat - self.lat0) * self.k
        return x * s, y * s

    def bounds(self):
        lon_a = self.lon0 - (W / 2) / (self.c * self.k)
        lon_b = self.lon0 + (W / 2) / (self.c * self.k)
        lat_a = self.lat0 - (H * 0.56) / self.k
        lat_b = self.lat0 + (H * 0.44) / self.k
        return lon_a, lon_b, lat_a, lat_b


def haversine(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[1], a[0], b[1], b[0]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def ease(t):
    return 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, t)))


PLANE_HALF = [(1.00, 0.00), (0.92, 0.05), (0.70, 0.075), (0.18, 0.075), (-0.18, 0.62),
              (-0.32, 0.62), (-0.12, 0.075), (-0.62, 0.07), (-0.82, 0.30), (-0.93, 0.30),
              (-0.86, 0.06), (-1.00, 0.03)]
PLANE = PLANE_HALF + [(x, -y) for x, y in reversed(PLANE_HALF)]


def plane_poly(cx, cy, ang, size):
    ca, sa = math.cos(ang), math.sin(ang)
    return [(cx + (x * ca - y * sa) * size, cy + (x * sa + y * ca) * size) for x, y in PLANE]


def tracked(d, xy, text, fnt, fill, tracking):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=fnt, fill=fill)
        x += d.textlength(ch, font=fnt) + tracking
    return x


def render_leg(out, start, end, cities, info, seconds=6.0, zoom=(1.0, 1.07), bulge=0.18, sea=None,
               center=None, fit=1.0):
    """start/end: (lon, lat, NOM, sous-titre). cities: [(lon, lat, nom)] pour le décor."""
    topo, arcs = load_topo("countries-50m.json")
    polys, borders, coasts = polygons_and_borders(topo, arcs)

    lon0, lat0 = center or ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    c = math.cos(math.radians(lat0))
    span_x = abs(end[0] - start[0]) * c
    span_y = abs(end[1] - start[1])
    k_base = fit * min((W * 0.62) / max(span_x, 0.3), (H * 0.42) / max(span_y, 0.3))

    # la route : arc de Bézier qui bombe vers le nord
    total_km = haversine(start, end)
    n = 400

    def route_lonlat(t):
        ax, ay = start[0] * c, start[1]
        bx, by = end[0] * c, end[1]
        mx, my = (ax + bx) / 2, (ay + by) / 2
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        px, py = -dy / L, dx / L
        if py < 0:
            px, py = -px, -py
        cx_, cy_ = mx + px * L * bulge, my + py * L * bulge
        x = (1 - t) ** 2 * ax + 2 * (1 - t) * t * cx_ + t * t * bx
        y = (1 - t) ** 2 * ay + 2 * (1 - t) * t * cy_ + t * t * by
        return x / c, y

    samples = [route_lonlat(i / n) for i in range(n + 1)]

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    proc = subprocess.Popen(
        [ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
         "-shortest", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
         "-profile:v", "high", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out],
        stdin=subprocess.PIPE)

    frames = int(seconds * FPS)
    t_start, t_end = 0.7, seconds - 1.2
    f_label = font(F_COND_B, 46)
    f_city = font(F_COND, 30)
    f_sub = font(F_MONO_M, 20)
    f_sea = font(F_COND, 34)
    f_k = font(F_MONO_M, 19)
    f_v = font(F_COND_B, 50)
    f_brand = font(F_MONO, 20)

    for fi in range(frames):
        tt = fi / (frames - 1)
        k = k_base * (zoom[0] + (zoom[1] - zoom[0]) * ease(tt))
        v = View(lon0, lat0, k)
        la, lb, pa, pb = v.bounds()

        big = Image.new("RGB", (W * SS, H * SS), OCEAN)
        d = ImageDraw.Draw(big)
        # graticule
        for g in range(math.floor(la), math.ceil(lb) + 1):
            d.line([v.xy(g, pa - 1, SS), v.xy(g, pb + 1, SS)], fill=GRID, width=2)
        for g in range(math.floor(pa), math.ceil(pb) + 1):
            d.line([v.xy(la - 1, g, SS), v.xy(lb + 1, g, SS)], fill=GRID, width=2)
        # terres
        for outer, pts in polys:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            if max(xs) < la - 1 or min(xs) > lb + 1 or max(ys) < pa - 1 or min(ys) > pb + 1:
                continue
            d.polygon([v.xy(x, y, SS) for x, y in pts], fill=LAND if outer else OCEAN)
        for arc in borders:
            if all(not (la - 1 < x < lb + 1 and pa - 1 < y < pb + 1) for x, y in arc):
                continue
            d.line([v.xy(x, y, SS) for x, y in arc], fill=BORDER, width=2)
        for arc in coasts:
            if all(not (la - 1 < x < lb + 1 and pa - 1 < y < pb + 1) for x, y in arc):
                continue
            d.line([v.xy(x, y, SS) for x, y in arc], fill=COAST, width=3)

        # route
        p = ease((tt * seconds - t_start) / (t_end - t_start))
        cut = int(p * n)
        pts = [v.xy(x, y, SS) for x, y in samples]
        # reste du trajet en pointillés
        for i in range(cut, n, 8):
            d.line(pts[i:min(i + 5, n) + 1], fill=(120, 140, 160), width=4)
        if cut > 0:
            d.line(pts[:cut + 1], fill=AMBER, width=8, joint="curve")
        for (lon, lat, *_), col in ((start, AMBER), (end, WHITE)):
            x, y = v.xy(lon, lat, SS)
            d.ellipse([x - 13, y - 13, x + 13, y + 13], fill=col, outline=OCEAN, width=4)
        for lon, lat, _ in cities:
            x, y = v.xy(lon, lat, SS)
            d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=MUTED)
        # avion
        i = min(max(cut, 1), n - 1)
        x0, y0 = pts[i - 1]
        x1, y1 = pts[i + 1]
        ang = math.atan2(y1 - y0, x1 - x0)
        px, py = pts[cut]
        d.polygon(plane_poly(px + 7, py + 9, ang, 78), fill=(3, 8, 14))
        d.polygon(plane_poly(px, py, ang, 78), fill=WHITE, outline=OCEAN, width=3)

        frame = big.resize((W, H), Image.LANCZOS)
        d = ImageDraw.Draw(frame)

        # noms de lieux
        if sea:
            x, y = v.xy(sea[0], sea[1])
            tracked(d, (x, y), sea[2].upper(), f_sea, (58, 96, 136), 8)
        for lon, lat, name in cities:
            x, y = v.xy(lon, lat)
            d.text((x + 12, y - 20), name.upper(), font=f_city, fill=MUTED)
        for (lon, lat, name, sub), other, col in ((start, end, AMBER), (end, start, WHITE)):
            x, y = v.xy(lon, lat)
            ox, _ = v.xy(other[0], other[1])
            if ox > x:  # l'avion arrive par la droite : le nom passe à gauche du point
                d.text((x - 48, y - 44), name.upper(), font=f_label, fill=col, anchor="ra")
                d.text((x - 50, y + 6), sub.upper(), font=f_sub, fill=col, anchor="ra")
            else:
                d.text((x + 48, y - 44), name.upper(), font=f_label, fill=col)
                d.text((x + 50, y + 6), sub.upper(), font=f_sub, fill=col)

        # bandeau du bas, façon écran de siège
        top = H - 168
        band = Image.new("RGBA", (W, 168), PANEL + (255,))
        frame.paste(band, (0, top), band)
        d.rectangle([0, top, W, top + 3], fill=AMBER)
        remaining = round(total_km * (1 - p))
        cols = [
            ("VOL", "OC 1996", AMBER),
            ("DE", start[2].upper(), WHITE),
            ("VERS", end[2].upper(), WHITE),
            ("DISTANCE RESTANTE", f"{remaining} KM", WHITE),
        ] + info
        cw = (W - 120) / len(cols)
        for j, (key, val, col) in enumerate(cols):
            x = 60 + j * cw
            tracked(d, (x, top + 34), key, f_k, MUTED, 2)
            d.text((x, top + 66), val, font=f_v, fill=col)
        tracked(d, (60, 44), "OCÉANE AIRLINES · CARTE DU VOL", f_brand, MUTED, 3)

        proc.stdin.write(frame.tobytes())
        if fi in (0, frames // 2, frames - 1):
            frame.save(out.replace(".mp4", f"-f{fi:03d}.png"))
    proc.stdin.close()
    proc.wait()


if __name__ == "__main__":
    render_leg(
        "carte-avignon-enac.mp4",
        start=(4.8055, 43.9493, "Avignon", "IUT"),
        end=(1.4787, 43.5649, "Toulouse", "ENAC"),
        cities=[(4.3601, 43.8367, "Nîmes"), (3.8767, 43.6108, "Montpellier"),
                (5.3698, 43.2965, "Marseille"), (2.3491, 43.2130, "Carcassonne")],
        info=[("PASSAGÈRE 1A", "ACCOUDOIR SERRÉ", AMBER)],
        sea=(3.55, 42.75, "Mer Méditerranée"),
        center=(3.15, 43.35), fit=0.78,
    )
