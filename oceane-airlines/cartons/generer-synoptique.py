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
ROW = (13, 28, 44)


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


# temps, sequence, equipage, registre
LEFT = [
    ("0:00", "Générique, panneau des départs", "Le commandant", ""),
    ("0:35", "Consignes de sécurité", "Nathan et Coralie", "G"),
    ("1:25", "Décollage, Nîmes 1996", "Véronique, puis Serge", "S"),
    ("2:10", "Rapport d'incidents, l'enfance", "Le fil de fer, les poignets", "G"),
    ("2:45", "Escale Tecktonik", "Amis d'ado, fratrie", "G"),
    ("3:15", "MESSAGES DE LA CABINE  1", "Tous les passagers", "M"),
    ("4:10", "Escale ENAC", "Julien", "M"),
    ("4:40", "Escale Avignon, la rencontre", "Célestin", "G"),
    ("5:15", "Escale Marignane", "Hervé et Julien", "M"),
    ("5:50", "Turbulences, la conduite", "Documentaire animalier", "G"),
]
RIGHT = [
    ("6:30", "Escale Pointe-à-Pitre", "Sébastien", "S"),
    ("7:00", "Cabine : première ou éco", "Cousins, Guy, Marité, Paul", "G"),
    ("7:35", "Duty free", "À pourvoir", "G"),
    ("8:05", "MESSAGES DE LA CABINE  2", "Tous les passagers", "M"),
    ("8:50", "Présidence de la compagnie", "Mamie Christiane", "S"),
    ("9:20", "Perte de signal", "Tout le monde", "G"),
    ("9:50", "Terminal Maternité", "Célestin et Joséphine", "S"),
    ("10:30", "Atterrissage, compte à rebours", "Tout le monde", "F"),
    ("11:00", "Prochaine destination", "Pointe-à-Pitre, décembre", ""),
]

COLOR = {"G": AMBER, "S": BLUE, "M": MUTED, "F": GOLD, "": MUTED}

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)
for y in range(0, H, 4):
    d.line([(0, y), (W, y)], fill=(11, 24, 38))
d.rectangle([40, 40, W - 40, H - 40], outline=MUTED, width=2)

tracked(d, (W / 2, 76), "PLAN DE VOL   OC 1996", f(FB, 48), WHITE, 16)
tracked(d, (W / 2, 142), "OCÉANE AIRLINES   ///   11 MINUTES   ///   9 NOVEMBRE 2026",
        f(FM, 24), MUTED, 8)
d.line([(80, 196), (W - 80, 196)], fill=MUTED, width=2)

ft, fs, fe = f(FM, 30), f(FB, 27), f(FR, 23)


def column(items, x0, width):
    y = 232
    for i, (t, seq, eq, reg) in enumerate(items):
        col = COLOR[reg]
        if i % 2 == 0:
            d.rectangle([x0, y - 8, x0 + width, y + 60], fill=ROW)
        d.rectangle([x0, y - 8, x0 + 7, y + 60], fill=col)
        d.text((x0 + 26, y), t, font=ft, fill=WHITE)
        d.text((x0 + 148, y - 2), seq, font=fs, fill=col if reg else WHITE)
        d.text((x0 + 148, y + 32), eq, font=fe, fill=MUTED)
        y += 70


column(LEFT, 80, 840)
column(RIGHT, 1000, 840)

ly = 232 + 70 * 10 + 10
d.line([(80, ly), (W - 80, ly)], fill=MUTED, width=2)

fl = f(FM, 21)
x = 300
for lab, c in [("SKETCH", AMBER), ("SINCÈRE", BLUE), ("MIXTE", MUTED), ("FÊTE", GOLD)]:
    d.ellipse([x, ly + 24, x + 15, ly + 39], fill=c)
    d.text((x + 26, ly + 22), lab, font=fl, fill=c)
    x += 300

tracked(d, (W / 2, ly + 70), "VIDÉOS À ENVOYER AVANT LE DIMANCHE 11 OCTOBRE",
        f(FB, 26), AMBER, 10)

img.save(os.path.join(OUT, "14-synoptique.png"))
print("14-synoptique.png")
