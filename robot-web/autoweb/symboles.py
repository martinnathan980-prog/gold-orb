"""Symboles d'affichage : jolis en Unicode, ASCII sous Windows par défaut.

Les consoles Windows (cmd, PowerShell classique) affichent mal ✔ ✘ ⚠ ; on
bascule donc en ASCII, sauf si AUTOWEB_UNICODE=1 (ex. Windows Terminal).
AUTOWEB_ASCII=1 force l'ASCII partout.
"""

from __future__ import annotations

import os
import sys

UNICODE = os.environ.get("AUTOWEB_ASCII") != "1" and (
    sys.platform != "win32" or os.environ.get("AUTOWEB_UNICODE") == "1"
)

OK = "✔" if UNICODE else "OK"
ERREUR = "✘" if UNICODE else "X"
ATTENTION = "⚠" if UNICODE else "!"
IGNORE = "↷" if UNICODE else "~"
FLECHE = "→" if UNICODE else "->"
GAUCHE = "←" if UNICODE else "<-"
PAUSE = "⏸" if UNICODE else "||"
LIGNE = "━━" if UNICODE else "=="
GUILLEMET_OUVRANT = "«" if UNICODE else '"'
GUILLEMET_FERMANT = "»" if UNICODE else '"'

TOUS = (OK, ERREUR, ATTENTION, IGNORE, FLECHE, PAUSE, LIGNE)
