#!/usr/bin/env python3
"""Genere les cartons d'Oceane Airlines, 1920x1080, style panneau d'aeroport."""
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
OUT = "/home/user/gold-orb/oceane-airlines/cartons"
os.makedirs(OUT, exist_ok=True)

FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FM = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

BG = (8, 19, 31)
AMBER = (245, 176, 35)
WHITE = (255, 255, 255)
MUTED = (92, 122, 153)
GOLD = (201, 162, 39)
RED = (200, 60, 50)


def f(path, size):
    return ImageFont.truetype(path, size)


def tw(d, text, font, tracking=0):
    if tracking == 0:
        return d.textlength(text, font=font)
    return sum(d.textlength(c, font=font) + tracking for c in text) - tracking


def draw_tracked(d, xy, text, font, fill, tracking=0, anchor_center=True):
    x, y = xy
    width = tw(d, text, font, tracking)
    if anchor_center:
        x -= width / 2
    for c in text:
        d.text((x, y), c, font=font, fill=fill)
        x += d.textlength(c, font=font) + tracking
    return width


def base(scanlines=True):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    if scanlines:
        for y in range(0, H, 4):
            d.line([(0, y), (W, y)], fill=(11, 24, 38), width=1)
    return img, d


def frame(d, color=MUTED):
    d.rectangle([48, 48, W - 48, H - 48], outline=color, width=2)


def card(filename, kicker, title, sub=None, code=None, accent=AMBER, note=None):
    img, d = base()
    frame(d)
    if code:
        fcode = f(FM, 150)
        draw_tracked(d, (W / 2, 250), code, fcode, MUTED, tracking=18)
    if kicker:
        fk = f(FB, 40)
        draw_tracked(d, (W / 2, 430 if code else 330), kicker, fk, MUTED, tracking=14)
    ft_size = 118 if len(title) <= 18 else (92 if len(title) <= 26 else 70)
    ft = f(FB, ft_size)
    ty = 500 if code else 430
    draw_tracked(d, (W / 2, ty), title, ft, accent, tracking=8)
    d.line([(W / 2 - 220, ty + ft_size + 46), (W / 2 + 220, ty + ft_size + 46)],
           fill=accent, width=3)
    if sub:
        fs = f(FR, 46)
        draw_tracked(d, (W / 2, ty + ft_size + 90), sub, fs, WHITE, tracking=6)
    if note:
        fn = f(FR, 30)
        draw_tracked(d, (W / 2, H - 140), note, fn, MUTED, tracking=4)
    fl = f(FM, 26)
    draw_tracked(d, (W / 2, H - 92), "OCÉANE AIRLINES   ///   VOL OC 1996", fl, MUTED, tracking=8)
    img.save(os.path.join(OUT, filename))
    print("  " + filename)


# ----- logo -----
def logo():
    img, d = base(scanlines=False)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(8 + 10 * t), int(19 + 18 * t), int(31 + 28 * t)))
    cy = 470
    d.line([(W / 2 - 430, cy - 110), (W / 2 + 430, cy - 110)], fill=GOLD, width=3)
    draw_tracked(d, (W / 2, cy - 70), "OCÉANE", f(FB, 190), WHITE, tracking=26)
    draw_tracked(d, (W / 2, cy + 160), "A I R L I N E S", f(FR, 74), GOLD, tracking=16)
    d.line([(W / 2 - 430, cy + 290), (W / 2 + 430, cy + 290)], fill=GOLD, width=3)
    draw_tracked(d, (W / 2, cy + 330), "DEPUIS 1996", f(FM, 32), MUTED, tracking=14)
    img.save(os.path.join(OUT, "00-logo.png"))
    print("  00-logo.png")


# ----- panneau des departs -----
def board():
    img, d = base()
    frame(d)
    draw_tracked(d, (W / 2, 96), "DÉPARTS  /  DEPARTURES", f(FB, 50), WHITE, tracking=14)
    d.line([(120, 178), (W - 120, 178)], fill=MUTED, width=2)
    hdr = f(FM, 30)
    cols = [200, 470, 1180, 1500]
    for x, t in zip(cols, ["VOL", "DESTINATION", "HEURE", "PORTE"]):
        d.text((x, 208), t, font=hdr, fill=MUTED)
    rows = [
        ("OC 1996", "NÎMES", "1996", "A1"),
        ("OC 2000", "ÉCOLE", "20--", "B2"),
        ("OC 2018", "MARIGNANE", "20--", "C3"),
        ("OC 2024", "POINTE-À-PITRE", "20--", "D4"),
        ("OC 0030", "TRENTE ANS", "09 NOV", "1A"),
    ]
    fr = f(FM, 44)
    y = 300
    for i, (vol, dest, h, p) in enumerate(rows):
        last = i == len(rows) - 1
        col = AMBER if last else WHITE
        if last:
            d.rectangle([120, y - 22, W - 120, y + 76], outline=AMBER, width=2)
        d.text((cols[0], y), vol, font=fr, fill=col)
        d.text((cols[1], y), dest, font=fr, fill=col)
        d.text((cols[2], y), h, font=fr, fill=col)
        d.text((cols[3], y), p, font=fr, fill=col)
        y += 122
    draw_tracked(d, (W / 2, H - 112), "EMBARQUEMENT IMMÉDIAT", f(FB, 40), AMBER, tracking=14)
    img.save(os.path.join(OUT, "01-panneau-departs.png"))
    print("  01-panneau-departs.png")


# ----- carte d'embarquement -----
def boarding_pass():
    img = Image.new("RGB", (W, H), (14, 28, 44))
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = 140, 220, W - 140, 860
    split = x1 - 420
    d.rectangle([x0, y0, x1, y1], fill=(246, 244, 238))
    d.rectangle([x0, y0, x1, y0 + 92], fill=(11, 27, 43))
    draw_tracked(d, (x0 + 340, y0 + 26), "OCÉANE AIRLINES", f(FB, 42), WHITE, tracking=10)
    draw_tracked(d, (x1 - 230, y0 + 32), "CARTE D'EMBARQUEMENT", f(FR, 24), GOLD, tracking=4)
    for y in range(y0 + 108, y1 - 14, 26):
        d.line([(split, y), (split, y + 13)], fill=(168, 168, 168), width=3)

    lab = f(FR, 26)
    dark, grey = (20, 32, 48), (112, 122, 134)

    def field(x, y, label, value, size=52):
        d.text((x, y), label, font=lab, fill=grey)
        d.text((x, y + 36), value, font=f(FB, size), fill=dark)

    field(x0 + 60, 360, "PASSAGÈRE", "OCÉANE")
    field(x0 + 60, 500, "DE", "NÎMES")
    field(x0 + 470, 500, "À", "TRENTE ANS")
    field(x0 + 60, 640, "DATE", "09 NOV 2026", 44)
    field(x0 + 470, 640, "VOL", "OC 1996", 44)
    field(x0 + 830, 640, "CLASSE", "FAMILLE", 44)
    d.text((x0 + 60, 790), "PROCHAINE DESTINATION   /   POINTE-À-PITRE   /   DÉCEMBRE 2026",
           font=f(FR, 26), fill=grey)

    sx = split + 55
    d.text((sx, 360), "VOL", font=lab, fill=grey)
    d.text((sx, 396), "OC 1996", font=f(FB, 44), fill=dark)
    d.text((sx, 500), "SIÈGE", font=lab, fill=grey)
    d.text((sx, 536), "1A", font=f(FB, 72), fill=dark)

    import random
    random.seed(1996)
    bx, by, bend = sx, 690, x1 - 55
    while bx < bend - 10:
        bw = random.choice([3, 3, 4, 7])
        if bx + bw > bend:
            break
        d.rectangle([bx, by, bx + bw, by + 96], fill=dark)
        bx += bw + random.choice([4, 5, 8])
    img.save(os.path.join(OUT, "13-carte-embarquement.png"))
    print("  13-carte-embarquement.png")


print("Generation des cartons :")
logo()
board()
card("02-carton-nimes.png", "DÉCOLLAGE", "NÎMES", "9 NOVEMBRE 1996", code="NIM")
card("03-carton-ecole.png", "ESCALE", "L'ÉCOLE", "MÊME PROMOTION",
     note="carton provisoire, à regénérer avec le nom exact de l'école")
card("04-carton-marignane.png", "ESCALE", "MARIGNANE", "AIRBUS HELICOPTERS", code="MRS")
card("05-carton-turbulences.png", "ATTENTION", "ZONE DE TURBULENCES",
     "RESTEZ ASSIS, CEINTURE ATTACHÉE", accent=RED)
card("06-carton-pointe-a-pitre.png", "ESCALE", "POINTE-À-PITRE", "GUADELOUPE", code="PTP")
card("07-carton-cabine.png", "À BORD", "CLASSE ÉCONOMIQUE", "RANGS 20 À 34")
card("08-carton-duty-free.png", "VENTE À BORD", "BOUTIQUE HORS TAXES", "OFFRES LIMITÉES")
card("09-carton-presidence.png", "DIRECTION", "CONSEIL D'ADMINISTRATION", "SÉANCE EXCEPTIONNELLE")
card("10-carton-perte-signal.png", "", "PERTE DE SIGNAL", "TRANSMISSION INTERROMPUE", accent=RED)
card("11-carton-maternite.png", "ARRIVÉES", "TERMINAL MATERNITÉ", "PLUS JEUNE PASSAGÈRE")
card("12-carton-final.png", "PROCHAINE DESTINATION", "POINTE-À-PITRE", "DÉCEMBRE 2026", accent=GOLD)
boarding_pass()
print("Termine.")
