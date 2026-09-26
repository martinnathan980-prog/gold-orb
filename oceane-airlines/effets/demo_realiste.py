#!/usr/bin/env python3
"""Démo réaliste de 15 secondes : la cabine, l'annonce du commandant, on entre dans l'écran du siège.

Usage : demo_realiste.py CABINE.jpg "x1,y1 x2,y2 x3,y3 x4,y4" COMMANDANT.jpg
(les quatre coins de l'écran du siège : haut-gauche, haut-droit, bas-droit, bas-gauche)
"""
import math
import os
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
import imageio_ffmpeg

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
FF = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS, SR = 1920, 1080, 30, 48000
LOGO = "/home/user/gold-orb/oceane-airlines/cartons/00-logo.png"

cabin_path, corners_arg, captain_path = sys.argv[1], sys.argv[2], sys.argv[3]
QUAD = [tuple(float(v) for v in c.split(",")) for c in corners_arg.split()]

rng = np.random.default_rng(9)


def font(name, size):
    return ImageFont.truetype(os.path.join(HERE, name), size)


def ease(t):
    t = max(0.0, min(1.0, t))
    return 0.5 - 0.5 * math.cos(math.pi * t)


def perspective_coeffs(dst, src):
    """Coefficients PIL qui envoient chaque point de dst (sortie) vers src (entrée)."""
    m = []
    for (x, y), (u, v) in zip(dst, src):
        m.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        m.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    a = np.array(m, dtype=float)
    b = np.array([c for pt in src for c in pt], dtype=float)
    return np.linalg.solve(a, b).tolist()


def lcd_look(img):
    """Un contenu vu sur un écran de siège : un peu moins de contraste, un peu plus doux."""
    img = ImageEnhance.Contrast(img).enhance(0.88)
    img = ImageEnhance.Color(img).enhance(0.9)
    img = ImageEnhance.Brightness(img).enhance(0.92)
    return img.filter(ImageFilter.GaussianBlur(0.6))


def insert_screen(cabin, content):
    """Pose le contenu dans l'écran du siège, en perspective, avec un léger reflet."""
    cw, ch = content.size
    coeffs = perspective_coeffs(QUAD, [(0, 0), (cw, 0), (cw, ch), (0, ch)])
    warped = lcd_look(content).transform(cabin.size, Image.PERSPECTIVE, coeffs, Image.BICUBIC)
    mask = Image.new("L", cabin.size, 0)
    ImageDraw.Draw(mask).polygon(QUAD, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(0.8))
    out = cabin.copy()
    out.paste(warped, (0, 0), mask)
    # reflet discret de la lumière du hublot, en diagonale sur la vitre
    qx0, qx1 = min(p[0] for p in QUAD), max(p[0] for p in QUAD)
    grad = Image.linear_gradient("L").rotate(-35, expand=False).resize(cabin.size)
    grad = grad.crop((0, 0) + cabin.size)
    ramp = np.asarray(grad, dtype=np.float32) / 255.0
    xs = np.clip((np.arange(cabin.size[0]) - qx0) / max(1, qx1 - qx0), 0, 1)[None, :]
    alpha = (np.asarray(mask, dtype=np.float32) / 255.0) * (0.04 + 0.12 * xs * (1 - ramp))
    arr = np.asarray(out, dtype=np.float32)
    arr = arr * (1 - alpha[..., None]) + 255 * alpha[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def fit_cover(img, size):
    w, h = size
    s = max(w / img.width, h / img.height)
    img = img.resize((int(img.width * s + 0.5), int(img.height * s + 0.5)), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def grade(img):
    """Même étalonnage pour tout : léger contraste, vignettage, grain."""
    arr = np.asarray(img).astype(np.float32)
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    vign = 1.0 - 0.18 * np.clip(r - 0.35, 0, 1) ** 1.5
    return vign[..., None]


VIGN = None


def finish(img, i):
    global VIGN
    if VIGN is None:
        VIGN = grade(img)
    arr = np.asarray(img).astype(np.float32) * VIGN
    arr += rng.normal(0, 1.8, (H // 2, W // 2, 1)).repeat(2, 0).repeat(2, 1)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def camera(img, box, i):
    """Cadrage + léger mouvement de main, comme filmé au téléphone."""
    x0, y0, x1, y1 = box
    t = i / FPS
    dx = 5 * math.sin(t * 1.3) + 2.5 * math.sin(t * 3.1 + 1)
    dy = 4 * math.sin(t * 1.7 + 2) + 2 * math.sin(t * 2.6)
    k = (x1 - x0) / img.width
    cx, cy = (x0 + x1) / 2 + dx * k * 3, (y0 + y1) / 2 + dy * k * 3
    bw, bh = (x1 - x0) * 0.96, (y1 - y0) * 0.96
    cx = min(max(cx, bw / 2), img.width - bw / 2)
    cy = min(max(cy, bh / 2), img.height - bh / 2)
    return img.resize((W, H), Image.BICUBIC, box=(cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2))


def caption(img, text, alpha):
    if alpha <= 0:
        return img
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    f = font("BarlowCondensed-SemiBold.ttf", 50)
    tw = d.textlength(text, font=f)
    x, y = (W - tw) / 2, H - 150
    d.rounded_rectangle([x - 26, y - 14, x + tw + 26, y + 70], radius=10, fill=(0, 0, 0, int(150 * alpha)))
    d.text((x, y), text, font=f, fill=(255, 255, 255, int(255 * alpha)))
    img = img.convert("RGBA")
    img.alpha_composite(over)
    return img.convert("RGB")


def lower_third(img, t):
    if t <= 0:
        return img
    a = ease(t / 0.4)
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    x = 110 - (1 - a) * 60
    d.rectangle([x, 790, x + 8, 900], fill=(245, 176, 35, int(255 * a)))
    d.text((x + 30, 782), "Commandant Nathan", font=font("BarlowCondensed-Bold.ttf", 64),
           fill=(255, 255, 255, int(255 * a)))
    d.text((x + 32, 858), "OCÉANE AIRLINES · VOL OC 1996", font=font("IBMPlexMono-Medium.ttf", 30),
           fill=(230, 230, 230, int(235 * a)))
    img = img.convert("RGBA")
    img.alpha_composite(over)
    return img.convert("RGB")


def main():
    cabin = Image.open(cabin_path).convert("RGB")
    captain = Image.open(captain_path).convert("RGB")
    logo = Image.open(LOGO).convert("RGB")
    sw = max(QUAD[1][0] - QUAD[0][0], QUAD[2][0] - QUAD[3][0])
    sh = max(QUAD[3][1] - QUAD[0][1], QUAD[2][1] - QUAD[1][1])
    content_size = (1600, int(1600 * sh / sw))
    cab_logo = insert_screen(cabin, fit_cover(logo, content_size))
    cab_capt = insert_screen(cabin, fit_cover(captain, content_size))
    capt_full = fit_cover(captain, (W, H))

    # cadrages dans la photo de cabine
    cw, chh = cabin.size
    wide = (0, (chh - cw * 9 / 16) / 2, cw, (chh + cw * 9 / 16) / 2) if cw * 9 / 16 <= chh else \
        ((cw - chh * 16 / 9) / 2, 0, (cw + chh * 16 / 9) / 2, chh)
    qx0, qx1 = min(p[0] for p in QUAD), max(p[0] for p in QUAD)
    qy0, qy1 = min(p[1] for p in QUAD), max(p[1] for p in QUAD)
    qcx, qcy = (qx0 + qx1) / 2, (qy0 + qy1) / 2
    zw = (qx1 - qx0) * 0.92
    tight = (qcx - zw / 2, qcy - zw * 9 / 32, qcx + zw / 2, qcy + zw * 9 / 32)
    push = tuple(w + (tt - w) * 0.12 for w, tt in zip(wide, tight))

    def lerp_box(a, b, t):
        return tuple(x + (y - x) * t for x, y in zip(a, b))

    proc = subprocess.Popen([FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
                             "-crf", "23", "-pix_fmt", "yuv420p", "-profile:v", "main", "demo-realiste-video.mp4"],
                            stdin=subprocess.PIPE)
    total = 16.0
    n = int(total * FPS)
    for i in range(n):
        t = i / FPS
        if t < 4.6:                                    # la cabine, le logo à l'écran
            src = cab_logo if t < 4.2 else (cab_capt if int(t * 30) % 3 else cab_logo)
            img = camera(src, lerp_box(wide, push, ease(t / 4.6)), i)
            img = caption(img, "« Mesdames et messieurs, ici votre commandant. »", ease((t - 1.2) / 0.3))
        elif t < 7.2:                                  # on entre dans l'écran
            z = ease((t - 4.6) / 2.6)
            img = camera(cab_capt, lerp_box(push, tight, z), i)
            if t > 6.7:
                img = Image.blend(img, capt_full.resize((W, H)), ease((t - 6.7) / 0.5))
        elif t < 13.4:                                 # le commandant plein écran
            k = (t - 7.2) / 6.2
            s = 1.0 + 0.06 * k
            bw, bh = W / s, H / s
            img = capt_full.resize((W, H), Image.BICUBIC,
                                   box=((W - bw) / 2 + 30 * k, (H - bh) / 2, (W + bw) / 2 + 30 * k, (H + bh) / 2))
            img = lower_third(img, t - 7.8)
            img = caption(img, "« Nous amorçons notre descente vers les 30 ans d'Océane. »", ease((t - 8.6) / 0.3))
        else:                                          # on ressort dans la cabine
            z = ease((t - 13.4) / 2.2)
            img = camera(cab_capt, lerp_box(tight, push, z), i)
            if t < 13.8:
                img = Image.blend(capt_full.resize((W, H)), img, ease((t - 13.4) / 0.4))
        img = finish(img, i)
        proc.stdin.write(img.tobytes())
        if i in (30, 100, 170, 260, 330, 420, 470):
            img.save(f"chk/r_{i:03d}.png")
    proc.stdin.close()
    proc.wait()

    # son : ambiance cabine + ding de l'annonce
    ns = int(total * SR)
    x = np.cumsum(rng.standard_normal(ns))
    cs = np.cumsum(np.concatenate([np.zeros(2400), x]))
    x = x - (cs[2400:] - cs[:-2400]) / 2400
    cs = np.cumsum(np.concatenate([np.zeros(30), x]))
    x = (cs[30:] - cs[:-30]) / 30
    x = x / (np.max(np.abs(x)) + 1e-9) * 0.10
    tt = np.arange(ns) / SR
    x *= np.where(tt < 0.5, tt / 0.5, 1.0) * np.where(tt > total - 0.6, (total - tt) / 0.6, 1.0)
    for f0, start, tau in ((1046.5, 0.6, 0.55), (830.6, 1.15, 0.65)):
        k = int(start * SR)
        tn = np.arange(int(2.2 * SR)) / SR
        s = (np.sin(2 * math.pi * f0 * tn) + 0.25 * np.sin(4 * math.pi * f0 * tn)) * np.exp(-tn / tau) * 0.26
        x[k:k + len(s)] += s[: max(0, min(len(s), ns - k))]
    x = np.clip(x, -0.95, 0.95)
    st = np.repeat((x * 32767).astype(np.int16)[:, None], 2, axis=1)
    with wave.open("demo-realiste.wav", "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(st.tobytes())
    subprocess.run([FF, "-y", "-loglevel", "error", "-i", "demo-realiste-video.mp4", "-i", "demo-realiste.wav",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
                    "demo-realiste.mp4"], check=True)
    # aperçu animé, sans son, qui s'affiche partout
    subprocess.run([FF, "-y", "-loglevel", "error", "-i", "demo-realiste-video.mp4", "-vf",
                    "fps=10,scale=640:-1:flags=lanczos,hqdn3d=4:3:6:4.5,split[a][b];[a]palettegen=max_colors=160[p];"
                    "[b][p]paletteuse=dither=bayer:bayer_scale=4", "-loop", "0", "demo-realiste.gif"], check=True)
    print("ok", n, "frames")


if __name__ == "__main__":
    main()
