#!/usr/bin/env python3
"""Le synoptique : le plan de vol complet sur une page, a montrer a la famille."""
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
BLUE = (110, 168, 224)
WHITE = (255, 255, 255)
MUTED = (92, 122, 153)
GOLD = (201, 162, 39)
ROW = (12, 26, 41)


def f(p, s):
    return ImageFont.truetype(p, s)


def tracked(d, xy, text, font, fill, tracking=0, center=True):
    x, y = xy
    w = sum(d.textlength(c, font=font) + tracking for c in text) - tracking
    if center:
        x -= w / 2
    for c in text:
        d.text((x, y), c, font=font, fill=fill)
        x += d.textlength(c, font=font) + tracking


# temps, sequence, equipage, type
ROWS = [
    ("0:00", "Générique, panneau des départs", "Le commandant", ""),
    ("0:30", "Consignes de sécurité", "Nathan et Coralie", "GAG"),
    ("1:15", "Décollage, Nîmes 1996", "Véronique, puis Serge", "SINCÈRE"),
    ("2:00", "Escale École", "Julien", "GAG"),
    ("2:30", "Escale Marignane", "Hervé et Julien", "MIXTE"),
    ("3:00", "Turbulences, la conduite", "Documentaire animalier", "GAG"),
    ("3:30", "Escale Pointe-à-Pitre", "Sébastien", "SINCÈRE"),
    ("4:00", "Cabine, classe éco", "Cousins, Guy, Marité, Paul", "GAG"),
    ("4:30", "Duty free", "À pourvoir", "GAG"),
    ("5:00", "Présidence de la compagnie", "Mamie Christiane", "SINCÈRE"),
    ("5:30", "Perte de signal", "Tout le monde", "GAG"),
    ("6:00", "Terminal Maternité", "Célestin et Joséphine", "SINCÈRE"),
    ("6:30", "Atterrissage, compte à rebours", "Tout le monde", "FÊTE"),
    ("7:00", "Prochaine destination", "Pointe-à-Pitre, décembre", ""),
]

COLOR = {"GAG": AMBER, "SINCÈRE": BLUE, "MIXTE": MUTED, "FÊTE": GOLD, "": MUTED}

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)
for y in range(0, H, 4):
    d.line([(0, y), (W, y)], fill=(11, 24, 38))
d.rectangle([40, 40, W - 40, H - 40], outline=MUTED, width=2)

tracked(d, (W / 2, 72), "PLAN DE VOL   OC 1996", f(FB, 46), WHITE, 14)
tracked(d, (W / 2, 132), "OCÉANE AIRLINES   ///   7 MINUTES   ///   9 NOVEMBRE 2026",
        f(FM, 24), MUTED, 8)

cx = [110, 260, 1090, 1580]
d.line([(90, 190), (W - 90, 190)], fill=MUTED, width=2)
hf = f(FM, 22)
for x, t in zip(cx, ["HEURE", "SÉQUENCE", "ÉQUIPAGE", "REGISTRE"]):
    d.text((x, 200), t, font=hf, fill=MUTED)

y = 238
fh = f(FM, 28)
fs = f(FB, 28)
fe = f(FR, 26)
ft = f(FM, 20)
for i, (t, seq, eq, typ) in enumerate(ROWS):
    col = COLOR[typ]
    if i % 2 == 0:
        d.rectangle([90, y - 7, W - 90, y + 41], fill=ROW)
    d.rectangle([90, y - 7, 96, y + 41], fill=col)
    d.text((cx[0], y), t, font=fh, fill=WHITE)
    d.text((cx[1], y), seq, font=fs, fill=col if typ else WHITE)
    d.text((cx[2], y + 2), eq, font=fe, fill=MUTED)
    if typ:
        d.ellipse([cx[3], y + 10, cx[3] + 15, y + 25], fill=col)
        d.text((cx[3] + 28, y + 5), typ, font=ft, fill=col)
    y += 50

d.line([(90, y + 4), (W - 90, y + 4)], fill=MUTED, width=2)
tracked(d, (W / 2, y + 26),
        "ALTERNANCE STRICTE   ///   CHAQUE CLIP FINIT PAR «  ET DANS SA VALISE, JE METS...  »",
        f(FM, 20), GOLD, 5)
tracked(d, (W / 2, H - 92), "VIDÉOS À ENVOYER AVANT LE DIMANCHE 11 OCTOBRE",
        f(FB, 26), AMBER, 10)

img.save(os.path.join(OUT, "14-synoptique.png"))
print("14-synoptique.png")
