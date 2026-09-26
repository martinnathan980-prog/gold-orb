#!/usr/bin/env python3
"""Démo du montage Océane Airlines : ce que vous filmez, ce que je fabrique.

Les plans de la famille sont remplacés par des emplacements « VOTRE VIDÉO ».
Tout le reste (alerte, cartes, écran du siège, tremblements, perte de signal,
cartons, sons) est fabriqué ici. Sortie : demo-montage.mp4, 1920x1080, 30 i/s.
"""
import math
import os
import random
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
CARTONS = os.path.join(HERE, "..", "cartons")
FF = imageio_ffmpeg.get_ffmpeg_exe()

W, H, FPS, SR = 1920, 1080, 30, 48000

BG = (8, 19, 31)
PANEL = (13, 29, 45)
AMBER = (245, 176, 35)
WHITE = (238, 243, 248)
MUTED = (138, 162, 188)
RED = (214, 64, 52)
BLUE = (47, 111, 176)
INK = (11, 27, 43)


def font(name, size):
    return ImageFont.truetype(os.path.join(HERE, name), size)


COND = lambda s: font("BarlowCondensed-SemiBold.ttf", s)  # noqa: E731
CONDB = lambda s: font("BarlowCondensed-Bold.ttf", s)  # noqa: E731
MONO = lambda s: font("IBMPlexMono-SemiBold.ttf", s)  # noqa: E731
MONOM = lambda s: font("IBMPlexMono-Medium.ttf", s)  # noqa: E731


def ease(t):
    t = max(0.0, min(1.0, t))
    return 0.5 - 0.5 * math.cos(math.pi * t)


def lerp(a, b, t):
    return a + (b - a) * t


# ---------------------------------------------------------------- son

TOTAL_S = 90
AUDIO = np.zeros(TOTAL_S * SR, dtype=np.float32)
rng = np.random.default_rng(1996)


def mix(t, sig, gain=1.0):
    i = int(t * SR)
    j = min(len(AUDIO), i + len(sig))
    if i < len(AUDIO):
        AUDIO[i:j] += (sig[: j - i] * gain).astype(np.float32)


def tone(freq, dur, tau, partials=((1, 1.0), (2, 0.25), (3, 0.08)), attack=0.004):
    t = np.arange(int(dur * SR)) / SR
    s = sum(a * np.sin(2 * math.pi * freq * k * t) for k, a in partials)
    env = np.exp(-t / tau) * np.minimum(1.0, t / attack)
    return s * env / sum(a for _, a in partials)


def chime():
    a = tone(1046.5, 1.8, 0.55)
    b = tone(830.6, 2.0, 0.65)
    out = np.zeros(int(2.7 * SR))
    out[: len(a)] += a
    k = int(0.55 * SR)
    out[k:k + len(b)] += b
    return out * 0.32


def beep(freq=950, dur=0.17):
    t = np.arange(int(dur * SR)) / SR
    s = np.sin(2 * math.pi * freq * t) + 0.3 * np.sin(2 * math.pi * 3 * freq * t)
    env = np.minimum(1.0, np.minimum(t / 0.005, (dur - t) / 0.01))
    return s * env * 0.18


def click():
    n = int(0.006 * SR)
    t = np.arange(n) / SR
    s = rng.standard_normal(n) * np.exp(-t / 0.0009)
    s = np.diff(np.concatenate([[0], s]))
    return s * 0.09


def lowpass(x, width):
    cs = np.cumsum(np.concatenate([np.zeros(width), x, np.zeros(width)]))
    y = (cs[width:] - cs[:-width]) / width
    start = width // 2
    return y[start:start + len(x)]


def rumble(dur, env_fn, gain):
    n = int(dur * SR)
    x = np.cumsum(rng.standard_normal(n))
    x -= lowpass(x, 2400)
    x = lowpass(x, 40)
    x /= np.max(np.abs(x)) + 1e-9
    t = np.arange(n) / n
    return x * env_fn(t) * gain


def hiss(dur, gain):
    n = int(dur * SR)
    x = np.diff(np.concatenate([[0], rng.standard_normal(n)]))
    x = lowpass(x, 3)
    x /= np.max(np.abs(x)) + 1e-9
    return x * gain


def thud(gain=0.45):
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    s = np.sin(2 * math.pi * 62 * t) * np.exp(-t / 0.07)
    s += lowpass(rng.standard_normal(n), 25) * np.exp(-t / 0.03) * 2.0
    return s / (np.max(np.abs(s)) + 1e-9) * gain


def whoosh(dur, gain=0.16):
    n = int(dur * SR)
    t = np.arange(n) / n
    x = lowpass(rng.standard_normal(n), 12)
    x /= np.max(np.abs(x)) + 1e-9
    return x * np.sin(math.pi * t) ** 2 * gain


# ---------------------------------------------------------------- dessin

def tracked(d, xy, text, fnt, fill, tracking=0, anchor="l"):
    x, y = xy
    width = sum(d.textlength(c, font=fnt) + tracking for c in text) - tracking
    if anchor == "m":
        x -= width / 2
    for c in text:
        d.text((x, y), c, font=fnt, fill=fill)
        x += d.textlength(c, font=fnt) + tracking
    return width


def wrap(d, text, fnt, maxw):
    lines, cur = [], ""
    for w in text.split(" "):
        test = (cur + " " + w).strip()
        if d.textlength(test, font=fnt) <= maxw:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def pill(d, x, y, label, bg, fg):
    fnt = MONO(24)
    w = sum(d.textlength(c, font=fnt) + 3 for c in label) - 3
    d.rounded_rectangle([x, y, x + w + 40, y + 50], radius=25, fill=bg)
    tracked(d, (x + 20, y + 9), label, fnt, fg, 3)
    return w + 40


def roles(img, who, right=False, mark=True):
    d = ImageDraw.Draw(img)
    x = W - 60 - 262 if right else 60
    if "vous" in who:
        x += pill(d, x, 48, "VOUS FILMEZ", AMBER, INK) + 14
    if "moi" in who:
        pill(d, x, 48, "JE FABRIQUE", BLUE, WHITE)
    if mark:
        d.text((W - 60, H - 40), "DÉMO · OCÉANE AIRLINES", font=MONOM(20), fill=(92, 112, 134), anchor="rs")


def subtitle(img, label, text, alpha=1.0):
    if alpha <= 0:
        return
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    fnt = COND(46)
    lines = wrap(d, text, fnt, 1480)
    h = 70 + 58 * len(lines)
    x0, x1 = (W - 1620) / 2, (W + 1620) / 2
    y1 = H - 70
    y0 = y1 - h
    d.rounded_rectangle([x0, y0, x1, y1], radius=18, fill=(4, 10, 17, int(225 * alpha)))
    tracked(d, (x0 + 40, y0 + 22), label, MONO(22), AMBER + (int(255 * alpha),), 4)
    for i, line in enumerate(lines):
        d.text((x0 + 40, y0 + 52 + i * 58), line, font=fnt, fill=WHITE + (int(255 * alpha),))
    img.paste(over, (0, 0), over)


def camera_icon(d, x, y, s, color):
    d.rounded_rectangle([x, y, x + 90 * s, y + 60 * s], radius=10 * s, outline=color, width=int(5 * s))
    d.polygon([(x + 96 * s, y + 30 * s), (x + 130 * s, y + 10 * s), (x + 130 * s, y + 50 * s)],
              outline=color, fill=None, width=int(5 * s))
    d.ellipse([x + 28 * s, y + 13 * s, x + 62 * s, y + 47 * s], outline=color, width=int(4 * s))


def dashed_rect(d, box, color, dash=26, gap=16, width=4):
    x0, y0, x1, y1 = box
    for x in range(int(x0), int(x1), dash + gap):
        d.line([(x, y0), (min(x + dash, x1), y0)], fill=color, width=width)
        d.line([(x, y1), (min(x + dash, x1), y1)], fill=color, width=width)
    for y in range(int(y0), int(y1), dash + gap):
        d.line([(x0, y), (x0, min(y + dash, y1))], fill=color, width=width)
        d.line([(x1, y), (x1, min(y + dash, y1))], fill=color, width=width)


def placeholder(title, lines, kicker="VOTRE VIDÉO"):
    img = Image.new("RGB", (W, H), (14, 26, 38))
    d = ImageDraw.Draw(img)
    for k in range(-H, W, 60):
        d.line([(k, H), (k + H, 0)], fill=(17, 31, 45), width=18)
    box = (130, 150, W - 130, H - 200)
    d.rectangle(box, fill=(12, 23, 34))
    dashed_rect(d, box, AMBER)
    camera_icon(d, box[0] + 70, box[1] + 70, 1.0, AMBER)
    tracked(d, (box[0] + 250, box[1] + 82), kicker, MONO(30), AMBER, 6)
    d.text((box[0] + 70, box[1] + 190), title, font=CONDB(92), fill=WHITE)
    for i, line in enumerate(lines):
        d.text((box[0] + 72, box[1] + 320 + i * 62), line, font=COND(48), fill=MUTED)
    return img


def zoomed(img, scale, cx=W / 2, cy=H / 2):
    if abs(scale - 1.0) < 1e-3:
        return img.copy()
    w, h = W / scale, H / scale
    box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
    return img.resize((W, H), Image.BILINEAR, box=box)


def rec_dot(img, t):
    if int(t * 2) % 2 == 0:
        d = ImageDraw.Draw(img)
        d.ellipse([W - 250, 185, W - 222, 213], fill=RED)
        d.text((W - 210, 180), "REC", font=MONO(30), fill=RED)


# ---------------------------------------------------------------- plateau à volets

CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ÀÉÈ'-"


def flap_board(d, x, y, text, t, t0, cell=(40, 64), size=44, color=WHITE, seed=0, gap=6):
    """Dessine une rangée de volets. Renvoie le nombre de volets encore en mouvement."""
    r = random.Random(seed)
    moving = 0
    fnt = MONO(size)
    cw, ch = cell
    for i, c in enumerate(text):
        settle = t0 + 0.05 * i + r.uniform(0.1, 0.55)
        cx = x + i * (cw + gap)
        d.rounded_rectangle([cx, y, cx + cw, y + ch], radius=5, fill=(16, 32, 48))
        if c == " ":
            continue
        if t < t0:
            shown = " "
        elif t < settle:
            moving += 1
            shown = CHARS[(int(t * 24) + i * 7 + seed) % len(CHARS)]
        else:
            shown = c
        d.text((cx + cw / 2, y + ch / 2), shown, font=fnt, fill=color, anchor="mm")
        d.line([(cx, y + ch / 2), (cx + cw, y + ch / 2)], fill=(6, 14, 22), width=2)
    return moving


def flap_width(text, cell=(40, 64), gap=6):
    return len(text) * (cell[0] + gap) - gap


# ---------------------------------------------------------------- scènes

class Writer:
    def __init__(self, out):
        self.t = 0.0
        self.n = 0
        self.proc = subprocess.Popen(
            [FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
             "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
             "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
        self.checks = []

    def frame(self, img):
        self.proc.stdin.write(img.convert("RGB").tobytes())
        self.n += 1
        self.t = self.n / FPS

    def close(self):
        self.proc.stdin.close()
        self.proc.wait()


def frames(dur):
    n = int(round(dur * FPS))
    for i in range(n):
        yield i / FPS


def s_intro(w):
    t0 = w.t
    logo = Image.open(os.path.join(CARTONS, "00-logo.png")).convert("RGB").resize((960, 540), Image.LANCZOS)
    mix(t0 + 0.3, chime())
    for t in frames(4.2):
        img = Image.new("RGB", (W, H), BG)
        a = ease(t / 0.8)
        img.paste(Image.blend(Image.new("RGB", logo.size, BG), logo, a), ((W - 960) // 2, 40))
        d = ImageDraw.Draw(img)
        if t > 1.0:
            tracked(d, (W / 2, 610), "DÉMO DU MONTAGE", CONDB(66), AMBER, 8, anchor="m")
        if t > 1.6:
            pill(d, 360, 740, "VOUS FILMEZ", AMBER, INK)
            d.text((640, 744), "vos scènes, vos photos, vos messages", font=COND(46), fill=WHITE)
        if t > 2.2:
            pill(d, 360, 830, "JE FABRIQUE", BLUE, WHITE)
            d.text((640, 834), "le montage, les effets, les cartons, le son", font=COND(46), fill=WHITE)
        w.frame(img)


def s_board(w):
    t0 = w.t
    rows = [
        ("OC 1996", "NÎMES", "A1", "PARTI", MUTED),
        ("OC 0030", "30 ANS D'OCÉANE", "1A", "EMBARQUEMENT", AMBER),
    ]
    for t in frames(5.5):
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        tracked(d, (W / 2, 150), "DÉPARTS  ·  DEPARTURES", CONDB(60), WHITE, 12, anchor="m")
        d.line([(160, 240), (W - 160, 240)], fill=MUTED, width=2)
        cols = [160, 480, 1130, 1260]
        for x, lab in zip(cols, ["VOL", "DESTINATION", "PORTE", "STATUT"]):
            d.text((x, 270), lab, font=MONOM(26), fill=MUTED)
        moving = 0
        for r, (vol, dest, porte, statut, col) in enumerate(rows):
            y = 340 + r * 130
            if r == 1:
                d.rounded_rectangle([140, y - 18, W - 140, y + 100], radius=10, outline=AMBER, width=3)
            st = statut if not (r == 1 and t > 4.0 and int(t * 3) % 2) else " " * len(statut)
            for k, (x, txt) in enumerate(zip(cols, [vol, dest, porte, st])):
                moving += flap_board(d, x, y, txt, t, 0.3 + r * 0.5 + k * 0.15, color=col,
                                     seed=r * 10 + k, cell=(36, 64), size=40, gap=5)
        if t > 3.0:
            tracked(d, (W / 2, 800), "VOL OC 1996  ·  EMBARQUEMENT IMMÉDIAT", MONO(34), AMBER, 6, anchor="m")
        for _ in range(min(moving, 6)):
            if random.random() < 0.55:
                mix(t0 + t + random.random() / FPS, click())
        roles(img, ["moi"])
        w.frame(img)


def s_placeholder(w, title, lines, dur, sub=None, who=("vous",), sub_from=0.3, push=0.03):
    base = placeholder(title, lines)
    for t in frames(dur):
        img = zoomed(base, 1.0 + push * t / dur)
        rec_dot(img, t)
        roles(img, list(who))
        if sub and t > sub_from:
            subtitle(img, sub[0], sub[1], alpha=ease((t - sub_from) / 0.3))
        w.frame(img)


def s_controle(w):
    t0 = w.t
    base = placeholder("Le contrôle", ["« Océane », de dos, tend sa carte d'embarquement",
                                       "Les agents se figent…"])
    for k in range(8):
        mix(t0 + 1.8 + k * 0.35, beep())
    for t in frames(5.1):
        if t < 1.8:
            img = zoomed(base, 1.0 + 0.02 * t)
            rec_dot(img, t)
            roles(img, ["vous"])
        elif t < 4.6:
            img = zoomed(base, 1.036 + 0.05 * ease((t - 1.8) / 2.8))
            flash = 0.62 + 0.2 * (0.5 + 0.5 * math.sin((t - 1.8) * 2 * math.pi * 2.8))
            img = Image.blend(img, Image.new("RGB", (W, H), (120, 12, 10)), flash)
            d = ImageDraw.Draw(img)
            d.rectangle([0, 130, W, 290], fill=RED)
            tracked(d, (W / 2, 142), "ALERTE SÉCURITÉ", CONDB(120), WHITE, 10, anchor="m")
            d.rounded_rectangle([360, 420, W - 360, 700], radius=16, fill=(10, 8, 10), outline=RED, width=4)
            tracked(d, (W / 2, 460), "HOMONYME FICHÉ S DÉTECTÉ", MONO(58), WHITE, 3, anchor="m")
            tracked(d, (W / 2, 560), "PASSAGÈRE 1A  ·  CONTRÔLE APPROFONDI", MONO(34), AMBER, 3, anchor="m")
            sy = 430 + ((t - 1.8) * 260) % 260
            d.line([(372, sy), (W - 372, sy)], fill=(255, 90, 80), width=4)
            roles(img, ["vous", "moi"])
        else:
            img = Image.new("RGB", (W, H), (0, 0, 0))
        w.frame(img)


def s_voiture(w):
    t0 = w.t
    mix(t0 + 3.3, thud())
    mix(t0 + 3.75, thud(0.4))
    s_placeholder(w, "La voiture chargée", ["Le coffre de toit plein à craquer", "Les portières qui claquent"],
                  4.8, sub=("COMMANDANT · VOIX DE NATHAN",
                            "« Fausse alerte : c'était un homonyme. La passagère du 1A a peur de l'avion : "
                            "ce vol se fera donc en voiture. »"), sub_from=0.2)


def photo_card(label, tint):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = 760, 90, 1560, 860
    d.rectangle([x0 + 14, y0 + 18, x1 + 14, y1 + 18], fill=(3, 8, 14))
    d.rectangle([x0, y0, x1, y1], fill=(242, 238, 228))
    ix0, iy0, ix1, iy1 = x0 + 40, y0 + 40, x1 - 40, y1 - 170
    for y in range(iy0, iy1):
        k = (y - iy0) / (iy1 - iy0)
        d.line([(ix0, y), (ix1, y)], fill=tuple(int(c * (0.75 + 0.25 * k)) for c in tint))
    d.text(((ix0 + ix1) / 2, (iy0 + iy1) / 2), "PHOTO", font=MONO(40), fill=(250, 246, 238), anchor="mm")
    d.text(((x0 + x1) / 2, y1 - 85), label, font=COND(50), fill=(60, 60, 64), anchor="mm")
    return img


def s_decollage(w):
    t0 = w.t
    p1 = photo_card("Océane à la naissance", (196, 150, 120))
    p2 = photo_card("La masse de cheveux", (170, 136, 160))
    mix(t0 + 0.0, rumble(5.6, lambda x: np.minimum(1, x * 1.6) * (1 - np.maximum(0, x - 0.85) / 0.15), 0.34))
    mix(t0 + 4.05, thud(0.5))
    for t in frames(6.5):
        if t < 3.3:
            img = zoomed(p1, 1.0 + 0.10 * t / 3.3, W / 2 - 20 * t, H / 2)
        else:
            a = ease((t - 3.3) / 0.4)
            img = Image.blend(zoomed(p1, 1.1, W / 2 - 66, H / 2), zoomed(p2, 1.0 + 0.08 * (t - 3.3) / 3.2), a)
        d = ImageDraw.Draw(img)
        if 0.4 < t < 3.3:
            d.rounded_rectangle([90, 420, 660, 550], radius=14, fill=(4, 10, 17))
            tracked(d, (130, 445), "ALTITUDE : 0", MONO(64), AMBER, 4)
        if t > 3.8:
            s = 1.0 + 0.5 * max(0.0, 1 - (t - 3.8) / 0.25)
            stamp = Image.new("RGBA", (1000, 220), (0, 0, 0, 0))
            sd = ImageDraw.Draw(stamp)
            sd.rectangle([10, 10, 990, 210], outline=RED + (235,), width=12)
            sd.text((500, 110), "BAGAGE HORS FORMAT", font=CONDB(118), fill=RED + (235,), anchor="mm")
            stamp = stamp.resize((int(1000 * s), int(220 * s))).rotate(8, expand=True, resample=Image.BICUBIC)
            img.paste(stamp, (1160 - stamp.width // 2, 480 - stamp.height // 2), stamp)
        roles(img, ["vous", "moi"])
        if t < 3.2:
            subtitle(img, "COMMANDANT · VOIX DE NATHAN",
                     "« Départ : Nîmes, 9 novembre 1996. Destination : trente ans. »", ease((t - 0.2) / 0.3))
        w.frame(img)


def seat_scene():
    big = Image.new("RGB", (W * 2, H * 2), (22, 30, 40))
    d = ImageDraw.Draw(big)
    for y in range(H * 2):
        k = y / (H * 2)
        d.line([(0, y), (W * 2, y)], fill=(int(20 + 10 * k), int(28 + 12 * k), int(38 + 14 * k)))
    d.rounded_rectangle([760, 120, 3080, 2400], radius=180, fill=(34, 44, 58))
    d.rounded_rectangle([1180, 40, 2660, 520], radius=120, fill=(44, 56, 72))
    d.rounded_rectangle([1150, 620, 2690, 1520], radius=40, fill=(10, 14, 20))
    screen = (1210, 680, 2630, 1480)
    logo = Image.open(os.path.join(CARTONS, "00-logo.png")).convert("RGB")
    big.paste(logo.resize((screen[2] - screen[0], screen[3] - screen[1]), Image.LANCZOS), screen[:2])
    d.rounded_rectangle([1500, 1700, 2340, 1760], radius=20, fill=(26, 34, 46))
    return big, screen


def s_annonce(w):
    t0 = w.t
    big, (sx0, sy0, sx1, sy1) = seat_scene()
    msg = placeholder("Le message de Véro et Guitou", ["Chez eux, 15 secondes, à l'horizontale"])
    mix(t0 + 0.2, chime())
    mix(t0 + 1.6, whoosh(1.4))
    for t in frames(7.2):
        if t < 3.0:
            z = ease((t - 1.6) / 1.4) if t > 1.6 else 0.0
            x0, y0, x1, y1 = lerp(0, sx0, z), lerp(0, sy0, z), lerp(W * 2, sx1, z), lerp(H * 2, sy1, z)
            img = big.resize((W, H), Image.BILINEAR, box=(x0, y0, x1, y1))
            if t > 2.6:
                img = Image.blend(img, msg, ease((t - 2.6) / 0.4))
            roles(img, ["moi"])
            if t < 1.8:
                subtitle(img, "COMMANDANT · VOIX DE NATHAN",
                         "« Mesdames et messieurs, nous avons une annonce de dernière minute. »",
                         ease((t - 0.3) / 0.3))
        else:
            img = zoomed(msg, 1.0 + 0.02 * (t - 3.0))
            rec_dot(img, t)
            roles(img, ["vous", "moi"])
            if t > 3.4:
                d = ImageDraw.Draw(img)
                slide = ease((t - 3.4) / 0.35)
                x = int(lerp(-900, 90, slide))
                d.rectangle([x, 890, x + 820, 980], fill=AMBER)
                tracked(d, (x + 30, 912), "SIÈGE 3C · VÉRO ET GUITOU", MONO(38), INK, 2)
        w.frame(img)


def s_carte(w):
    proc = subprocess.Popen([FF, "-loglevel", "error", "-i", "carte-avignon-enac.mp4", "-f", "rawvideo",
                             "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    size = W * H * 3
    t0 = w.t
    mix(t0, rumble(6.0, lambda x: 0.6 + 0.4 * np.sin(np.pi * x), 0.07))
    while True:
        buf = proc.stdout.read(size)
        if len(buf) < size:
            break
        img = Image.frombytes("RGB", (W, H), buf)
        d = ImageDraw.Draw(img)
        roles(img, ["moi"], right=True, mark=False)
        w.frame(img)
    proc.wait()


def seatbelt_panel(on):
    img = Image.new("RGB", (W, H), (18, 24, 32))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([560, 300, 1360, 780], radius=40, fill=(30, 38, 50))
    col = AMBER if on else (70, 78, 90)
    d.ellipse([860, 360, 1060, 560], outline=col, width=14)
    d.ellipse([930, 395, 990, 455], fill=col)
    d.rounded_rectangle([915, 465, 1005, 535], radius=20, fill=col)
    d.line([(885, 505), (1035, 505)], fill=(30, 38, 50), width=12)
    tracked(d, (W / 2, 620), "ATTACHEZ VOS CEINTURES", CONDB(64), col, 6, anchor="m")
    return img


def s_turbulences(w):
    t0 = w.t
    off, on = seatbelt_panel(False), seatbelt_panel(True)
    base = placeholder("Dans la voiture qui tremble", ["Tout le monde se secoue, Véro dort",
                                                      "Signe de croix général"])
    mix(t0 + 0.35, tone(1046.5, 1.6, 0.5) * 0.3)
    mix(t0 + 1.0, rumble(4.5, lambda x: 0.55 + 0.45 * np.abs(np.sin(x * 9)), 0.42))
    r = random.Random(7)
    for t in frames(5.6):
        if t < 1.0:
            img = on if t > 0.3 else off
            img = img.copy()
            roles(img, ["moi"])
        else:
            amp = 16 + 10 * abs(math.sin(t * 9))
            img = base.rotate(r.uniform(-0.8, 0.8), resample=Image.BILINEAR,
                              translate=(r.uniform(-amp, amp), r.uniform(-amp, amp)), fillcolor=BG)
            img = zoomed(img, 1.05)
            d = ImageDraw.Draw(img)
            d.rectangle([0, 128, W, 222], fill=RED)
            tracked(d, (W / 2, 138), "ZONE DE TURBULENCES", CONDB(72), WHITE, 8, anchor="m")
            rec_dot(img, t)
            roles(img, ["vous", "moi"])
            subtitle(img, "COMMANDANT · VOIX DE NATHAN",
                     "« Turbulences parfaitement normales : l'appareil est actuellement conduit par Océane. »",
                     ease((t - 1.3) / 0.3))
        w.frame(img)


def static_frame(seed, dim=1.0):
    g = np.random.default_rng(seed).integers(0, 255, (H // 4, W // 4), dtype=np.uint8)
    img = Image.fromarray((g * dim).astype(np.uint8), "L").resize((W, H), Image.NEAREST).convert("RGB")
    return img


def s_signal(w):
    t0 = w.t
    names = ["Coco", "Célestin", "Mamie", "Tout le monde"]
    cards = [placeholder("« Allô ? Allô ? »", [n], kicker="VOTRE VIDÉO · 1 SECONDE") for n in names]
    mix(t0, hiss(1.3, 0.12))
    for t in frames(4.6):
        if t < 1.3:
            img = static_frame(int(t * FPS), 0.9)
            d = ImageDraw.Draw(img)
            jx = random.randint(-8, 8)
            d.rectangle([520, 440, 1400, 640], fill=(0, 0, 0))
            tracked(d, (W / 2 + jx, 470), "SIGNAL PERDU", MONO(96), RED, 6, anchor="m")
            roles(img, ["moi"])
        else:
            k = (t - 1.3) / 0.8
            i = int(k)
            if i >= len(cards):
                i = len(cards) - 1
            if k - int(k) > 0.8:
                img = static_frame(int(t * FPS) + 99, 0.7)
                if int((t - 1.3) * FPS) % 24 == 20:
                    mix(t0 + t, hiss(0.15, 0.1))
            else:
                img = cards[i].copy()
                rec_dot(img, t)
            roles(img, ["vous", "moi"])
        w.frame(img)


def s_destination(w):
    t0 = w.t
    txt = "À TOI DE CHOISIR"
    cell, gap = (84, 128), 10
    x = (W - flap_width(txt, cell, gap)) / 2
    mix(t0 + 4.4, chime())
    for t in frames(7.8):
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        if t < 4.4:
            tracked(d, (W / 2, 250), "PROCHAINE DESTINATION", CONDB(70), MUTED, 12, anchor="m")
            moving = flap_board(d, x, 420, txt, t, 0.4, cell=cell, size=92, color=AMBER, seed=3, gap=gap)
            for _ in range(min(moving, 6)):
                if random.random() < 0.55:
                    mix(t0 + t + random.random() / FPS, click())
            if t > 2.6:
                a = ease((t - 2.6) / 0.5)
                col = tuple(int(lerp(BG[i], WHITE[i], a)) for i in range(3))
                tracked(d, (W / 2, 640), "UN VOYAGE POUR DEUX, EN EUROPE", COND(58), col, 6, anchor="m")
        else:
            img = Image.new("RGB", (W, H), (3, 8, 14))
            d = ImageDraw.Draw(img)
            a = ease((t - 4.6) / 0.6)
            col = tuple(int(lerp(3, c, a)) for c in AMBER)
            tracked(d, (W / 2, 470), "CECI N'EST PAS UNE BLAGUE.", CONDB(104), col, 8, anchor="m")
        roles(img, ["moi"])
        w.frame(img)


def s_outro(w):
    for t in frames(7.0):
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        tracked(d, (W / 2, 90), "QUI FAIT QUOI", CONDB(70), WHITE, 10, anchor="m")
        left = ["Les scènes : salle d'attente, contrôle,", "voiture, consignes, cabine…",
                "Les photos et vidéos de la famille", "Les messages des proches", "La voix du commandant"]
        right = ["Tout le montage", "L'alerte, les cartes du vol,", "l'écran du siège",
                 "Les tremblements, la perte de signal", "Les cartons, les textes, le son"]
        a = ease(t / 0.5)
        pill(d, 170, 240, "VOUS FILMEZ", AMBER, INK)
        pill(d, 1010, 240, "JE FABRIQUE", BLUE, WHITE)
        for i, line in enumerate(left):
            d.text((170, 340 + i * 72), line, font=COND(50), fill=WHITE)
        for i, line in enumerate(right):
            d.text((1010, 340 + i * 72), line, font=COND(50), fill=WHITE)
        if t > 1.5:
            tracked(d, (W / 2, 850), "VOUS REGARDEZ CHAQUE VERSION, VOUS ME DITES QUOI CHANGER.",
                    MONO(30), AMBER, 3, anchor="m")
        if a < 1:
            img = Image.blend(Image.new("RGB", (W, H), BG), img, a)
        w.frame(img)


def main():
    random.seed(30)
    w = Writer("demo-video.mp4")
    marks = {}
    for name, fn in [
        ("intro", s_intro), ("board", s_board),
        ("attente", lambda w: s_placeholder(
            w, "La salle d'attente", ["4 ou 5 chaises, des bobs, des valises", "Socrate et Sissi déguisés"], 4.2,
            sub=("DANS LA SCÈNE", "« On va où ? – Aux 30 ans d'Océane ! »"))),
        ("controle", s_controle), ("voiture", s_voiture), ("decollage", s_decollage),
        ("consignes", lambda w: s_placeholder(
            w, "Les consignes de sécurité", ["Coco dit les consignes, les garçons miment",
                                             "Au fond, ça bavarde…"], 5.0,
            sub=("DANS LA SCÈNE", "« Madame ! Madame ! Ils parlent au fond ! »"), sub_from=2.0)),
        ("annonce", s_annonce), ("carte", s_carte), ("turbulences", s_turbulences),
        ("signal", s_signal), ("destination", s_destination), ("outro", s_outro),
    ]:
        marks[name] = w.t
        fn(w)
    w.close()
    total = w.n / FPS
    audio = np.clip(AUDIO[: int(total * SR)], -0.95, 0.95)
    peak = float(np.max(np.abs(audio)))
    stereo = np.repeat((audio * 32767).astype(np.int16)[:, None], 2, axis=1)
    with wave.open("demo-audio.wav", "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(stereo.tobytes())
    subprocess.run([FF, "-y", "-loglevel", "error", "-i", "demo-video.mp4", "-i", "demo-audio.wav",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
                    "demo-montage.mp4"], check=True)
    print(f"total {total:.1f} s, peak {peak:.2f}")
    for k, v in marks.items():
        print(f"  {k:12s} {v:5.1f} s")


if __name__ == "__main__":
    main()
